"""Versioned structural contract and CPU window oracle for stage-2 RTL.

NHWC4 contains four bytes per channel tile at each pixel. The bytes are kept
opaque here: the MAC adapter chooses U8 or S8 interpretation. Missing channels
and image-padding taps are zero. Window traversal order is
(output_y, output_x, channel_tile, kernel_y, kernel_x).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Iterator


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class WindowDescriptor:
    width: int
    height: int
    channels: int
    kernel: int
    stride: int
    padding: int

    def __post_init__(self) -> None:
        if (not 1 <= self.width <= 320 or not 1 <= self.height <= 320
                or not 1 <= self.channels <= 1024
                or self.kernel not in (1, 3, 6)
                or self.stride not in (1, 2)
                or not 0 <= self.padding < self.kernel
                or self.width + 2 * self.padding < self.kernel
                or self.height + 2 * self.padding < self.kernel):
            raise ContractError("invalid window descriptor")

    @property
    def channel_tiles(self) -> int:
        return (self.channels + 3) // 4

    @property
    def output_width(self) -> int:
        return (self.width + 2 * self.padding - self.kernel) // self.stride + 1

    @property
    def output_height(self) -> int:
        return (self.height + 2 * self.padding - self.kernel) // self.stride + 1

    @property
    def input_bytes(self) -> int:
        return self.width * self.height * self.channel_tiles * 4


def iter_windows_nhwc4(
    pixels: bytes, desc: WindowDescriptor
) -> Iterator[tuple[int, int, int, int, int, bytes]]:
    """Yield every logical four-byte tap, including zero-padded taps."""
    if len(pixels) != desc.input_bytes:
        raise ContractError("packed input size differs from descriptor")
    for oy in range(desc.output_height):
        for ox in range(desc.output_width):
            for channel_tile in range(desc.channel_tiles):
                for ky in range(desc.kernel):
                    iy = oy * desc.stride + ky - desc.padding
                    for kx in range(desc.kernel):
                        ix = ox * desc.stride + kx - desc.padding
                        if 0 <= iy < desc.height and 0 <= ix < desc.width:
                            offset = (((iy * desc.width + ix)
                                       * desc.channel_tiles + channel_tile) * 4)
                            word = bytearray(pixels[offset:offset + 4])
                            for lane in range(4):
                                if channel_tile * 4 + lane >= desc.channels:
                                    word[lane] = 0
                            tap = bytes(word)
                        else:
                            tap = bytes(4)
                        yield oy, ox, channel_tile, ky, kx, tap


def window_traffic(desc: WindowDescriptor) -> dict[str, int]:
    """Logical byte budget, not a claim about measured DDR transactions."""
    return {
        "source_bytes": desc.input_bytes,
        "naive_tap_bytes": (
            desc.output_width * desc.output_height * desc.channel_tiles
            * desc.kernel * desc.kernel * 4
        ),
        "tap_count": (
            desc.output_width * desc.output_height * desc.channel_tiles
            * desc.kernel * desc.kernel
        ),
    }


def conv2d_nhwc4_int32(
    pixels: bytes,
    desc: WindowDescriptor,
    weights: bytes,
    output_channels: int,
    bias: list[int] | None = None,
    *,
    input_signed: bool = True,
) -> list[int]:
    """Exact integer reference with OIHW S8 weights and INT32 output.

    Output is ordered (output_y, output_x, output_channel). Activation,
    requantization, and SiLU are intentionally outside this reference.
    """
    if not 1 <= output_channels <= 1024:
        raise ContractError("invalid output channel count")
    expected_weights = (output_channels * desc.channels
                        * desc.kernel * desc.kernel)
    if len(weights) != expected_weights or len(pixels) != desc.input_bytes:
        raise ContractError("input or weight size differs from descriptor")
    if bias is not None and (len(bias) != output_channels
                             or any(type(v) is not int
                                    or not -(1 << 31) <= v < (1 << 31)
                                    for v in bias)):
        raise ContractError("invalid INT32 bias")
    output_pixels = desc.output_height * desc.output_width
    result = [bias[oc] if bias is not None else 0
              for _ in range(output_pixels) for oc in range(output_channels)]
    for oy, ox, channel_tile, ky, kx, tap in iter_windows_nhwc4(pixels, desc):
        result_base = (oy * desc.output_width + ox) * output_channels
        for lane in range(4):
            channel = channel_tile * 4 + lane
            if channel >= desc.channels:
                continue
            activation = tap[lane]
            if input_signed and activation >= 128:
                activation -= 256
            for oc in range(output_channels):
                weight_index = (
                    ((oc * desc.channels + channel) * desc.kernel + ky)
                    * desc.kernel + kx
                )
                weight = weights[weight_index]
                if weight >= 128:
                    weight -= 256
                result[result_base + oc] += activation * weight
    if any(not -(1 << 31) <= value < (1 << 31) for value in result):
        raise ContractError("INT32 accumulator overflow")
    return result


def conv2d_nhwc4_segmented_int32(
    pixels: bytes,
    desc: WindowDescriptor,
    weights: bytes,
    output_channels: int,
    bias: list[int] | None = None,
    *,
    segment_k: int = 256,
    input_signed: bool = True,
) -> list[int]:
    """Accumulate flattened K segments in INT32 before any requantization.

    The logical K order is (kernel_y, kernel_x, input_channel). A segment
    boundary never applies bias, rounding, saturation, or activation.
    """
    if not 1 <= segment_k <= 256:
        raise ContractError("invalid segment K")
    if not 1 <= output_channels <= 1024:
        raise ContractError("invalid output channel count")
    total_k = desc.channels * desc.kernel * desc.kernel
    if len(pixels) != desc.input_bytes or len(weights) != output_channels * total_k:
        raise ContractError("input or weight size differs from descriptor")
    if bias is not None and (len(bias) != output_channels or
                             any(type(v) is not int or
                                 not -(1 << 31) <= v < (1 << 31)
                                 for v in bias)):
        raise ContractError("invalid INT32 bias")
    values: list[int] = []
    for oy in range(desc.output_height):
        for ox in range(desc.output_width):
            for oc in range(output_channels):
                accumulator = bias[oc] if bias is not None else 0
                for start in range(0, total_k, segment_k):
                    partial = 0
                    for scalar in range(start, min(start + segment_k, total_k)):
                        tap, channel = divmod(scalar, desc.channels)
                        ky, kx = divmod(tap, desc.kernel)
                        iy = oy * desc.stride + ky - desc.padding
                        ix = ox * desc.stride + kx - desc.padding
                        if 0 <= iy < desc.height and 0 <= ix < desc.width:
                            offset = (((iy * desc.width + ix)
                                       * desc.channel_tiles + channel // 4)
                                      * 4 + channel % 4)
                            activation = pixels[offset]
                            if input_signed and activation >= 128:
                                activation -= 256
                            weight_index = (((oc * desc.channels + channel)
                                             * desc.kernel + ky)
                                            * desc.kernel + kx)
                            weight = weights[weight_index]
                            if weight >= 128:
                                weight -= 256
                            partial += activation * weight
                    accumulator += partial
                    if not -(1 << 31) <= accumulator < (1 << 31):
                        raise ContractError("INT32 accumulator overflow")
                values.append(accumulator)
    return values


def manifest_digest(manifest: dict) -> str:
    body = {key: value for key, value in manifest.items()
            if key != "manifest_sha256"}
    encoded = json.dumps(body, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _shape(value: object, rank: int) -> bool:
    return (isinstance(value, list) and len(value) == rank
            and all(type(x) is int and 1 <= x <= 65536 for x in value))


def validate_manifest(
    manifest: dict,
    expected_config_sha256: str,
    expected_class_sha256: str | None = None,
    expected_code_sha256: str | None = None,
) -> None:
    """Reject changed graph metadata before exposing it to a converter.

    Pass independently computed expected hashes for every identity field used
    by the consumer. The embedded manifest digest detects accidental edits;
    it is not an authentication mechanism on its own.
    """
    if not isinstance(manifest, dict):
        raise ContractError("manifest must be an object")
    hashes = ("class_names_sha256", "config_sha256", "code_sha256",
              "manifest_sha256")
    if any(not isinstance(manifest.get(key), str)
           or re.fullmatch(r"[0-9a-f]{64}", manifest[key]) is None
           for key in hashes):
        raise ContractError("missing or malformed hash")
    if (manifest["manifest_sha256"] != manifest_digest(manifest)
            or manifest["config_sha256"] != expected_config_sha256
            or (expected_class_sha256 is not None
                and manifest["class_names_sha256"] != expected_class_sha256)
            or (expected_code_sha256 is not None
                and manifest["code_sha256"] != expected_code_sha256)):
        raise ContractError("manifest or model identity mismatch")
    if (type(manifest.get("schema_version")) is not int
            or manifest["schema_version"] != 1
            or manifest.get("model") != "yolov5n"
            or manifest.get("class_count") != 14
            or manifest.get("input_shape") != [1, 3, 320, 320]
            or manifest.get("reference_layout") != "NCHW"
            or manifest.get("reference_dtype") != "float32"
            or manifest.get("device_layout") != "NHWC4"
            or manifest.get("device_element_bytes") != 1
            or manifest.get("device_channel_tail") != "zero"
            or manifest.get("preprocess") != {
                "source_channels": "BGR", "model_channels": "RGB",
                "letterbox_shape": [320, 320], "letterbox_auto": False,
                "letterbox_scale_fill": False, "letterbox_scale_up": False,
                "letterbox_stride": 32,
                "letterbox_color": [114, 114, 114],
                "reference_scaling": "uint8_div_255_to_float32",
            }
            or manifest.get("device_conv_output_order") !=
            ["output_y", "output_x", "output_channel"]
            or manifest.get("window_order") !=
            ["output_y", "output_x", "channel_tile", "kernel_y", "kernel_x"]
            or manifest.get("detect_raw_order") !=
            ["batch", "anchor", "grid_y", "grid_x", "prediction"]
            or manifest.get("detect_decoded_order") !=
            ["batch", "candidate", "prediction"]
            or manifest.get("trained_weights") is not False
            or manifest.get("weight_sha256") is not None
            or manifest.get("detect_raw_shapes") !=
            [[1, 3, 40, 40, 19], [1, 3, 20, 20, 19], [1, 3, 10, 10, 19]]
            or manifest.get("detect_decoded_shape") != [1, 6300, 19]):
        raise ContractError("unsupported model contract")
    layers = manifest.get("layers")
    if not isinstance(layers, list) or not layers:
        raise ContractError("empty layer list")
    for number, layer in enumerate(layers):
        if (not isinstance(layer, dict) or layer.get("index") != number
                or not isinstance(layer.get("operator"), str)
                or not _shape(layer.get("input_shape"), 4)
                or not _shape(layer.get("output_shape"), 4)):
            raise ContractError("invalid layer descriptor")
        if layer["operator"] == "Conv2d":
            if (not _shape(layer.get("weight_shape"), 4)
                    or not _shape(layer.get("kernel"), 2)
                    or not _shape(layer.get("stride"), 2)
                    or not isinstance(layer.get("padding"), list)
                    or len(layer["padding"]) != 2
                    or any(type(x) is not int or x < 0 or x > 6
                           for x in layer["padding"])
                    or type(layer.get("groups")) is not int
                    or layer["groups"] < 1):
                raise ContractError("invalid convolution parameters")
            n, cin, h, w = layer["input_shape"]
            on, cout, oh, ow = layer["output_shape"]
            wc, wcin, kh, kw = layer["weight_shape"]
            sh, sw = layer["stride"]
            ph, pw = layer["padding"]
            if (layer["kernel"] != [kh, kw] or on != n or wc != cout
                    or cin != wcin * layer["groups"]
                    or (h + 2 * ph - kh) // sh + 1 != oh
                    or (w + 2 * pw - kw) // sw + 1 != ow):
                raise ContractError("inconsistent convolution shapes")
