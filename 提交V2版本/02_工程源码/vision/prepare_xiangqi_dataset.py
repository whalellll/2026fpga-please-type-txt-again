"""Import paired in_850/out_850 LabelMe data for a conservative temporal trial.

No provenance is inferred from serial filenames. Val/test are separate held-out
intervals with excluded boundary frames, but independent captures and FEN gold
remain a separate acceptance gate. Original images/annotations are read only.
"""
from __future__ import annotations

import argparse
import collections
import json
import shutil
import time
from pathlib import Path

from PIL import Image

from m0_exploratory_import import _circle_row, _hash_entries
from model_m0_audit import EXPECTED_CLASSES, sha256_file


def _index(directory: Path, suffix: str) -> dict[str, Path]:
    result = {}
    for path in directory.iterdir():
        if path.is_file() and path.suffix.lower() == suffix:
            key = path.stem.casefold()
            if key in result:
                raise ValueError(f"duplicate filename stem: {path}")
            result[key] = path
    return result


def prepare_dataset(images: Path, annotations: Path, output: Path,
                    train_count: int, val_count: int, test_count: int,
                    gap_count: int) -> dict:
    started = time.perf_counter()
    images, annotations, output = (p.resolve() for p in (images, annotations, output))
    for source in (images, annotations):
        if not source.is_dir():
            raise ValueError(f"source directory missing: {source}")
        if output == source or source in output.parents:
            raise ValueError("output must be outside both source directories")
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must be empty")
    if min(train_count, val_count, test_count) < 1 or gap_count < 0:
        raise ValueError("split counts must be positive and gaps nonnegative")
    image_index, label_index = _index(images, ".png"), _index(annotations, ".json")
    if image_index.keys() != label_index.keys():
        missing = sorted(image_index.keys() ^ label_index.keys())
        raise ValueError(f"images and annotations are not paired: {missing[:8]}")
    expected = train_count + val_count + test_count + 2 * gap_count
    if len(image_index) != expected:
        raise ValueError(f"split expects {expected} images, found {len(image_index)}")

    prepared, source_entries = [], []
    image_hashes, image_sizes = {}, collections.Counter()
    bytes_hashed = duplicate_labels_removed = 0
    # Validate the entire source before creating any candidate files.
    for key in sorted(image_index):
        image, annotation = image_index[key], label_index[key]
        with Image.open(image) as opened:
            width, height = opened.size
            opened.verify()
        image_sizes[f"{width}x{height}"] += 1
        data = json.loads(annotation.read_text(encoding="utf-8-sig"))
        if (data.get("imageWidth"), data.get("imageHeight")) != (width, height):
            raise ValueError(f"declared dimensions differ from image: {annotation.name}")
        shapes = data.get("shapes")
        if not isinstance(shapes, list):
            raise ValueError(f"invalid shapes: {annotation.name}")
        rows = [_circle_row(shape, width, height, (0, 0, width, height)) for shape in shapes]
        unique = list(dict.fromkeys(rows))
        duplicate_labels_removed += len(rows) - len(unique)
        digest, size = sha256_file(image)
        if digest in image_hashes:
            raise ValueError(f"duplicate image bytes: {image.name}, {image_hashes[digest]}")
        image_hashes[digest] = image.name
        bytes_hashed += size
        source_entries.append(("images/" + image.name, digest))
        annotation_hash, annotation_size = sha256_file(annotation)
        bytes_hashed += annotation_size
        source_entries.append(("annotations/" + annotation.name, annotation_hash))
        prepared.append({"image": image, "rows": "".join(unique),
                         "image_sha256": digest, "image_bytes": size,
                         "annotation_sha256": annotation_hash})

    val_start = train_count + gap_count
    test_start = val_start + val_count + gap_count
    split_rows = {"train": prepared[:train_count],
                  "val": prepared[val_start:val_start + val_count],
                  "test": prepared[test_start:]}
    excluded = prepared[train_count:val_start] + prepared[val_start + val_count:test_start]
    output.mkdir(parents=True, exist_ok=True)
    output_entries, file_records = [], []
    class_counts, groups = {}, {}
    for split, records in split_rows.items():
        image_dir, label_dir = output / "images" / split, output / "labels" / split
        image_dir.mkdir(parents=True); label_dir.mkdir(parents=True)
        counts = collections.Counter()
        for record in records:
            image = record["image"]
            dest = image_dir / (image.stem + ".png")
            # Copy instead of hard-linking so a later consumer cannot mutate source data.
            shutil.copy2(image, dest)
            label = label_dir / (image.stem + ".txt")
            label.write_text(record["rows"], encoding="utf-8", newline="\n")
            counts.update(EXPECTED_CLASSES[int(row.split()[0])] for row in record["rows"].splitlines())
            image_relative, label_relative = dest.relative_to(output).as_posix(), label.relative_to(output).as_posix()
            output_entries.extend([(image_relative, record["image_sha256"]),
                                   (label_relative, sha256_file(label)[0])])
            groups[image_relative] = "in_850_unknown_capture"
            file_records.append({"stem": image.stem, "split": split,
                                 "image_sha256": record["image_sha256"],
                                 "annotation_sha256": record["annotation_sha256"]})
        class_counts[split] = {name: counts[name] for name in EXPECTED_CLASSES}
    (output / "classes.txt").write_text("".join(f"{i} {n}\n" for i, n in enumerate(EXPECTED_CLASSES)), encoding="utf-8")
    (output / "chess14_320.yaml").write_text(
        f"path: {output.as_posix()}\ntrain: images/train\nval: images/val\ntest: images/test\n"
        "nc: 14\nnames:\n" + "".join(f"  {i}: {n}\n" for i, n in enumerate(EXPECTED_CLASSES)), encoding="utf-8")
    (output / "capture_groups_observed.json").write_text(json.dumps(groups, indent=2) + "\n", encoding="utf-8")
    report = {"schema_version": 1, "purpose": "full-frame chronological training candidate",
              "independent_capture_acceptance": False,
              "capture_provenance": "not supplied; treat all files as one capture group",
              "image_directory": str(images), "annotation_directory": str(annotations),
              "preprocess": {"roi": None, "input_size": [320, 320], "channels": "RGB",
                             "letterbox_auto": False, "letterbox_scaleup": False,
                             "letterbox_stride": 32, "padding_value": 114},
              "class_names": list(EXPECTED_CLASSES), "images_scanned": len(prepared),
              "dimensions": dict(image_sizes), "bytes_hashed": bytes_hashed,
              "duplicate_labels_removed": duplicate_labels_removed,
              "split_counts": {s: len(r) for s, r in split_rows.items()} | {"excluded": len(excluded)},
              "split_names": {s: [r["image"].stem for r in records] for s, records in split_rows.items()},
              "excluded_names": [r["image"].stem for r in excluded],
              "class_counts": class_counts, "files": file_records,
              "source_sha256": _hash_entries(source_entries),
              "dataset_sha256": _hash_entries(output_entries),
              "elapsed_ms": round((time.perf_counter() - started) * 1000, 3)}
    (output / "dataset_manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--train-count", type=int, default=720)
    parser.add_argument("--val-count", type=int, default=141)
    parser.add_argument("--test-count", type=int, default=141)
    parser.add_argument("--gap-count", type=int, default=20)
    args = parser.parse_args()
    result = prepare_dataset(args.images, args.annotations, args.output,
                             args.train_count, args.val_count, args.test_count, args.gap_count)
    print("XIANGQI_DATASET_IMPORT_PASS", result["split_counts"], "dataset_sha256=" + result["dataset_sha256"],
          "elapsed_ms=" + str(result["elapsed_ms"]))


if __name__ == "__main__":
    main()
