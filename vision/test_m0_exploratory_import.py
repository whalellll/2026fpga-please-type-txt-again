"""Correctness and measured preparation cost for the M0 trial dataset."""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from PIL import Image

from m0_exploratory_import import prepare_dataset


class ExploratoryImportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.output = self.root / "candidate"

    def add_pair(self, i: int, annotated: bool = True) -> str:
        name = f"CMOS2_20260926_{i:06}_000_frame{i:010}.png"
        image = self.source / name
        Image.new("RGB", (20, 20), color=(i, 80, 120)).save(image)
        if annotated:
            labelme = {
                "imageWidth": 20, "imageHeight": 20,
                "shapes": [{"label": "red_ju", "shape_type": "circle",
                            "points": [[10, 10], [12, 10]]}],
            }
            image.with_suffix(".json").write_text(json.dumps(labelme))
        return name

    def test_temporal_split_crop_and_source_preservation(self) -> None:
        names = [self.add_pair(i) for i in range(9)]
        self.add_pair(10, annotated=False)
        report = prepare_dataset(self.source, self.output, (2, 2, 18, 18),
                                 train_count=5, val_count=1,
                                 test_count=1, gap_count=1)
        self.assertEqual(report["split_counts"],
                         {"train": 5, "val": 1, "test": 1, "excluded": 2})
        self.assertEqual(report["unannotated_count"], 1)
        self.assertEqual(report["split_names"]["train"], names[:5])
        self.assertEqual(report["split_names"]["val"], [names[6]])
        self.assertEqual(report["split_names"]["test"], [names[8]])
        self.assertEqual(len(report["source_sha256"]), 64)
        self.assertEqual(len(report["dataset_sha256"]), 64)
        with Image.open(self.output / "images/val" / names[6]) as cropped:
            self.assertEqual(cropped.size, (16, 16))
        row = (self.output / "labels/val" /
               names[6].replace(".png", ".txt")).read_text().strip().split()
        self.assertEqual(row[0], "4")
        self.assertEqual(list(map(float, row[1:])), [0.5, 0.5, 0.25, 0.25])
        self.assertTrue((self.source / names[6]).is_file())
        self.assertTrue((self.output / "chess14_trial.yaml").is_file())
        groups = json.loads((self.output / "capture_groups_observed.json").read_text())
        self.assertEqual(set(groups.values()), {"CMOS2_20260926"})
        with self.assertRaisesRegex(ValueError, "empty"):
            prepare_dataset(self.source, self.output, (2, 2, 18, 18),
                            train_count=5, val_count=1,
                            test_count=1, gap_count=1)

    def test_rejects_bad_annotation_before_writing(self) -> None:
        for i in range(9):
            self.add_pair(i)
        bad = sorted(self.source.glob("*.json"))[0]
        value = json.loads(bad.read_text())
        value["imageWidth"] = 100
        bad.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "declared size"):
            prepare_dataset(self.source, self.output, (2, 2, 18, 18),
                            train_count=5, val_count=1,
                            test_count=1, gap_count=1)
        self.assertFalse(self.output.exists())

    def test_exact_duplicate_annotation_is_reported_and_removed(self) -> None:
        for i in range(9):
            self.add_pair(i)
        duplicate = sorted(self.source.glob("*.json"))[0]
        value = json.loads(duplicate.read_text())
        value["shapes"].append(value["shapes"][0].copy())
        duplicate.write_text(json.dumps(value))
        report = prepare_dataset(self.source, self.output, (2, 2, 18, 18),
                                 train_count=5, val_count=1,
                                 test_count=1, gap_count=1)
        self.assertEqual(report["duplicate_labels_removed"], 1)
        first_label = self.output / "labels/train" / (duplicate.stem + ".txt")
        self.assertEqual(len(first_label.read_text().splitlines()), 1)

    def test_performance_counters(self) -> None:
        for i in range(95):
            self.add_pair(i)
        start = time.perf_counter()
        report = prepare_dataset(self.source, self.output, (2, 2, 18, 18),
                                 train_count=65, val_count=12,
                                 test_count=12, gap_count=3)
        elapsed_ms = (time.perf_counter() - start) * 1000
        self.assertEqual(report["split_counts"],
                         {"train": 65, "val": 12, "test": 12, "excluded": 6})
        self.assertEqual(report["box_count"], 89)
        self.assertGreater(report["source_bytes_hashed"], 0)
        self.assertGreater(report["output_image_bytes"], 0)
        print(f"M0_IMPORT_PERF annotated=95 exported=89 "
              f"source_bytes={report['source_bytes_hashed']} "
              f"output_bytes={report['output_image_bytes']} "
              f"elapsed_ms={elapsed_ms:.3f}")


if __name__ == "__main__":
    unittest.main()
