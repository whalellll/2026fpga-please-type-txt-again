"""Fail-closed, portable BoardRelease identity and CoreMark evidence checks.

Production/ShortPilot remain separate contracts. This verifier never turns a
short RTL run into a score. UART scores are recomputed from full CLINT ticks;
the host oracle is used exclusively for iteration-dependent CRC correctness.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import statistics
import subprocess

from coremark_crc_reference import CrcReference, PINNED_CORE

FLAGS = "-O2 -march=rv32ima_zicsr_zifencei -mabi=ilp32"
COMPILER = "riscv32-unknown-elf-gcc 16.2.0"
BASELINE = 5.070148251157226
CAMPAIGN_START = datetime(2026, 10, 8, 12, 55, 41, tzinfo=timezone.utc)
SESSION_FILES = {
    "uart.txt", "result.json", "program.json", "program.txt", "preflight.txt",
    "clock.json", "cpu_source.json", "fpga_input_snapshot.json",
    "fpga_build_evidence.json", "firmware.build.json", "firmware.bin",
    "bootrom.hex", "soc_top.sbit", "timing_summary.txt",
    "preflight_gate.json", "cpu_ads_controls.json", "cpu_sys_cdc_ads.json",
    "icache_pad_ads.json", "final_timing_report.txt", "final_timing_xml.xml", "pll_video.v", "soc.fdc",
}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_uart_pad_contract(cpu_ads, snapshot, snapshot_sha, vm_sha):
    """Portable summary recheck; no new session files or source dependencies.

    Full native connectivity is proved by the frozen checker at pre-PnR; this
    validates that exact same-run artifact and its complete mapping summary.
    """
    inputs = snapshot['inputs']
    if 'scripts/audit_uart_tx_pad_ads.py' not in inputs:
        return  # Historical snapshots keep their original, narrower scope.
    uart = cpu_ads.get('uart_tx_pad_contract')
    need(isinstance(uart, dict), 'UART TX pad ADS contract missing')
    expected = dict(schema=1, status='PASS', scope='MAPPED_UART_TX_WADDR_PADS', hierarchy='soc_top/u_local/u_tx',
                    run_id=snapshot['run_id'], input_snapshot_sha256=snapshot_sha, vm_sha256=vm_sha,
                    checker_sha256=inputs['scripts/audit_uart_tx_pad_ads.py'],
                    parser_sha256=inputs.get('scripts/audit_icache_pad_ads.py'),
                    uart_rtl_sha256=inputs.get('rtl/soc/uart_tx_fifo.v'), primitive='GTP_LUT6D',
                    init='CCCCCCCC_AAAAAAAA', preservation_attribute='PAP_DONT_TOUCH',
                    address_bits=4, upstream_ff_bits=4, memory_cells=4, data_bits=8, waddr_pins_checked=16)
    need(all(uart.get(key) == value for key, value in expected.items()), 'UART TX pad ADS identity/count differs')
    for field in ('checker_sha256', 'parser_sha256', 'uart_rtl_sha256', 'vm_sha256', 'module_sha256'):
        need(re.fullmatch('[0-9a-f]{64}', str(uart.get(field, ''))), 'UART TX pad ADS hash incomplete')
    need(cpu_ads.get('input_snapshot_sha256') == snapshot_sha and cpu_ads.get('input_snapshot_run_id') == snapshot['run_id'] and
         cpu_ads.get('netlist_sha256') == vm_sha, 'UART TX pad ADS is not from the same CPU/VM snapshot')
    need(uart.get('unique_drivers') is True and uart.get('bypass') is False and
         uart.get('post_pnr_physical_retention_proven') is False and uart.get('routed_hold_margin_proven') is False,
         'UART TX pad ADS proof boundary changed')
    pairs, memories = uart.get('pairs', []), uart.get('memories', [])
    need(len(pairs) == 2 and len(memories) == 4, 'UART TX pad ADS pair/RAM coverage incomplete')
    first_inputs = pairs[0].get('inputs', [])
    pointer = re.fullmatch(r'(wr_ptr|pad_address_in)\[0\]', str(first_inputs[0])) if len(first_inputs) == 2 else None
    need(pointer is not None, 'UART TX pad ADS write pointer mapping differs')
    pointer_bus = pointer[1]
    outputs = []
    for index, pair in enumerate(pairs):
        need(pair.get('pair') == index and pair.get('instance') == f'\\write_address_pad[{index}].u_hold_dual_lut' and
             pair.get('inputs') == [f'{pointer_bus}[{index*2}]', f'{pointer_bus}[{index*2+1}]'] and len(pair.get('outputs', [])) == 2,
             'UART TX pad ADS pair mapping differs')
        outputs += pair['outputs']
    need(len(set(outputs)) == 4 and all(isinstance(w, str) and re.fullmatch(r'[A-Za-z_][\w$]*(?:\[\d+\])?', w) and
         w.split('[')[0] not in ('wr_ptr', 'pad_address_in') for w in outputs), 'UART TX pad ADS outputs tied or bypassed')
    data, names, common_address = [], [], None
    for ram in memories:
        order = ram.get('waddr_low_to_high_pointer_bits', [])
        need(len(order) == 4 and all(type(x) is int for x in order) and sorted(order) == [0,1,2,3] and
             ram.get('primitive') == 'GTP_RAM32X2DP' and isinstance(ram.get('instance'), str) and ram['instance'] and
             len(ram.get('data_bits', [])) == 2, 'UART TX pad ADS RAM mapping incomplete')
        expected_address = "{1'b0," + ','.join(outputs[x] for x in reversed(order)) + '}'
        need(ram.get('waddr') == expected_address and (common_address is None or common_address == expected_address),
             'UART TX pad ADS RAM WADDR bypass or inconsistent permutation')
        common_address = expected_address
        data += ram['data_bits']; names.append(ram['instance'])
    need(len(set(names)) == 4 and all(type(x) is int for x in data) and sorted(data) == list(range(8)),
         'UART TX pad ADS FIFO data coverage incomplete')


def safe(root, relative):
    need(isinstance(relative, str) and relative and "\\" not in relative and ":" not in relative,
         "Unsafe evidence path")
    parts = PurePosixPath(relative)
    need(not parts.is_absolute() and all(p not in (".", "..") for p in parts.parts), "Unsafe evidence path")
    root = Path(root).resolve()
    path = root.joinpath(*parts.parts)
    for cursor in (path, *path.parents):
        need(not cursor.is_symlink() and not (cursor.exists() and getattr(cursor.stat(), "st_file_attributes", 0) & 0x400),
             f"Linked evidence path: {relative}")
        if cursor == root:
            break
    need(path.is_file() and root in path.resolve().parents, f"Missing or escaping evidence file: {relative}")
    return path


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def referenced(root, record):
    need(isinstance(record, dict) and set(record) == {"path", "sha256"}, "Evidence reference needs path and sha256")
    path = safe(root, record["path"])
    need(sha(path) == record["sha256"], f"Evidence reference hash changed: {record['path']}")
    return path


def timestamp(value):
    need(isinstance(value, str), "Missing evidence UTC timestamp")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    need(stamp.tzinfo is not None, "Evidence timestamp must have a timezone")
    return stamp.astimezone(timezone.utc)


def git_object_hash(kind, payload):
    return hashlib.sha1(kind.encode("ascii") + b" " + str(len(payload)).encode("ascii") + b"\0" + payload).hexdigest()


def validate_implementation(snapshot, expected_commit, root=None):
    """Replay Git commit/tree membership without needing a .git directory."""
    identity = snapshot.get("implementation_git", {})
    need(identity.get("schema") == 1 and identity.get("object_format") == "sha1" and
         identity.get("commit_sha1") == expected_commit and identity.get("all_frozen_inputs_match_commit") is True,
         "Missing or mismatched frozen Git implementation proof")
    commit = base64.b64decode(identity["commit_object_base64"], validate=True)
    need(git_object_hash("commit", commit) == expected_commit, "Git commit proof hash differs")
    match = re.match(rb"tree ([0-9a-f]{40})\n", commit)
    need(match is not None, "Git commit proof lacks root tree")
    root_tree = match[1].decode("ascii")
    trees = {}
    for oid, encoded in identity["tree_objects_base64"].items():
        payload = base64.b64decode(encoded, validate=True)
        need(git_object_hash("tree", payload) == oid, "Git tree proof hash differs")
        entries, offset = {}, 0
        while offset < len(payload):
            end = payload.find(b"\0", offset)
            need(end >= offset and end + 21 <= len(payload), "Malformed Git tree proof")
            mode, name = payload[offset:end].split(b" ", 1)
            name = name.decode("utf-8")
            need(name not in entries and name not in ("", ".", "..") and "/" not in name and "\\" not in name, "Invalid Git tree name")
            entries[name] = (mode, payload[end + 1:end + 21].hex())
            offset = end + 21
        trees[oid] = entries
    blobs = identity["input_blob_sha1"]
    need(set(blobs) == set(snapshot["inputs"]), "Git proof input inventory differs")
    for relative, blob in blobs.items():
        tree, parts = root_tree, relative.split("/")
        for index, name in enumerate(parts):
            need(tree in trees and name in trees[tree], f"Git proof omits input: {relative}")
            mode, oid = trees[tree][name]
            if index < len(parts) - 1:
                need(mode == b"40000", "Git input ancestor is not a tree")
                tree = oid
        need(mode in (b"100644", b"100755") and oid == blob, f"Git input membership differs: {relative}")
        if root is not None:
            path = safe(root, relative)
            need(git_object_hash("blob", path.read_bytes()) == blob and sha(path) == snapshot["inputs"][relative],
                 f"Frozen input differs from Git implementation commit: {relative}")


def regression_test_paths(root):
    """Stable test implementation inputs, excluding runtime output and docs."""
    extensions = {".ps1", ".py", ".cs", ".c", ".h", ".tcl", ".sh", ".ld", ".s", ".sv", ".v", ".vh", ".hex", ".json"}
    root = Path(root)
    return {path.relative_to(root).as_posix() for folder in ("scripts", "sim")
            for path in (root / folder).rglob("*") if path.is_file() and
            path.suffix.lower() in extensions and "__pycache__" not in path.parts and
            not re.fullmatch(r"scripts/pds_[^/]*_run\.tcl", path.relative_to(root).as_posix(), re.IGNORECASE) and
            path.relative_to(root).as_posix().lower() != "sim/linux_capability.hex"}


def validate_regression(regression, snapshot, cpu_sha, transcript, stderr, tests_root):
    need(regression.get("schema_version") == 1 and regression.get("status") == "PASS" and
         type(regression.get("exit_code")) is int and regression["exit_code"] == 0 and
         regression.get("marker") == "SOC_ALL_TESTS_PASS" and regression.get("cpu_rtl_sha256") == cpu_sha,
         "Current complete RTL regression required")
    need(CAMPAIGN_START <= timestamp(regression["started_utc"]) <= timestamp(regression["completed_utc"]) <=
         timestamp(snapshot["started_utc"]), "Regression must finish in this campaign before the final snapshot")
    need(sha(transcript) == regression["transcript"]["sha256"] and sha(stderr) == regression["stderr"]["sha256"],
         "Regression stdout/stderr hash changed")
    need(len(re.findall(r"^SOC_ALL_TESTS_PASS[ \t]*$", Path(transcript).read_text(encoding="utf-8-sig", errors="replace").replace("\r", ""),
                        re.MULTILINE)) == 1, "RTL regression transcript requires one complete success marker")
    needed_sources = {name: digest for name, digest in snapshot["inputs"].items() if not name.startswith("artifacts/")}
    need(regression.get("source_files_sha256") == needed_sources, "Regression source/configuration differs from final snapshot")
    tests = regression.get("test_files_sha256")
    need(isinstance(tests, dict) and set(tests) == regression_test_paths(tests_root) and
         {"scripts/run_all_tests.ps1", "scripts/run_release_regression.ps1", "scripts/bounded_process.cs",
          "scripts/verify_board_release.py"} <= set(tests), "Regression test inventory is incomplete or changed")
    for relative, expected in tests.items():
        need(sha(safe(tests_root, relative)) == expected, f"Regression test implementation changed: {relative}")


def one(text, pattern, label):
    found = re.findall(pattern, text, re.MULTILINE)
    need(len(found) == 1, f"Expected exactly one {label}, got {len(found)}")
    return found[0]


def parse_uart(text, hz, oracle):
    text = text.replace("\r", "")
    need(not re.search(r"COREMARK_FAIL|ERROR!|Errors detected|Cannot validate operation", text), "UART contains failure")
    bodies = re.findall(r"^CPU_HZ=(\d+)[ \t]*\n(.*?)^COREMARK_DONE[ \t]*(?:\n|$)", text, re.MULTILINE | re.DOTALL)
    need(len(bodies) == 4 and len(re.findall(r"^CPU_HZ=", text, re.MULTILINE)) == 4 and
         len(re.findall(r"^COREMARK_DONE[ \t]*$", text, re.MULTILINE)) == 4, "Exactly consecutive performance 3 + validation 1 required")
    runs = []
    for index, (reported_hz, body) in enumerate(bodies):
        mode = "performance" if index < 3 else "validation"
        need(int(reported_hz) == hz, "UART CPU clock differs from loaded build")
        for label in ("SYS_HZ", "TIMEBASE_HZ"):
            need(int(one(body, rf"^{label}=(\d+)[ \t]*$", label)) == 49_500_000, "SYS/TIMEBASE must stay 49.5 MHz")
        need(one(body, r"^COREMARK_MODE=(\w+)[ \t]*$", "mode") == mode, "Wrong run order/seed mode")
        need(one(body, r"^Compiler flags\s*:\s*(.+)$", "flags").strip() == FLAGS, "CoreMark flags changed")
        need(one(body, r"^Compiler version\s*:\s*(.+)$", "compiler").strip() == COMPILER, "CoreMark compiler changed")
        need(int(one(body, r"^CoreMark Size\s*:\s*(\d+)[ \t]*$", "workload")) == 666, "CoreMark workload changed")
        ticks = int(one(body, r"^PORT_TICKS64\s*:\s*(\d+)[ \t]*$", "64-bit ticks"))
        low_ticks = int(one(body, r"^Total ticks\s*:\s*(\d+)[ \t]*$", "official ticks"))
        iterations = int(one(body, r"^Iterations\s*:\s*(\d+)[ \t]*$", "iterations"))
        need(ticks >= 495_000_000 and 1 <= iterations <= 1_000_000, "Run shorter than ten seconds or invalid iterations")
        need(low_ticks == ticks % (1 << 32), "Full/official ticks disagree")
        printed_seconds = float(one(body, r"^Total time \(secs\):\s*([0-9.]+)[ \t]*$", "printed seconds"))
        need(abs(printed_seconds - ticks / 49_500_000) <= .000002, "Printed duration disagrees with full ticks")
        for marker in ("COREMARK_PASS", "Correct operation validated. See readme.txt for run and reporting rules."):
            one(body, "^" + re.escape(marker) + r"[ \t]*$", marker)
        expected = dict(oracle.get(mode, iterations))
        expected["seedcrc"] = "e9f5" if mode == "performance" else "18f2"
        crcs = {}
        for label, value in expected.items():
            actual = one(body, "^" + re.escape(label) + r"\s*:\s*0x([0-9a-fA-F]{4})[ \t]*$", label).lower()
            need(actual == value, f"Wrong CRC {mode}/{iterations}/{label}: {actual}, expected {value}")
            crcs[label] = actual
        runs.append(dict(run=index + 1, mode=mode, cpu_hz=hz, sys_hz=49_500_000,
                         timebase_hz=49_500_000, ticks=ticks, iterations=iterations,
                         duration_seconds=ticks / 49_500_000,
                         iterations_per_second=iterations * 49_500_000 / ticks,
                         coremark_per_mhz=iterations * 49_500_000 * 1_000_000 / (ticks * hz), crc=crcs))
    return runs


def timing_summary(path):
    text = Path(path).read_text(encoding="utf-8-sig").replace("\r", "")
    need(text.lstrip().startswith("Design Summary : All Constraints Met."), "Final STA did not pass")
    for corner in ("Slow", "Fast"):
        for kind in ("Setup", "Hold", "Recovery", "Removal", "Minimum Pulse Width"):
            heading = f"{kind} Summary({corner} Corner):"
            need(text.count(heading) == 1, f"Missing/duplicate timing table {heading}")
            section = text.split(heading, 1)[1]
            match = re.search(r"^-{10,}\s*\n(.*?)^={10,}", section, re.MULTILINE | re.DOTALL)
            need(match is not None, f"Incomplete timing table {heading}")
            rows = [line.split() for line in match[1].splitlines() if line.strip()]
            need(rows, f"Empty timing table {heading}")
            offset = 1 if kind == "Minimum Pulse Width" else 2
            for row in rows:
                need(len(row) == offset + 4, f"Malformed timing row {row}")
                need(float(row[offset]) >= 0 and float(row[offset + 1]) == 0 and int(row[offset + 2]) == 0 and int(row[offset + 3]) > 0,
                     f"Timing violation {heading}: {row}")
            if kind in ("Setup", "Hold"):
                for clock in ("cpu_clk", "sys_clk"):
                    need(any(row[:2] == [clock, clock] for row in rows), f"Missing {clock} {heading}")


def validate_program_transcript(log, assigned):
    """PDS prints a begin and a success line for each completed operation."""
    need(not re.search(r"(?im)^\s*E:\s|COMMAND\[Program\]\s+execute\s+fail", log),
         "CRAM tool reported a programming error")
    need("COMMAND[Program] execute successfully" in log and "The done bit is 1" in log,
         "CRAM tool did not report successful loading")
    operations = ("cfg_scan_chain", f"cfg_assign_file -file {assigned} -device_index 0",
                  "cfg_program -device_index 0", "cfg_disconnect")
    expected = ["Executing : " + operation + suffix
                for operation in operations for suffix in ("", " successfully.")]
    # Select all occurrences of these operations, including unexpected paths,
    # devices, repeats and failure suffixes; compare complete lines, not prefixes.
    actual = [line.strip() for line in log.splitlines() if re.match(
        r"^\s*Executing\s*:\s*cfg_(?:scan_chain|assign_file|program|disconnect)(?:\s|$)", line)]
    need(actual == expected,
         "Program transcript does not preserve scan/assign/program/disconnect identity")


def validate_session(path, oracle, campaign_start, expected_cpu_version, expected_hz=None):
    session = read(path)
    need(session.get("schema_version") == 1 and session.get("evidence_kind") == "board_coremark_session" and
         session.get("status") == "BOARD_COREMARK_3_PLUS_1_PASS", "Not a current board session")
    directory = Path(path).parent
    hashes = session.get("files_sha256", {})
    need(set(hashes) == SESSION_FILES, "Board session file inventory differs")
    for name, expected in hashes.items():
        need(sha(safe(directory, name)) == expected, f"Board session file hash changed: {name}")
    load = lambda name: read(directory / name)
    clock, source, snapshot, build, fw, program, result = [load(name) for name in
        ("clock.json", "cpu_source.json", "fpga_input_snapshot.json", "fpga_build_evidence.json",
         "firmware.build.json", "program.json", "result.json")]
    hz = clock["cpu_hz"]
    need(expected_hz is None or hz == expected_hz, "Wrong board session frequency")
    need(clock["sys_hz"] == clock["timebase_hz"] == 49_500_000, "Session SYS/TIMEBASE changed")
    need(clock["input_hz"] == 27_000_000 and clock["pll_vco_hz"] == 891_000_000 and
         hz == (891_000_000 + clock["cpu_divisor"] // 2) // clock["cpu_divisor"], "PLL intent does not derive the reported frequency")
    pll = (directory / "pll_video.v").read_text(encoding="utf-8-sig")
    need(re.search(r"parameter integer CPU_DIVISOR = " + str(clock["cpu_divisor"]) + r"\b", pll) and
         re.search(r"STATIC_RATIO3\s*=\s*CPU_DIVISOR", pll) and re.search(r"\.STATIC_RATIO3\s*\(\s*STATIC_RATIO3\s*\)", pll),
         "Loaded PLL divider is not connected to the checked CPU ratio")
    need(source["cpu_version"] == expected_cpu_version and source["isa"] == "rv32ima_zicsr_zifencei" and
         source["compressed_instructions"] is False and source.get("source_worktree_dirty") is False,
         "Session CPU is not the committed release profile")
    need(build["run_id"] == snapshot["run_id"] and build["input_snapshot_sha256"] == hashes["fpga_input_snapshot.json"], "PDS snapshot/run identity differs")
    need(build["release"] == snapshot["release"] == "V6.5", "Board PDS build is not the current release version")
    need(timestamp(snapshot["started_utc"]) >= campaign_start, "Historical PDS snapshot cannot prove this release")
    need(build["timing"] == "All Constraints Met" and build["device"] == "PG2L100H-6-FBG676" and build["pds"] == "2022.2-SP6.4", "Wrong final PDS target/acceptance")
    for flag in ("max_skew_verified", "cpu_ads_controls_verified", "icache_pad_ads_verified", "ordered_post_synthesis_stages_verified", "post_map_constraints_verified"):
        need(build.get(flag) is True, f"Missing final FPGA gate: {flag}")
    need(build.get("latches") == 0 and build.get("max_skew_groups") == 10 and build.get("max_skew_rows") == 20, "Latch/CDC gate changed")
    input_bindings = {"clock.json": "config/clocks.json", "cpu_source.json": "rtl/cpu/source.json",
                      "firmware.build.json": "artifacts/bootloader.build.json", "firmware.bin": "artifacts/bootloader.bin", "bootrom.hex": "artifacts/bootrom.hex",
                      "pll_video.v": "rtl/video/pll_video.v", "soc.fdc": "pds/soc.fdc"}
    for local, original in input_bindings.items():
        need(snapshot["inputs"].get(original) == hashes[local], f"Frozen board input differs: {original}")
    need(snapshot["inputs"].get("rtl/cpu/CoreTop.sv") == source["sha256"], "CPU RTL not bound to snapshot")
    for name, expected in PINNED_CORE.items():
        need(snapshot["inputs"].get("sw/coremark/" + name) == expected, "Frozen official CoreMark algorithm changed")
    for local, original in (("soc_top.sbit", "artifacts/soc_top.sbit"), ("timing_summary.txt", "artifacts/timing_summary.txt")):
        need(build["outputs"].get(original) == hashes[local], f"Final PDS output differs: {original}")
    for name in ("preflight_gate.json", "cpu_ads_controls.json", "cpu_sys_cdc_ads.json", "icache_pad_ads.json", "final_timing_report.txt", "final_timing_xml.xml"):
        need(build["outputs"].get("artifacts/" + name) == hashes[name], f"Same-run FPGA gate hash differs: {name}")
    gate = load("preflight_gate.json")
    need(gate["status"] == "PASS" and gate["run_id"] == snapshot["run_id"] and
         gate["input_snapshot_sha256"] == hashes["fpga_input_snapshot.json"], "ADS preflight belongs to another build")
    for resource, capacity in (("LUT", 66600), ("FF", 133200), ("LUTRAM", 19900), ("DRM", 155)):
        item = gate["resources"][resource]
        need(item["capacity"] == capacity and 0 <= item["used"] <= (140 if resource == "DRM" else capacity), f"Resource gate exceeded: {resource}")
    need(load("cpu_ads_controls.json")["status"] == "PASS" and load("icache_pad_ads.json")["status"] == "PASS", "ADS controls were not retained")
    validate_uart_pad_contract(load('cpu_ads_controls.json'), snapshot, hashes['fpga_input_snapshot.json'],
                               build.get('report_hashes', {}).get('pds/synthesize/soc_top_syn.vm'))
    need(fw["binary_sha256"] == hashes["firmware.bin"] and fw["coremark_iterations"] == 0 and
         fw["coremark_contract"]["preprocessed_macros"]["ITERATIONS"] == "0", "Board firmware is not production automatic calibration")
    contract = fw["coremark_contract"]
    need(contract["total_data_size_bytes"] == 2000 and contract["timebase_hz"] == 49500000 and
         contract["runtime_performance_seed"] == [0, 0, 102] and contract["runtime_validation_seed"] == [13333, 13333, 102], "CoreMark workload or seeds changed")
    for name, expected in {"TOTAL_DATA_SIZE": "2*1000", "VALIDATION_RUN": "0", "PERFORMANCE_RUN": "(!VALIDATION_RUN)",
                           "PROFILE_RUN": "0", "CORE_CLOCKS_PER_SEC": "49500000ULL", "SEED_METHOD": "SEED_VOLATILE", "MULTITHREAD": "1"}.items():
        need(contract["preprocessed_macros"].get(name) == expected, f"CoreMark compile contract changed: {name}")
    need((fw["compiler_target"], fw["compiler_version"], fw["march"], fw["abi"]) ==
         ("riscv32-unknown-elf", "16.2.0", "rv32ima_zicsr_zifencei", "ilp32"), "Board target compiler changed")
    commands = [command for command in fw["build_commands"] if command["kind"] == "compile_coremark"]
    need(len(commands) == 6, "CoreMark compilation provenance is incomplete")
    for command in commands:
        relevant = [arg for arg in command["argv"] if re.fullmatch(r"-O\S+|-march=\S+|-mabi=\S+", arg)]
        need(sorted(relevant) == sorted(FLAGS.split()), "CoreMark compiler argv violates fixed flags")
    words = (directory / "bootrom.hex").read_text(encoding="ascii").splitlines()
    need(len(words) == 32768 and all(re.fullmatch("[0-9a-fA-F]{8}", word) for word in words), "Incomplete ROM image")
    rom = b"".join(int(word, 16).to_bytes(4, "little") for word in words)
    binary = (directory / "firmware.bin").read_bytes()
    need(rom[:len(binary)] == binary and not any(rom[len(binary):]), "ROM does not contain the captured firmware")
    need(program.get("schema_version") == 1 and program.get("evidence_kind") == "volatile_cram_program" and program.get("status") == "PASS" and
         program.get("operation") == "CRAM" and program.get("device") == "PG2L100H" and program.get("device_id") == "0x00602899" and
         program.get("device_count") == 1 and program.get("device_index") == 0, "Missing fresh unique target CRAM load")
    for field, expected in {
        "bitstream_sha256": hashes["soc_top.sbit"], "firmware_binary_sha256": hashes["firmware.bin"],
        "cpu_rtl_sha256": source["sha256"], "cpu_source_manifest_sha256": hashes["cpu_source.json"],
        "pds_snapshot_run_id": snapshot["run_id"], "pds_snapshot_sha256": hashes["fpga_input_snapshot.json"],
        "pds_build_evidence_sha256": hashes["fpga_build_evidence.json"],
        "program_log_sha256": hashes["program.txt"], "preflight_log_sha256": hashes["preflight.txt"],
    }.items():
        need(program.get(field) == expected, f"CRAM identity mismatch: {field}")
    need(campaign_start <= timestamp(build["completed_utc"]) <= timestamp(program["started_utc"]) <=
         timestamp(program["completed_utc"]) <= timestamp(result["captured_utc"]) <= timestamp(session["created_utc"]), "Board capture predates final build/load/campaign")
    for name in ("program.txt", "preflight.txt"):
        log = (directory / name).read_text(encoding="utf-8-sig", errors="replace")
        need(len(re.findall(r"(?im)^\s*PG2L100H\s*$", log)) == 1 and
             len(re.findall(r"(?im)^\s*The ID value is:\s*0x00602899\s*$", log)) == 1 and
             len(re.findall(r"(?im)^\s*This device configure situation \(done bit\):\s*[01]\s*$", log)) == 1,
             f"JTAG scan does not identify exactly one expected device: {name}")
        need("Executing : cfg_scan_chain successfully." in log and
             "Executing : cfg_read_device_property -mode 0 -device_index 0 successfully." in log, "Incomplete JTAG scan")
    log = (directory / "program.txt").read_text(encoding="utf-8-sig", errors="replace")
    assigned = program.get("assigned_bitstream_path", "")
    need(re.fullmatch(r"[A-Za-z]:/[A-Za-z0-9._/-]+\.sbit", assigned), "Missing exact programmed bitstream assignment")
    validate_program_transcript(log, assigned)
    need(result.get("status") == "PASS" and result.get("evidence_kind") == "board_uart_capture" and result.get("board_acceptance") is True,
         "Offline or failed capture is not board evidence")
    need(result["log_sha256"] == hashes["uart.txt"] and result["bitstream"]["sha256"] == hashes["soc_top.sbit"] and
         result["firmware"]["sha256"] == hashes["firmware.bin"], "Measurement artifact identity differs")
    runs = parse_uart((directory / "uart.txt").read_text(encoding="utf-8-sig"), hz, oracle)
    need(len(result["runs"]) == 4, "Measurement result lost runs")
    for parsed, recorded in zip(runs, result["runs"]):
        for field, expected in parsed.items():
            if isinstance(expected, float):
                need(abs(recorded[field] - expected) < 1e-10, f"Computed board metric differs: {field}")
            else:
                need(recorded[field] == expected, f"Recorded UART result differs: {field}")
    timing_summary(directory / "timing_summary.txt")
    scores = [run["coremark_per_mhz"] for run in runs[:3]]
    return {"cpu_hz": hz, "cpu_rtl_sha256": source["sha256"], "cpu_commit": source["source_reference_commit"],
            "cpu_source_manifest_sha256": hashes["cpu_source.json"], "cpu_generator_source_sha256": source["generator_source_sha256"],
            "snapshot_sha256": hashes["fpga_input_snapshot.json"], "build_sha256": hashes["fpga_build_evidence.json"],
            "bitstream_sha256": hashes["soc_top.sbit"], "runs": runs,
            "mean_coremark": statistics.mean(run["iterations_per_second"] for run in runs[:3]),
            "mean_coremark_per_mhz": statistics.mean(scores), "median_coremark_per_mhz": statistics.median(scores),
            "minimum_coremark_per_mhz": min(scores), "maximum_coremark_per_mhz": max(scores)}


def validate_release(root, manifest_path, oracle):
    root = Path(root)
    manifest = read(manifest_path)
    soc_version = (root / "VERSION").read_text(encoding="utf-8-sig").strip()
    cpu_source = json.loads((root / "rtl" / "cpu" / "source.json").read_text(encoding="utf-8-sig"))
    cpu_version = cpu_source["cpu_version"]
    need(manifest.get("schema_version") == 1 and manifest.get("evidence_mode") == "BoardRelease" and
         manifest.get("release_version") == soc_version and manifest.get("cpu_version") == cpu_version, "Wrong explicit release manifest/version/mode")
    need((root / "VERSION").read_text(encoding="utf-8-sig").strip() == manifest["release_version"], "Manifest is for another SoC version")
    start = timestamp(manifest["campaign_started_utc"])
    need(start == CAMPAIGN_START, "Wrong release campaign start (historical evidence forbidden)")
    for field in ("cpu_implementation_commit", "soc_implementation_commit"):
        need(re.fullmatch("[0-9a-f]{40}", manifest.get(field, "")), f"Missing implementation identity: {field}")
    final_path = referenced(root, manifest["final_session"])
    control_path = referenced(root, manifest["same_frequency_session"])
    final = validate_session(final_path, oracle, start, manifest["cpu_version"])
    control = validate_session(control_path, oracle, start, manifest["cpu_version"], 59_400_000)
    need(final["cpu_rtl_sha256"] == control["cpu_rtl_sha256"] and
         final["cpu_commit"] == control["cpu_commit"] == manifest["cpu_implementation_commit"], "Same-frequency control used another CPU implementation")
    need(final["cpu_hz"] > 59_400_000, "Final CPU clock must exceed 59.4 MHz")
    need(final["mean_coremark_per_mhz"] >= BASELINE * 1.01, "Final-frequency CoreMark/MHz improvement is below 1 percent")
    snapshot = read(root / "artifacts/build_snapshot.json")
    validate_implementation(snapshot, manifest["soc_implementation_commit"], root)
    build = read(root / "artifacts/build_evidence.json")
    for relative, expected in snapshot["inputs"].items():
        need(sha(safe(root, relative)) == expected, f"Final frozen input changed: {relative}")
    for relative, expected in build["outputs"].items():
        need(sha(safe(root, relative)) == expected, f"Final FPGA output changed: {relative}")
    need(final["snapshot_sha256"] == sha(root / "artifacts/build_snapshot.json") and
         final["build_sha256"] == sha(root / "artifacts/build_evidence.json") and
         final["bitstream_sha256"] == sha(root / "artifacts/soc_top.sbit"), "Final board session is not the delivered FPGA build")
    pilot_path = referenced(root, manifest["short_pilot"])
    validate_short_pilot(pilot_path, final_path, final, oracle, start)
    regression_path = referenced(root, manifest["rtl_regression"])
    regression = read(regression_path)
    validate_regression(regression, snapshot, final["cpu_rtl_sha256"], referenced(root, regression["transcript"]),
                        referenced(root, regression["stderr"]), root)
    return {"status": "BOARD_RELEASE_PASS", "release_version": manifest["release_version"],
            "baseline_coremark_per_mhz": BASELINE, "threshold_coremark_per_mhz": BASELINE * 1.01,
            "improvement_percent": (final["mean_coremark_per_mhz"] / BASELINE - 1) * 100,
            "final": final, "same_frequency": control,
            "limitations": ["CoreMark/console board acceptance; Linux and all-peripheral acceptance are not implied.",
                            "Configured PLL and loaded image provenance; no independent frequency-meter measurement."]}


def validate_short_pilot(pilot_path, final_path, final, oracle, start):
    pilot = read(pilot_path)
    need(pilot.get("evidence_kind") == "short_pilot" and pilot.get("status") == "RTL_SHORT_PILOT_ESTIMATE_NOT_A_SCORE_NOT_BOARD" and
         pilot.get("formal_coremark_score_valid") is False and pilot.get("board_acceptance") is False and
         timestamp(pilot["created_utc"]) >= start, "Current short RTL pilot required; historical/Long claims rejected")
    need(pilot["cpu_rtl_sha256"] == final["cpu_rtl_sha256"] and pilot["pds_snapshot_sha256"] == final["snapshot_sha256"] and
         pilot["released_bitstream_sha256"] == final["bitstream_sha256"], "Short RTL is not bound to the final CPU/build")
    for relative, expected in pilot["files_sha256"].items():
        need(sha(safe(pilot_path.parent, relative)) == expected, f"Short RTL evidence changed: {relative}")
    directory = pilot_path.parent
    summary = read(directory / "summary.json")
    need(summary["status"] == "PILOT_ONLY_NOT_A_SCORE" and summary["kind"] == "Pilot" and
         summary["cpu_hz"] == final["cpu_hz"] and len(summary["cases"]) == 2 and
         summary["run_plan"] == ["performance", "validation"], "Invalid current RTL pilot plan")
    for index, mode in enumerate(("performance", "validation")):
        name = f"run0{index + 1}-{mode}"
        result = read(directory / (name + ".json"))
        log_path = safe(directory, name + ".uart.txt")
        log = log_path.read_text(encoding="utf-8-sig").replace("\r", "")
        need(result["status"] == "PILOT_PASS_NOT_A_SCORE" and result["kind"] == "pilot" and result["iterations"] == 10 and
             result["cpu_rtl_sha256"] == final["cpu_rtl_sha256"] and result["cpu_hz"] == final["cpu_hz"] and
             0 < result["ticks"] < 495_000_000 and result["timebase_hz"] == result["sys_hz"] == 49_500_000 and
             result["log_sha256"] == sha(log_path) and result["timer_stimulus_scale_during_command"] == 1,
             "Invalid short RTL result")
        need("COREMARK_FAIL" in log and "COREMARK_PASS" not in log and
             "ERROR! Must execute for at least 10 secs for a valid result!" in log, "Short RTL was incorrectly accepted as a score")
        need(int(one(log, r"^PORT_TICKS64\s*:\s*(\d+)$", "pilot ticks")) == result["ticks"] and
             one(log, r"^COREMARK_MODE=(\w+)$", "pilot mode") == mode and
             int(one(log, r"^Iterations\s*:\s*(\d+)$", "pilot iterations")) == 10, "Pilot UART/result mismatch")
        for label, expected in oracle.get(mode, 10).items():
            need(one(log, "^" + re.escape(label) + r"\s*:\s*0x([0-9a-f]{4})$", label) == expected and
                 result["crc"][label] == expected, "Pilot CRC mismatch")
    final_snapshot = read(final_path.parent / "fpga_input_snapshot.json")
    model = read(directory / "verilator_model.json")
    need(sha(directory / "verilator_model.exe") == model["model_sha256"] == pilot["verilator_model_sha256"], "Pilot model identity changed")
    for relative, expected in model["source_files"].items():
        if relative in final_snapshot["inputs"]:
            need(final_snapshot["inputs"][relative] == expected, "Pilot model differs from the final FPGA input")


def export_receipt(root, manifest_path, result, destination):
    """Export only after the full source-tree validation has succeeded."""
    root = Path(root)
    destination = Path(destination)
    need(not destination.exists(), "Receipt export requires a new directory")
    destination.mkdir(parents=True)
    manifest = read(manifest_path)
    soc_version = (root / "VERSION").read_text(encoding="utf-8-sig").strip()
    cpu_version = read(root / "rtl/cpu/source.json")["cpu_version"]
    need(manifest.get("release_version") == soc_version and manifest.get("cpu_version") == cpu_version,
         "Receipt export version differs from the validated source tree")
    references = {}
    for field, folder in (("final_session", "final"), ("same_frequency_session", "control"), ("short_pilot", "short")):
        source = referenced(root, manifest[field])
        record = read(source)
        names = set(record["files_sha256"]) | {source.name}
        for name in names:
            target = destination / folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(safe(source.parent, name), target)
        references[field] = {"path": folder + "/" + source.name, "sha256": sha(source)}
    for relative in ("scripts/verify_board_release.py", "scripts/coremark_crc_reference.py", "scripts/coremark_crc_reference.c",
                     "sw/coremark/upstream.json", "sw/coremark/core_portme.h", "sw/coremark/coremark.h",
                     "sw/coremark/core_main.c", "sw/coremark/core_list_join.c", "sw/coremark/core_matrix.c",
                     "sw/coremark/core_state.c", "sw/coremark/core_util.c"):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(safe(root, relative), target)
    shutil.copyfile(manifest_path, destination / "source-release-manifest.json")
    regression_path = referenced(root, manifest["rtl_regression"])
    shutil.copyfile(regression_path, destination / "rtl-regression.json")
    regression = read(regression_path)
    shutil.copyfile(referenced(root, regression["transcript"]), destination / "rtl-regression.txt")
    shutil.copyfile(referenced(root, regression["stderr"]), destination / "rtl-regression.stderr.txt")
    for relative in regression["test_files_sha256"]:
        target = destination / "regression-inputs" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(safe(root, relative), target)
    hashes = {path.relative_to(destination).as_posix(): sha(path) for path in sorted(destination.rglob("*")) if path.is_file()}
    receipt = {"schema_version": 1, "evidence_kind": "integrated_soc_board_release_receipt", "status": "BOARD_RELEASE_PASS",
               "release_version": soc_version, "cpu_version": cpu_version, "campaign_started_utc": manifest["campaign_started_utc"],
               "cpu_implementation_commit": manifest["cpu_implementation_commit"], "soc_implementation_commit": manifest["soc_implementation_commit"],
               **references, "acceptance": result, "files_sha256": hashes,
               "scope": "Portable replay of board UART, program identity, short RTL and archived FPGA gates. Full SoC source/frozen-input audit was performed before export; the CPU package is separately checked against the CPU implementation."}
    (destination / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return destination / "receipt.json"


def validate_receipt(path, oracle, cpu_root=None):
    receipt = read(path)
    root = Path(path).parent
    manifest = read(root / "source-release-manifest.json")
    soc_version = manifest.get("release_version")
    cpu_version = manifest.get("cpu_version")
    need(manifest.get("evidence_mode") == "BoardRelease" and soc_version == "6.5" and cpu_version == "3.5.0",
         "Wrong portable board release manifest")
    need(receipt.get("schema_version") == 1 and receipt.get("evidence_kind") == "integrated_soc_board_release_receipt" and
         receipt.get("status") == "BOARD_RELEASE_PASS" and receipt.get("cpu_version") == cpu_version and
         receipt.get("release_version") == soc_version and timestamp(receipt["campaign_started_utc"]) == CAMPAIGN_START, "Wrong portable board receipt")
    for relative, expected in receipt["files_sha256"].items():
        need(sha(safe(root, relative)) == expected, f"Portable receipt file changed: {relative}")
    final_path = referenced(root, receipt["final_session"])
    validate_implementation(read(final_path.parent / "fpga_input_snapshot.json"), receipt["soc_implementation_commit"])
    final = validate_session(final_path, oracle, CAMPAIGN_START, cpu_version)
    control = validate_session(referenced(root, receipt["same_frequency_session"]), oracle, CAMPAIGN_START, cpu_version, 59_400_000)
    need(final["cpu_commit"] == control["cpu_commit"] == receipt["cpu_implementation_commit"] and
         final["cpu_rtl_sha256"] == control["cpu_rtl_sha256"], "Portable control CPU identity differs")
    need(final["cpu_hz"] > 59_400_000 and final["mean_coremark_per_mhz"] >= BASELINE * 1.01, "Portable result does not meet both release targets")
    need(final == receipt["acceptance"]["final"] and control == receipt["acceptance"]["same_frequency"], "Receipt metrics disagree with raw board runs")
    validate_short_pilot(referenced(root, receipt["short_pilot"]), final_path, final, oracle, CAMPAIGN_START)
    regression = read(root / "rtl-regression.json")
    validate_regression(regression, read(final_path.parent / "fpga_input_snapshot.json"), final["cpu_rtl_sha256"],
                        root / "rtl-regression.txt", root / "rtl-regression.stderr.txt", root / "regression-inputs")
    if cpu_root:
        cpu_root = Path(cpu_root)
        source = read(final_path.parent / "cpu_source.json")
        need(sha(safe(cpu_root, "cpu/generated/core/CoreTop.sv")) == source["sha256"] and
             sha(safe(cpu_root, "cpu/generated/core/emit-config.json")) == source["config_sha256"], "CPU package generated RTL/config differs from tested SoC")
        names = [path.relative_to(cpu_root).as_posix() for path in (cpu_root / "cpu/src/main").rglob("*") if path.is_file()]
        names += ["cpu/build.sbt", "cpu/project/build.properties", "cpu/project/plugins.sbt"]
        rows = [relative + " " + sha(safe(cpu_root, relative)) for relative in sorted(names, key=str.casefold)]
        need(hashlib.sha256("\n".join(rows).encode()).hexdigest() == source["generator_source_sha256"], "CPU package generator source differs from tested implementation")
    return receipt["acceptance"]


def run_native_release_gates(root, manifest_path):
    """The portable receipt must only be minted after the existing full gates.

    Direct library calls are used by synthetic policy fixtures; every public
    source-tree CLI path invokes these native checks with a finite timeout.
    """
    root = Path(root).resolve()
    manifest = read(manifest_path)
    pilot = referenced(root, manifest["short_pilot"])
    snapshot = read(root / "artifacts/build_snapshot.json")
    clock = read(root / "config/clocks.json")
    directory = root / "docs/validation/frequency-search" / f"div{clock['cpu_divisor']}-PASS-{snapshot['run_id']}"
    archive = read(safe(directory, "archive_manifest.json"))
    need(archive["run_id"] == snapshot["run_id"] and archive["status"] == "PASS" and
         archive["snapshot_sha256"] == sha(root / "artifacts/build_snapshot.json"), "Final frequency archive identity differs")
    for relative in ("artifacts/soc_top.sbit", "artifacts/build_evidence.json"):
        matches = [entry for entry in archive["files"] if entry["path"] == relative]
        need(len(matches) == 1 and matches[0]["sha256"] == sha(root / relative), "Final frequency archive output differs")
    commands = [
        ("audit_project.ps1", ["-Root", str(root)]),
        ("verify_frequency_portable.ps1", ["-PortableDirectory", str(directory)]),
        ("verify_coremark_short_pilot_evidence.ps1", ["-Root", str(root), "-EvidenceDirectory", str(pilot.parent), "-PythonPath", __import__("sys").executable]),
    ]
    for script, arguments in commands:
        completed = subprocess.run(["powershell.exe", "-NoProfile", "-File", str(safe(root, "scripts/" + script)), *arguments],
                                   capture_output=True, text=True, errors="replace", timeout=180,
                                   creationflags=0x08000000 if os.name == "nt" else 0)
        need(completed.returncode == 0, f"Existing release gate failed: {script}: {(completed.stdout + completed.stderr)[-3000:]}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--session", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--cpu-root", type=Path)
    parser.add_argument("--export-receipt", type=Path)
    parser.add_argument("--host-gcc", default=r"D:\LJL\WORK\msys64\mingw64\bin\gcc.exe")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    need(sum(bool(item) for item in (args.manifest, args.session, args.receipt)) == 1, "Select exactly one release manifest, session or receipt")
    root = args.root or (args.receipt.parent if args.receipt else None)
    need(root is not None, "--root is required for source-tree/session validation")
    with CrcReference(root, args.host_gcc) as oracle:
        if args.receipt:
            result = validate_receipt(args.receipt, oracle, args.cpu_root)
        elif args.manifest:
            result = validate_release(root, args.manifest, oracle)
        else:
            cpu_source = json.loads((root / "rtl" / "cpu" / "source.json").read_text(encoding="utf-8-sig"))
            result = validate_session(args.session, oracle, CAMPAIGN_START, cpu_source["cpu_version"])
    if args.manifest:
        run_native_release_gates(root, args.manifest)
    if args.export_receipt:
        need(args.manifest is not None, "Portable export requires complete source-tree release validation")
        export_receipt(root, args.manifest, result, args.export_receipt)
    encoded = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(f"BOARD_RELEASE_REJECTED: {error}")
