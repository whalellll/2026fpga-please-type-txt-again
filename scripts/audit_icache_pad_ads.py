"""Fail-closed Icache pad review for integrated ADS; never starts implementation."""
import argparse
import calendar
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys

# Assertions are the fail-closed structural contract, never optional checks.
if sys.flags.optimize:
    raise RuntimeError("ICache ADS audit requires Python without -O/PYTHONOPTIMIZE")


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def utc_timestamp_ns(value):
    """Parse the six/seven-digit UTC timestamps emitted by Python/.NET."""
    assert isinstance(value, str), "Invalid UTC snapshot timestamp"
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\.(\d{6,7})(Z|\+00:00)", value)
    assert match, "Invalid UTC snapshot timestamp"
    second = datetime.strptime(match[1], "%Y-%m-%dT%H:%M:%S")
    return calendar.timegm(second.timetuple()) * 1_000_000_000 + int(match[2].ljust(9, "0"))


def module(text, name):
    found = re.findall(r"(?m)^[ \t]*(?:\(\*[^\r\n]*?\*\)[ \t]*)?module " + re.escape(name) + r"\b[\s\S]*?^endmodule\b", text)
    assert len(found) == 1, f"Expected unique module {name}"
    return found[0]


def clean(text):
    return re.sub(r"/\*.*?\*/|//[^\r\n]*", "", text, flags=re.S)


def ports(text):
    values = re.findall(r"\.(\w+)\s*\(([^()]*)\)", text)
    assert len(values) == len(dict(values)), "Duplicate port/parameter"
    return {k: re.sub(r"\s+", "", v) for k, v in values}


def cells(body, kind):
    pattern = (r"(?m)^[ \t]*(?P<attr>\(\*[^\r\n]*\*\)\s*)?" + re.escape(kind) +
               r"\s*(?:#\s*\((?P<params>.*?)\)\s*)?" +
               r"(?P<name>\\\S+|\w+)\s+\((?P<ports>.*?)\);")
    return list(re.finditer(pattern, clean(body), re.S))


def bus(name, width):
    return "{" + ",".join(f"{name}[{i}]" for i in range(width-1, -1, -1)) + "}"


