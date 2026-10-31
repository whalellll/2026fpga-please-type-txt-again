"""Extract the trusted local YOLOv5 checkpoint's M0 identity and Detect metadata."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from model_m0_audit import sha256_file, validate_checkpoint_metadata


def pixel_anchors(anchor_grid: list, strides: list[int]) -> list:
    if len(anchor_grid) != len(strides):
        raise ValueError("anchor/stride head count mismatch")
    result = []
    for head, stride in zip(anchor_grid, strides):
        pixels = []
        for x, y in head:
            scaled = (x * stride, y * stride)
            rounded = (round(scaled[0]), round(scaled[1]))
            if any(abs(value - integer) > 1e-6
                   for value, integer in zip(scaled, rounded)):
                raise ValueError("fractional pixel anchor in checkpoint")
            pixels.append(list(rounded))
        result.append(pixels)
    return result


def probe_checkpoint(path: Path) -> dict:
    # PyTorch checkpoints use pickle. Accept only a locally produced/trusted .pt.
    import torch

    started = time.perf_counter()
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    model = checkpoint.get("ema") or checkpoint["model"]
    detect = model.model[-1]
    names = model.names
    if isinstance(names, dict):
        names = [names[index] for index in range(len(names))]
    strides = [int(value) for value in detect.stride.tolist()]
    anchor_grid = detect.anchors.tolist()
    anchors_px = pixel_anchors(anchor_grid, strides)
    digest, size = sha256_file(path)
    result = {
        "schema_version": 1,
        "model_sha256": digest,
        "model_bytes": size,
        "input_shape": [1, 3, 320, 320],
        "classes": list(names),
        "strides": strides,
        "anchors_px": anchors_px,
        "detect_shapes": [[1, int(detect.na), 320 // stride,
                           320 // stride, int(detect.no)] for stride in strides],
        "probe_elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    validate_checkpoint_metadata(path, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    metadata = probe_checkpoint(args.model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"MODEL_M0_PROBE_PASS sha256={metadata['model_sha256']} "
          f"bytes={metadata['model_bytes']} elapsed_ms={metadata['probe_elapsed_ms']}")


if __name__ == "__main__":
    main()
