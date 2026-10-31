import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from verify_picture_model import verify


class ModelPackageTest(unittest.TestCase):
    def add_payload(self, root, data, name):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic manifest test fixture; not a model")
        data["files"][name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                               "bytes": path.stat().st_size}

    def save(self, root, data):
        (root / "manifest.json").write_text(json.dumps(data), encoding="utf-8")

    def make_board_package(self, root, delivery_round=2):
        data = self.make_package(root)
        data.update(contract_version=2, scheme="board-detect-v2", delivery_round=delivery_round)
        data["board_model"] = {
            "version": delivery_round, "input_width": 160, "input_height": 160,
            "parameter_count": 999999, "fp32": "board_model/best.onnx",
            "int8": "board_model/int8/weights.bin",
            "preprocessing": "board_model/preprocessing.json",
            "qc": "board_model/qc.json"}
        main = {"algorithm": "geometry/README.md", "c_reference": "geometry/reference.c",
                "python_reference": "geometry/reference.py", "test_vectors": "geometry/vectors.json",
                "test_vector_count": 20}
        fallback = {key: value.replace("geometry/", "geometry/geometry_fallback/")
                    if isinstance(value, str) else value for key, value in main.items()}
        data["geometry"] = dict(main, fallback=fallback)
        for section in (data["board_model"], main, fallback):
            for value in section.values():
                if isinstance(value, str):
                    self.add_payload(root, data, value)
        data["metrics"].update(board_corner_error_p50_px=8, board_corner_error_p95_px=15,
                               board_grid_assignment_accuracy=.99, board_quantization_drift_px=2)
        if delivery_round == 1:
            self.add_payload(root, data, "relabel_candidate/README.md")
        self.save(root, data)
        return data

    def make_package(self, root):
        files = {}
        for name in ("best.onnx", "int8/scales.json", "golden/README.md",
                     "tools/README.md", "report/test.json", "training_manifest.json"):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"synthetic manifest test fixture; not a model")
            files[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                           "bytes": path.stat().st_size}
        maps = {"synthetic_%d" % i: .7 for i in range(11)}
        maps.update(black_pao=.5, black_ma=.6, red_ma=.7)
        data = {"contract_version": 1, "files": files,
                "metrics": {"fp32_board_exact_accuracy": .87,
                            "w8a8_board_exact_accuracy": .85, "class_map50": maps},
                "split_games": {"train": [1], "val": [2], "test": [3]},
                "boundary_gap_frames": 20, "board_confidence_threshold_permille": 800}
        (root / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
        return data

    def test_integrity_is_not_smoke_or_acceptance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_package(root)
            result = verify(root)
            self.assertTrue(result["reported_metrics_pass"])
            self.assertFalse(result["golden_smoke_pass"])
            self.assertFalse(result["m0_accepted"])
            (root / "best.onnx").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "identity mismatch"):
                verify(root)

    def test_no_leakage_bad_metrics_or_unlisted_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = self.make_package(root)
            for change in ("split", "weak", "quantization", "path", "threshold"):
                data = json.loads(json.dumps(original))
                if change == "split": data["split_games"]["test"] = [2]
                if change == "weak": data["metrics"]["class_map50"]["black_pao"] = .49
                if change == "quantization": data["metrics"]["fp32_board_exact_accuracy"] = .90
                if change == "path": data["files"]["../outside"] = data["files"]["best.onnx"]
                if change == "threshold": data["board_confidence_threshold_permille"] = 0
                (root / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(ValueError): verify(root)
            (root / "manifest.json").write_text(json.dumps(original), encoding="utf-8")
            (root / "extra.txt").write_text("unregistered", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unlisted"):
                verify(root)

    def test_round2_static_gate_and_version_dispatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = self.make_board_package(root)
            for version in (1, 2):
                data["contract_version"] = version
                self.save(root, data)
                result = verify(root)
                self.assertEqual(result["scheme"], "board-detect-v2")
                self.assertTrue(result["reported_metrics_pass"])
                self.assertTrue(result["m0_eligible"])
                self.assertFalse(result["golden_smoke_pass"])
                self.assertFalse(result["m0_accepted"])
                self.assertFalse(result["main_chain_switch_allowed"])

    def test_round1_only_allows_explicit_geometry_smoke(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = self.make_board_package(root, 1)
            # Round1 may miss final piece/board metrics; it never earns M0.
            data["metrics"] = {"board_corner_error_p50_px": 20, "board_corner_error_p95_px": 50}
            self.save(root, data)
            with self.assertRaisesRegex(ValueError, "Round1"):
                verify(root)
            result = verify(root, purpose="geometry-smoke")
            self.assertFalse(result["m0_eligible"])
            self.assertFalse(result["reported_metrics_pass"])
            self.assertFalse(result["main_chain_switch_allowed"])
            self.assertFalse(result["m0_accepted"])
            (root / "board_model/best.onnx").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "identity mismatch"):
                verify(root, purpose="geometry-smoke")

    def test_board_gates_reject_malformed_missing_and_out_of_range_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = self.make_board_package(root)
            changes = [
                ("scheme", "unknown"), ("scheme", None), ("contract_version", True),
                ("delivery_round", True), ("delivery_round", 3), ("board_model", []),
                ("board_model.version", 1), ("board_model.input_width", 193),
                ("board_model.input_height", 0), ("board_model.parameter_count", 1000001),
                ("board_model.int8", "int8/scales.json"),
                ("board_model.preprocessing", "board_model/missing.json"),
                ("board_model.qc", None), ("geometry.test_vector_count", 19),
                ("geometry.c_reference", "geometry/reference.py"),
                ("geometry.fallback", None),
                ("metrics.board_corner_error_p50_px", 8.01),
                ("metrics.board_corner_error_p95_px", 15.01),
                ("metrics.board_corner_error_p50_px", 16),
                ("metrics.board_grid_assignment_accuracy", .989),
                ("metrics.board_quantization_drift_px", 2.01),
                ("metrics.board_quantization_drift_px", float("nan")),
                ("metrics.board_corner_error_p95_px", True),
                ("files.best.onnx.bytes", True), ("boundary_gap_frames", True),
            ]
            for name, value in changes:
                with self.subTest(field=name, value=value):
                    data = json.loads(json.dumps(original))
                    target = data
                    parts = name.split(".") if not name.startswith("files.") else ["files", "best.onnx", "bytes"]
                    for part in parts[:-1]:
                        target = target[part]
                    target[parts[-1]] = value
                    self.save(root, data)
                    with self.assertRaises(ValueError):
                        verify(root)

    def test_unknown_scheme_cannot_fall_through_legacy_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = self.make_package(root)
            data["scheme"] = "board-detect-typo"
            self.save(root, data)
            with self.assertRaises(ValueError):
                verify(root)

    def test_round1_identity_does_not_bypass_safety_checks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = self.make_board_package(root, 1)
            for name in ("../outside", "BOARD_MODEL/BEST.ONNX", "manifest.json"):
                data = json.loads(json.dumps(original))
                data["files"][name] = data["files"]["best.onnx"]
                self.save(root, data)
                with self.assertRaises(ValueError):
                    verify(root, purpose="geometry-smoke")


if __name__ == "__main__":
    unittest.main()
