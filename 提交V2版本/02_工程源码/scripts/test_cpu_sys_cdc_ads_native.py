#!/usr/bin/env python3
"""Exercise the CPU/SYS CDC auditor against an isolated native ADS probe.

The probe's source snapshot predates its trial FDC. This test copies the snapshot
with the trial FDC hash into a temporary directory only for auditor regression;
the resulting PASS is not a frozen production build provenance claim.
"""

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def load_auditor(path):
    spec = importlib.util.spec_from_file_location("audit_cpu_sys_cdc_ads", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expect_rejection(action, label, audit_error, message):
    try:
        action()
    except audit_error as error:
        if message not in str(error):
            raise AssertionError(label + " rejected for wrong reason: " + str(error)) from error
        print(label + " rejected")
        return
    raise AssertionError(label + " was accepted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("probe", type=Path)
    parser.add_argument("--fdc", type=Path, help="FDC under test; default: probe FDC")
    args = parser.parse_args()
    probe = args.probe.resolve()
    project = probe / "project" / "pds"
    auditor_path = Path(__file__).resolve().parents[1] / "pds" / "audit_cpu_sys_cdc_ads.py"
    auditor = load_auditor(auditor_path)
    fdc_path = args.fdc.resolve() if args.fdc else project / "soc.fdc"
    vm_path = project / "synthesize" / "soc_top_syn.vm"
    adf_path = project / "synthesize" / "soc_top_syn.adf"
    ccr_path = project / "constraint_check" / "constraint_check.ccr"
    source_snapshot = probe / "source_snapshot.json"
    for path in (fdc_path, vm_path, adf_path, ccr_path, source_snapshot):
        if not path.is_file():
            raise FileNotFoundError(path)
    fdc = fdc_path.read_text(encoding="utf-8")
    vm = vm_path.read_text(encoding="utf-8", errors="replace")
    ccr = ccr_path.read_text(encoding="utf-8", errors="replace")
    snapshot = json.loads(source_snapshot.read_text(encoding="utf-8-sig"))
    snapshot["inputs"]["pds/soc.fdc"] = hashlib.sha256(fdc_path.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="cdc_ads_probe_") as temporary:
        snapshot_path = Path(temporary) / "snapshot.json"
        output_path = Path(temporary) / "audit.json"
        snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
        command = [
            sys.executable, "-B", str(auditor_path), "--netlist", str(vm_path),
            "--ccr", str(ccr_path), "--adf", str(adf_path),
            "--fdc", str(fdc_path), "--snapshot", str(snapshot_path),
            "--output", str(output_path),
        ]
        subprocess.run(command, check=True, timeout=120)
        result = json.loads(output_path.read_text(encoding="utf-8"))
    counts = result["constraints"]
    assert result["status"] == "PASS"
    assert (counts["total_constraints"], counts["cdc_directives"]) == (1171, 48)
    assert (
        counts["mapped_endpoint_tags"], counts["mapped_payload_output_tags"],
        counts["mapped_first_stage_tags"], counts["mapped_second_stage_tags"],
    ) == (300, 298, 8, 4)
    assert sum(item["mapped_ram_cells"] for item in result["payloads"]) == 76
    assert {item["fifo"]: (item["launch_clock"], item["capture_clock"])
            for item in result["payloads"]} == {
                "ar": ("cpu_clk", "sys_clk"),
                "aw": ("cpu_clk", "sys_clk"),
                "w": ("cpu_clk", "sys_clk"),
                "r": ("sys_clk", "cpu_clk"),
                "b": ("sys_clk", "cpu_clk"),
            }
    print("native ADS/CCR audit PASS: 1171 constraints, 48 CDC, 76 RAM, 300/298/8/4 tags")

    wrong_clock_vm, substitutions = re.subn(
        r"(axi_async_fifo\s+u_ar_fifo\s*\(.*?\.wr_clk\s*\()cpu_clk(\s*\)\s*\);)",
        r"\1sys_clk\2", vm, count=1, flags=re.DOTALL,
    )
    assert substitutions == 1, "native AR FIFO parent clock connection not found"
    expect_rejection(
        lambda: auditor.mapped_payload_ram_audit(wrong_clock_vm, fdc),
        "wrong mapped payload clock", auditor.AuditError,
        "mapped payload FIFO clock changed: ar/wr_clk",
    )

    ar_line = auditor.expected_payload_constraints()["ar"]["lines"]["max_delay"]
    line_number = fdc.splitlines().index(ar_line) + 1
    tag = re.compile(
        r"(?m)^\s*// SDC constraint : \(object DO\[0\]\) \(id \d+\) "
        r"\(from\) \(" + str(line_number) + r" :[^\n]*\n"
    )
    missing_tag_vm, substitutions = tag.subn("", vm)
    assert substitutions >= 1, "native AR payload mapped tag not found"
    expect_rejection(
        lambda: auditor.mapped_payload_ram_audit(missing_tag_vm, fdc),
        "missing mapped payload tag", auditor.AuditError,
        "payload FDC did not reach mapped RAM output",
    )

    wrong_fdc = fdc.replace(ar_line, ar_line.replace("/storage(", "/wrong_storage("), 1)
    assert wrong_fdc != fdc
    expect_rejection(
        lambda: auditor.mapped_payload_ram_audit(vm, wrong_fdc),
        "wrong payload selector", auditor.AuditError,
        "payload FDC line missing or duplicated",
    )

    bad_ccr = ccr.replace(
        "u_cpu/u_cpu_wrapper/u_axi_cdc/u_ar_fifo/storage",
        "u_cpu/u_cpu_wrapper/u_axi_cdc/u_ar_fifo/wrong_storage", 1,
    )
    assert bad_ccr != ccr
    expect_rejection(
        lambda: auditor.constraint_audit(
            bad_ccr, fdc, result["fifos"], result["payloads"],
            result["first_stage_crossings"]),
        "wrong native CCR logical selector", auditor.AuditError,
        "payload FDC must select one exact logical storage array",
    )

    timer_line = auditor.expected_sync_constraints()["timer_c1"]["lines"]["max_delay"]
    line_number = fdc.splitlines().index(timer_line) + 1
    tag = re.compile(
        r"(?m)^\s*// SDC constraint : \(object D\) \(id \d+\) "
        r"\(to\) \(" + str(line_number) + r" :[^\n]*\n"
    )
    missing_tag_vm, substitutions = tag.subn("", vm)
    assert substitutions >= 1, "native timer first-stage mapped tag not found"
    expect_rejection(
        lambda: auditor.mapped_sync_first_stage_audit(missing_tag_vm, fdc),
        "missing mapped first-stage tag", auditor.AuditError,
        "first-stage FDC did not reach mapped FF D",
    )

    bad_ccr = ccr.replace(
        "u_cpu/u_cpu_wrapper/u_irq_sync/timer_c1",
        "u_cpu/u_cpu_wrapper/u_irq_sync/wrong_timer_c1", 1,
    )
    assert bad_ccr != ccr
    expect_rejection(
        lambda: auditor.constraint_audit(
            bad_ccr, fdc, result["fifos"], result["payloads"],
            result["first_stage_crossings"]),
        "wrong native first-stage CCR selector", auditor.AuditError,
        "first-stage FDC must select one exact FF",
    )


if __name__ == "__main__":
    main()
