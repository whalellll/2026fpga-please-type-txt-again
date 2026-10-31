"""Synthetic acceptance fixtures; no fixture is board/performance evidence."""
import argparse
import copy
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
from zipfile import ZipFile

from coremark_crc_reference import CrcReference
from test_release_regression_contract import main as regression_contract_tests, synthetic_git_identity
from verify_candidate_delivery import validate as validate_candidate
from verify_board_release import (CAMPAIGN_START, SESSION_FILES, parse_uart, read, sha,
                                  timing_summary, validate_session, validate_release,
                                  export_receipt, validate_receipt, regression_test_paths,
                                  validate_program_transcript)
from verify_board_release import validate_uart_pad_contract
from audit_uart_tx_pad_ads import audit as audit_uart_pad
from test_uart_tx_pad_ads import fixture as uart_pad_fixture

ROOT = Path(__file__).resolve().parent.parent
LEGACY = ROOT / "docs/validation/v6_1-board-coremark-20261008"


def program_transcript_tests():
    """Native begin+success shape; synthetic text, never a hardware result."""
    assigned = "D:/SYNTHETIC/soc_top.sbit"
    operations = ("cfg_scan_chain", f"cfg_assign_file -file {assigned} -device_index 0",
                  "cfg_program -device_index 0", "cfg_disconnect")
    pairs = [f"Executing : {op}\nExecuting : {op} successfully.\n" for op in operations]
    suffix = "COMMAND[Program] execute successfully, takes 1.0 secs.\nThe done bit is 1\n"
    valid = "SYNTHETIC FIXTURE ONLY\n" + "".join(pairs) + suffix
    checks = 0
    for name, text in (("native_lf", valid), ("native_crlf", valid.replace("\n", "\r\n"))):
        validate_program_transcript(text, assigned)
        print("PROGRAM_TRANSCRIPT_CASE_PASS " + name)
        checks += 1
    failures = {
        "duplicate_complete_sequence": valid + valid,
        "duplicate_program_pair": valid.replace(pairs[2], pairs[2] * 2),
        "missing_begin": valid.replace("Executing : cfg_program -device_index 0\n", ""),
        "missing_success": valid.replace("Executing : cfg_program -device_index 0 successfully.\n", ""),
        "success_only": "".join(pair.splitlines()[1] + "\n" for pair in pairs) + suffix,
        "wrong_order": pairs[1] + pairs[0] + pairs[2] + pairs[3] + suffix,
        "missing_stage": valid.replace(pairs[1], ""),
        "success_before_begin": valid.replace(pairs[2], "\n".join(reversed(pairs[2].splitlines())) + "\n"),
        "wrong_assignment": valid.replace(assigned, "D:/SYNTHETIC/other.sbit"),
        "extra_assignment": valid.replace(pairs[1], pairs[1] + pairs[1].replace(assigned, "D:/SYNTHETIC/other.sbit")),
        "extra_device_program": valid.replace(pairs[2], pairs[2] + pairs[2].replace("device_index 0", "device_index 1")),
        "native_error_even_with_success": valid + "E: Configuration-0012: Tcl Command: cfg_program exec failed.\n",
        "program_failure_even_with_success": valid + "COMMAND[Program] execute failed.\n",
        "missing_done": valid.replace("The done bit is 1", "The done bit is 0"),
        "missing_program_success": valid.replace("COMMAND[Program] execute successfully", "COMMAND[Program] incomplete"),
    }
    for name, text in failures.items():
        try:
            validate_program_transcript(text, assigned)
        except ValueError:
            print("PROGRAM_TRANSCRIPT_CASE_PASS " + name)
            checks += 1
        else:
            raise AssertionError("Accepted invalid program transcript " + name)
    print(f"PROGRAM_TRANSCRIPT_POLICY_PASS checks={checks} synthetic_only=true hardware_tests_run=false")
    return checks


def write(path, record):
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def stamp(minutes):
    return (CAMPAIGN_START + timedelta(minutes=minutes)).isoformat()


