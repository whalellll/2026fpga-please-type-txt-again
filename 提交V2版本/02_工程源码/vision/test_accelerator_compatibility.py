"""Prevent structural graph matches from claiming whole-model accelerator support."""
import json
import time
import unittest
from pathlib import Path

from accelerator_compatibility import audit_layers, source_capabilities


class AcceleratorCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.layers = json.loads((cls.root / "vision/yolov5n_14_320_contract.json").read_text())["layers"]
        cls.caps = source_capabilities(cls.root)

    def test_real_60_layer_graph_has_only_first_direct_conv(self):
        report = audit_layers(self.layers, self.caps)
        self.assertEqual(report["conv_count"], 60)
        self.assertEqual(report["direct_conv_shape_count"], 1)
        self.assertEqual(report["direct_conv_names"], ["model.0.conv"])
        self.assertEqual(report["conv_macs"], 523033600)
        self.assertEqual(report["direct_conv_macs"], 44236800)
        self.assertEqual(report["max_k"], 1152)
        self.assertFalse(report["whole_model_conv_abi_ready"])
        self.assertFalse(report["device_model_ready"])

    def test_quantized_first_layer_still_needs_runtime_and_cpu_ops(self):
        first = [x for x in self.layers if x["name"] == "model.0.conv"]
        report = audit_layers(first, self.caps)
        self.assertTrue(report["whole_model_conv_abi_ready"])
        self.assertFalse(report["device_model_ready"])
        self.assertIn("W8A8 calibration and device packaging", report["blocking_requirements"])

    def test_detect57_tail_and_k1152_are_not_existing_conv_support(self):
        report = audit_layers(self.layers, self.caps)
        dense = {r["name"]: r for r in report["convs"]}
        self.assertIn("Cout exceeds ABI3 limit", dense["model.24.m.0"]["direct_conv_rejections"])
        self.assertEqual(dense["model.24.m.0"]["dense_plan"]["output_tail_channels"], 25)
        self.assertEqual(dense["model.7.conv"]["dense_plan"]["k_segments"], 5)
        self.assertFalse(dense["model.7.conv"]["dense_plan"]["implemented"])

    def test_reject_malformed_geometry_and_missing_limits(self):
        from copy import deepcopy
        bad = deepcopy(self.layers[0]); bad["output_shape"][2] += 1
        with self.assertRaises(ValueError): audit_layers([bad], self.caps)
        with self.assertRaises(ValueError): audit_layers(self.layers, {})

    def test_all_dense_planned_jobs_fit_actual_1mib_and_caps(self):
        started = time.perf_counter()
        report = audit_layers(self.layers, self.caps)
        for layer in report["convs"]:
            plan = layer["dense_plan"]
            self.assertLessEqual(plan["max_pixels_per_job"], 16)
            self.assertLessEqual(plan["max_k_per_job"], 256)
            self.assertLessEqual(plan["peak_job_bytes"], 1024 * 1024)
            self.assertTrue(plan["shape_feasible"])
        self.assertEqual(report["dense_planned_jobs"], 6956)
        self.assertEqual(max(r["dense_plan"]["peak_job_bytes"] for r in report["convs"]), 90112)
        print(f"ACCELERATOR_COMPAT_PERF convs=60 planned_jobs={report['dense_planned_jobs']} elapsed_ms={(time.perf_counter()-started)*1000:.3f}")


if __name__ == "__main__":
    unittest.main()
