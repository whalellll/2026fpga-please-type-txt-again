import copy
import unittest

from board_corner_domain_contract import evaluate_predictions, validate_split


def sample(identity="a", split="train", group="capture-a", sha="a"):
    return {
        "id": identity, "split": split, "source": "authorized_old_domain",
        "capture_group": group, "duplicate_cluster": group,
        "root_image_sha256": sha * 64, "image_sha256": sha * 64,
        "background": "white", "exposure": "low",
    }


class SplitTests(unittest.TestCase):
    def document(self, rows):
        return {"schema": "board-corner-domain-split/1", "data_permission_reference": "synthetic test only", "records": rows}

    def test_disjoint_groups_pass_without_reading_images(self):
        result = validate_split(self.document([
            sample(), sample("b", "blind", "capture-b", "b"),
            sample("c", "dev", "capture-c", "c"),
        ]))
        self.assertEqual(result["samples"], {"train": 1, "blind": 1, "dev": 1})
        self.assertFalse(result["images_read"])

    def test_same_capture_cannot_cross_splits(self):
        with self.assertRaisesRegex(ValueError, "lineage"):
            validate_split(self.document([sample(), sample("b", "blind", "capture-a", "b")]))

    def test_augmentation_parent_cannot_cross_splits(self):
        derived = sample("augmented", "dev", "another-name", "b")
        derived["root_image_sha256"] = "a" * 64
        with self.assertRaisesRegex(ValueError, "lineage"):
            validate_split(self.document([sample(), derived]))

    def test_sealed_source_is_rejected(self):
        row = sample()
        row["source"] = "CAMERA_v2/game2"
        with self.assertRaisesRegex(ValueError, "excluded"):
            validate_split(self.document([row]))

    def test_diagnosed_case_is_not_blind_or_training(self):
        row = sample()
        row["regression_only"] = True
        with self.assertRaisesRegex(ValueError, "development"):
            validate_split(self.document([row]))


class MetricTests(unittest.TestCase):
    def document(self):
        truth = [[100.0, 100.0], [600.0, 100.0], [600.0, 500.0], [100.0, 500.0]]
        return {"schema": "board-corner-predictions/1", "rows": [{
            "id": "synthetic", "split": "dev", "width": 1280, "height": 720,
            "truth_pixel_centres": truth, "prediction": copy.deepcopy(truth),
            "prediction_space": "pixel_centres", "strict_native_status": 0,
        }]}

    def test_pixel_units_and_whole_board_boundary(self):
        data = self.document()
        data["rows"][0]["prediction"] = [[x + 3, y + 4] for x, y in data["rows"][0]["prediction"]]
        result = evaluate_predictions(data)
        self.assertEqual(result["rows"][0]["mean_corner_error_px"], 5.0)
        self.assertIsNone(result["whole_board_accuracy"])
        self.assertFalse(result["native_status_independently_run"])

    def test_half_pixel_contract(self):
        data = self.document()
        row = data["rows"][0]
        row["prediction_space"] = "normalized_pixel_centres"
        row["prediction"] = [[(x + 0.5) / 1280, (y + 0.5) / 720] for x, y in row["prediction"]]
        self.assertLess(evaluate_predictions(data)["rows"][0]["max_corner_error_px"], 1e-10)
        row["prediction"] = [[x / 1280, y / 720] for x, y in row["truth_pixel_centres"]]
        self.assertAlmostEqual(evaluate_predictions(data)["rows"][0]["mean_corner_error_px"], 2 ** -0.5)

    def test_missing_prediction_cannot_claim_success(self):
        data = self.document()
        data["rows"][0]["prediction"] = None
        with self.assertRaisesRegex(ValueError, "missing prediction"):
            evaluate_predictions(data)
        data["rows"][0]["strict_native_status"] = 5
        result = evaluate_predictions(data)
        self.assertEqual(result["summary"]["dev"]["missing_predictions"], 1)
        self.assertEqual(result["summary"]["dev"]["declared_native_geometry_passes"], 0)

    def test_nonfinite_coordinate_is_rejected(self):
        data = self.document()
        data["rows"][0]["prediction"][0][0] = float("nan")
        with self.assertRaisesRegex(ValueError, "Finite"):
            evaluate_predictions(data)


if __name__ == "__main__":
    unittest.main()