def fixture(directory, oracle, hz=63642857):
    directory.mkdir()
    mapping = {
        "cpu_source.json": "rtl/cpu/source.json", "clock.json": "config/clocks.json",
        "fpga_input_snapshot.json": "artifacts/build_snapshot.json", "fpga_build_evidence.json": "artifacts/build_evidence.json",
        "firmware.build.json": "artifacts/bootloader.build.json", "firmware.bin": "artifacts/bootloader.bin",
        "bootrom.hex": "artifacts/bootrom.hex", "soc_top.sbit": "artifacts/soc_top.sbit",
        "pll_video.v": "rtl/video/pll_video.v", "soc.fdc": "pds/soc.fdc",
    }
    for name in SESSION_FILES - set(mapping) - {"uart.txt", "result.json", "program.json", "program.txt", "preflight.txt"}:
        mapping[name] = "artifacts/" + name
    for target, source in mapping.items():
        shutil.copyfile(ROOT / source, directory / target)
    source = read(directory / "cpu_source.json")
    source["cpu_version"] = "3.5.0"
    source["source_worktree_dirty"] = False
    write(directory / "cpu_source.json", source)
    clock = read(directory / "clock.json")
    clock.update(cpu_hz=hz, cpu_divisor=14 if hz == 63642857 else 15)
    write(directory / "clock.json", clock)
    pll_path = directory / "pll_video.v"
    pll_path.write_text(re.sub(r"parameter integer CPU_DIVISOR = \d+", "parameter integer CPU_DIVISOR = " + str(clock["cpu_divisor"]),
                               pll_path.read_text(encoding="utf-8-sig")), encoding="utf-8")
    snapshot = read(directory / "fpga_input_snapshot.json")
    # Exercise the new hold-fix capability explicitly even when repository
    # artifacts still belong to an earlier candidate without UART pads.
    snapshot['inputs']['scripts/audit_uart_tx_pad_ads.py'] = sha(ROOT / 'scripts/audit_uart_tx_pad_ads.py')
    for original in snapshot["inputs"]:
        snapshot["inputs"][original] = sha(ROOT / original)
    snapshot["started_utc"] = stamp(1)
    snapshot["release"] = "V6.5"
    for local, original in mapping.items():
        if original in snapshot["inputs"]:
            snapshot["inputs"][original] = sha(directory / local)
    input_files = {relative: (ROOT / relative).read_bytes() for relative in snapshot["inputs"]}
    for local, original in mapping.items():
        if original in input_files:
            input_files[original] = (directory / local).read_bytes()
    # The fixture validates the V6.5 release policy even when the current
    # integration checkout has a different SoC package version.
    if "VERSION" in input_files:
        synthetic_version = b"6.5\n"
        snapshot["inputs"]["VERSION"] = hashlib.sha256(synthetic_version).hexdigest()
        input_files["VERSION"] = synthetic_version
    snapshot["implementation_git"] = synthetic_git_identity(input_files)
    write(directory / "fpga_input_snapshot.json", snapshot)
    cpu_ads = read(directory / 'cpu_ads_controls.json')
    synthetic_vm = uart_pad_fixture()
    vm_sha = hashlib.sha256(synthetic_vm.encode('utf-8')).hexdigest()
    uart = audit_uart_pad(synthetic_vm)
    uart.update(run_id=snapshot['run_id'], input_snapshot_sha256=sha(directory/'fpga_input_snapshot.json'),
                vm_sha256=vm_sha, checker_sha256=snapshot['inputs']['scripts/audit_uart_tx_pad_ads.py'],
                parser_sha256=snapshot['inputs']['scripts/audit_icache_pad_ads.py'],
                uart_rtl_sha256=snapshot['inputs']['rtl/soc/uart_tx_fifo.v'])
    cpu_ads.update(uart_tx_pad_contract=uart, netlist_sha256=vm_sha, input_snapshot_run_id=snapshot['run_id'],
                   input_snapshot_sha256=sha(directory/'fpga_input_snapshot.json'))
    write(directory/'cpu_ads_controls.json', cpu_ads)
    gate = read(directory / "preflight_gate.json")
    gate["input_snapshot_sha256"] = sha(directory / "fpga_input_snapshot.json")
    write(directory / "preflight_gate.json", gate)
    build = read(directory / "fpga_build_evidence.json")
    build['report_hashes']['pds/synthesize/soc_top_syn.vm'] = vm_sha
    # The fixture borrows formats, not acceptance: rebuilding current firmware
    # legitimately changes outputs since the historical PDS evidence was made.
    for original in build["outputs"]:
        build["outputs"][original] = sha(ROOT / original)
    build.update(started_utc=stamp(1), completed_utc=stamp(2), release="V6.5",
                 input_snapshot_sha256=sha(directory / "fpga_input_snapshot.json"))
    for local, original in mapping.items():
        if original in build["outputs"]:
            build["outputs"][original] = sha(directory / local)
    write(directory / "fpga_build_evidence.json", build)
    # Explicitly synthetic transcript. It is never promoted outside this temp dir.
    scan = "SYNTHETIC FIXTURE ONLY\nExecuting : cfg_scan_chain\nPG2L100H\nThe ID value is: 0x00602899\nThis device configure situation (done bit): 1\nExecuting : cfg_scan_chain successfully.\nExecuting : cfg_read_device_property -mode 0 -device_index 0\nExecuting : cfg_read_device_property -mode 0 -device_index 0 successfully.\n"
    (directory / "preflight.txt").write_text(scan, encoding="utf-8")
    (directory / "program.txt").write_text(scan + "Executing : cfg_assign_file -file D:/SYNTHETIC/soc_top.sbit -device_index 0\nExecuting : cfg_assign_file -file D:/SYNTHETIC/soc_top.sbit -device_index 0 successfully.\nExecuting : cfg_program -device_index 0\nCOMMAND[Program] execute successfully\nExecuting : cfg_program -device_index 0 successfully.\nThe done bit is 1\nExecuting : cfg_disconnect\nExecuting : cfg_disconnect successfully.\n", encoding="utf-8")
    program = dict(schema_version=1, evidence_kind="volatile_cram_program", status="PASS", operation="CRAM",
                   started_utc=stamp(3), completed_utc=stamp(4), device="PG2L100H", device_id="0x00602899", device_count=1, device_index=0,
                   bitstream_sha256=sha(directory / "soc_top.sbit"), firmware_binary_sha256=sha(directory / "firmware.bin"),
                   cpu_rtl_sha256=source["sha256"], cpu_source_manifest_sha256=sha(directory / "cpu_source.json"),
                   pds_snapshot_run_id=snapshot["run_id"], pds_snapshot_sha256=sha(directory / "fpga_input_snapshot.json"),
                   pds_build_evidence_sha256=sha(directory / "fpga_build_evidence.json"),
                   program_log_sha256=sha(directory / "program.txt"), preflight_log_sha256=sha(directory / "preflight.txt"))
    program["assigned_bitstream_path"] = "D:/SYNTHETIC/soc_top.sbit"
    write(directory / "program.json", program)
    raw = (LEGACY / "uart.log.txt").read_text(encoding="utf-8-sig").replace("\r", "")
    raw = raw.replace("CPU_HZ=59400000", f"CPU_HZ={hz}")
    raw = re.sub(r"^(PORT_TICKS64\s*:\s*)\d+", r"\g<1>600000000", raw, flags=re.MULTILINE)
    raw = re.sub(r"^(Total ticks\s*:\s*)\d+", r"\g<1>600000000", raw, flags=re.MULTILINE)
    raw = re.sub(r"^(Total time \(secs\):\s*)[0-9.]+", r"\g<1>12.121212", raw, flags=re.MULTILINE)
    (directory / "uart.txt").write_text(raw, encoding="utf-8")
    result = read(LEGACY / "result.json")
    result.update(captured_utc=stamp(5), runs=parse_uart(raw, hz, oracle), log_sha256=sha(directory / "uart.txt"))
    result["bitstream"]["sha256"] = sha(directory / "soc_top.sbit")
    result["firmware"]["sha256"] = sha(directory / "firmware.bin")
    write(directory / "result.json", result)
    session = dict(schema_version=1, evidence_kind="board_coremark_session", status="BOARD_COREMARK_3_PLUS_1_PASS",
                   created_utc=stamp(6), files_sha256={name: sha(directory / name) for name in SESSION_FILES})
    write(directory / "session.json", session)
    return directory / "session.json"


