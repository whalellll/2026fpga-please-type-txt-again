"""Verify the V2.1 release from timed board CoreMark and exact board images.

The V6.5 BoardRelease verifier has a different frequency-improvement contract.
This verifier never accepts RTL CoreMark as a substitute for board UART data.
"""

import argparse
import json
from pathlib import Path
import statistics
import zlib

from coremark_crc_reference import CrcReference, PINNED_CORE
from verify_board_release import (
    need, parse_uart, read, safe, sha, timestamp, timing_summary,
    validate_program_transcript,
)


RUN_ID = "5f802f47f8ad4907925af156b227ad21"
BITSTREAM_SHA = "a3f288b30991b111c3a840c03aae18694c748529ea57278c228b7d277c408b33"
LOADER_SHA = "861392887c0701ea789a3090468c7f8e674e4ee495b8c508e20e5ca6407f68ec"
SD_CONTRACT = {
    "brfw.bin": (266448, 0x8072B5C4),
    "Image": (7480792, 0xAEC00080),
    "brfs2.bin": (8227328, 0xB6F3CCE0),
    "br.dtb": (2335, 0xCF189F13),
    "pikafish.pff": (68122688, 0x80322636),
    "pikafish.atk": (34603072, 0xCBA1DD72),
}


def same_run(actual, expected, label):
    for field, value in expected.items():
        found = actual.get(field)
        if isinstance(value, float):
            need(isinstance(found, (float, int)) and abs(found - value) < 1e-9,
                 f"{label} differs: {field}")
        else:
            need(found == value, f"{label} differs: {field}")


