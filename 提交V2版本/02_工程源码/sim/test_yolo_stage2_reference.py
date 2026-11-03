"""Deterministic structure/window oracle tests for stage-2 RTL development."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vision"))

from stage2_contract import (  # noqa: E402
    ContractError,
    WindowDescriptor,
    conv2d_nhwc4_int32,
    conv2d_nhwc4_segmented_int32,
    iter_windows_nhwc4,
    manifest_digest,
    validate_manifest,
    window_traffic,
)


class WindowReferenceTest(unittest.TestCase):
    def test_one_by_one_bypass_and_tail_zero(self):
        desc = WindowDescriptor(width=2, height=1, channels=3,
                                kernel=1, stride=1, padding=0)
        pixels = bytes([1, 2, 3, 0, 4, 5, 6, 0])
        self.assertEqual(
            list(iter_windows_nhwc4(pixels, desc)),
            [(0, 0, 0, 0, 0, bytes([1, 2, 3, 0])),
             (0, 1, 0, 0, 0, bytes([4, 5, 6, 0]))],
        )

    def test_three_by_three_border_and_order(self):
        desc = WindowDescriptor(width=2, height=2, channels=1,
                                kernel=3, stride=1, padding=1)
        pixels = bytes([1, 0, 0, 0, 2, 0, 0, 0,
                        3, 0, 0, 0, 4, 0, 0, 0])
        taps = list(iter_windows_nhwc4(pixels, desc))
        self.assertEqual(len(taps), 4 * 9)
        self.assertEqual(taps[0], (0, 0, 0, 0, 0, bytes(4)))
        self.assertEqual(taps[4], (0, 0, 0, 1, 1, bytes([1, 0, 0, 0])))
        self.assertEqual(taps[-1], (1, 1, 0, 2, 2, bytes(4)))

    def test_six_by_six_stride_two(self):
        desc = WindowDescriptor(width=7, height=7, channels=3,
                                kernel=6, stride=2, padding=2)
        pixels = b"".join(bytes([i, i + 1, i + 2, 0])
                          for i in range(49))
        taps = list(iter_windows_nhwc4(pixels, desc))
        self.assertEqual((desc.output_height, desc.output_width), (3, 3))
        self.assertEqual(len(taps), 3 * 3 * 36)
        self.assertEqual(taps[0][-1], bytes(4))
        self.assertEqual(taps[2 * 6 + 2][-1], bytes([0, 1, 2, 0]))
        self.assertEqual(taps[(3 * 3 - 1) * 36 + 5 * 6 + 5][-1], bytes(4))

    def test_multi_channel_tile(self):
        desc = WindowDescriptor(width=1, height=1, channels=5,
                                kernel=1, stride=1, padding=0)
        taps = list(iter_windows_nhwc4(bytes([1, 2, 3, 4, 5, 0, 0, 0]), desc))
        self.assertEqual([tap[-1] for tap in taps],
                         [bytes([1, 2, 3, 4]), bytes([5, 0, 0, 0])])
        with self.assertRaises(ContractError):
            list(iter_windows_nhwc4(bytes(4), desc))

    def test_bad_descriptor(self):
        for changes in (
            {"width": 0}, {"channels": 0}, {"kernel": 2},
            {"stride": 0}, {"padding": 6}, {"width": 65536},
        ):
            values = dict(width=2, height=2, channels=3,
                          kernel=3, stride=1, padding=1)
            values.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                WindowDescriptor(**values)

    def test_traffic_baselines_are_not_hardware_claims(self):
        one = window_traffic(WindowDescriptor(160, 160, 16, 1, 1, 0))
        three = window_traffic(WindowDescriptor(160, 160, 4, 3, 1, 1))
        six = window_traffic(WindowDescriptor(320, 320, 3, 6, 2, 2))
        self.assertEqual(one["source_bytes"], one["naive_tap_bytes"])
        self.assertEqual(three["source_bytes"], 102400)
        self.assertEqual(three["naive_tap_bytes"], 921600)
        self.assertEqual(six["source_bytes"], 409600)
        self.assertEqual(six["naive_tap_bytes"], 3686400)

    def test_integer_conv_negative_values_and_bias(self):
        desc = WindowDescriptor(1, 1, 3, 1, 1, 0)
        pixels = bytes([254, 3, 4, 0])
        weights = bytes([1, 255, 2, 2, 0, 253])
        self.assertEqual(
            conv2d_nhwc4_int32(pixels, desc, weights, 2, [1, -2]),
            [4, -18],
        )

    def test_int32_accumulator_overflow_rejected(self):
        desc = WindowDescriptor(1, 1, 1, 1, 1, 0)
        with self.assertRaises(ContractError):
            conv2d_nhwc4_int32(bytes([1, 0, 0, 0]), desc,
                               bytes([1]), 1, [(1 << 31) - 1])

    def test_integer_conv_three_by_three_boundary(self):
        desc = WindowDescriptor(3, 3, 1, 3, 1, 1)
        pixels = b"".join(bytes([v, 0, 0, 0]) for v in range(1, 10))
        output = conv2d_nhwc4_int32(pixels, desc, bytes(range(9)), 1)
        self.assertEqual(len(output), 9)
        self.assertEqual(output[0], 82)
        self.assertEqual(output[4], 240)

    def test_integer_conv_six_by_six_and_unsigned_input(self):
        desc = WindowDescriptor(7, 7, 3, 6, 2, 2)
        pixels = bytes([200, 2, 3, 0]) * 49
        weights = bytes([1]) * (3 * 6 * 6)
        output = conv2d_nhwc4_int32(
            pixels, desc, weights, 1, input_signed=False
        )
        self.assertEqual(len(output), 9)
        self.assertEqual(output[0], 16 * 205)
        with self.assertRaises(ContractError):
            conv2d_nhwc4_int32(pixels, desc, weights[:-1], 1)

    def test_k_over_256_keeps_int32_until_final_requant(self):
        desc = WindowDescriptor(3, 3, 32, 3, 1, 0)
        pixels = bytes([7, 0, 0, 0] * 8 * 9)
        weights = bytes([1] * (32 * 3 * 3))
        direct = conv2d_nhwc4_int32(pixels, desc, weights, 1, [-40])
        segments = conv2d_nhwc4_segmented_int32(
            pixels, desc, weights, 1, [-40], segment_k=256)
        self.assertEqual(direct, segments)
        self.assertEqual(direct, [464])
        self.assertEqual((segments[0] + 8) >> 4, 29)
        self.assertEqual(((448 - 40 + 8) >> 4) + ((56 + 8) >> 4), 30)


class ManifestTest(unittest.TestCase):
    def setUp(self):
        self.manifest = {
            "schema_version": 1,
            "model": "yolov5n",
            "class_count": 14,
            "input_shape": [1, 3, 320, 320],
            "reference_layout": "NCHW",
            "reference_dtype": "float32",
            "device_layout": "NHWC4",
            "device_element_bytes": 1,
            "device_channel_tail": "zero",
            "preprocess": {
                "source_channels": "BGR", "model_channels": "RGB",
                "letterbox_shape": [320, 320], "letterbox_auto": False,
                "letterbox_scale_fill": False, "letterbox_scale_up": False,
                "letterbox_stride": 32,
                "letterbox_color": [114, 114, 114],
                "reference_scaling": "uint8_div_255_to_float32",
            },
            "device_conv_output_order": ["output_y", "output_x",
                                         "output_channel"],
            "window_order": ["output_y", "output_x", "channel_tile",
                             "kernel_y", "kernel_x"],
            "detect_raw_order": ["batch", "anchor", "grid_y", "grid_x",
                                 "prediction"],
            "detect_decoded_order": ["batch", "candidate", "prediction"],
            "trained_weights": False,
            "weight_sha256": None,
            "detect_raw_shapes": [[1, 3, 40, 40, 19],
                                  [1, 3, 20, 20, 19],
                                  [1, 3, 10, 10, 19]],
            "detect_decoded_shape": [1, 6300, 19],
            "class_names_sha256": "1" * 64,
            "config_sha256": "2" * 64,
            "code_sha256": "3" * 64,
            "layers": [{
                "index": 0, "operator": "Conv2d",
                "input_shape": [1, 3, 320, 320],
                "output_shape": [1, 16, 160, 160],
                "weight_shape": [16, 3, 6, 6],
                "kernel": [6, 6], "stride": [2, 2],
                "padding": [2, 2], "groups": 1,
            }],
        }
        self.manifest["manifest_sha256"] = manifest_digest(self.manifest)

    def test_valid_and_tampered_manifest(self):
        validate_manifest(self.manifest, expected_config_sha256="2" * 64)
        changed = json.loads(json.dumps(self.manifest))
        changed["layers"][0]["output_shape"][2] = 159
        with self.assertRaises(ContractError):
            validate_manifest(changed, expected_config_sha256="2" * 64)

    def test_wrong_version_and_model_identity(self):
        for key, value in (("schema_version", 2),
                           ("class_count", 80),
                           ("device_layout", "NHWC"),
                           ("device_element_bytes", 2),
                           ("device_channel_tail", "garbage"),
                           ("preprocess", {}),
                           ("detect_raw_order", ["grid_x", "grid_y"]),
                           ("window_order", ["x", "y"]),
                           ("detect_raw_shapes", [[1, 3, 40, 40, 85]]),
                           ("trained_weights", True),
                           ("config_sha256", "4" * 64),
                           ("class_names_sha256", "4" * 64),
                           ("code_sha256", "4" * 64)):
            changed = dict(self.manifest, **{key: value})
            changed["manifest_sha256"] = manifest_digest(changed)
            with self.subTest(key=key), self.assertRaises(ContractError):
                validate_manifest(changed, expected_config_sha256="2" * 64,
                                  expected_class_sha256="1" * 64,
                                  expected_code_sha256="3" * 64)


if __name__ == "__main__":
    unittest.main()