def release_fixture(root, oracle):
    """Copy real formats into an isolated, conspicuously synthetic valid bundle."""
    root.mkdir()
    final_path = fixture(root / "final", oracle)
    control_path = fixture(root / "control", oracle, 59400000)
    snapshot = read(final_path.parent / "fpga_input_snapshot.json")
    build = read(final_path.parent / "fpga_build_evidence.json")
    for relative in set(snapshot["inputs"]) | set(build["outputs"]):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    (root / "VERSION").write_bytes(b"6.5\n")
    mapping = {"cpu_source.json": "rtl/cpu/source.json", "clock.json": "config/clocks.json",
               "fpga_input_snapshot.json": "artifacts/build_snapshot.json", "fpga_build_evidence.json": "artifacts/build_evidence.json",
               "firmware.build.json": "artifacts/bootloader.build.json", "firmware.bin": "artifacts/bootloader.bin",
               "bootrom.hex": "artifacts/bootrom.hex", "soc_top.sbit": "artifacts/soc_top.sbit",
               "pll_video.v": "rtl/video/pll_video.v", "soc.fdc": "pds/soc.fdc"}
    for name in SESSION_FILES - set(mapping) - {"uart.txt", "result.json", "program.json", "program.txt", "preflight.txt"}:
        mapping[name] = "artifacts/" + name
    for local, relative in mapping.items():
        shutil.copyfile(final_path.parent / local, root / relative)
    assert (root / "VERSION").read_text(encoding="utf-8-sig").strip() == "6.5"
    short = root / "short"
    shutil.copytree(ROOT / "docs/validation/v6_1-short-pilot", short)
    pilot = read(short / "release_evidence.json")
    pilot.update(created_utc=stamp(6), cpu_hz=63642857, cpu_rtl_sha256=snapshot["inputs"]["rtl/cpu/CoreTop.sv"],
                 pds_snapshot_sha256=sha(root / "artifacts/build_snapshot.json"), released_bitstream_sha256=sha(root / "artifacts/soc_top.sbit"))
    summary = read(short / "summary.json")
    summary["cpu_hz"] = 63642857
    write(short / "summary.json", summary)
    for index, mode in enumerate(("performance", "validation")):
        name = f"run0{index + 1}-{mode}"
        case = read(short / (name + ".json"))
        case.update(cpu_hz=63642857, cpu_rtl_sha256=snapshot["inputs"]["rtl/cpu/CoreTop.sv"])
        write(short / (name + ".json"), case)
    model = read(short / "verilator_model.json")
    for relative in model["source_files"]:
        if relative in snapshot["inputs"]:
            model["source_files"][relative] = snapshot["inputs"][relative]
    write(short / "verilator_model.json", model)
    pilot["files_sha256"] = {name: sha(short / name) for name in pilot["files_sha256"]}
    write(short / "release_evidence.json", pilot)
    transcript = root / "regression.txt"
    transcript.write_text("SYNTHETIC FIXTURE ONLY\nSOC_ALL_TESTS_PASS\n", encoding="utf-8")
    stderr = root / "regression.stderr.txt"
    stderr.write_text("", encoding="utf-8")
    for relative in ("scripts/run_all_tests.ps1", "scripts/run_release_regression.ps1", "scripts/bounded_process.cs",
                     "scripts/verify_board_release.py", "scripts/coremark_crc_reference.py", "scripts/coremark_crc_reference.c"):
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, root / relative)
    ref = lambda path: {"path": path.relative_to(root).as_posix(), "sha256": sha(path)}
    source = read(final_path.parent / "cpu_source.json")
    regression = dict(schema_version=1, status="PASS", exit_code=0, marker="SOC_ALL_TESTS_PASS", started_utc=stamp(0), completed_utc=stamp(1),
                      cpu_rtl_sha256=source["sha256"], transcript=ref(transcript), stderr=ref(stderr),
                      source_files_sha256={name: value for name, value in snapshot["inputs"].items() if not name.startswith("artifacts/")},
                      test_files_sha256={name: sha(root / name) for name in regression_test_paths(root)})
    write(root / "regression.json", regression)
    manifest = dict(schema_version=1, evidence_mode="BoardRelease", release_version="6.5", cpu_version="3.5.0",
                    campaign_started_utc=CAMPAIGN_START.isoformat(), cpu_implementation_commit=source["source_reference_commit"],
                    soc_implementation_commit=snapshot["implementation_git"]["commit_sha1"], final_session=ref(final_path), same_frequency_session=ref(control_path),
                    short_pilot=ref(short / "release_evidence.json"), rtl_regression=ref(root / "regression.json"))
    write(root / "release.json", manifest)
    # Receipt copies the verifier/oracle from the validated source tree.
    for relative in ("scripts/verify_board_release.py", "scripts/coremark_crc_reference.py", "scripts/coremark_crc_reference.c"):
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, root / relative)
    return root / "release.json"


