"""Audit trained YOLO shapes against the current source-level MAC capabilities.

Dense plans describe a possible software backend, never an implemented or tested
model backend. Source capability inspection cannot replace live GET_INFO or
calibrated integer model/board acceptance.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import re
import time
from pathlib import Path


def source_capabilities(root: Path) -> dict:
    sources = {name: (root / name).read_text() for name in (
        "rtl/mac_accel/mac_conv_compute_core.v",
        "rtl/mac_accel/mac_conv_descriptor_guard.v",
        "linux/mac_accel/kernel/pango_mac.c", "linux/mac_accel/pango_mac_uapi.h",
        "linux/pikafish/pikafish_mac_runtime.h", "linux/cpu_v2.dts")}
    core = sources["rtl/mac_accel/mac_conv_compute_core.v"]
    driver = sources["linux/mac_accel/kernel/pango_mac.c"]

    def number(pattern, source):
        match = re.search(pattern, source)
        if not match:
            raise ValueError(f"capability source changed or missing: {pattern}")
        return int(match.group(1), 0)

    return {
        "scope": "source profile; query GET_INFO on the actual board before execution",
        "conv_max_cin": number(r"\bchannels\s*<=\s*(\d+)", core),
        "conv_max_cout": number(r"\boutput_channels\s*<=\s*(\d+)", core),
        "conv_max_k": number(r"channels\s*\*\s*kernel\s*\*\s*kernel\s*<=\s*(\d+)", core),
        "conv_max_dimension": number(r"\bwidth\s*>\s*(\d+)", sources["rtl/mac_accel/mac_conv_descriptor_guard.v"]),
        "dense_max_pixels": number(r"#define\s+PANGO_MAC_MAX_PIXELS\s+(\d+)u", driver),
        "dense_max_channels": number(r"#define\s+PANGO_MAC_MAX_CHANNELS\s+(\d+)u", driver),
        "scratch_bytes": number(r"mac_accel_mem:\s*mac-accel@1b000000\s*\{\s*reg\s*=\s*<0x1b000000\s+(0x[0-9a-f]+)>", sources["linux/cpu_v2.dts"]),
        "s8s8_mode": number(r"\bS8S8\s*=\s*(\d+)", sources["linux/pikafish/pikafish_mac_runtime.h"]),
        "int32_output_format": number(r"\bI32\s*=\s*(\d+)", sources["linux/pikafish/pikafish_mac_runtime.h"]),
        "source_sha256": {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sources},
    }


def audit_layers(layers: list[dict], caps: dict) -> dict:
    required = ("conv_max_cin", "conv_max_cout", "conv_max_k", "conv_max_dimension",
                "dense_max_pixels", "dense_max_channels", "scratch_bytes")
    if any(type(caps.get(k)) is not int or caps[k] <= 0 for k in required):
        raise ValueError("invalid or missing accelerator limits")
    started = time.perf_counter()
    rows = []
    for layer in layers:
        if layer["operator"] != "Conv2d":
            continue
        n, cin, h, w = layer["input_shape"]
        on, cout, oh, ow = layer["output_shape"]
        wc, wcin, kh, kw = layer["weight_shape"]
        sh, sw = layer["stride"]
        ph, pw = layer["padding"]
        groups = layer["groups"]
        if (min(n, on, cin, cout, h, w, oh, ow, kh, kw, sh, sw, groups) <= 0 or
                n != 1 or on != 1 or wc != cout or cin != wcin * groups or
                min(ph, pw) < 0 or oh != (h + 2*ph-kh)//sh + 1 or
                ow != (w + 2*pw-kw)//sw + 1):
            raise ValueError("invalid convolution geometry or weights")
        k = wcin * kh * kw
        macs = oh * ow * cout * k
        rejections = []
        if cin > caps["conv_max_cin"]:
            rejections.append("Cin exceeds ABI3 limit")
        if cout > caps["conv_max_cout"]:
            rejections.append("Cout exceeds ABI3 limit")
        if k > caps["conv_max_k"]:
            rejections.append("K exceeds ABI3 limit")
        if (groups != 1 or kh != kw or kh not in (1, 3, 6) or
                sh != sw or sh not in (1, 2) or ph != pw or ph >= kh or
                (kh == 1 and ph != 0) or max(h, w) > caps["conv_max_dimension"]):
            rejections.append("geometry unsupported by ABI3")
        windows = oh * ow
        dense_channels = caps["dense_max_channels"]
        dense_pixels = caps["dense_max_pixels"]
        job_k, job_cout, job_pixels = min(k, dense_channels), min(cout, dense_channels), min(windows, dense_pixels)
        input_bytes = job_pixels * math.ceil(job_k / 4) * 8
        weight_bytes = math.ceil(job_cout / 32) * math.ceil(job_k / 4) * 128
        output_bytes = job_pixels * job_cout * 4
        peak_bytes = input_bytes + weight_bytes + output_bytes
        planned_jobs = math.ceil(windows / dense_pixels) * math.ceil(k / dense_channels) * math.ceil(cout / dense_channels)
        plan = {"implemented": False, "model_backend_tested": False,
                "shape_feasible": groups == 1 and peak_bytes <= caps["scratch_bytes"],
                "jobs": planned_jobs, "k_segments": math.ceil(k / dense_channels),
                "max_pixels_per_job": job_pixels, "max_k_per_job": job_k,
                "max_cout_per_job": job_cout, "output_tail_channels": cout % 32,
                "peak_job_bytes": peak_bytes,
                "mode": "S8S8", "output": "INT32", "zero_bias": True,
                "out_shift": 0, "activation": 0,
                "required_software": "im2col; INT32 segment sum; bias once; final requant once"}
        rows.append({"name": layer["name"], "cin": cin, "cout": cout, "kernel": [kh, kw],
                     "k": k, "output_hw": [oh, ow], "macs": macs,
                     "direct_conv_shape": not rejections,
                     "direct_conv_rejections": rejections, "dense_plan": plan})
    if not rows:
        raise ValueError("graph has no convolutions")
    total = sum(r["macs"] for r in rows)
    direct = [r for r in rows if r["direct_conv_shape"]]
    direct_macs = sum(r["macs"] for r in direct)
    return {"schema_version": 1, "capabilities": caps,
            "conv_count": len(rows), "conv_macs": total,
            "direct_conv_shape_count": len(direct), "direct_conv_macs": direct_macs,
            "direct_conv_macs_percent": direct_macs / total * 100,
            "direct_conv_names": [r["name"] for r in direct], "max_k": max(r["k"] for r in rows),
            "whole_model_conv_abi_ready": len(direct) == len(rows),
            "device_model_ready": False, "live_device_verified": False,
            "dense_model_backend_implemented": False,
            "dense_planned_jobs": sum(r["dense_plan"]["jobs"] for r in rows),
            "leaf_operator_counts": dict(collections.Counter(l["operator"] for l in layers)),
            "blocking_requirements": ["W8A8 calibration and device packaging",
                                      "complete convolution backend and graph runtime",
                                      "verified CPU SiLU/residual/Concat/MaxPool/Upsample/Detect/NMS",
                                      "live driver identity, serialized ownership and board acceptance"],
            "quantization": "ABI3: S8, INT32 bias, shift 0..30, half-away rounding; no general scale multiplier",
            "dense_warning": "planned matrix jobs; CPU packing/copies/partial sums are unmeasured; not a speedup claim",
            "convs": rows, "audit_elapsed_ms": round((time.perf_counter()-started)*1000, 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-device-ready", action="store_true")
    args = parser.parse_args()
    graph = json.loads(args.graph.read_text())
    digest = hashlib.sha256(args.model.read_bytes()).hexdigest()
    if graph.get("model_sha256") != digest:
        raise ValueError("execution graph does not belong to this checkpoint")
    report = audit_layers(graph["layers"], source_capabilities(Path(__file__).resolve().parents[1]))
    report["model_sha256"] = digest
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"ACCELERATOR_COMPAT_AUDIT_PASS direct_conv_shapes={report['direct_conv_shape_count']}/{report['conv_count']} "
          f"mac_coverage={report['direct_conv_macs_percent']:.4f}% device_ready=False "
          f"dense_planned_jobs={report['dense_planned_jobs']}")
    if args.require_device_ready and not report["device_model_ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
