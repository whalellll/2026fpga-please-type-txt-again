"""Contract tests for a trained first-layer hardware probe."""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from trained_conv_tile import make_tile, pack_weights, requant, validate_tile


class TrainedConvTileTests(unittest.TestCase):
    def test_weight_lane_order_and_tail(self):
        weights = bytes(
            (oc * 11 + ci * 3 + ky * 6 + kx) & 255
            for oc in range(16) for ci in range(3)
            for ky in range(6) for kx in range(6))
        packed = pack_weights(weights, 3, 16, 6)
        self.assertEqual(len(packed), 27 * 128)
        self.assertEqual(packed[0:4], bytes((0, 3, 6, 1)))
        self.assertEqual(packed[4:8], bytes((11, 14, 17, 12)))
        self.assertEqual(packed[27 * 128 - 4:], bytes(4))

    def test_rounding_and_saturation(self):
        self.assertEqual([requant(v, 1) for v in (-257, -5, 5, 255)],
                         [-128, -3, 3, 127])

    def test_tile_reference_and_corruption_rejection(self):
        pixels = bytes((i * 17) & 127 for i in range(8 * 8 * 4))
        weights = bytes((i % 7 - 3) & 255 for i in range(16 * 3 * 6 * 6))
        started = time.perf_counter()
        tile = make_tile(pixels, 8, 8, weights, [0] * 16, [8] * 16)
        self.assertEqual(len(tile["output"]), 4 * 4 * 16)
        self.assertEqual(tile["traffic"], {
            "input_bytes": 256, "weight_bytes": 3456,
            "output_bytes": 256, "tap_count": 576,
        })
        validate_tile(tile)
        tile["output"] = bytes([tile["output"][0] ^ 1]) + tile["output"][1:]
        with self.assertRaises(ValueError):
            validate_tile(tile)
        self.assertLess(time.perf_counter() - started, 5.0)


if __name__ == "__main__":
    unittest.main()
