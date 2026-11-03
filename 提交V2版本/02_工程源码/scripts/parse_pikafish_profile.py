"""Validate measured NNUE profile hierarchies; nested timings are inclusive."""
import argparse
import json
from pathlib import Path
import re

from profile_pikafish_nnue import STAGES

GROUPS = {
    "network": ["accumulator", "feature_transform", "fc0", "activation0", "fc1", "activation1", "fc2", "mlp_post"],
    "accumulator": ["refresh_psq_indices", "refresh_threat_indices", "refresh_vectors", "refresh_psqt"],
    "refresh_vectors": ["stagea_session", "stagea_descriptors", "stagea_copyin", "stagea_gather", "stagea_copyout"],
    "fc0": ["fc0_setup", "fc0_pack", "fc0_submit", "fc0_merge"],
    "fc0_submit": ["fc0_ioctl"],
}


def parse(text, hardware=False):
    if "NNUE_LATENCY_CORRECTNESS_PASS" not in text or "NNUE_LATENCY_FAIL" in text:
        raise ValueError("Integer correctness was not established")
    if hardware:
        if "NNUE_CLOCK_SOURCE source=clint hz=49500000 address=0200bff8 readonly=1" not in text:
            raise ValueError("Calibrated board clock was not established")
        if re.search(r"PIKAFISH_MAC_RUNTIME_READY[^\n]*backend=driver", text) is None:
            raise ValueError("Kernel driver ownership was not established")
        if re.search(r"PIKAFISH_STAGEB_ACCEL_STATS[^\n]*fallbacks=0 mismatches=0", text) is None:
            raise ValueError("Hardware fallback or mismatch")
    result = {"timing_scope": "Network::evaluate only; inclusive nested profile; load/FEN/search excluded", "phases": {}}
    for phase in ("cold", "warm"):
        rows = {}
        pattern = rf"NNUE_PROFILE phase={phase} stage=(\w+) calls=(\d+) total_ns=(\d+) mean_us=(\d+)"
        for name, calls, total, mean in re.findall(pattern, text):
            if name in rows: raise ValueError(f"Duplicate {phase}/{name}")
            rows[name] = {"calls": int(calls), "total_ns": int(total)}
        if set(rows) != set(STAGES): raise ValueError(f"Incomplete {phase} profile")
        match = re.search(rf"NNUE_LATENCY phase={phase} samples=(\d+) mean_us=(\d+) min_us=(\d+) p50_us=(\d+) p95_us=(\d+) max_us=(\d+)", text)
        if not match: raise ValueError(f"Missing {phase} latency")
        samples, mean, minimum, p50, p95, maximum = map(int, match.groups())
        for name in ("network", "accumulator", "feature_transform", "fc0", "activation0", "fc1", "activation1", "fc2", "mlp_post"):
            if rows[name]["calls"] != samples: raise ValueError(f"Wrong {phase}/{name} sample count")
        for name in ("refresh_psq_indices", "refresh_threat_indices", "refresh_vectors", "refresh_psqt"):
            if rows[name]["calls"] != samples*2: raise ValueError(f"Wrong {phase}/{name} perspective count")
        residuals = {}
        for parent, children in GROUPS.items():
            residual = rows[parent]["total_ns"]-sum(rows[n]["total_ns"] for n in children)
            if residual < 0: raise ValueError(f"Double counting or invalid clock in {phase}/{parent}")
            residuals[parent] = residual/samples/1e6
        if abs(mean/1000-rows["network"]["total_ns"]/samples/1e6) > .5:
            raise ValueError(f"Outer clock disagrees with network in {phase}")
        if hardware:
            for name in ("fc0_pack", "fc0_submit", "fc0_ioctl", "fc0_merge"):
                if rows[name]["calls"] != samples*4: raise ValueError(f"Wrong {phase}/{name} tile count")
            match = re.search(rf"NNUE_LATENCY_BREAKDOWN phase={phase} gather_jobs=(\d+) gather_terms=(\d+) gather_cycles=(\d+) gather_ioctl_mean_us=(\d+) fc0_cycles=(\d+) fc0_host_mean_us=(\d+) resident=(\d+)", text)
            if not match or match[7] != "1": raise ValueError("Strict resident hardware was not established")
            jobs, terms, cycles, ioctl_us, fc_cycles, host_us, _ = map(int, match.groups())
            for name in ("stagea_descriptors", "stagea_copyin", "stagea_gather", "stagea_copyout"):
                if rows[name]["calls"] != jobs: raise ValueError(f"Wrong {phase}/{name} gather count")
            result.setdefault("hardware", {})[phase] = {
                "gather_jobs": jobs, "gather_terms": terms, "gather_cycles": cycles,
                "fc0_cycles": fc_cycles, "gather_hw_mean_ms": cycles/samples/49500,
                "fc0_hw_mean_ms": fc_cycles/samples/49500,
                "gather_ioctl_existing_mean_ms": ioctl_us/1000, "fc0_host_existing_mean_ms": host_us/1000,
                "gather_copy_bytes_per_eval": (4096*jobs+4*terms)/samples,
                "fc0_copy_bytes_per_eval": 2560,
            }
            if re.search(rf"NNUE_LATENCY_BACKEND phase={phase}[^\n]*fused=0", text) is None:
                raise ValueError("Hardware runtime fused")
        for row in rows.values(): row["mean_ms"] = row["total_ns"]/samples/1e6
        result["phases"][phase] = {"samples": samples, "mean_ms": mean/1000, "p50_ms": p50/1000, "p95_ms": p95/1000,
                                   "min_ms": minimum/1000, "max_ms": maximum/1000, "stages": rows, "unattributed_ms": residuals}
    cal = re.search(r"NNUE_PROFILE_CALIBRATION pairs=10000 mean_pair_ns=(\d+)", text)
    if not cal: raise ValueError("Missing probe overhead calibration")
    result["mean_probe_pair_ns"] = int(cal[1])
    micro = []
    for engine, terms, cin, cout, samples, host, hw, cycles, copied in re.findall(
            r"NNUE_MICRO engine=(gather|dense) terms=(\d+) cin=(\d+) cout=(\d+) samples=(\d+) host_mean_us=(\d+) hw_mean_us=(\d+) cycles=(\d+) copy_bytes=(\d+) mismatches=0", text):
        micro.append(dict(engine=engine, terms=int(terms), cin=int(cin), cout=int(cout), samples=int(samples),
                          host_mean_ms=int(host)/1000, hw_mean_ms=int(cycles)/int(samples)/49500,
                          cycles=int(cycles), copy_bytes=int(copied), correctness="exact zero output"))
    if "NNUE_MICRO" in text:
        if "NNUE_MICRO_CORRECTNESS_PASS" not in text or len(micro) != 13:
            raise ValueError("Incomplete microbenchmark correctness")
        expected = {('gather', n, 0, 1024) for n in (2,4,16,64,256)}
        expected |= {('dense', 0, n, c) for n in (4,16,64,256) for c in (1,32)}
        if {(m['engine'],m['terms'],m['cin'],m['cout']) for m in micro} != expected:
            raise ValueError("Duplicate or missing microbenchmark workload")
        for m in micro:
            copied = 4096+m['terms']*4 if m['engine']=='gather' else m['cin']*2+m['cout']*4
            if m['samples']!=50 or m['cycles']<=0 or m['copy_bytes']!=copied:
                raise ValueError("Invalid microbenchmark counters")
        result["microbenchmarks"] = micro
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--hardware", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evidence = parse(args.log.read_text(encoding="ascii", errors="replace"), args.hardware)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("PIKAFISH_PROFILE_ACCOUNTING_PASS", args.output)