def main():
    global ROOT, LEGACY
    parser = argparse.ArgumentParser()
    parser.add_argument("--host-gcc", default=r"D:\LJL\WORK\msys64\mingw64\bin\gcc.exe")
    parser.add_argument("--program-transcript-only", action="store_true")
    parser.add_argument("--fixture-root", type=Path,
                        help="Complete reference artifact corpus for synthetic policy fixtures only; never candidate acceptance")
    args = parser.parse_args()
    if args.fixture_root:
        ROOT = args.fixture_root.resolve()
        LEGACY = ROOT / "docs/validation/v6_1-board-coremark-20261008"
        print("BOARD_RELEASE_SYNTHETIC_FIXTURE_ROOT=" + str(ROOT))
    transcript_checks = program_transcript_tests()
    if args.program_transcript_only:
        return
    regression_contract_tests()
    checks = transcript_checks
    with CrcReference(ROOT, args.host_gcc) as oracle, tempfile.TemporaryDirectory(prefix="soc_board_release_fixture_") as temp:
        directory = Path(temp)
        path = fixture(directory / "session", oracle)
        valid = validate_session(path, oracle, CAMPAIGN_START, "3.5.0")
        assert valid["mean_coremark_per_mhz"] > 5.120849733668798
        checks += 1
        # Dynamic iteration-dependent CRC independently checked against known
        # ten/4000 results, and another iteration count with different final CRC.
        assert oracle.get("performance", 10)["[0]crcfinal"] == "fcaf"
        assert oracle.get("validation", 4000)["[0]crcfinal"] == "5249"
        assert oracle.get("performance", 3000)["[0]crcfinal"] != "65c5"
        checks += 3

        def reject(name, action, expected):
            nonlocal checks
            action()
            try:
                validate_session(path, oracle, CAMPAIGN_START, "3.5.0")
            except ValueError as error:
                assert expected in str(error), (name, str(error))
                checks += 1
            else:
                raise AssertionError("Accepted invalid " + name)

        base = {file.name: file.read_bytes() for file in path.parent.iterdir()}

        def mutate(name, change, rehash=True):
            for file, data in base.items():
                (path.parent / file).write_bytes(data)
            target = path.parent / name
            record = read(target)
            change(record)
            write(target, record)
            if rehash:
                session = read(path)
                session["files_sha256"][name] = sha(target)
                write(path, session)

        reject("wrong bitstream", lambda: mutate("program.json", lambda r: r.update(bitstream_sha256="0" * 64)), "CRAM identity mismatch")
        reject("old load", lambda: mutate("program.json", lambda r: r.update(started_utc="2026-10-07T00:00:00Z")), "capture predates")
        reject("wrong target", lambda: mutate("program.json", lambda r: r.update(device_id="0x00000000")), "unique target")
        reject("wrong assigned image", lambda: mutate("program.json", lambda r: r.update(assigned_bitstream_path="D:/SYNTHETIC/other.sbit")), "transcript does not preserve")
        reject("offline capture", lambda: mutate("result.json", lambda r: r.update(evidence_kind="offline_log_validation")), "Offline or failed")
        reject("wrong raw hash", lambda: mutate("result.json", lambda r: r.update(log_sha256="0" * 64)), "artifact identity")
        reject("changed artifact", lambda: mutate("program.json", lambda r: r.update(status="FAIL"), False), "file hash changed")
        reject("wrong compiler", lambda: mutate("result.json", lambda r: r["runs"][0].update(ticks=1)), "Recorded UART result")
        def mutate_ads(change):
            mutate('cpu_ads_controls.json', change)
            build = read(path.parent/'fpga_build_evidence.json')
            build['outputs']['artifacts/cpu_ads_controls.json'] = sha(path.parent/'cpu_ads_controls.json')
            write(path.parent/'fpga_build_evidence.json', build)
            program = read(path.parent/'program.json')
            program['pds_build_evidence_sha256'] = sha(path.parent/'fpga_build_evidence.json')
            write(path.parent/'program.json', program)
            session = read(path)
            session['files_sha256']['fpga_build_evidence.json'] = sha(path.parent/'fpga_build_evidence.json')
            session['files_sha256']['program.json'] = sha(path.parent/'program.json')
            write(path, session)
        def merged_pointer(record):
            for index, pair in enumerate(record['uart_tx_pad_contract']['pairs']):
                pair['inputs'] = [f'pad_address_in[{index*2}]', f'pad_address_in[{index*2+1}]']
        mutate_ads(merged_pointer)
        validate_session(path, oracle, CAMPAIGN_START, '3.5.0')
        checks += 1
        print('BOARD_UART_PAD_CASE_PASS native_merged_pointer_contract_accepted')
        for name, change in {
            'missing_uart_contract': lambda r:r.pop('uart_tx_pad_contract'),
            'missing_pad': lambda r:r['uart_tx_pad_contract'].update(pairs=r['uart_tx_pad_contract']['pairs'][:1]),
            'wrong_checker': lambda r:r['uart_tx_pad_contract'].update(checker_sha256='0'*64),
            'wrong_parser': lambda r:r['uart_tx_pad_contract'].update(parser_sha256='0'*64),
            'wrong_uart_rtl': lambda r:r['uart_tx_pad_contract'].update(uart_rtl_sha256='0'*64),
            'foreign_vm': lambda r:r['uart_tx_pad_contract'].update(vm_sha256='0'*64),
            'foreign_run': lambda r:r['uart_tx_pad_contract'].update(run_id='0'*32),
            'mixed_pointer_buses': lambda r:r['uart_tx_pad_contract']['pairs'][1].update(inputs=['pad_address_in[2]','pad_address_in[3]']),
            'unknown_pointer_bus': lambda r:r['uart_tx_pad_contract']['pairs'][0].update(inputs=['foreign[0]','foreign[1]']),
            'pointer_output_alias': lambda r:r['uart_tx_pad_contract']['pairs'][0].update(outputs=['pad_address_in[0]','pad[1]']),
            'ram_bypass': lambda r:r['uart_tx_pad_contract']['memories'][0].update(waddr="{1'b0,wr_ptr[3],pad[2],pad[1],pad[0]}"),
            'wrong_data_coverage': lambda r:r['uart_tx_pad_contract']['memories'][0].update(data_bits=[0,0]),
            'false_routed_claim': lambda r:r['uart_tx_pad_contract'].update(routed_hold_margin_proven=True),
        }.items():
            reject(name, lambda change=change:mutate_ads(change), 'UART TX pad ADS')
            print('BOARD_UART_PAD_CASE_PASS ' + name + '_rejected')
        old_snapshot = read(path.parent/'fpga_input_snapshot.json')
        old_snapshot['inputs'].pop('scripts/audit_uart_tx_pad_ads.py')
        validate_uart_pad_contract({}, old_snapshot, 'unused', 'unused')
        checks += 1
        print('BOARD_UART_PAD_CASE_PASS historical_snapshot_keeps_original_scope')
        # UART gates operate independently of report.json claims.
        raw = (LEGACY / "uart.log.txt").read_text(encoding="utf-8-sig")
        negative_uart = {
            "short": (re.sub(r"(PORT_TICKS64\s*:\s*)\d+", r"\g<1>100", raw), "shorter than ten"),
            "wrong_crc": (raw.replace("0x65c5", "0x0000"), "Wrong CRC"),
            "wrong_flags": (raw.replace("-O2", "-O3"), "flags changed"),
            "wrong_iterations_crc": (re.sub(r"(Iterations\s*:\s*)4000", r"\g<1>3000", raw), "Wrong CRC"),
            "duplicate_run": (raw + raw, "Exactly consecutive"),
            "wrong_order": (raw.replace("COREMARK_MODE=validation", "COREMARK_MODE=performance"), "Wrong run order"),
            "missing_done": (raw.replace("COREMARK_DONE", "", 1), "Exactly consecutive"),
        }
        for name, (text, expected) in negative_uart.items():
            try:
                parse_uart(text, 59400000, oracle)
            except ValueError as error:
                assert expected in str(error), (name, str(error))
                checks += 1
            else:
                raise AssertionError("Accepted UART fixture " + name)
        # Historical manifests cannot silently become the current release.
        fake_manifest = directory / "release.json"
        write(fake_manifest, dict(schema_version=1, evidence_mode="ShortPilot", release_version="6.1"))
        try:
            validate_release(ROOT, fake_manifest, oracle)
        except ValueError as error:
            assert "Wrong explicit release" in str(error)
            checks += 1
        else:
            raise AssertionError("Accepted historical release selection")
        timing_summary(ROOT / "artifacts/timing_summary.txt")
        checks += 1
        full_root = directory / "full"
        manifest_path = release_fixture(full_root, oracle)
        result = validate_release(full_root, manifest_path, oracle)
        assert result["status"] == "BOARD_RELEASE_PASS"
        checks += 1
        receipt_path = export_receipt(full_root, manifest_path, result, directory / "portable")
        assert validate_receipt(receipt_path, oracle) == result
        checks += 1
        manifest = read(manifest_path)
        manifest["campaign_started_utc"] = "2026-10-07T00:00:00Z"
        write(manifest_path, manifest)
        try:
            validate_release(full_root, manifest_path, oracle)
        except ValueError as error:
            assert "Wrong release campaign" in str(error)
            checks += 1
        else:
            raise AssertionError("Accepted a stale campaign")
        receipt = read(receipt_path)
        receipt["acceptance"]["final"]["mean_coremark_per_mhz"] += 1
        write(receipt_path, receipt)
        try:
            validate_receipt(receipt_path, oracle)
        except ValueError as error:
            assert "Receipt metrics disagree" in str(error)
            checks += 1
        else:
            raise AssertionError("Accepted fabricated receipt score")
        candidate_path = directory / "candidate.zip"
        payload = {"rtl/cpu/source.json": b"synthetic source", "rtl/cpu/CoreTop.sv": b"synthetic RTL"}
        import hashlib
        hashes = {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()}
        candidate_record = dict(status="CANDIDATE_NOT_RELEASE", incomplete_acceptance=["synthetic fixture, never board evidence"],
                                files_sha256=hashes, cpu_source_manifest_sha256=hashes["rtl/cpu/source.json"], cpu_rtl_sha256=hashes["rtl/cpu/CoreTop.sv"])
        for tampered in (False, True):
            with ZipFile(candidate_path, "w") as archive:
                for name, data in payload.items():
                    archive.writestr("SOC_CANDIDATE/" + name, data + (b"changed" if tampered else b""))
                archive.writestr("SOC_CANDIDATE/candidate-delivery.json", json.dumps(candidate_record))
            if tampered:
                try:
                    validate_candidate(candidate_path)
                except ValueError as error:
                    assert "content hash differs" in str(error)
                else:
                    raise AssertionError("Accepted changed candidate bytes")
            else:
                assert validate_candidate(candidate_path)["status"] == "CANDIDATE_NOT_RELEASE"
            checks += 1
    print(f"BOARD_RELEASE_POLICY_PASS checks={checks} synthetic_only=true hardware_tests_run=false")


if __name__ == "__main__":
    main()
