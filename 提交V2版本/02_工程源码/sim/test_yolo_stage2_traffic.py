"""Logical budgets and measured-counter guards for stage-2 Conv2d rows."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vision"))
from stage2_traffic_report import (  # noqa: E402
    budget_for_layer, class_name_digest, validate_measurement,
)


class Stage2TrafficTest(unittest.TestCase):
    def setUp(self):
        self.first = {
            "index": 0, "operator": "Conv2d", "name": "model.0.conv",
            "input_shape": [1, 3, 320, 320],
            "output_shape": [1, 16, 160, 160],
            "weight_shape": [16, 3, 6, 6],
            "kernel": [6, 6], "stride": [2, 2],
            "padding": [2, 2], "groups": 1,
        }

    def test_first_layer_logical_budget_and_supported_tile(self):
        row = budget_for_layer(self.first)
        self.assertEqual(row["input_bytes"], 409600)
        self.assertEqual(row["weight_bytes"], 3456)
        self.assertEqual(row["compact_output_bytes"], 409600)
        self.assertEqual(row["legacy_output_bytes"], 1638400)
        self.assertEqual(row["window_count"], 25600)
        self.assertEqual(row["tap_count"], 921600)
        self.assertTrue(row["supported_tile"])

    def test_class_identity_is_independent_of_checkout_line_endings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "classes.txt"
            path.write_bytes(b"0 red_shuai\n1 red_shi\n")
            lf_digest = class_name_digest(path)
            path.write_bytes(b"0 red_shuai\r\n1 red_shi\r\n")
            self.assertEqual(class_name_digest(path), lf_digest)

    def test_measured_counter_must_match_mode_and_shape(self):
        row = budget_for_layer(self.first)
        measurement = {
            "mode": "window", "input_ddr_bytes": 409600,
            "weight_ddr_bytes": 3456, "output_ddr_bytes": 0,
            "window_count": 25600, "tap_count": 921600,
            "stall_cycles": 1, "cycles": 1342255,
            "bitstream_sha256": "a" * 64,
            "test_image_sha256": "b" * 64,
            "marker": "CONV_CASE_PASS id=3",
        }
        validate_measurement(row, measurement)
        wrong = dict(measurement, output_ddr_bytes=409600)
        with self.assertRaises(ValueError):
            validate_measurement(row, wrong)
        compute = dict(measurement, mode="compute", output_ddr_bytes=409600)
        validate_measurement(row, compute)

    def test_deep_layer_is_explicitly_unmeasured(self):
        deep = dict(self.first, input_shape=[1, 32, 40, 40],
                    output_shape=[1, 64, 40, 40],
                    weight_shape=[64, 32, 3, 3],
                    kernel=[3, 3], stride=[1, 1], padding=[1, 1])
        row = budget_for_layer(deep)
        self.assertFalse(row["supported_tile"])
        self.assertEqual(row["compact_output_bytes"], 102400)
        with self.assertRaises(ValueError):
            validate_measurement(row, {"mode": "compute"})

    def test_compute_board_counters_must_match_raw_log(self):
        row = budget_for_layer(self.first)
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "board.log"
            log.write_text(
                "MAC_CONV_FULL_FIRST_LAYER_PASS output=409600 input=409600 "
                "weight=3456 taps=921600 reuse=25600 crc=eb240272 "
                "compute_cycles=15466918 weight_cycles=2738 "
                "stalls=14119561\n", encoding="utf-8")
            measured = {
                "mode": "compute", "input_ddr_bytes": 409600,
                "weight_ddr_bytes": 3456, "output_ddr_bytes": 409600,
                "window_count": 25600, "tap_count": 921600,
                "stall_cycles": 14119561, "cycles": 15466918,
                "bitstream_sha256": "a" * 64,
                "test_image_sha256": "b" * 64,
                "marker": "MAC_CONV_FULL_FIRST_LAYER_PASS",
                "board_log": str(log), "crc32": "eb240272",
            }
            validate_measurement(row, measured)
            log.write_text(log.read_text(encoding="utf-8").replace(
                "compute_cycles=15466918", "compute_cycles=15466919"),
                encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_measurement(row, measured)


if __name__ == "__main__":
    unittest.main()
