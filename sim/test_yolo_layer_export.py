"""Structural tests run with the pinned vision Python environment."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vision"))

from export_layer_contract import build_manifest  # noqa: E402
from stage2_contract import validate_manifest  # noqa: E402


class LayerExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = build_manifest()

    def test_identity_and_integrity(self):
        manifest = self.manifest
        self.assertEqual(manifest["input_shape"], [1, 3, 320, 320])
        self.assertEqual(manifest["class_count"], 14)
        self.assertFalse(manifest["trained_weights"])
        self.assertEqual(manifest["preprocess"], {
            "source_channels": "BGR", "model_channels": "RGB",
            "letterbox_shape": [320, 320], "letterbox_auto": False,
            "letterbox_scale_fill": False, "letterbox_scale_up": False,
            "letterbox_stride": 32, "letterbox_color": [114, 114, 114],
            "reference_scaling": "uint8_div_255_to_float32",
        })
        self.assertEqual(manifest["detect_raw_order"],
                         ["batch", "anchor", "grid_y", "grid_x", "prediction"])
        self.assertEqual(manifest["device_conv_output_order"],
                         ["output_y", "output_x", "output_channel"])
        validate_manifest(manifest, manifest["config_sha256"])
        self.assertGreater(len(manifest["layers"]), 100)

    def test_first_convolution_and_detect_shapes(self):
        conv = next(layer for layer in self.manifest["layers"]
                    if layer["operator"] == "Conv2d")
        self.assertEqual(conv["input_shape"], [1, 3, 320, 320])
        self.assertEqual(conv["output_shape"], [1, 16, 160, 160])
        self.assertEqual(conv["weight_shape"], [16, 3, 6, 6])
        self.assertEqual(conv["stride"], [2, 2])
        self.assertEqual(conv["padding"], [2, 2])
        self.assertEqual(self.manifest["detect_raw_shapes"],
                         [[1, 3, 40, 40, 19],
                          [1, 3, 20, 20, 19],
                          [1, 3, 10, 10, 19]])
        self.assertEqual(self.manifest["detect_decoded_shape"], [1, 6300, 19])

    def test_graph_contains_branch_and_pool_operators(self):
        names = {layer["operator"] for layer in self.manifest["layers"]}
        self.assertIn("Concat", names)
        self.assertIn("Upsample", names)
        self.assertIn("MaxPool2d", names)
        self.assertIn("SiLU", names)


if __name__ == "__main__":
    unittest.main()
