"""M0 acceptance tests: model identity, dataset isolation and audit cost."""

from __future__ import annotations

import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path

from model_m0_audit import (
    EXPECTED_ANCHORS_PX,
    EXPECTED_CLASSES,
    AuditError,
    audit_dataset,
    validate_checkpoint_metadata,
    validate_data_config,
    validate_golden_boards,
)
from probe_model_m0 import pixel_anchors


class M0AuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.model = self.root / "best.pt"
        self.model.write_bytes(b"frozen-test-checkpoint")
        self.metadata = {
            "schema_version": 1,
            "model_sha256": hashlib.sha256(self.model.read_bytes()).hexdigest(),
            "model_bytes": self.model.stat().st_size,
            "input_shape": [1, 3, 320, 320],
            "classes": list(EXPECTED_CLASSES),
            "strides": [8, 16, 32],
            "anchors_px": EXPECTED_ANCHORS_PX,
            "detect_shapes": [[1, 3, 40, 40, 19], [1, 3, 20, 20, 19],
                              [1, 3, 10, 10, 19]],
        }

    def add_sample(self, split: str, name: str, image: bytes,
                   label: str = "0 0.5 0.5 0.1 0.1\n") -> str:
        image_dir = self.root / "images" / split
        label_dir = self.root / "labels" / split
        image_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)
        (image_dir / name).write_bytes(image)
        (label_dir / (Path(name).stem + ".txt")).write_text(label)
        return f"images/{split}/{name}"

    def three_splits(self) -> dict[str, str]:
        return {
            self.add_sample("train", "a.png", b"train"): "game-a",
            self.add_sample("val", "b.png", b"val"): "game-b",
            self.add_sample("test", "c.png", b"test"): "game-c",
        }

    def test_checkpoint_contract_and_rejections(self) -> None:
        validate_checkpoint_metadata(self.model, self.metadata)
        for key, wrong in (
            ("model_sha256", "0" * 64),
            ("model_bytes", 1),
            ("input_shape", [1, 3, 640, 640]),
            ("classes", list(reversed(EXPECTED_CLASSES))),
            ("strides", [8, 16, 16]),
            ("anchors_px", [[[1, 1]] * 3] * 3),
            ("detect_shapes", [[1, 3, 40, 40, 18]] * 3),
            ("schema_version", 2),
        ):
            with self.subTest(key=key):
                damaged = {**self.metadata, key: wrong}
                with self.assertRaises(AuditError):
                    validate_checkpoint_metadata(self.model, damaged)

    def test_fractional_pixel_anchor_is_rejected(self) -> None:
        self.assertEqual(pixel_anchors([[[1.25, 1.625]]], [8]),
                         [[[10, 13]]])
        with self.assertRaisesRegex(ValueError, "fractional"):
            pixel_anchors([[[1.30, 1.625]]], [8])

    def test_dataset_split_and_content_isolation(self) -> None:
        groups = self.three_splits()
        report = audit_dataset(self.root, groups)
        self.assertEqual(report["image_count"], 3)
        self.assertEqual(report["label_count"], 3)
        self.assertEqual(report["split_counts"], {"train": 1, "val": 1, "test": 1})
        self.assertEqual(report["bytes_hashed"], 12)

        groups["images/test/c.png"] = "game-a"
        with self.assertRaisesRegex(AuditError, "capture group"):
            audit_dataset(self.root, groups)
        groups["images/test/c.png"] = "game-c"
        (self.root / "images/test/c.png").write_bytes(b"train")
        with self.assertRaisesRegex(AuditError, "duplicate image"):
            audit_dataset(self.root, groups)

    def test_dataset_config_and_class_file_rejections(self) -> None:
        class_file = self.root / "classes.txt"
        class_file.write_text("".join(f"{i} {name}\n" for i, name in
                                      enumerate(EXPECTED_CLASSES)))
        config = {
            "path": str(self.root), "train": "images/train",
            "val": "images/val", "test": "images/test", "nc": 14,
            "names": {i: name for i, name in enumerate(EXPECTED_CLASSES)},
        }
        config_path = self.root / "data.yaml"
        config_path.write_text(json.dumps(config))
        validate_data_config(config_path, self.root, class_file)
        config["val"] = "images/test"
        config_path.write_text(json.dumps(config))
        with self.assertRaisesRegex(AuditError, "split paths"):
            validate_data_config(config_path, self.root, class_file)
        config["val"] = "images/val"
        config_path.write_text(json.dumps(config))
        class_file.write_text("0 black_jiang\n")
        with self.assertRaisesRegex(AuditError, "class file"):
            validate_data_config(config_path, self.root, class_file)

    def test_missing_pairs_and_group_assignment_rejected(self) -> None:
        groups = self.three_splits()
        del groups["images/test/c.png"]
        with self.assertRaisesRegex(AuditError, "capture group"):
            audit_dataset(self.root, groups)
        groups["images/test/c.png"] = "game-c"
        (self.root / "labels/test/c.txt").unlink()
        with self.assertRaisesRegex(AuditError, "image/label"):
            audit_dataset(self.root, groups)

    def test_duplicate_label_is_rejected(self) -> None:
        groups = self.three_splits()
        (self.root / "labels/test/c.txt").write_text(
            "0 0.5 0.5 0.1 0.1\n0 0.5 0.5 0.1 0.1\n")
        with self.assertRaisesRegex(AuditError, "duplicate label"):
            audit_dataset(self.root, groups)

    def test_golden_board_requires_complete_fen_and_roi(self) -> None:
        groups = self.three_splits()
        report = audit_dataset(self.root, groups)
        gold = [{
            "image": "images/test/c.png",
            "roi_xyxy": [0, 0, 740, 650],
            "corners_xy": [[0, 0], [739, 0], [739, 649], [0, 649]],
            "fen": "4k4/9/9/9/9/9/9/9/9/4K4 w - - 0 1",
        }]
        validate_golden_boards(gold, report["images_by_split"])
        with self.assertRaisesRegex(AuditError, "golden"):
            validate_golden_boards([], report["images_by_split"])
        with self.assertRaisesRegex(AuditError, "FEN"):
            validate_golden_boards([{**gold[0], "fen": "4k4/9 w"}],
                                   report["images_by_split"])

    def test_audit_performance_counter_is_measured(self) -> None:
        groups: dict[str, str] = {}
        for i in range(300):
            split = ("train", "val", "test")[i % 3]
            payload = i.to_bytes(4, "little") + bytes([i % 251]) * 60
            groups[self.add_sample(split, f"{i:04}.png", payload)] = split
        start = time.perf_counter()
        report = audit_dataset(self.root, groups)
        elapsed_ms = (time.perf_counter() - start) * 1000
        self.assertEqual(report["image_count"], 300)
        self.assertEqual(report["bytes_hashed"], 300 * 64)
        self.assertGreater(report["hash_elapsed_ms"], 0)
        print(f"M0_AUDIT_PERF files=300 bytes=19200 elapsed_ms={elapsed_ms:.3f} "
              f"hash_ms={report['hash_elapsed_ms']:.3f}")


if __name__ == "__main__":
    unittest.main()
