"""Offline parser tests against supplied real ADS; never invokes PDS.

The combined hierarchy/LUTRAM cases are parser fixtures, not integrated builds.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def dotnet_utc(value, suffix="Z"):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "7" + suffix


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--standalone-netlist", type=Path, required=True)
    p.add_argument("--old-full-netlist", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise RuntimeError("Refuse to overwrite prior fixture results")
    checker = Path(__file__).with_name("audit_icache_pad_ads.py")
    spec = importlib.util.spec_from_file_location("icache_review", checker)
    review = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(review)
    original = {q.resolve(): q.read_bytes() for q in (a.standalone_netlist, a.old_full_netlist, checker)}
    new = original[a.standalone_netlist.resolve()].decode()
    old = original[a.old_full_netlist.resolve()].decode()
    checks = []

    def reject(name, text, standalone=True):
        try:
            review.check(text, standalone_fixture=standalone)
        except (AssertionError, KeyError) as exc:
            checks.append(dict(name=name, status="REJECTED_AS_REQUIRED", reason=str(exc)))
        else:
            raise RuntimeError("Invalid fixture accepted: " + name)

    positive = review.check(new, standalone_fixture=True)
    assert positive["pairs"] == 64 and positive["bits"] == 128
    checks.append(dict(name="real_standalone_ads", status="PASS", scope="ISOLATED_ACTUAL_ICACHE_ADS_ONLY"))
    reject("real_old_full_soc_without_pad", old, False)
    combined = new
    for name in ("wayMem_128x256", "wayMem_128x256_unq4"):
        combined = combined.replace(review.module(combined, name), review.module(old, name))
    assert all(w["mapping"] == "256_GTP_RAM128X1SP" for w in review.check(combined, True)["ways"])
    checks.append(dict(name="combined_lutram_parser_fixture", status="PASS", scope="SYNTHETIC_ONLY"))
    for name, before, after, target in (
        ("missing_preservation", "(* PAP_DONT_TOUCH *)", "", "PangoIdentityPad"),
        ("wrong_init", "1100110011001100", "0000110011001100", "PangoIdentityPad"),
        ("wrong_constant", ".I5 (1'b1)", ".I5 (1'b0)", "PangoIdentityPad"),
        ("duplicate_lutram_di", ".DI (W0_data[0])", ".DI (W0_data[1])", "wayMem_128x256"),
        ("truncated_ram_bus", "refillWriteLine[0]", "refillWriteLine[1]", "Icache"),
    ):
        body = review.module(combined, target)
        changed = body.replace(before, after, 1)
        assert changed != body, "Fixture mutation did not match: " + name
        reject(name, combined.replace(body, changed))
    for target, statement in (("Icache", "assign refillWriteLine = 256'b0;"),
                              ("wayMem_128x256", "assign W0_data = 256'b0;")):
        body = review.module(combined, target)
        changed = body.replace("endmodule", statement + "\nendmodule")
        reject("whole_bus_alias_" + target, combined.replace(body, changed))

    # A fake parent hierarchy exercises the CLI and provenance checks. It is
    # deliberately labeled synthetic; it cannot substitute for a native SoC run.
    hierarchy = "\n".join(review.module(old, n) for n in
                          ("soc_top", "core_top", "cpu_core_top", "CoreTop", "Core", "CoreFrontend"))
    synthetic = hierarchy + "\n" + combined.replace("nt_io_axiRetData", "io_axiRetData")
    review.check(synthetic)
    with tempfile.TemporaryDirectory(prefix="icache_ads_fixture_") as temp:
        root = Path(temp)
        for d in ("scripts", "rtl/cpu", "pds/synthesize"):
            (root / d).mkdir(parents=True)
        copied = root / "scripts/audit_icache_pad_ads.py"
        shutil.copyfile(checker, copied)
        core = root / "rtl/cpu/CoreTop.sv"
        core.write_text("// SYNTHETIC FIXTURE ONLY\n")
        config = root / "rtl/cpu/emit-config.json"
        config.write_text('{"scope":"SYNTHETIC_ONLY"}\n')
        source = root / "rtl/cpu/source.json"
        source.write_text(json.dumps(dict(sha256=review.sha(core), config_sha256=review.sha(config))))
        net = root / "pds/synthesize/soc_top_syn.vm"
        net.write_text(synthetic)
        snapshot = dict(run_id="a" * 32, started_utc=dotnet_utc(datetime.now(timezone.utc) - timedelta(seconds=5)),
                        inputs={q.relative_to(root).as_posix(): review.sha(q) for q in (core, config, source, copied)})
        snap = root / "pds/build_snapshot.json"

        def cli(name, data, expect_ok=False, optimized=False, expected_error=None):
            snap.write_text(json.dumps(data))
            result = root / (name + ".json")
            command = [sys.executable] + (["-O"] if optimized else []) + [str(copied), "--project-root", str(root), "--output", str(result)]
            run = subprocess.run(command, capture_output=True, text=True, timeout=15)
            if (run.returncode == 0) != expect_ok:
                raise RuntimeError(name + ": " + run.stderr[-1500:])
            if expected_error and expected_error not in run.stderr:
                raise RuntimeError(name + ": expected rejection was absent: " + run.stderr[-1500:])
            if expect_ok:
                parsed = json.loads(result.read_text())
                assert parsed["checker_sha256"] == review.sha(copied)
                assert parsed["source_json_sha256"] == review.sha(source)
                assert parsed["inputs_unchanged"] is True
                assert parsed["post_pnr_physical_retention_proven"] is False
                assert len(parsed["input_hashes"]) == 6
            checks.append(dict(name=name, status="PASS" if expect_ok else "REJECTED_AS_REQUIRED", scope="SYNTHETIC_CLI_ONLY", exit_code=run.returncode))

        cli("matching_dotnet_7_digit_z", snapshot, True)
        dotnet_offset = deepcopy(snapshot)
        dotnet_offset["started_utc"] = dotnet_offset["started_utc"].replace("Z", "+00:00")
        cli("matching_dotnet_7_digit_offset", dotnet_offset, True)
        python_utc = deepcopy(snapshot)
        python_utc["started_utc"] = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
        cli("matching_python_6_digit_offset", python_utc, True)
        future = deepcopy(snapshot)
        future["started_utc"] = dotnet_utc(datetime.now(timezone.utc) + timedelta(minutes=1))
        cli("future_dotnet_7_digit_ads", future, expected_error="ADS output predates run")
        for rel in snapshot["inputs"]:
            bad = deepcopy(snapshot)
            bad["inputs"][rel] = "0" * 64
            cli("foreign_" + Path(rel).name.replace(".", "_"), bad)
        cli("optimized_python_rejected", snapshot, optimized=True)
    assert all(q.read_bytes() == value for q, value in original.items()), "Original inputs changed"
    result = dict(schema=1, status="PASS", scope="OFFLINE_PARSER_AND_SYNTHETIC_BINDING_TESTS_ONLY",
                  no_native_tool_started=True, inputs_unchanged=True, count=len(checks), checks=checks,
                  checker_sha256=review.sha(checker), runner_sha256=review.sha(Path(__file__)),
                  standalone_netlist_sha256=review.sha(a.standalone_netlist), old_full_netlist_sha256=review.sha(a.old_full_netlist))
    a.output.write_text(json.dumps(result, indent=2) + "\n")
    print("ICACHE_ADS_FIXTURES_PASS count=" + str(len(checks)))


if __name__ == "__main__":
    main()
