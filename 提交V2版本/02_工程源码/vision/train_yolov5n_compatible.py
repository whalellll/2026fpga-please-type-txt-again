"""Train a local candidate while preserving the frozen SoC YOLOv5n contract."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import time
from pathlib import Path

os.environ.setdefault("WANDB_MODE", "disabled")
os.environ.setdefault("WANDB_DISABLED", "true")
os.environ.setdefault("COMET_MODE", "DISABLED")
os.environ.setdefault("YOLOv5_AUTOINSTALL", "false")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--check-only", action="store_true", help="check graph and source capabilities without training")
    args = parser.parse_args()
    if args.epochs < 1 or args.batch < 1 or args.workers < 0:
        raise ValueError("invalid training dimensions")
    dataset, output, weights = (p.resolve() for p in (args.dataset, args.output, args.weights))
    if output.exists() and any(output.iterdir()):
        raise ValueError("training output must be empty; use upstream --resume to resume a saved run")

    # Avoid the upstream font URL redirect with Windows' existing Arial font.
    config_directory = output.parent / "yolo_config"
    config_directory.mkdir(parents=True, exist_ok=True)
    os.environ["YOLOV5_CONFIG_DIR"] = str(config_directory)
    local_font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/arial.ttf"
    if local_font.is_file() and not (config_directory / "Arial.ttf").exists():
        shutil.copy2(local_font, config_directory / "Arial.ttf")

    import torch
    import yaml
    import yolov5
    from export_layer_contract import build_manifest, MODEL_CONFIG
    from accelerator_compatibility import audit_layers, source_capabilities
    from model_m0_audit import sha256_file, validate_data_config
    from probe_model_m0 import probe_checkpoint

    if importlib.metadata.version("yolov5") != "7.0.14" or torch.__version__ != "2.5.1+cu124":
        raise ValueError("use the pinned yolov5 7.0.14 / torch 2.5.1+cu124 environment")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU required for this training run")
    validate_data_config(dataset / "chess14_320.yaml", dataset, dataset / "classes.txt")
    manifest = json.loads((dataset / "dataset_manifest.json").read_text())
    contract_path = Path(__file__).with_name("yolov5n_14_320_contract.json")
    frozen = json.loads(contract_path.read_text())
    torch.set_num_threads(4)
    actual = build_manifest()
    # Git checks this text file out as CRLF on Windows; compare the exact LF
    # canonical bytes used by the contract, after validating the ordered names.
    class_bytes = Path(__file__).with_name("dataset").joinpath("classes.txt").read_bytes()
    canonical_class_hash = hashlib.sha256(class_bytes.replace(b"\r\n", b"\n")).hexdigest()
    if canonical_class_hash != frozen["class_names_sha256"]:
        raise ValueError("ordered class file differs from frozen contract")
    for key in ("code_sha256", "config_sha256", "layers",
                "preprocess", "detect_raw_shapes", "detect_decoded_shape"):
        if actual[key] != frozen[key]:
            raise ValueError(f"installed graph differs from frozen contract: {key}")
    weight_hash, weight_bytes = sha256_file(weights)
    if weight_hash != "4f180cf23ba0717ada0badd6c685026d73d48f184d00fc159c2641284b2ac0a3":
        raise ValueError("initial checkpoint must be the verified local COCO yolov5n.pt")
    package_root = Path(yolov5.__file__).parent
    compatibility = audit_layers(actual["layers"], source_capabilities(Path(__file__).resolve().parents[1]))
    hyp = yaml.safe_load((package_root / "data/hyps/hyp.scratch-low.yaml").read_text())
    # Never mirror character glyphs; avoid shrinking already small pieces aggressively.
    hyp.update(lr0=0.001, warmup_bias_lr=0.01, hsv_h=0.01, hsv_s=0.3, hsv_v=0.3,
               scale=0.2, translate=0.05, fliplr=0.0, flipud=0.0, mosaic=0.25)
    output.mkdir(parents=True, exist_ok=True)
    hyp_file = output / "candidate_hyp.yaml"
    hyp_file.write_text(yaml.safe_dump(hyp, sort_keys=False), encoding="utf-8")
    settings = dict(data=str(dataset / "chess14_320.yaml"), cfg=str(MODEL_CONFIG),
                    weights=str(weights), hyp=str(hyp_file), imgsz=320,
                    batch_size=args.batch, epochs=args.epochs, workers=args.workers,
                    device="0", optimizer="AdamW", cos_lr=True, patience=35,
                    noautoanchor=True, seed=20261005, cache="ram",
                    project=str(output), name="run", exist_ok=False)
    provenance = {"schema_version": 1, "settings": settings,
                  "source_sha256": manifest["source_sha256"],
                  "dataset_sha256": manifest["dataset_sha256"],
                  "initial_checkpoint_sha256": weight_hash, "initial_checkpoint_bytes": weight_bytes,
                  "contract_sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
                  "code_sha256": actual["code_sha256"], "config_sha256": actual["config_sha256"],
                  "class_file_sha256": hashlib.sha256(class_bytes).hexdigest(),
                  "canonical_class_sha256": canonical_class_hash,
                  "torch_version": torch.__version__, "yolov5_version": "7.0.14",
                  "gpu": torch.cuda.get_device_name(0), "preprocess": manifest["preprocess"],
                  "current_accelerator": {key: compatibility[key] for key in (
                      "conv_count", "direct_conv_shape_count", "direct_conv_macs_percent",
                      "whole_model_conv_abi_ready", "device_model_ready", "dense_model_backend_implemented")},
                  "independent_capture_acceptance": False,
                  "board_acceptance": False, "quantization_acceptance": False,
                  "status": "preflight_only" if args.check_only else "training"}
    provenance_path = output / "training_manifest.json"
    provenance_path.write_text(json.dumps(provenance, indent=2) + "\n")
    print("YOLOV5N_TRAIN_PREFLIGHT_PASS",
          f"direct_conv_shapes={compatibility['direct_conv_shape_count']}/{compatibility['conv_count']}",
          "device_model_ready=False", flush=True)
    if args.check_only:
        return
    from yolov5.train import run
    started = time.perf_counter()
    try:
        options = run(**settings)
        best = Path(options.save_dir) / "weights/best.pt"
        metadata = probe_checkpoint(best)
        (output / "best_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
        provenance.update(status="trained_structure_pass", training_elapsed_s=round(time.perf_counter()-started, 3),
                          best_metadata=metadata)
        print("YOLOV5N_TRAIN_PASS", best, metadata["model_sha256"], flush=True)
    except BaseException as error:
        provenance.update(status="failed", error=repr(error))
        raise
    finally:
        provenance_path.write_text(json.dumps(provenance, indent=2) + "\n")


if __name__ == "__main__":
    main()
