"""Reproducible logical traffic baseline for the untrained 14-class graph.

These are byte counts from tensor shapes, not measured FPGA DDR transactions.
Run after vision/export_layer_contract.py. Future RTL/board tests must report
measured bytes and cycles alongside this table.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vision"))

from stage2_contract import WindowDescriptor, validate_manifest, window_traffic


def build_rows(manifest):
    validate_manifest(manifest, manifest["config_sha256"])
    rows = []
    for layer in manifest["layers"]:
        if layer["operator"] != "Conv2d":
            continue
        _, cin, height, width = layer["input_shape"]
        _, cout, out_height, out_width = layer["output_shape"]
        kh, kw = layer["kernel"]
        sh, sw = layer["stride"]
        ph, pw = layer["padding"]
        if kh != kw or sh != sw or ph != pw:
            raise ValueError("asymmetric convolution needs a separate contract")
        desc = WindowDescriptor(width, height, cin, kh, sh, ph)
        if (desc.output_height, desc.output_width) != (out_height, out_width):
            raise ValueError("exported output shape disagrees with window rules")
        traffic = window_traffic(desc)
        rows.append({
            "index": layer["index"],
            "name": layer["name"],
            "kernel": kh,
            "input_shape": str(layer["input_shape"]),
            "output_shape": str(layer["output_shape"]),
            "flattened_k": cin * kh * kw,
            "logical_source_bytes": traffic["source_bytes"],
            "naive_tap_bytes": traffic["naive_tap_bytes"],
            "window_taps": traffic["tap_count"],
            "weight_bytes_s8": cout * cin * kh * kw,
            "legacy_output_bytes_4b": out_height * out_width * cout * 4,
            "compact_output_bytes_s8": out_height * out_width * cout,
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--contract", type=Path,
        default=ROOT / "vision" / "yolov5n_14_320_contract.json")
    parser.add_argument(
        "--csv", type=Path,
        default=ROOT / "build" / "vision" / "yolov5n_stage2_traffic.csv")
    args = parser.parse_args()
    manifest = json.loads(args.contract.read_text(encoding="utf-8"))
    rows = build_rows(manifest)
    if not rows:
        raise ValueError("no convolution operators exported")
    first = rows[0]
    if (first["flattened_k"] != 108
            or first["legacy_output_bytes_4b"] != 1638400
            or first["compact_output_bytes_s8"] != 409600):
        raise ValueError("first-layer contract changed")
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print("YOLO_STAGE2_TRAFFIC_BASELINE_PASS",
          "conv_ops=" + str(len(rows)),
          "first_input_bytes=" + str(first["logical_source_bytes"]),
          "first_naive_tap_bytes=" + str(first["naive_tap_bytes"]),
          "first_legacy_output_bytes=" + str(first["legacy_output_bytes_4b"]),
          "first_compact_output_bytes=" + str(first["compact_output_bytes_s8"]),
          "measured_ddr_bytes=none")


if __name__ == "__main__":
    main()
