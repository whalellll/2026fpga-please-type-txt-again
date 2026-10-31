"""Audit a candidate YOLOv5n checkpoint and frozen Xiangqi acceptance data.

This gate deliberately requires an explicit capture-group map and test-set board
answers. A random image split from one camera session cannot pass by accident.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import time
from pathlib import Path

import yaml


EXPECTED_CLASSES = (
    "red_shuai", "red_shi", "red_xiang", "red_ma", "red_ju",
    "red_pao", "red_bing", "black_jiang", "black_shi",
    "black_xiang", "black_ma", "black_ju", "black_pao", "black_zu",
)
EXPECTED_ANCHORS_PX = [
    [[10, 13], [16, 30], [33, 23]],
    [[30, 61], [62, 45], [59, 119]],
    [[116, 90], [156, 198], [373, 326]],
]
EXPECTED_DETECT_SHAPES = [
    [1, 3, 40, 40, 19], [1, 3, 20, 20, 19], [1, 3, 10, 10, 19],
]
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
FEN_PIECES = set("rnbakcpRNBAKCP")


class AuditError(ValueError):
    pass


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            count += len(chunk)
    return digest.hexdigest(), count


def validate_checkpoint_metadata(model: Path, metadata: dict) -> dict:
    required = {
        "schema_version": 1,
        "input_shape": [1, 3, 320, 320],
        "classes": list(EXPECTED_CLASSES),
        "strides": [8, 16, 32],
        "anchors_px": EXPECTED_ANCHORS_PX,
        "detect_shapes": EXPECTED_DETECT_SHAPES,
    }
    if not isinstance(metadata, dict):
        raise AuditError("checkpoint metadata must be an object")
    for key, expected in required.items():
        if metadata.get(key) != expected:
            raise AuditError(f"checkpoint {key} differs from frozen 320 contract")
    expected_hash = metadata.get("model_sha256")
    if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise AuditError("checkpoint model_sha256 must be a lowercase SHA-256")
    if not model.is_file():
        raise AuditError(f"checkpoint missing: {model}")
    actual_hash, size = sha256_file(model)
    if actual_hash != expected_hash:
        raise AuditError(f"checkpoint hash mismatch: actual={actual_hash}")
    if metadata.get("model_bytes") != size:
        raise AuditError(f"checkpoint size mismatch: actual={size}")
    return {"model_sha256": actual_hash, "model_bytes": size}


def validate_data_config(config_path: Path, root: Path, class_file: Path) -> None:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise AuditError("dataset config must be a mapping")
    if Path(str(config.get("path", ""))).resolve() != root.resolve():
        raise AuditError("dataset config root differs from audited root")
    paths = [config.get(split) for split in ("train", "val", "test")]
    if (paths != ["images/train", "images/val", "images/test"]
            or len(set(map(str, paths))) != 3):
        raise AuditError("dataset split paths must be distinct train/val/test directories")
    names = config.get("names")
    if isinstance(names, dict):
        names = [names.get(i, names.get(str(i))) for i in range(14)]
    if config.get("nc") != 14 or names != list(EXPECTED_CLASSES):
        raise AuditError("dataset config 14-class order mismatch")
    classes = class_file.read_text(encoding="utf-8").splitlines()
    if classes != [f"{i} {name}" for i, name in enumerate(EXPECTED_CLASSES)]:
        raise AuditError("dataset class file differs from frozen 14-class order")


def _validate_label(path: Path) -> int:
    boxes = 0
    seen_rows: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        normalized = " ".join(line.split())
        if normalized in seen_rows:
            raise AuditError(f"{path}:{line_number}: duplicate label")
        seen_rows.add(normalized)
        parts = line.split()
        if len(parts) != 5:
            raise AuditError(f"{path}:{line_number}: expected five YOLO label fields")
        try:
            class_id = int(parts[0])
            x, y, width, height = map(float, parts[1:])
        except ValueError as exc:
            raise AuditError(f"{path}:{line_number}: invalid label number") from exc
        if not 0 <= class_id < 14:
            raise AuditError(f"{path}:{line_number}: invalid class id")
        if not all(map(math.isfinite, (x, y, width, height))):
            raise AuditError(f"{path}:{line_number}: non-finite label")
        if (width <= 0 or height <= 0 or x - width / 2 < -1e-6
                or y - height / 2 < -1e-6 or x + width / 2 > 1 + 1e-6
                or y + height / 2 > 1 + 1e-6):
            raise AuditError(f"{path}:{line_number}: box outside image")
        boxes += 1
    return boxes


def audit_dataset(root: Path, capture_groups: dict[str, str]) -> dict:
    if not isinstance(capture_groups, dict):
        raise AuditError("capture group map must be an object")
    split_counts: dict[str, int] = {}
    images_by_split: dict[str, list[str]] = {}
    group_owner: dict[str, str] = {}
    hash_owner: dict[str, str] = {}
    seen_paths: set[str] = set()
    label_count = box_count = bytes_hashed = 0
    hash_elapsed_ms = 0.0
    for split in ("train", "val", "test"):
        image_dir = root / "images" / split
        label_dir = root / "labels" / split
        if not image_dir.is_dir() or not label_dir.is_dir():
            raise AuditError(f"missing image/label split directories: {split}")
        images = sorted(p for p in image_dir.rglob("*")
                        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)
        labels = sorted(label_dir.rglob("*.txt"))
        image_stems = {p.relative_to(image_dir).with_suffix("").as_posix()
                       for p in images}
        label_stems = {p.relative_to(label_dir).with_suffix("").as_posix()
                       for p in labels}
        if len(image_stems) != len(images) or image_stems != label_stems:
            raise AuditError(f"{split}: image/label pairs differ")
        split_counts[split] = len(images)
        images_by_split[split] = []
        for image in images:
            relative = image.relative_to(root).as_posix()
            seen_paths.add(relative)
            group = capture_groups.get(relative)
            if not isinstance(group, str) or not group.strip():
                raise AuditError(f"missing capture group for {relative}")
            previous_split = group_owner.setdefault(group, split)
            if previous_split != split:
                raise AuditError(f"capture group {group!r} spans {previous_split}/{split}")
            start = time.perf_counter()
            digest, size = sha256_file(image)
            hash_elapsed_ms += (time.perf_counter() - start) * 1000
            bytes_hashed += size
            previous_image = hash_owner.setdefault(digest, relative)
            if previous_image != relative:
                raise AuditError(f"duplicate image content: {previous_image} / {relative}")
            images_by_split[split].append(relative)
        for label in labels:
            label_count += 1
            box_count += _validate_label(label)
    extra_groups = sorted(set(capture_groups) - seen_paths)
    if extra_groups:
        raise AuditError(f"capture group map references missing image: {extra_groups[0]}")
    if not all(split_counts.values()):
        raise AuditError("train, val and test must each contain images")
    return {
        "split_counts": split_counts,
        "image_count": sum(split_counts.values()),
        "label_count": label_count,
        "box_count": box_count,
        "bytes_hashed": bytes_hashed,
        "hash_elapsed_ms": round(hash_elapsed_ms, 3),
        "images_by_split": images_by_split,
        "capture_groups": {split: sorted(group for group, owner in group_owner.items()
                                         if owner == split) for split in split_counts},
    }


def _valid_fen(fen: object) -> bool:
    if not isinstance(fen, str):
        return False
    fields = fen.split()
    if len(fields) != 6 or fields[1] not in ("w", "b") or fields[2:4] != ["-", "-"]:
        return False
    ranks = fields[0].split("/")
    if len(ranks) != 10:
        return False
    for rank in ranks:
        if any(character not in FEN_PIECES and character not in "123456789"
               for character in rank):
            return False
        if sum(int(c) if c.isdigit() else 1 for c in rank) != 9:
            return False
    return (fields[4].isdigit() and fields[5].isdigit()
            and int(fields[5]) >= 1)


def validate_golden_boards(goldens: list[dict],
                           images_by_split: dict[str, list[str]]) -> None:
    if not isinstance(goldens, list) or not goldens:
        raise AuditError("golden board answers are required")
    test_images = set(images_by_split.get("test", []))
    seen: set[str] = set()
    for entry in goldens:
        if not isinstance(entry, dict):
            raise AuditError("golden board entry must be an object")
        image = entry.get("image")
        if image not in test_images or image in seen:
            raise AuditError(f"golden board image must be unique in test split: {image}")
        seen.add(image)
        roi = entry.get("roi_xyxy")
        corners = entry.get("corners_xy")
        if (not isinstance(roi, list) or len(roi) != 4
                or not all(isinstance(v, int) for v in roi)
                or roi[0] < 0 or roi[1] < 0 or roi[2] <= roi[0] or roi[3] <= roi[1]):
            raise AuditError(f"golden board ROI invalid: {image}")
        if (not isinstance(corners, list) or len(corners) != 4
                or not all(isinstance(point, list) and len(point) == 2
                           and all(isinstance(v, int) for v in point)
                           and roi[0] <= point[0] < roi[2]
                           and roi[1] <= point[1] < roi[3] for point in corners)):
            raise AuditError(f"golden board corners invalid: {image}")
        if not _valid_fen(entry.get("fen")):
            raise AuditError(f"golden board FEN invalid: {image}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--data-config", type=Path, required=True)
    parser.add_argument("--class-file", type=Path, required=True)
    parser.add_argument("--capture-groups", type=Path, required=True)
    parser.add_argument("--golden-boards", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
        groups = json.loads(args.capture_groups.read_text(encoding="utf-8"))
        goldens = json.loads(args.golden_boards.read_text(encoding="utf-8"))
        model_report = validate_checkpoint_metadata(args.model, metadata)
        validate_data_config(args.data_config, args.dataset_root, args.class_file)
        dataset_report = audit_dataset(args.dataset_root, groups)
        validate_golden_boards(goldens, dataset_report["images_by_split"])
    except (AuditError, OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"MODEL_M0_AUDIT_FAIL {exc}", file=sys.stderr)
        return 2
    report = {**model_report, **dataset_report, "golden_board_count": len(goldens)}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"MODEL_M0_AUDIT_PASS model={report['model_sha256']} "
          f"images={report['image_count']} boxes={report['box_count']} "
          f"goldens={report['golden_board_count']} "
          f"image_bytes={report['bytes_hashed']} "
          f"hash_ms={report['hash_elapsed_ms']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
