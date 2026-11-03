"""Correctness and bounded scan tests for the separate LabelMe dataset import."""
import json
import tempfile
import time
import unittest
from pathlib import Path

from PIL import Image

from prepare_xiangqi_dataset import prepare_dataset


class DatasetImportTests(unittest.TestCase):
    def make_source(self, root, count=12):
        images, labels = root / "in_850", root / "out_850"
        images.mkdir(); labels.mkdir()
        for i in range(1, count + 1):
            stem = f"IMG{i:05}"
            Image.new("RGB", (40, 32), (i % 256, i // 256, 17)).save(images / (stem + ".PNG"))
            data = {"imageWidth": 40, "imageHeight": 32,
                    "imagePath": "D:/nonexistent/" + stem + ".PNG",
                    "shapes": [{"label": "red_shuai", "shape_type": "circle",
                                "points": [[20, 16], [24, 16]]}]}
            (labels / (stem + ".json")).write_text(json.dumps(data), encoding="utf-8")
        return images, labels

    def prepare(self, root, count=12):
        images, labels = self.make_source(root, count)
        return images, labels, root / "prepared"

    def run_import(self, images, labels, output, train=6, val=2, test=2, gap=1):
        return prepare_dataset(images, labels, output, train, val, test, gap)

    def test_circle_classes_temporal_gap_and_source_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            images, labels, output = self.prepare(Path(temp))
            original = (images / "IMG00001.PNG").read_bytes()
            report = self.run_import(images, labels, output)
            self.assertEqual(report["split_counts"], {"train": 6, "val": 2, "test": 2, "excluded": 2})
            self.assertEqual((output / "labels/train/IMG00001.txt").read_text(),
                             "0 0.50000000 0.50000000 0.20000000 0.25000000\n")
            self.assertEqual(report["excluded_names"], ["IMG00007", "IMG00010"])
            self.assertEqual((images / "IMG00001.PNG").read_bytes(), original)
            self.assertFalse(report["independent_capture_acceptance"])
            self.assertEqual(report["class_names"][13], "black_zu")

    def test_reject_missing_pair_wrong_dimensions_and_unknown_class(self):
        for failure in ("missing", "dimensions", "class"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                images, labels, output = self.prepare(Path(temp))
                path = labels / "IMG00001.json"
                data = json.loads(path.read_text())
                if failure == "missing":
                    (images / "IMG00001.PNG").unlink()
                elif failure == "dimensions":
                    data["imageWidth"] = 41; path.write_text(json.dumps(data))
                else:
                    data["shapes"][0]["label"] = "king"; path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    self.run_import(images, labels, output)
                self.assertFalse(output.exists())

    def test_duplicate_labels_removed_and_duplicate_images_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            images, labels, output = self.prepare(Path(temp))
            path = labels / "IMG00001.json"
            data = json.loads(path.read_text()); data["shapes"] *= 2
            path.write_text(json.dumps(data))
            self.assertEqual(self.run_import(images, labels, output)["duplicate_labels_removed"], 1)
        with tempfile.TemporaryDirectory() as temp:
            images, labels, output = self.prepare(Path(temp))
            (images / "IMG00011.PNG").write_bytes((images / "IMG00001.PNG").read_bytes())
            with self.assertRaisesRegex(ValueError, "duplicate image"):
                self.run_import(images, labels, output)

    def test_reject_nonfinite_radius_and_output_in_source(self):
        with tempfile.TemporaryDirectory() as temp:
            images, labels, output = self.prepare(Path(temp))
            path = labels / "IMG00001.json"
            data = json.loads(path.read_text()); data["shapes"][0]["points"][1][0] = float("nan")
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError): self.run_import(images, labels, output)
            with self.assertRaises(ValueError): self.run_import(images, labels, images / "output")

    def test_300_file_deterministic_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            images, labels, output = self.prepare(Path(temp), 300)
            started = time.perf_counter()
            first = self.run_import(images, labels, output, 200, 45, 45, 5)
            second = self.run_import(images, labels, Path(temp) / "second", 200, 45, 45, 5)
            self.assertEqual(first["dataset_sha256"], second["dataset_sha256"])
            self.assertEqual(first["source_sha256"], second["source_sha256"])
            self.assertEqual(first["images_scanned"], 300)
            self.assertEqual(first["bytes_hashed"], sum(p.stat().st_size for p in images.iterdir()) +
                             sum(p.stat().st_size for p in labels.iterdir()))
            print(f"DATASET_300_SCAN_PASS bytes={first['bytes_hashed']} elapsed_ms={(time.perf_counter()-started)*1000:.1f}")


if __name__ == "__main__":
    unittest.main()
