"""Evaluate fixed-square FP32 detections and export the three raw Detect heads.

The export is a PC reference candidate. It is not an INT8 device model, and
existing Stage2 hardware has not accepted the remaining 59 complete layers.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import time
from pathlib import Path

os.environ.setdefault("YOLOv5_AUTOINSTALL", "false")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--export-deps", type=Path, required=True)
    args = parser.parse_args()
    import sys
    sys.path.insert(0, str(args.export_deps.resolve()))
    model_path, dataset, output = (p.resolve() for p in (args.model, args.dataset, args.output))
    output.mkdir(parents=True, exist_ok=True)
    os.environ["YOLOV5_CONFIG_DIR"] = str(output.parent / "yolo_config")

    import cv2
    import numpy as np
    import onnx
    import onnxruntime as ort
    import torch
    from model_m0_audit import validate_data_config, sha256_file
    from accelerator_compatibility import audit_layers, source_capabilities
    from probe_model_m0 import probe_checkpoint
    from yolov5.utils.augmentations import letterbox

    torch.set_num_threads(4)
    metadata = probe_checkpoint(model_path)
    validate_data_config(dataset / "chess14_320.yaml", dataset, dataset / "classes.txt")
    source_manifest = json.loads((dataset / "dataset_manifest.json").read_text())
    checkpoint = torch.load(model_path, map_location="cpu", weights_only=False)
    model = (checkpoint.get("ema") or checkpoint["model"]).float().eval()
    frozen = json.loads(Path(__file__).with_name("yolov5n_14_320_contract.json").read_text())
    records, hooks = [], []

    def shapes(value):
        if isinstance(value, torch.Tensor):
            return [list(value.shape)]
        if isinstance(value, (tuple, list)):
            return [shape for item in value for shape in shapes(item)]
        return []

    def recorder(name, module):
        def hook(_module, inputs, result):
            ins = [s for s in shapes(inputs) if len(s) == 4]
            outs = [s for s in shapes(result) if len(s) == 4]
            if not ins or not outs:
                return
            record = dict(index=len(records), name=name, operator=type(module).__name__,
                          input_shape=ins[0], input_shapes=ins, output_shape=outs[0], reference_dtype="float32")
            if isinstance(module, torch.nn.Conv2d):
                record.update(weight_shape=list(module.weight.shape), kernel=list(module.kernel_size),
                              stride=list(module.stride), padding=list(module.padding), groups=module.groups)
            records.append(record)
        return hook

    for name, module in model.named_modules():
        if name and not tuple(module.children()):
            hooks.append(module.register_forward_hook(recorder(name, module)))
    with torch.no_grad():
        decoded, raw = model(torch.zeros(1, 3, 320, 320))
    for hook in hooks:
        hook.remove()
    if records != frozen["layers"] or [list(t.shape) for t in raw] != frozen["detect_raw_shapes"]:
        raise ValueError("trained execution graph differs from the frozen contract")
    if list(decoded.shape) != frozen["detect_decoded_shape"]:
        raise ValueError("decoded output shape differs from the frozen contract")
    (output / "trained_graph.json").write_text(json.dumps({"model_sha256": metadata["model_sha256"],
                                                        "layers": records}, indent=2) + "\n")
    compatibility = audit_layers(records, source_capabilities(Path(__file__).resolve().parents[1]))
    compatibility["model_sha256"] = metadata["model_sha256"]
    (output / "accelerator_compatibility.json").write_text(json.dumps(compatibility, indent=2) + "\n")

    # Upstream .pt validation uses rectangular batches. Force the deployed square
    # letterbox here without changing installed third-party files or model code.
    import yolov5.val as validation
    original_loader = validation.create_dataloader

    def square_loader(*a, **kw):
        kw.update(rect=False, pad=0.0)
        return original_loader(*a, **kw)

    validation.create_dataloader = square_loader
    metrics = {}
    try:
        for split in ("val", "test"):
            result, per_class_maps, per_class_map50, speed = validation.run(
                data=str(dataset / "chess14_320.yaml"), weights=str(model_path),
                batch_size=1, imgsz=320, conf_thres=0.001, iou_thres=0.6,
                max_det=300, task=split, device="0", workers=0, half=False,
                verbose=True, save_txt=True, save_conf=True, plots=True,
                project=str(output), name=split + "_square_fp32", exist_ok=False)
            metrics[split] = {"images": source_manifest["split_counts"][split],
                              "boxes": sum(source_manifest["class_counts"][split].values()),
                              "precision": float(result[0]), "recall": float(result[1]),
                              "map50": float(result[2]), "map50_95": float(result[3]),
                              "class_map50_95": [float(v) for v in per_class_maps],
                              "class_map50": [float(v) for v in per_class_map50],
                              "pc_gpu_ms_per_image": dict(zip(("preprocess", "inference", "nms"), map(float, speed))),
                              "input_shape": [1, 3, 320, 320], "precision_mode": "FP32",
                              "independent_capture_acceptance": False}
    finally:
        validation.create_dataloader = original_loader
    (output / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")

    class RawHeads(torch.nn.Module):
        def __init__(self, network):
            super().__init__(); self.network = network

        def forward(self, images):
            return tuple(self.network(images)[1])

    exported = output / "yolov5n_chess14_320_raw.onnx"
    wrapper = RawHeads(model).eval()
    torch.onnx.export(wrapper, torch.zeros(1, 3, 320, 320), str(exported),
                      opset_version=12, do_constant_folding=True,
                      input_names=["images"], output_names=["p3", "p4", "p5"], dynamic_axes=None)
    graph = onnx.load(str(exported))
    onnx.checker.check_model(graph)
    hist = dict(collections.Counter(node.op_type for node in graph.graph.node))
    if hist.get("Conv") != 60 or "NonMaxSuppression" in hist:
        raise ValueError("export must have exactly 60 Conv nodes and no NMS")
    if any(node.domain for node in graph.graph.node):
        raise ValueError("custom-domain operators are not permitted")
    session_options = ort.SessionOptions()
    session_options.intra_op_num_threads = 4
    session = ort.InferenceSession(str(exported), sess_options=session_options,
                                   providers=["CPUExecutionProvider"])
    if session.get_inputs()[0].shape != [1, 3, 320, 320]:
        raise ValueError("ONNX input must be static batch-one 320 RGB NCHW")
    if [o.shape for o in session.get_outputs()] != frozen["detect_raw_shapes"]:
        raise ValueError("ONNX raw Detect outputs differ from the contract")
    candidates = sorted((dataset / "images/test").glob("*.png"))
    chosen = [candidates[int(i)] for i in np.linspace(0, len(candidates)-1, 5)]
    comparisons = []
    for index, path in enumerate(chosen):
        pixels = cv2.imread(str(path))
        pixels = letterbox(pixels, (320, 320), auto=False, scaleup=False, stride=32)[0]
        array = np.ascontiguousarray(pixels[:, :, ::-1].transpose(2, 0, 1)[None], dtype=np.float32) / 255.0
        with torch.no_grad():
            torch_raw = [t.numpy() for t in wrapper(torch.from_numpy(array))]
        started = time.perf_counter()
        onnx_raw = session.run(None, {"images": array})
        elapsed_ms = (time.perf_counter() - started) * 1000
        max_error = max(float(np.abs(a-b).max()) for a, b in zip(torch_raw, onnx_raw))
        for a, b in zip(torch_raw, onnx_raw):
            np.testing.assert_allclose(a, b, atol=1e-4, rtol=1e-4)
        if index == 0:
            np.savez_compressed(output / "fp32_golden_sample.npz", input=array,
                                p3=torch_raw[0], p4=torch_raw[1], p5=torch_raw[2])
        comparisons.append({"image": path.name, "image_sha256": sha256_file(path)[0],
                            "max_abs_error": max_error, "pc_onnx_cpu_ms": elapsed_ms})
    report = {"schema_version": 1, "model": metadata,
              "dataset_sha256": source_manifest["dataset_sha256"],
              "source_sha256": source_manifest["source_sha256"], "metrics": metrics,
              "graph_leaf_operators": len(records), "graph_matches_frozen_contract": True,
              "current_accelerator": {key: compatibility[key] for key in (
                  "conv_count", "direct_conv_shape_count", "direct_conv_macs_percent",
                  "whole_model_conv_abi_ready", "device_model_ready", "dense_model_backend_implemented")},
              "onnx_sha256": sha256_file(exported)[0], "onnx_bytes": exported.stat().st_size,
              "onnx_opset": 12, "onnx_operator_counts": hist, "onnx_comparisons": comparisons,
              "preprocess": source_manifest["preprocess"],
              "detect_decode": "CPU; raw heads use frozen anchors and stride",
              "nms": "CPU; not embedded in ONNX", "board_acceptance": False,
              "quantization_acceptance": False, "independent_capture_acceptance": False}
    (output / "acceptance.json").write_text(json.dumps(report, indent=2) + "\n")
    print("YOLOV5N_CANDIDATE_ACCEPT_PASS", metadata["model_sha256"],
          "test_map50=" + str(metrics["test"]["map50"]),
          "device_model_ready=False", flush=True)


if __name__ == "__main__":
    main()
