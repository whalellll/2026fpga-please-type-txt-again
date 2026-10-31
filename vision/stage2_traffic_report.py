"""Report logical Conv2d traffic beside verified hardware counter records.

Unmeasured rows stay unmeasured. No logical budget is labeled as DDR evidence.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

from stage2_contract import validate_manifest

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CONFIG_SHA256 = "c388fddf6310168e464ee4d63d751777329328720304ad48563109bcb0b20746"
EXPECTED_CODE_SHA256 = "e9bd89358c39f528927b74241a6ba141419fa74d1aed08725d916e4969bfbe93"


def class_name_digest(path: Path) -> str:
    """Hash class labels consistently across LF and CRLF checkouts."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def budget_for_layer(layer: dict) -> dict:
    """Describe the target's logical byte count and present tile coverage."""
    if layer.get("operator") != "Conv2d":
        raise ValueError("only Conv2d has this traffic contract")
    n, cin, height, width = layer["input_shape"]
    on, cout, out_height, out_width = layer["output_shape"]
    wc, wcin, kh, kw = layer["weight_shape"]
    sh, sw = layer["stride"]
    ph, pw = layer["padding"]
    groups = layer["groups"]
    if (n != 1 or on != 1 or wc != cout or cin != wcin * groups or
            min(cin, cout, height, width, out_height, out_width, kh, kw) <= 0):
        raise ValueError("invalid Conv2d shape")
    input_tiles = (cin + 3) // 4
    output_tiles = (cout + 15) // 16
    k = wcin * kh * kw
    weight_lines = (k + 3) // 4
    windows = out_height * out_width
    return {
        "index": layer["index"], "name": layer.get("name", ""),
        "input_shape": str(layer["input_shape"]),
        "output_shape": str(layer["output_shape"]),
        "input_bytes": height * width * input_tiles * 4,
        "weight_bytes": output_tiles * weight_lines * 128,
        "compact_output_bytes": windows * cout,
        "legacy_output_bytes": windows * cout * 4,
        "window_count": windows,
        "tap_count": windows * kh * kw * input_tiles,
        "weight_reuse_count": windows * output_tiles,
        "weight_lines": weight_lines,
        "supported_tile": (groups == 1 and cin <= 4 and cout <= 16 and
                           width <= 320 and height <= 320 and
                           kh == kw and kh in (1, 3, 6) and
                           sh == sw and sh in (1, 2) and ph == pw and
                           ph < kh and k <= 128 and weight_lines <= 32),
    }


def validate_measurement(budget: dict, measurement: dict) -> None:
    """Reject stale mode/shape/counter records before presenting evidence."""
    if not budget["supported_tile"]:
        raise ValueError("layer is not supported by the current compute tile")
    mode = measurement.get("mode")
    if mode not in ("window", "compute"):
        raise ValueError("unknown measured mode")
    expected = {
        "input_ddr_bytes": budget["input_bytes"],
        "weight_ddr_bytes": budget["weight_bytes"],
        "output_ddr_bytes": budget["compact_output_bytes"]
        if mode == "compute" else 0,
        "window_count": budget["window_count"],
        "tap_count": budget["tap_count"],
    }
    for field, value in expected.items():
        if measurement.get(field) != value:
            raise ValueError(f"measured {field} differs from descriptor")
    cycles = measurement.get("cycles")
    stalls = measurement.get("stall_cycles")
    if (type(cycles) is not int or cycles <= 0 or
            type(stalls) is not int or not 0 <= stalls <= cycles):
        raise ValueError("invalid measured cycle counters")
    for field in ("bitstream_sha256", "test_image_sha256"):
        if not isinstance(measurement.get(field), str) or not re.fullmatch(
                r"[0-9a-f]{64}", measurement[field]):
            raise ValueError(f"missing measured {field}")
    if not isinstance(measurement.get("marker"), str) or not measurement["marker"]:
        raise ValueError("missing board log marker")
    log_name = measurement.get("board_log")
    if log_name is not None:
        if (mode != "compute" or
                measurement["marker"] != "MAC_CONV_FULL_FIRST_LAYER_PASS"):
            raise ValueError("unsupported board counter log marker")
        path = Path(log_name)
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_file():
            raise ValueError("board counter log is missing")
        line = next((line.strip() for line in path.read_text(
            encoding="utf-8", errors="replace").splitlines()
            if line.strip().startswith(measurement["marker"] + " ")), None)
        if line is None:
            raise ValueError("board counter marker is missing from log")
        fields = dict(re.findall(r"\b([a-z_]+)=([0-9a-f]+)\b", line))
        expected_log = {
            "output": measurement["output_ddr_bytes"],
            "input": measurement["input_ddr_bytes"],
            "weight": measurement["weight_ddr_bytes"],
            "taps": measurement["tap_count"],
            "reuse": budget["weight_reuse_count"],
            "compute_cycles": cycles,
            "stalls": stalls,
        }
        for name, value in expected_log.items():
            if fields.get(name) != str(value):
                raise ValueError(f"board log {name} differs from measurement")
        crc32 = measurement.get("crc32")
        if (not isinstance(crc32, str) or
                not re.fullmatch(r"[0-9a-f]{8}", crc32) or
                fields.get("crc") != crc32):
            raise ValueError("board log CRC differs from measurement")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path,
                        default=ROOT / "vision/yolov5n_14_320_contract.json")
    parser.add_argument("--measurements", type=Path)
    parser.add_argument("--csv", type=Path,
                        default=ROOT / "build/vision/yolov5n_stage2_traffic.csv")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    class_hash = class_name_digest(ROOT / "vision/dataset/classes.txt")
    validate_manifest(manifest, EXPECTED_CONFIG_SHA256, class_hash,
                      EXPECTED_CODE_SHA256)
    measurements = (json.loads(args.measurements.read_text(encoding="utf-8"))
                    if args.measurements else {})
    if not isinstance(measurements, dict):
        raise ValueError("measurements must be indexed by layer number")
    rows = []
    for layer in manifest["layers"]:
        if layer["operator"] != "Conv2d":
            continue
        row = budget_for_layer(layer)
        measurement = measurements.get(str(row["index"]))
        if measurement is not None:
            validate_measurement(row, measurement)
            row.update({"measured_mode": measurement["mode"],
                        "measured_input_ddr_bytes": measurement["input_ddr_bytes"],
                        "measured_weight_ddr_bytes": measurement["weight_ddr_bytes"],
                        "measured_output_ddr_bytes": measurement["output_ddr_bytes"],
                        "measured_cycles": measurement["cycles"],
                        "measured_stall_cycles": measurement["stall_cycles"],
                        "bitstream_sha256": measurement.get("bitstream_sha256", "")})
        else:
            row.update({"measured_mode": "",
                        "measured_input_ddr_bytes": "",
                        "measured_weight_ddr_bytes": "",
                        "measured_output_ddr_bytes": "",
                        "measured_cycles": "",
                        "measured_stall_cycles": "", "bitstream_sha256": ""})
        rows.append(row)
    if set(measurements) - {str(row["index"]) for row in rows}:
        raise ValueError("measurements include a nonexistent Conv2d layer")
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print("YOLO_STAGE2_TRAFFIC_REPORT_PASS",
          f"layers={len(rows)}",
          f"supported={sum(row['supported_tile'] for row in rows)}",
          f"measured={len(measurements)}")


if __name__ == "__main__":
    main()