def check(text, standalone_fixture=False):
    if not standalone_fixture:
        for parent, kind, inst in (
            ("soc_top", "core_top", "u_cpu"),
            ("core_top", "cpu_core_top", "u_cpu_wrapper"),
            ("cpu_core_top", "CoreTop", "u_cpu"),
            ("CoreTop", "Core", "core"),
            ("Core", "CoreFrontend", "frontend"),
            ("CoreFrontend", "Icache", "cache")):
            linked = cells(module(text, parent), kind)
            assert len(linked) == 1 and linked[0]["name"] == inst, f"Missing/duplicate actual top hierarchy: {parent}/{inst}"
    pad = module(text, "PangoIdentityPad")
    icache = module(text, "Icache")
    assert re.search(r"\binput\s+\[127:0\]\s+dataIn\b", pad), "Unknown pad input width"
    assert re.search(r"\boutput\s+\[127:0\]\s+dataOut\b", pad), "Unknown pad output width"
    assert re.search(r"\bwire\s+\[127:0\]\s+refillB0\s*;", icache), "Unknown actual refill FF bus width"
    primitives = cells(pad, "GTP_LUT6D")
    assert len(primitives) == 64, "Not 64 dual LUT primitives"
    seen = set()
    for cell in primitives:
        name = re.fullmatch(r"\\data_pad\[(\d+)\]\.u_hold_dual_lut", cell["name"])
        assert name, "Unknown pad primitive name"
        i = int(name[1])
        assert 0 <= i < 64 and i not in seen, "Duplicate/out-of-range primitive"
        seen.add(i)
        assert cell["attr"] is not None and cell["attr"].strip() == "(* PAP_DONT_TOUCH *)", "Missing native preservation attribute"
        assert ports(cell["params"]) == {"INIT": "64'b" + f"{0xCCCCCCCCAAAAAAAA:064b}"}, "Identity INIT differs"
        assert ports(cell["ports"]) == {
            "Z": f"dataOut[{2*i+1}]", "Z5": f"dataOut[{2*i}]",
            "I0": f"dataIn[{2*i}]", "I1": f"dataIn[{2*i+1}]",
            "I2": "1'b0", "I3": "1'b0", "I4": "1'b0", "I5": "1'b1"}, "Identity primitive connections differ"
    for name in ("dataIn", "dataOut"):
        counts = Counter(map(int, re.findall(r"\b" + name + r"\[(\d+)\]", clean(pad))))
        assert counts == Counter({i: 1 for i in range(128)}), "Unknown extra pad driver/load"
    assert len(re.findall(r"\bGTP_\w+\s", clean(pad))) == 64, "Unexpected primitive in pad"
    assert not re.search(r"\bassign\b", clean(pad)), "Unknown pad alias/bypass"

    pad_instances = cells(icache, "PangoIdentityPad")
    assert len(pad_instances) == 1, "Pad is not uniquely instantiated by Icache"
    p = ports(pad_instances[0]["ports"])
    assert p == {"dataOut": bus("refillWriteLine", 128), "dataIn": "refillB0"}, "Actual shared pad bus differs"
    ff_bits = []
    for kind in sorted(set(re.findall(r"\bGTP_DFF\w*", clean(icache)))):
        for cell in cells(icache, kind):
            q = ports(cell["ports"]).get("Q", "")
            m = re.fullmatch(r"refillB0\[(\d+)\]", q)
            if m:
                ff_bits.append(int(m[1]))
    assert Counter(ff_bits) == Counter({i: 1 for i in range(128)}), "Missing/extra actual refill FF drivers"
    assert not re.search(r"\bassign\s+refillB0\b", clean(icache)), "Unexpected refill FF alias driver"

    ways = []
    expected = "{" + bus("nt_io_axiRetData" if standalone_fixture else "io_axiRetData", 128)[1:-1] + "," + bus("refillWriteLine", 128)[1:-1] + "}"
    for index, kind in enumerate(("wayMem_128x256", "wayMem_128x256_unq4")):
        child = cells(icache, kind)
        assert len(child) == 1 and child[0]["name"] == f"wayMem_{index}_ext", "Unexpected actual RAM hierarchy"
        assert ports(child[0]["ports"])["W0_data"] == expected, "Actual RAM write bus bypass/truncation/reordering"
        ram = module(text, kind)
        memory = cells(ram, "GTP_DRM36K_E1")
        lut_memory = cells(ram, "GTP_RAM128X1SP")
        all_memory_kinds = Counter(re.findall(r"\b(GTP_(?:DRM|RAM)\w+)\s", clean(ram)))
        consumed = []
        if len(memory) == 4 and not lut_memory:
            assert all_memory_kinds == {"GTP_DRM36K_E1": 4}, "Unknown/mixed RAM mapping"
            mapping = "4_GTP_DRM36K_E1"
            for cell in memory:
                params, pin = ports(cell["params"]), ports(cell["ports"])
                assert params["DATA_WIDTH_A"] == params["DATA_WIDTH_B"] == "64", "Unknown DRM width"
                for port in ("DIA", "DIB"):
                    expr = pin[port]
                    assert expr.startswith("{") and expr.endswith("}"), "Unknown DRM data expression"
                    for atom in expr[1:-1].split(","):
                        if atom == "1'b0":
                            continue
                        m = re.fullmatch(r"W0_data\[(\d+)\]", atom)
                        assert m, "Unknown RAM write-data driver"
                        consumed.append(int(m[1]))
        elif len(lut_memory) == 256 and not memory:
            assert all_memory_kinds == {"GTP_RAM128X1SP": 256}, "Unknown/mixed RAM mapping"
            mapping = "256_GTP_RAM128X1SP"
            for cell in lut_memory:
                pin = ports(cell["ports"])
                assert set(pin) == {"ADDR", "DO", "DI", "WCLK", "WE"}, "Unknown LUTRAM ports"
                assert pin["ADDR"] == "R0_addr" and pin["WCLK"] == "R0_clk" and pin["WE"] == "W0_en", "Unexpected LUTRAM write control"
                m = re.fullmatch(r"W0_data\[(\d+)\]", pin["DI"])
                assert m, "Unknown LUTRAM DI driver"
                consumed.append(int(m[1]))
        else:
            raise AssertionError("Unknown actual way RAM mapping; inspect before extending checker")
        assert Counter(consumed) == Counter({i: 1 for i in range(256)}), "RAM DI coverage differs"
        refs = Counter(map(int, re.findall(r"\bW0_data\[(\d+)\]", clean(ram))))
        assert refs == Counter({i: 1 for i in range(256)}), "Extra RAM write-data driver/load"
        assert re.search(r"\binput\s+\[255:0\]\s+W0_data\b", ram), "Unknown RAM data port width"
        assert len(re.findall(r"\bW0_data\b(?!\s*\[)", clean(ram))) == 1, "Unexpected whole RAM data-bus alias/load"
        assert not re.search(r"\bassign\s+W0_data\b", clean(ram)), "Unexpected RAM input alias driver"
        ways.append(dict(instance=child[0]["name"], module=kind, mapping=mapping,
                         write_bits_checked=256, padded_low_bits=128,
                         module_sha256=hashlib.sha256(ram.encode()).hexdigest()))
    refs = Counter(map(int, re.findall(r"\brefillWriteLine\[(\d+)\]", clean(icache))))
    assert refs == Counter({i: 3 for i in range(128)}), "Pad output must have one driver and both RAM loads only"
    assert len(re.findall(r"\brefillWriteLine\b(?!\s*\[)", clean(icache))) == 1, "Unexpected whole pad-output bus alias/load"
    assert not re.search(r"\bassign\s+refillWriteLine\b", clean(icache)), "Unexpected pad-output alias driver"
    return dict(primitive="GTP_LUT6D", pairs=64, bits=128, init="CCCCCCCC_AAAAAAAA",
                preservation_attribute="PAP_DONT_TOUCH", upstream_ff_bits=128,
                unique_driver_and_two_way_loads=True, bypass=False, ways=ways,
                pad_module_sha256=hashlib.sha256(pad.encode()).hexdigest(),
                icache_module_sha256=hashlib.sha256(icache.encode()).hexdigest())


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--project-root", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    assert not a.output.exists(), "Never overwrite prior review evidence"
    project = a.project_root.resolve()
    snapshot_path = project / "pds/build_snapshot.json"
    netlist = project / "pds/synthesize/soc_top_syn.vm"
    core = project / "rtl/cpu/CoreTop.sv"
    cpu_source = project / "rtl/cpu/source.json"
    config = project / "rtl/cpu/emit-config.json"
    checker = Path(__file__).resolve()
    assert checker == project / "scripts/audit_icache_pad_ads.py", "Run the frozen project checker"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8-sig"))
    assert snapshot.get("run_id") and snapshot.get("started_utc"), "Missing run binding"
    start_ns = utc_timestamp_ns(snapshot["started_utc"])
    assert netlist.stat().st_mtime_ns >= start_ns, "ADS output predates run"
    for path in (core, cpu_source, config, checker):
        assert snapshot["inputs"][path.relative_to(project).as_posix()] == sha(path), "Current CPU input differs from snapshot"
    provenance = json.loads(cpu_source.read_text(encoding="utf-8-sig"))
    assert provenance["sha256"] == sha(core) and provenance["config_sha256"] == sha(config), "CPU provenance mismatch"
    hashes = {path.relative_to(project).as_posix(): sha(path) for path in (snapshot_path, netlist, core, cpu_source, config, checker)}
    result = dict(schema=1, status="FAIL", scope="INTEGRATED_ADS_ONLY",
                  run_id=snapshot["run_id"], input_snapshot_sha256=sha(snapshot_path),
                  netlist_sha256=sha(netlist), source_rtl_sha256=sha(core),
                  source_json_sha256=sha(cpu_source), emit_config_sha256=sha(config),
                  checker_sha256=sha(Path(__file__)), input_hashes=hashes,
                  hierarchy="soc_top/u_cpu/u_cpu_wrapper/u_cpu/core/frontend/cache",
                  post_pnr_physical_retention_proven=False, routed_hold_margin_proven=False)
    try:
        result["connectivity"] = check(netlist.read_text())
        for rel, expected in hashes.items():
            assert sha(project / rel) == expected, "Input changed during check: " + rel
        result["inputs_unchanged"] = True
        result["status"] = "PASS"
    except Exception as exc:
        result["failure"] = str(exc)
        raise
    finally:
        a.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
