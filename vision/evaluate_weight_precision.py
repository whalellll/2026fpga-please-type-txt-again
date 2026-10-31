"""Evaluate W8/W4 weight-only sensitivity with the fixed FP32 chess14 graph.

Activations, bias, SiLU and detection remain FP32. This experiment neither
exports an integer device model nor measures accelerator performance.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path

os.environ.setdefault("YOLOv5_AUTOINSTALL", "false")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    model_path, dataset, golden, output = (
        p.resolve() for p in (args.model, args.dataset, args.golden, args.output))
    if output.exists() and any(output.iterdir()):
        raise ValueError("use an empty evidence directory")
    output.mkdir(parents=True, exist_ok=True)
    os.environ["YOLOV5_CONFIG_DIR"] = str(dataset.parent / "yolo_config")

    import numpy as np
    import torch
    import yolov5.val as validation
    from yolov5.utils.general import check_dataset
    from yolov5.utils.dataloaders import create_dataloader
    from model_m0_audit import validate_data_config
    from probe_model_m0 import probe_checkpoint
    from weight_quantization import quantize_per_output_channel, dequantize

    versions = {"torch": torch.__version__, "yolov5": importlib.metadata.version("yolov5")}
    if versions != {"torch": "2.5.1+cu124", "yolov5": "7.0.14"}:
        raise ValueError("use the pinned training environment: " + str(versions))
    if not torch.cuda.is_available():
        raise ValueError("this recorded experiment requires the local CUDA device")
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    metadata = probe_checkpoint(model_path)
    validate_data_config(dataset / "chess14_320.yaml", dataset, dataset / "classes.txt")
    manifest_path = dataset / "dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frozen = json.loads(Path(__file__).with_name("yolov5n_14_320_contract.json").read_text())
    data = check_dataset(str(dataset / "chess14_320.yaml"))
    checkpoint = torch.load(model_path, map_location="cpu", weights_only=False)
    unfused = (checkpoint.get("ema") or checkpoint["model"]).float().eval()
    convs = {n: list(m.weight.shape) for n, m in unfused.named_modules()
             if isinstance(m, torch.nn.Conv2d)}
    expected = {r["name"]: r["weight_shape"] for r in frozen["layers"]
                if r["operator"] == "Conv2d"}
    if convs != expected or len(convs) != 60:
        raise ValueError("Conv2d graph differs from the fixed model contract")
    fused = copy.deepcopy(unfused).fuse().eval()
    sample = np.load(golden)
    images = torch.from_numpy(sample["input"])
    if list(images.shape) != frozen["input_shape"]:
        raise ValueError("golden input shape differs from the fixed model contract")
    with torch.inference_mode():
        unfused_raw = unfused(images)[1]
        fused_raw = fused(images)[1]
    fusion_errors = []
    for i, (a, b) in enumerate(zip(unfused_raw, fused_raw)):
        np.testing.assert_allclose(a.numpy(), sample[("p3", "p4", "p5")[i]], atol=1e-4, rtol=1e-4)
        np.testing.assert_allclose(a.numpy(), b.numpy(), atol=1e-4, rtol=1e-4)
        fusion_errors.append(float((a - b).abs().max()))
    del unfused, checkpoint
    device = torch.device("cuda:0")
    report = {"schema_version": 1, "model": metadata, "versions": versions,
              "dataset_sha256": manifest["dataset_sha256"],
              "dataset_manifest_sha256": sha(manifest_path), "golden_sha256": sha(golden),
              "input_shape": frozen["input_shape"], "conv_count": len(convs),
              "batch_norm_folded_before_quantization": True,
              "fusion_raw_head_max_abs_error": fusion_errors,
              "activation_precision": "FP32", "bias_precision": "FP32",
              "rounding": "ties-to-even", "weight_scales": "symmetric per output channel",
              "reference_hardware_support": "S8 storage supports W8 values; no W4 MAC mode implemented",
              "device_model_ready": False, "integer_model_acceptance": False,
              "board_fps": None, "independent_capture_acceptance": False,
              "variants": {}}

    def check_input(_module, inputs):
        if list(inputs[0].shape) != frozen["input_shape"]:
            raise ValueError("evaluation input must be batch-one fixed square RGB")

    for label, bits in (("FP32", None), ("W8A32", 8), ("W4A32", 4)):
        candidate = copy.deepcopy(fused)
        errors = []
        if bits is not None:
            with torch.no_grad():
                for name, module in candidate.named_modules():
                    if not isinstance(module, torch.nn.Conv2d):
                        continue
                    original = module.weight.detach().numpy().copy()
                    q, scales = quantize_per_output_channel(original, bits)
                    restored = dequantize(q, scales)
                    module.weight.copy_(torch.from_numpy(restored))
                    error = original.astype(np.float64) - restored
                    errors.append({"name": name, "shape": list(q.shape),
                                   "quantized_sha256": hashlib.sha256(q.tobytes()).hexdigest(),
                                   "scale_sha256": hashlib.sha256(scales.tobytes()).hexdigest(),
                                   "max_abs_error": float(np.abs(error).max()),
                                   "mean_squared_error": float(np.mean(error**2)),
                                   "scale_min": float(scales.min()), "scale_max": float(scales.max())})
        candidate = candidate.to(device).eval()
        hook = candidate.register_forward_pre_hook(check_input)
        with torch.inference_mode():
            decoded, raw = candidate(images.to(device))
        if [list(t.shape) for t in raw] != frozen["detect_raw_shapes"] or list(decoded.shape) != frozen["detect_decoded_shape"]:
            raise ValueError("raw Detect contract changed")
        metrics = {}
        for split in ("val", "test"):
            save_dir = output / label / split
            save_dir.mkdir(parents=True, exist_ok=False)
            loader = create_dataloader(data[split], 320, 1, 32, False,
                                       pad=0.0, rect=False, workers=0, prefix=label + " " + split + ": ")[0]
            if len(loader.dataset) != manifest["split_counts"][split]:
                raise ValueError("dataset split image count changed")
            result, maps, maps50, speed = validation.run(
                data=copy.deepcopy(data), model=candidate, dataloader=loader,
                batch_size=1, imgsz=320, conf_thres=0.001, iou_thres=0.6,
                max_det=300, task=split, device="0", workers=0, half=False,
                verbose=False, save_txt=False, plots=False, save_dir=save_dir)
            entry = {"images": manifest["split_counts"][split],
                     "boxes": sum(manifest["class_counts"][split].values()),
                     "precision": float(result[0]), "recall": float(result[1]),
                     "map50": float(result[2]), "map50_95": float(result[3]),
                     "class_map50": [float(v) for v in maps50],
                     "class_map50_95": [float(v) for v in maps],
                     "pc_gpu_ms_per_image": dict(zip(("preprocess", "inference", "nms"), map(float, speed)))}
            if bits is not None:
                baseline = report["variants"]["FP32"]["metrics"][split]
                entry["delta_vs_fp32"] = {k: entry[k] - baseline[k] for k in ("map50", "map50_95")}
            metrics[split] = entry
            print("WEIGHT_PRECISION_SPLIT_DONE", label, split, entry["map50"], entry["map50_95"], flush=True)
        hook.remove()
        report["variants"][label] = {"weight_bits": bits, "layers": errors, "metrics": metrics}
        (output / "sensitivity.partial.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        del candidate, raw, decoded
        torch.cuda.empty_cache()
    if sha(model_path) != metadata["model_sha256"] or sha(manifest_path) != report["dataset_manifest_sha256"]:
        raise ValueError("model or dataset manifest changed during evaluation")
    report["source_sha256"] = {p.name: sha(p) for p in (Path(__file__), Path(__file__).with_name("weight_quantization.py"))}
    (output / "sensitivity.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("WEIGHT_PRECISION_SENSITIVITY_PASS", metadata["model_sha256"], "device_model_ready=False", flush=True)


if __name__ == "__main__":
    main()
