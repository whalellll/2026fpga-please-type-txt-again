"""Export a small, reproducible trained YOLOv5n first-convolution board probe.

This is an exploratory hardware vector, not the calibrated M2 model format.
Only a locally trusted checkpoint may be loaded: PyTorch .pt uses pickle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import zlib
from pathlib import Path

from stage2_contract import WindowDescriptor, conv2d_nhwc4_int32


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def requant(value: int, shift: int) -> int:
    if not 0 <= shift <= 30:
        raise ValueError("shift exceeds ABI3 range")
    magnitude = (abs(value) + ((1 << (shift - 1)) if shift else 0)) >> shift
    return max(-128, min(127, -magnitude if value < 0 else magnitude))


def pack_weights(weights: bytes, cin: int, cout: int, kernel: int) -> bytes:
    if not (1 <= cin <= 4 and 1 <= cout <= 16 and
            cin * kernel * kernel <= 128):
        raise ValueError("weight shape exceeds ABI3 tile")
    count = cin * kernel * kernel
    if len(weights) != cout * count:
        raise ValueError("OIHW weight length mismatch")
    packed = bytearray(((count + 3) // 4) * 128)
    for oc in range(cout):
        for ky in range(kernel):
            for kx in range(kernel):
                for ci in range(cin):
                    scalar = (ky * kernel + kx) * cin + ci
                    packed[(scalar // 4) * 128 + oc * 4 + scalar % 4] = (
                        weights[((oc * cin + ci) * kernel + ky) * kernel + kx])
    return bytes(packed)


def make_tile(pixels: bytes, width: int, height: int, weights: bytes,
              bias: list[int], shift: list[int]) -> dict:
    desc = WindowDescriptor(width, height, 3, 6, 2, 2)
    if len(pixels) != desc.input_bytes or len(bias) != 16 or len(shift) != 16:
        raise ValueError("first-layer tile dimensions mismatch")
    if any(not -(1 << 31) <= v < (1 << 31) for v in bias):
        raise ValueError("INT32 bias overflow")
    if any(not 0 <= v <= 30 for v in shift):
        raise ValueError("shift exceeds ABI3 range")
    packed = pack_weights(weights, 3, 16, 6)
    raw = conv2d_nhwc4_int32(pixels, desc, weights, 16, bias)
    output = bytes(requant(v, shift[i % 16]) & 255
                   for i, v in enumerate(raw))
    return {
        "width": width, "height": height, "input": pixels,
        "weights": packed, "oihw_weights": weights,
        "bias": list(bias), "shift": list(shift), "output": output,
        "traffic": {
            "input_bytes": len(pixels), "weight_bytes": len(packed),
            "output_bytes": len(output),
            "tap_count": desc.output_width * desc.output_height * 36,
        },
    }


def validate_tile(tile: dict) -> None:
    rebuilt = make_tile(tile["input"], tile["width"], tile["height"],
                        tile["oihw_weights"], tile["bias"], tile["shift"])
    if any(tile[key] != rebuilt[key] for key in
           ("weights", "output", "traffic")):
        raise ValueError("tile bytes differ from integer golden reference")


def _hex_words(data: bytes) -> str:
    if len(data) % 4:
        raise ValueError("word file must be aligned")
    return "".join(f"{int.from_bytes(data[i:i+4], 'little'):08x}\n"
                   for i in range(0, len(data), 4))


def _c_array(name: str, data: bytes) -> str:
    lines = [f"static const unsigned char {name}[{len(data)}] = {{"]
    for offset in range(0, len(data), 16):
        lines.append("    " + ", ".join(f"0x{x:02x}" for x in data[offset:offset+16]) + ",")
    return "\n".join(lines + ["};"])


def export_tile(tile: dict, output_dir: Path, identity: dict) -> dict:
    validate_tile(tile)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1, "purpose": "exploratory trained first-layer board probe",
        **identity,
        "shape": [tile["height"], tile["width"], 3, 16, 6, 2, 2],
        "traffic": tile["traffic"], "bias": tile["bias"],
        "shift": tile["shift"],
        "input_sha256": sha256(tile["input"]),
        "weight_sha256": sha256(tile["weights"]),
        "output_sha256": sha256(tile["output"]),
        "output_crc32": f"{zlib.crc32(tile['output']):08x}",
    }
    for name, data in (("input", tile["input"]),
                       ("weights", tile["weights"]),
                       ("expected", tile["output"])):
        (output_dir / f"{name}.hex").write_text(_hex_words(data), encoding="ascii")
    verilog_bias = ["function integer tile_bias(input integer index);",
                    "begin", "case(index)"]
    verilog_bias.extend(f"{i}: tile_bias=32'sd{v};" if v >= 0 else
                        f"{i}: tile_bias=-32'sd{-v};"
                        for i, v in enumerate(tile["bias"]))
    verilog_bias.extend(["default: tile_bias=0;", "endcase", "end", "endfunction"])
    (output_dir / "bias.vh").write_text("\n".join(verilog_bias) + "\n", encoding="ascii")
    header = ["/* Generated exploratory vector; see manifest.json. */",
              "#ifndef TRAINED_CONV_TILE_VECTOR_H",
              "#define TRAINED_CONV_TILE_VECTOR_H",
              f"#define TILE_WIDTH {tile['width']}u",
              f"#define TILE_HEIGHT {tile['height']}u",
              f"#define TILE_OUTPUT_BYTES {len(tile['output'])}u",
              f"#define TILE_OUTPUT_CRC32 0x{manifest['output_crc32']}u"]
    for name, data in (("tile_input", tile["input"]),
                       ("tile_weights", tile["weights"]),
                       ("tile_expected", tile["output"])):
        header.append(_c_array(name, data))
    for name in ("bias", "shift"):
        header.append(f"static const int tile_{name}[16] = {{" +
                      ", ".join(str(v) for v in tile[name]) + "};")
    header.append("#endif")
    (output_dir / "trained_conv_tile_vector.h").write_text(
        "\n".join(header) + "\n", encoding="ascii")
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def checkpoint_tile(model_path: Path, image_path: Path, x: int, y: int,
                    size: int = 16) -> tuple[dict, dict]:
    import cv2
    import numpy as np
    import torch

    checkpoint_bytes = model_path.read_bytes()
    checkpoint = torch.load(model_path, map_location="cpu", weights_only=False)
    model = checkpoint.get("ema") or checkpoint["model"]
    first = model.model[0]
    conv, bn = first.conv, first.bn
    if (tuple(conv.weight.shape) != (16, 3, 6, 6) or
            tuple(conv.stride) != (2, 2) or tuple(conv.padding) != (2, 2) or
            getattr(model, "nc", None) != 14):
        raise ValueError("checkpoint first layer or class count changed")
    rgb_source = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if rgb_source is None:
        raise ValueError("cannot read source image")
    source_h, source_w = rgb_source.shape[:2]
    gain = min(320 / source_h, 320 / source_w)
    resized_w, resized_h = round(source_w * gain), round(source_h * gain)
    resized = cv2.resize(rgb_source, (resized_w, resized_h), interpolation=cv2.INTER_LINEAR)
    pad_w, pad_h = 320 - resized_w, 320 - resized_h
    top, bottom = round(pad_h / 2 - .1), round(pad_h / 2 + .1)
    left, right = round(pad_w / 2 - .1), round(pad_w / 2 + .1)
    rgb = cv2.cvtColor(cv2.copyMakeBorder(
        resized, top, bottom, left, right, cv2.BORDER_CONSTANT,
        value=(114, 114, 114)), cv2.COLOR_BGR2RGB)
    if not (0 <= x <= 320 - size and 0 <= y <= 320 - size):
        raise ValueError("tile crop outside preprocessed image")
    patch = rgb[y:y+size, x:x+size]
    quant_input = np.rint(patch.astype(np.float32) * (127.0 / 255.0)).astype(np.uint8)
    pixels = np.zeros((size, size, 4), dtype=np.uint8)
    pixels[:, :, :3] = quant_input
    # Conv+BN fusion, preserving trained layer's channel ordering.
    weights_fp = conv.weight.detach().float().numpy()
    gamma = bn.weight.detach().float().numpy()
    beta = bn.bias.detach().float().numpy()
    mean = bn.running_mean.detach().float().numpy()
    var = bn.running_var.detach().float().numpy()
    factor = gamma / np.sqrt(var + float(bn.eps))
    fused_w = weights_fp * factor[:, None, None, None]
    fused_b = beta - mean * factor
    weight_scales = np.max(np.abs(fused_w), axis=(1, 2, 3)) / 127.0
    if np.any(weight_scales == 0):
        raise ValueError("zero trained weight channel")
    weights_s8 = np.clip(np.rint(fused_w / weight_scales[:, None, None, None]),
                         -127, 127).astype(np.int8)
    input_scale = 1.0 / 127.0
    bias_i32 = np.rint(fused_b / (input_scale * weight_scales)).astype(np.int64)
    if np.any(np.abs(bias_i32) >= 1 << 31):
        raise ValueError("fused bias exceeds INT32")
    # This fixed shift exercises ABI3. M2 will calibrate output scales.
    shifts = [10] * 16
    tile = make_tile(pixels.tobytes(), size, size, weights_s8.tobytes(),
                     [int(v) for v in bias_i32], shifts)
    identity = {
        "model_sha256": sha256(checkpoint_bytes),
        "image_sha256": sha256(image_path.read_bytes()),
        "crop_xy_size": [x, y, size], "letterbox_320": {
            "resize_wh": [resized_w, resized_h],
            "padding_ltrb": [left, top, right, bottom],
        },
        "input_scale": input_scale,
        "weight_scales": [float(v) for v in weight_scales],
        "output_scales": [float(v * input_scale * 1024) for v in weight_scales],
        "quantization_status": "hardware probe only; M2 calibration pending",
    }
    return tile, identity


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--x", type=int, default=152)
    parser.add_argument("--y", type=int, default=152)
    args = parser.parse_args()
    started = time.perf_counter()
    tile, identity = checkpoint_tile(args.model, args.image, args.x, args.y)
    manifest = export_tile(tile, args.output, identity)
    print("TRAINED_CONV_TILE_EXPORT_PASS", "crc32=" + manifest["output_crc32"],
          "bytes=" + str(manifest["traffic"]),
          "elapsed_ms=" + str(round((time.perf_counter()-started)*1000, 2)))


if __name__ == "__main__":
    main()
