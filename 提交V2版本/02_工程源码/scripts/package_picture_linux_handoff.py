"""Create/verify a source-only Linux build handoff. No training data/weights,
release binaries, RTL, PDS, camera captures, tool caches or credentials.
"""
import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path


def package(repo, output):
    selected = {}
    suffixes = {".c", ".cpp", ".h", ".inc", ".patch", ".sh", ".py", ".md", ".txt", ".S", ".ld"}
    for directory in ("linux/vision", "linux/pikafish", "linux/voice", "linux/mac_accel", "linux/audio", "sw/xiangqi", "sw/video",
                      "sw/bootloader", "sw/mac_accel", "sw/pikafish_mlp_stage_b"):
        for path in (repo / directory).rglob("*"):
            if path.is_file() and path.suffix in suffixes and "__pycache__" not in path.parts:
                selected[path.relative_to(repo).as_posix()] = path
    explicit = ("AGENTS.md", "README.md", "VERSION", "linux/soc.dts", "linux/boot/soc.dtb",
                "linux/mac_accel/pango_mac_uapi.h", "linux/picture_roi.dts", "docs/PICTURE_INPUT.md",
                "scripts/build_picture_roi_kernel.ps1", "scripts/build_picture_roi_linux.ps1",
                "scripts/prepare_picture_roi_candidate.py", "scripts/test_picture_roi_cv.py",
                "scripts/make_picture_rootfs.ps1", "scripts/make_rootfs.ps1", "scripts/build_picture_loader.ps1",
                "scripts/serial_load_picture_ram.ps1", "scripts/serial_boot_v2_1_sd.ps1", "scripts/riscv_toolchain.ps1",
                "docs/validation/picture-roi-preparation-20261019/README.md",
                "docs/PICTURE_NEW_MODEL_CONTRACT.md", "docs/PICTURE_CHECKPOINT_20261018.md",
                "docs/BUILD.md", "docs/ARCHITECTURE.md", "docs/Validation.md", "docs/V2_1_BOARD_BOOT.md",
                "docs/OV5640_BOOTLOADER_CAMERA.md", "docs/CAMERA_SD_PNG.md",
                "docs/YOLOv5n_Model_Integration_TODO.md", "docs/Multi_Model_Resource_Plan.md",
                "docs/PICTURE_LINUX_BUILD_HANDOFF_20261017.md", "scripts/build_pikafish_rv32.ps1",
                "docs/validation/picture-interaction-20261017/README.md",
                "docs/validation/picture-interaction-20261017/host-tests.json",
                "scripts/prepare_picture_engine.py", "scripts/test_picture_candidate.py",
                "scripts/prepare_picture_candidate.py", "scripts/test_picture_model.py",
                "scripts/verify_picture_model.py", "scripts/test_picture_png.py",
                "scripts/test_picture_speech_assets.py", "scripts/generate_picture_speech.ps1")
    for name in explicit: selected[name] = repo / name
    local_evidence = repo / "docs/validation/picture-localbuild-20261017"
    if local_evidence.is_dir():
        for path in local_evidence.iterdir():
            if path.is_file() and path.suffix in {".md", ".json", ".txt", ".log"}:
                selected[path.relative_to(repo).as_posix()] = path
    for path in (repo / "linux/boot/v2_1_sd/rootfs_payloads/picture").rglob("*"):
        if path.is_file(): selected[path.relative_to(repo).as_posix()] = path
    selected["BUILD_ON_LINUX.md"] = repo / "docs/PICTURE_LINUX_BUILD_HANDOFF_20261017.md"
    blobs = {name: path.read_bytes() for name, path in sorted(selected.items())}
    for name in blobs:
        if name.endswith(".sh"): blobs[name] = blobs[name].replace(b"\r\n", b"\n")
    manifest = {"contract_version": 1, "scope": "Picture Linux source build handoff; NOT model or BoardRelease",
                "source_head": subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=repo, text=True).strip(),
                "source_branch": subprocess.check_output(("git", "branch", "--show-current"), cwd=repo, text=True).strip(),
                "board_validated": False,
                "shell_scripts_normalized_lf": True,
                "files": {name: {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}
                          for name, blob in blobs.items()}}
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, blob in blobs.items(): archive.writestr(name, blob)
        archive.writestr("handoff_manifest.json", manifest_bytes)
    with zipfile.ZipFile(output) as archive:
        if set(archive.namelist()) != set(blobs) | {"handoff_manifest.json"}:
            raise ValueError("handoff archive inventory mismatch")
        for name, rec in manifest["files"].items():
            blob = archive.read(name)
            if len(blob) != rec["bytes"] or hashlib.sha256(blob).hexdigest() != rec["sha256"]:
                raise ValueError("handoff round-trip mismatch: " + name)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256.txt").write_text(digest + "  " + output.name + "\n", encoding="utf-8")
    print("PICTURE_LINUX_HANDOFF_PASS files=%d bytes=%d sha256=%s path=%s" % (
        len(blobs), output.stat().st_size, digest, output))
    print("INPUT_MANIFEST_SHA256=" + hashlib.sha256(manifest_bytes).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    package(root, args.output or root / "artifacts/Picture_Linux_Build_20261017.zip")