def verify(root, manifest_path, host_gcc):
    root = Path(root).resolve()
    manifest_path = Path(manifest_path)
    if not manifest_path.is_absolute():
        manifest_path = safe(root, manifest_path.as_posix())
    need(manifest_path.is_file() and root / "docs/validation" in manifest_path.parents,
         "Release manifest must be under docs/validation")
    manifest = read(manifest_path)
    need(manifest.get("schema_version") == 1 and
         manifest.get("release_version") == "2.1" and
         manifest.get("evidence_mode") == "BoardRelease" and
         manifest.get("run_id") == RUN_ID and
         (root / "VERSION").read_text(encoding="utf-8-sig").strip() == "2.1",
         "Wrong V2.1 board release manifest")

    board_dir = root / "docs/validation/v2_1-board-coremark-5f802-20261015"
    need(manifest.get("coremark_directory") == board_dir.relative_to(root).as_posix(),
         "Board CoreMark evidence selection changed")
    record = read(safe(root, manifest["coremark_directory"] + "/manifest.json"))
    need(record["run_id"] == RUN_ID and
         record["status"] == "BOARD_COREMARK_3_PLUS_1_PASS_NOT_FORMAL_RELEASE",
         "Board session is not the captured 3+1 run")
    for name in ("README.md", "program.json", "program.txt", "result.json", "uart.txt"):
        need(sha(safe(board_dir, name)) == record["evidence_files_sha256"][name],
             f"Board evidence changed: {name}")
    need(record["evidence_files_sha256"]["program.txt"] ==
         record["evidence_files_sha256"]["program.log"] and
         record["evidence_files_sha256"]["uart.txt"] ==
         record["evidence_files_sha256"]["uart.log"],
         "Packaged board logs differ from captured raw logs")
    for name, expected in record["build_files_sha256"].items():
        need(sha(safe(root, name)) == expected, f"Board build identity changed: {name}")

    snapshot = read(safe(root, "artifacts/build_snapshot.json"))
    build = read(safe(root, "artifacts/build_evidence.json"))
    cpu = read(safe(root, "rtl/cpu/source.json"))
    clocks = read(safe(root, "config/clocks.json"))
    need(snapshot["run_id"] == build["run_id"] == RUN_ID and
         snapshot["release"] == build["release"] == "V2.1" and
         build["input_snapshot_sha256"] == sha(root / "artifacts/build_snapshot.json"),
         "FPGA build/run identity changed")
    need(build["timing"] == "All Constraints Met" and
         build["device"] == "PG2L100H-6-FBG676" and
         build["pds"] == "2022.2-SP6.4" and build["latches"] == 0 and
         all(build.get(flag) is True for flag in
             ("max_skew_verified", "cpu_ads_controls_verified", "icache_pad_ads_verified",
              "ordered_post_synthesis_stages_verified", "post_map_constraints_verified")),
         "Final FPGA implementation gate failed")
    for relative, expected in snapshot["inputs"].items():
        need(sha(safe(root, relative)) == expected, f"Frozen FPGA input changed: {relative}")
    for relative, expected in build["outputs"].items():
        need(sha(safe(root, relative)) == expected, f"Final FPGA output changed: {relative}")
    need(sha(root / "artifacts/soc_top.sbit") == BITSTREAM_SHA and
         cpu["cpu_version"] == "3.5.0" and
         cpu["sha256"] == snapshot["inputs"]["rtl/cpu/CoreTop.sv"] and
         cpu["source_worktree_dirty"] is False and
         clocks["cpu_hz"] == 59_400_000 and
         clocks["sys_hz"] == clocks["timebase_hz"] == 49_500_000,
         "CPU or clock identity changed")
    for name, expected in PINNED_CORE.items():
        need(snapshot["inputs"].get("sw/coremark/" + name) == expected,
             f"Official CoreMark source changed: {name}")
    timing_summary(root / "artifacts/timing_summary.txt")
    gate = read(safe(root, "artifacts/preflight_gate.json"))
    need(gate["status"] == "PASS" and gate["run_id"] == RUN_ID and
         gate["input_snapshot_sha256"] == sha(root / "artifacts/build_snapshot.json") and
         gate["resources"]["DRM"]["used"] <= 140 and
         gate["resources"]["DRM"]["capacity"] == 155,
         "Preflight resource gate failed")

    program = read(safe(board_dir, "program.json"))
    result = read(safe(board_dir, "result.json"))
    need(program["status"] == "PASS" and program["operation"] == "CRAM" and
         program["device_id"] == "0x00602899" and program["device_count"] == 1 and
         program["bitstream_sha256"] == BITSTREAM_SHA and
         program["program_log_sha256"] == sha(board_dir / "program.txt") and
         program["firmware_binary_sha256"] == sha(root / "artifacts/bootloader.bin") and
         program["cpu_rtl_sha256"] == cpu["sha256"] and
         program["pds_snapshot_sha256"] == sha(root / "artifacts/build_snapshot.json") and
         program["pds_build_evidence_sha256"] == sha(root / "artifacts/build_evidence.json") and
         program["pds_snapshot_run_id"] == RUN_ID,
         "CRAM programming receipt is for another build")
    log = (board_dir / "program.txt").read_text(encoding="utf-8-sig", errors="replace")
    assigned = program["assigned_bitstream_path"]
    need(assigned.endswith("/artifacts/soc_top.sbit") and
         "The ID value is: 0x00602899" in log and
         "The done bit is 1" in log,
         "JTAG target or DONE confirmation absent")
    validate_program_transcript(log, assigned)
    need(timestamp(build["completed_utc"]) <= timestamp(program["started_utc"]) <=
         timestamp(program["completed_utc"]) <= timestamp(result["captured_utc"]),
         "Board measurement predates final build/programming")
    need(result["status"] == "PASS" and result["board_acceptance"] is True and
         result["evidence_kind"] == "board_uart_capture" and
         result["bitstream"]["sha256"] == BITSTREAM_SHA and
         result["firmware"]["sha256"] == sha(root / "artifacts/bootloader.bin") and
         result["log_sha256"] == sha(board_dir / "uart.txt"),
         "Board CoreMark capture identity changed")
    with CrcReference(root, host_gcc) as oracle:
        runs = parse_uart((board_dir / "uart.txt").read_text(encoding="utf-8-sig"),
                          clocks["cpu_hz"], oracle)
    need(len(result["runs"]) == 4, "Board CoreMark run count changed")
    for parsed, reported in zip(runs, result["runs"]):
        same_run(reported, parsed, "Board CoreMark run")
        need(reported["validated"] is True and reported["compiler"] ==
             "riscv32-unknown-elf-gcc 16.2.0", "Board CoreMark validation/compiler changed")
    mean = statistics.mean(run["coremark_per_mhz"] for run in runs[:3])
    need(abs(result["summary"]["mean_coremark_per_mhz"] - mean) < 1e-10 and
         result["summary"]["performance_runs"] == 3 and
         result["summary"]["validation_runs"] == 1,
         "Board CoreMark summary changed")

    loader = safe(root, manifest["sd_loader"])
    need(sha(loader) == LOADER_SHA and loader.stat().st_size == 14696,
         "Tested SD loader binary is missing or changed")
    need(set(manifest["sd_files"]) == set(SD_CONTRACT), "SD payload inventory changed")
    for name, (size, crc) in SD_CONTRACT.items():
        content = safe(root, manifest["sd_files"][name]).read_bytes()
        need(len(content) == size and zlib.crc32(content) == crc,
             f"SD payload differs from board loader contract: {name}")
    gui_dir = root / "docs/validation/v2_1-board-gui-nonblocking-20261015"
    for index in (1, 2, 3):
        boot = read(safe(gui_dir, f"board_nonblocking_gui_20261015_run{index}.json"))
        need(boot["outcome"] == "pikafish_ready" and boot["loader_sha256"] == LOADER_SHA and
             boot["rootfs_sha256"] == sha(root / manifest["sd_files"]["brfs2.bin"]) and
             0 < boot["sd_loader_pass_s"] < boot["pikafish_ready_s"],
             f"Board GUI cold boot {index} is missing")
    for name in ("boot2", "boot3"):
        move = read(safe(gui_dir, f"board_nonblocking_move_20261015_{name}.json"))
        need(move["outcome"] == "pass" and move["bitstream_sha256"] == BITSTREAM_SHA and
             move["rootfs_sha256"] == sha(root / manifest["sd_files"]["brfs2.bin"]) and
             "red=h2e2 black=b9c7" in move["move_line"],
             f"Accelerated board move {name} is missing")
    visual = read(safe(gui_dir, "board_nonblocking_visual_20261015.json"))
    need(visual["status"] == "PASS" and visual["bitstream_sha256"] == BITSTREAM_SHA and
         visual["rootfs_sha256"] == sha(root / manifest["sd_files"]["brfs2.bin"]) and
         "mouse selection highlight" in visual["operator_report"] and
         "black engine response" in visual["operator_report"],
         "HDMI/mouse operator acceptance missing")
    print(f"V2_1_BOARD_RELEASE_PASS run_id={RUN_ID} board_runs=4 "
          f"mean_coremark_per_mhz={mean:.9f} gui_boots=3")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--host-gcc", required=True)
    args = parser.parse_args()
    verify(args.root, args.manifest, args.host_gcc)


if __name__ == "__main__":
    main()
