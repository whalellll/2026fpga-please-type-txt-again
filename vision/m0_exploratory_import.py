"""Prepare a chronological LabelMe trial set without modifying source images.

All frames may still share one acquisition session. This split is for exploratory
training only; it does not establish M0's independent validation/test gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from PIL import Image

from model_m0_audit import EXPECTED_CLASSES, sha256_file


def _circle_row(shape: dict, width: int, height: int,
                crop: tuple[int, int, int, int]) -> str:
    name = shape.get("label")
    if name not in EXPECTED_CLASSES or shape.get("shape_type") != "circle":
        raise ValueError(f"unsupported LabelMe shape or class: {name}")
    points = shape.get("points")
    if (not isinstance(points, list) or len(points) != 2
            or any(not isinstance(point, list) or len(point) != 2
                   for point in points)):
        raise ValueError(f"invalid circle points for {name}")
    (cx, cy), (px, py) = points
    cx, cy, px, py = map(float, (cx, cy, px, py))
    if not all(map(math.isfinite, (cx, cy, px, py))):
        raise ValueError(f"non-finite circle points for {name}")
    radius = math.hypot(px - cx, py - cy)
    if radius <= 0:
        raise ValueError(f"zero circle radius for {name}")
    x0, y0, x1, y1 = crop
    left = max(0.0, cx - radius - x0)
    top = max(0.0, cy - radius - y0)
    right = min(float(x1 - x0), cx + radius - x0)
    bottom = min(float(y1 - y0), cy + radius - y0)
    if right <= left or bottom <= top:
        raise ValueError(f"circle outside ROI for {name}")
    out_width, out_height = x1 - x0, y1 - y0
    return (f"{EXPECTED_CLASSES.index(name)} "
            f"{(left + right) / (2 * out_width):.8f} "
            f"{(top + bottom) / (2 * out_height):.8f} "
            f"{(right - left) / out_width:.8f} "
            f"{(bottom - top) / out_height:.8f}\n")


def _hash_entries(entries: list[tuple[str, str]]) -> str:
    digest = hashlib.sha256()
    for name, checksum in sorted(entries):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(checksum.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def prepare_dataset(source: Path, output: Path,
                    crop: tuple[int, int, int, int],
                    train_count: int, val_count: int,
                    test_count: int, gap_count: int) -> dict:
    source = source.resolve()
    output = output.resolve()
    if not source.is_dir():
        raise ValueError(f"source folder missing: {source}")
    if output == source or source in output.parents:
        raise ValueError("output must be outside the source folder")
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must be empty")
    if min(train_count, val_count, test_count) < 1 or gap_count < 0:
        raise ValueError("invalid chronological split counts")
    if len(crop) != 4 or not all(isinstance(v, int) for v in crop):
        raise ValueError("crop must contain four integer coordinates")

    annotations = sorted(source.glob("CMOS2_*.json"))
    expected_count = train_count + val_count + test_count + 2 * gap_count
    if len(annotations) != expected_count:
        raise ValueError(f"expected {expected_count} annotations, found {len(annotations)}")
    all_png = {path.name for path in source.glob("CMOS2_*.png")}
    source_entries: list[tuple[str, str]] = []
    prepared: list[tuple[Path, str]] = []
    source_bytes_hashed = 0
    duplicate_labels_removed = 0
    for annotation in annotations:
        image = annotation.with_suffix(".png")
        if not image.is_file():
            raise ValueError(f"annotation has no PNG: {annotation.name}")
        with Image.open(image) as opened:
            width, height = opened.size
            opened.verify()
        x0, y0, x1, y1 = crop
        if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
            raise ValueError(f"crop {crop} is outside {image.name}: {width}x{height}")
        data = json.loads(annotation.read_text(encoding="utf-8"))
        if (data.get("imageWidth"), data.get("imageHeight")) != (width, height):
            raise ValueError(f"{annotation.name}: declared size differs from image")
        shapes = data.get("shapes")
        if not isinstance(shapes, list) or not shapes:
            raise ValueError(f"{annotation.name}: no labeled pieces")
        converted = [_circle_row(shape, width, height, crop)
                     for shape in shapes]
        unique_rows = list(dict.fromkeys(converted))
        duplicate_labels_removed += len(converted) - len(unique_rows)
        rows = "".join(unique_rows)
        prepared.append((image, rows))
        for path in (image, annotation):
            digest, size = sha256_file(path)
            source_entries.append((path.name, digest))
            source_bytes_hashed += size

    splits = {
        "train": prepared[:train_count],
        "val": prepared[train_count + gap_count:
                        train_count + gap_count + val_count],
        "test": prepared[train_count + 2 * gap_count + val_count:],
    }
    excluded = (prepared[train_count:train_count + gap_count]
                + prepared[train_count + gap_count + val_count:
                           train_count + 2 * gap_count + val_count])
    output.mkdir(parents=True, exist_ok=True)
    output_entries: list[tuple[str, str]] = []
    groups: dict[str, str] = {}
    output_image_bytes = box_count = 0
    for split, pairs in splits.items():
        image_dir = output / "images" / split
        label_dir = output / "labels" / split
        image_dir.mkdir(parents=True)
        label_dir.mkdir(parents=True)
        for image, rows in pairs:
            image_out = image_dir / image.name
            label_out = label_dir / (image.stem + ".txt")
            with Image.open(image) as opened:
                opened.crop(crop).save(image_out)
            label_out.write_text(rows, encoding="utf-8")
            box_count += len(rows.splitlines())
            groups[image_out.relative_to(output).as_posix()] = "_".join(
                image.stem.split("_")[:2])
            for path in (image_out, label_out):
                digest, size = sha256_file(path)
                output_entries.append((path.relative_to(output).as_posix(), digest))
                if path == image_out:
                    output_image_bytes += size

    class_file = output / "classes.txt"
    class_file.write_text("".join(f"{i} {name}\n" for i, name in
                                  enumerate(EXPECTED_CLASSES)), encoding="utf-8")
    config = output / "chess14_trial.yaml"
    config.write_text(
        f"path: {output.as_posix()}\n"
        "train: images/train\nval: images/val\ntest: images/test\n"
        "nc: 14\nnames:\n"
        + "".join(f"  {i}: {name}\n" for i, name in
                  enumerate(EXPECTED_CLASSES)), encoding="utf-8")
    (output / "capture_groups_observed.json").write_text(
        json.dumps(groups, indent=2) + "\n", encoding="utf-8")
    report = {
        "purpose": "exploratory chronological training; not independent M0 acceptance",
        "crop_xyxy": list(crop),
        "split_counts": {split: len(pairs) for split, pairs in splits.items()}
                        | {"excluded": len(excluded)},
        "split_names": {split: [image.name for image, _ in pairs]
                        for split, pairs in splits.items()},
        "excluded_names": [image.name for image, _ in excluded],
        "unannotated_count": len(all_png) - len(annotations),
        "box_count": box_count,
        "duplicate_labels_removed": duplicate_labels_removed,
        "source_bytes_hashed": source_bytes_hashed,
        "output_image_bytes": output_image_bytes,
        "source_sha256": _hash_entries(source_entries),
        "dataset_sha256": _hash_entries(output_entries),
    }
    (output / "trial_manifest.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--crop", nargs=4, required=True, type=int)
    parser.add_argument("--train-count", type=int, default=65)
    parser.add_argument("--val-count", type=int, default=12)
    parser.add_argument("--test-count", type=int, default=12)
    parser.add_argument("--gap-count", type=int, default=3)
    args = parser.parse_args()
    report = prepare_dataset(args.source, args.output, tuple(args.crop),
                             args.train_count, args.val_count,
                             args.test_count, args.gap_count)
    print(f"M0_TRIAL_IMPORT_PASS counts={report['split_counts']} "
          f"boxes={report['box_count']} source={report['source_sha256']} "
          f"dataset={report['dataset_sha256']}")


if __name__ == "__main__":
    main()
