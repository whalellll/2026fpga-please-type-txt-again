"""Package the corner retraining task, contracts, and synthetic-only checks.

Does not read image datasets, checkpoints, live IPC, or device state.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/validation/picture-e42-integration-20261026"
SHA = lambda data: hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.drive.lower() != "e:":
        parser.error("Use a new private E directory")
    out.mkdir(parents=True, exist_ok=False)
    kit = out / "KIT"
    kit.mkdir()

    sources = {
        "START_HERE.md": DOCS / "model-corner-domain-r26-start-prompt-20261031.md",
        "current_contract.json": DOCS / "model-corner-domain-r26-contract-20261031.json",
        "tools/board_corner_domain_contract.py": ROOT / "scripts/board_corner_domain_contract.py",
        "tools/test_board_corner_domain_contract.py": ROOT / "scripts/test_board_corner_domain_contract.py",
        "provenance/package_builder.py": Path(__file__).resolve(),
    }
    payload = {name: path.read_bytes() for name, path in sources.items()}

    records = []
    for identity, split, digest in (("toy-train", "train", "a"), ("toy-dev", "dev", "b"), ("toy-blind", "blind", "c")):
        records.append({
            "id": identity, "split": split, "source": "synthetic_fixture_no_real_data",
            "capture_group": identity, "duplicate_cluster": identity,
            "root_image_sha256": digest * 64, "image_sha256": digest * 64,
            "background": "synthetic", "exposure": "synthetic",
        })
    split = {"schema": "board-corner-domain-split/1", "data_permission_reference": "Synthetic metadata only; grants no real data access", "records": records}
    truth = [[100, 100], [600, 100], [600, 500], [100, 500]]
    predictions = {"schema": "board-corner-predictions/1", "rows": [{
        "id": "toy-offset", "split": "dev", "width": 1280, "height": 720,
        "truth_pixel_centres": truth, "prediction_space": "normalized_pixel_centres",
        "prediction": [[(x + 3 + 0.5) / 1280, (y + 4 + 0.5) / 720] for x, y in truth],
        "strict_native_status": None,
    }, {
        "id": "toy-missing", "split": "blind", "width": 1280, "height": 720,
        "truth_pixel_centres": truth, "prediction": None,
        "prediction_space": "pixel_centres", "strict_native_status": None,
    }]}
    template = {
        "schema": "board-corner-training-return/1", "status": "TEMPLATE_NOT_RUN",
        "candidate_id": None, "baseline_checkpoint_sha256": None,
        "trained_checkpoint_sha256": None, "actual_runner_sha256": None,
        "split_manifest_sha256": None, "training_configuration_sha256": None,
        "environment": None, "data_permission_reference": None,
        "private_data_in_public_return": False, "files": [],
        "reports": {"corner_metrics": None, "product_ablation": None, "numerical_reference": None},
        "native_export_available": False, "board_tested": False,
    }
    for name, value in (("split.synthetic.json", split), ("predictions.synthetic.json", predictions), ("return_manifest.template.json", template)):
        payload["examples/" + name] = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    payload["TOOLS_README.md"] = """# 工具使用

这是数据清单与角点指标工具，不含训练器、checkpoint或真实照片。训练工作按START_HERE.md进行。
Python3.10或更高版本，仅使用标准库，无需在工程Python中安装torch。

在解压目录运行：

```text
python -B tools/test_board_corner_domain_contract.py -v
python -B tools/board_corner_domain_contract.py validate-split examples/split.synthetic.json
python -B tools/board_corner_domain_contract.py evaluate examples/predictions.synthetic.json
```

替换成真实清单时，输入和`--output`都应位于训练侧私有目录。输出目标必须尚不存在。
合成例子的开发样本四角均偏移3/4像素，误差应为5像素；盲测例子缺失预测，不得计成功。
清单检查不读取照片、不验证声明的来源真实性，也不会自动发现未标记的近重复。
`strict_native_status`是调用方提供的结果，工具不会代跑产品、确认棋子或产生整盘准确率。
provenance中的打包器仅供工程审计，训练侧无需执行。
""".encode("utf-8")

    def save(name, data):
        path = kit / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)

    for name, data in payload.items():
        save(name, data)

    checks = []
    for name, arguments in (
        ("tool-tests", ["tools/test_board_corner_domain_contract.py", "-v"]),
        ("split-example", ["tools/board_corner_domain_contract.py", "validate-split", "examples/split.synthetic.json"]),
        ("metrics-example", ["tools/board_corner_domain_contract.py", "evaluate", "examples/predictions.synthetic.json"]),
    ):
        process = subprocess.run([sys.executable, "-B", *arguments], cwd=kit, capture_output=True, timeout=30)
        log = process.stdout + process.stderr
        if process.returncode:
            (out / (name + "-FAILED.txt")).write_bytes(log)
            raise RuntimeError(name + " failed")
        if name == "split-example":
            report = json.loads(process.stdout)
            assert report["samples"] == {"train": 1, "dev": 1, "blind": 1} and not report["images_read"]
        elif name == "metrics-example":
            report = json.loads(process.stdout)
            assert abs(report["rows"][0]["max_corner_error_px"] - 5) < 1e-10
            assert report["summary"]["blind"]["missing_predictions"] == 1
            assert report["whole_board_accuracy"] is None and not report["native_status_independently_run"]
        key = "proof/" + name + ".txt"
        payload[key] = log
        save(key, log)
        checks.append({"name": name, "exit": process.returncode, "log_sha256": SHA(log)})

    manifest = {name: {"bytes": len(data), "sha256": SHA(data)} for name, data in payload.items()}
    manifest_data = (json.dumps({"schema": "corner-domain-task-package/1", "files": manifest,
        "manifest_self_excluded_outer_archive_hash_covers_it": True,
        "real_images_checkpoints_live_payloads_included": False}, indent=2) + "\n").encode()
    save("MANIFEST.json", manifest_data)
    archive = out / "xinyi-board-corner-domain-r26-20261031-r01.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as stream:
        for name, data in payload.items():
            stream.writestr(name, data)
        stream.writestr("MANIFEST.json", manifest_data)
    with zipfile.ZipFile(archive) as stream:
        assert stream.testzip() is None
        assert set(stream.namelist()) == set(payload) | {"MANIFEST.json"}
        for name, identity in manifest.items():
            data = stream.read(name)
            assert len(data) == identity["bytes"] and SHA(data) == identity["sha256"]
    receipt = {
        "status": "TRAINING_TASK_TOOLS_AND_ZIP_READBACK_PASS_NOT_TRAINED",
        "archive": str(archive), "bytes": archive.stat().st_size,
        "sha256": SHA(archive.read_bytes()), "members": len(payload) + 1,
        "checks": checks, "real_data_included": False,
        "trainer_or_checkpoint_included": False, "new_model_selected": False,
        "source_files": {str(path.relative_to(ROOT)): SHA(path.read_bytes()) for path in sources.values()},
    }
    (out / "package-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in receipt.items() if key not in ("source_files", "checks")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
