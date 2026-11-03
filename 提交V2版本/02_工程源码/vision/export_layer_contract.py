"""Export the untrained, pinned YOLOv5n/14 structural contract.

Run with vision/.conda/python.exe. This records topology and FP32 reference
shapes; it does not invent trained weights or quantization scales.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import inspect
import json
from pathlib import Path

import torch
import yolov5
from yolov5.models.common import Conv
from yolov5.models.yolo import Model

from stage2_contract import manifest_digest, validate_manifest


ROOT = Path(__file__).resolve().parents[1]
CLASS_FILE = ROOT / "vision" / "dataset" / "classes.txt"
MODEL_CONFIG = Path(yolov5.__file__).resolve().parent / "models" / "yolov5n.yaml"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tensor_shapes(value: object) -> list[list[int]]:
    if isinstance(value, torch.Tensor):
        return [list(value.shape)]
    if isinstance(value, (tuple, list)):
        shapes = []
        for item in value:
            shapes.extend(_tensor_shapes(item))
        return shapes
    return []


def build_manifest() -> dict:
    """Inspect actual execution of the locally installed 14-class graph."""
    model = Model(str(MODEL_CONFIG), ch=3, nc=14).eval()
    layers: list[dict] = []
    hooks = []

    def record(name: str, module: torch.nn.Module):
        def hook(_module: torch.nn.Module, inputs: tuple, output: object):
            source_shapes = [s for s in _tensor_shapes(inputs) if len(s) == 4]
            output_shapes = [s for s in _tensor_shapes(output) if len(s) == 4]
            if not source_shapes or not output_shapes:
                return
            entry = {
                "index": len(layers),
                "name": name,
                "operator": type(module).__name__,
                "input_shape": source_shapes[0],
                "input_shapes": source_shapes,
                "output_shape": output_shapes[0],
                "reference_dtype": "float32",
            }
            if isinstance(module, torch.nn.Conv2d):
                entry.update({
                    "weight_shape": list(module.weight.shape),
                    "kernel": list(module.kernel_size),
                    "stride": list(module.stride),
                    "padding": list(module.padding),
                    "groups": module.groups,
                })
            layers.append(entry)
        return hook

    for name, module in model.named_modules():
        if name and not tuple(module.children()):
            hooks.append(module.register_forward_hook(record(name, module)))
    try:
        with torch.no_grad():
            decoded, raw = model(torch.zeros(1, 3, 320, 320))
    finally:
        for hook in hooks:
            hook.remove()

    source_code = Path(inspect.getfile(Model)).read_bytes()
    common_code = Path(inspect.getfile(Conv)).read_bytes()
    manifest = {
        "schema_version": 1,
        "model": "yolov5n",
        "class_count": 14,
        "input_shape": [1, 3, 320, 320],
        "reference_layout": "NCHW",
        "reference_dtype": "float32",
        "device_layout": "NHWC4",
        "device_element_bytes": 1,
        "device_channel_tail": "zero",
        "preprocess": {
            "source_channels": "BGR",
            "model_channels": "RGB",
            "letterbox_shape": [320, 320],
            "letterbox_auto": False,
            "letterbox_scale_fill": False,
            "letterbox_scale_up": False,
            "letterbox_stride": 32,
            "letterbox_color": [114, 114, 114],
            "reference_scaling": "uint8_div_255_to_float32",
        },
        "device_conv_output_order": ["output_y", "output_x", "output_channel"],
        "window_order": ["output_y", "output_x", "channel_tile",
                         "kernel_y", "kernel_x"],
        "detect_raw_order": ["batch", "anchor", "grid_y", "grid_x",
                             "prediction"],
        "detect_decoded_order": ["batch", "candidate", "prediction"],
        "trained_weights": False,
        "weight_sha256": None,
        "class_names_sha256": _sha256(CLASS_FILE),
        "config_sha256": _sha256(MODEL_CONFIG),
        "code_sha256": hashlib.sha256(source_code + common_code).hexdigest(),
        "torch_version": torch.__version__,
        "yolov5_version": "7.0.14",
        "detect_raw_shapes": [list(tensor.shape) for tensor in raw],
        "detect_decoded_shape": list(decoded.shape),
        "layers": layers,
    }
    manifest["manifest_sha256"] = manifest_digest(manifest)
    validate_manifest(
        manifest, _sha256(MODEL_CONFIG), _sha256(CLASS_FILE),
        hashlib.sha256(source_code + common_code).hexdigest()
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path,
                        default=ROOT / "build" / "vision" /
                        "yolov5n_14_320_contract.json")
    parser.add_argument("--csv", type=Path,
                        default=ROOT / "build" / "vision" /
                        "yolov5n_14_320_layers.csv")
    args = parser.parse_args()
    manifest = build_manifest()
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    with args.csv.open("w", newline="", encoding="utf-8") as stream:
        fields = ("index", "name", "operator", "input_shape", "output_shape",
                  "weight_shape", "kernel", "stride", "padding", "groups")
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for layer in manifest["layers"]:
            writer.writerow({key: layer.get(key, "") for key in fields})
    print("YOLO_STAGE2_CONTRACT_PASS",
          "operators=" + str(len(manifest["layers"])),
          "manifest_sha256=" + manifest["manifest_sha256"])


if __name__ == "__main__":
    main()
