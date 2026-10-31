"""Read graph/parameter files only; export the upstream 80-layer interface inventory.

Uses Python's standard library, never imports the inference/training pipeline or
opens examples, photographs, predictions, calibration lists or game annotations.
The native pack and source NPZ must agree byte for byte before anything is emitted.
"""
import argparse
import ast
import collections
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import zipfile
import zlib

REPO = Path(__file__).resolve().parents[2]
ADAPTER = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def rel(path):
    return path.resolve().relative_to(REPO).as_posix()


def npy(data):
    require(data[:6] == b"\x93NUMPY", "NPY magic")
    version = tuple(data[6:8])
    require(version in ((1, 0), (2, 0)), "NPY version")
    width = 2 if version[0] == 1 else 4
    length = int.from_bytes(data[8:8 + width], "little")
    end = 8 + width + length
    header = ast.literal_eval(data[8 + width:end].decode("latin1"))
    require(not header["fortran_order"], "Fortran-order tensor")
    dtype = header["descr"]
    require(dtype in ("|i1", "<i4", "<i8"), "unexpected parameter dtype: " + dtype)
    raw = data[end:]
    size = int(dtype[-1])
    require(len(raw) == math.prod(header["shape"]) * size, "NPY length")
    values = [v[0] for v in struct.iter_unpack({1: "<b", 4: "<i", 8: "<q"}[size], raw)]
    return dict(shape=list(header["shape"]), dtype=dtype, raw=raw, values=values)


def dense_plan(cin, cout, kh, kw, oh, ow, batch):
    k = cin * kh * kw
    m = batch * oh * ow
    co_step = min(256, 32 * (64 // math.ceil(min(k, 256) / 4)))
    histogram = collections.Counter()
    # Histograms rather than all jobs: retain exact spatial and K/Cout tails.
    ms = collections.Counter(min(16, m - x) for x in range(0, m, 16))
    ks = collections.Counter(min(256, k - x) for x in range(0, k, 256))
    ns = collections.Counter(min(co_step, cout - x) for x in range(0, cout, co_step))
    for mt, mc in ms.items():
        for nt, nc in ns.items():
            for kt, kc in ks.items():
                require(math.ceil(kt / 4) * math.ceil(nt / 32) <= 64, "bank64 overflow")
                histogram[mt, kt, nt] += mc * kc * nc
    jobs = sum(histogram.values())
    require(jobs == math.ceil(m / 16) * math.ceil(k / 256) * math.ceil(cout / co_step), "job count")
    return dict(batch=batch, M=m, K=k, N=cout, output_channel_step=co_step,
                jobs=jobs, MACs=m * k * cout,
                job_shapes=[dict(M=mt, K=kt, N=nt, count=count,
                                 weight_bank_lines=math.ceil(kt / 4) * math.ceil(nt / 32))
                            for (mt, kt, nt), count in sorted(histogram.items())],
                # An operation-count floor is NOT the hardware busy counter.
                ideal_compute_cycles_at_128_MACs_per_cycle=math.ceil(m * k * cout / 128),
                measured_busy_cycles=None,
                busy_cycle_scope="sum(job.cycles) at SYS/MAC 49.5MHz; unmeasured for CPU80/r14")


def collect(candidate, models):
    selector_path = ADAPTER / "working_combination.json"
    selector = load(selector_path)
    selected = selector["profiles"]["working-r14"]
    require(selector["default_profile"] == "working-r14" and selector["default_backend"] == "fp32", "default changed")
    graph_path = candidate / "integer_graph.json"
    graph = load(graph_path)
    require(sha(graph_path.read_bytes()) == selected["quantized_graph_sha256"], "graph identity")
    require(graph["model_SHA256"] == {k: v["sha256"] for k, v in selected["models"].items()}, "model identity")
    manifest_path = models / "native_manifest.json"
    manifest = load(manifest_path)
    require(manifest["source_graph_sha256"] == selected["quantized_graph_sha256"], "native source graph")
    sources = {rel(p): sha(p.read_bytes()) for p in (selector_path, graph_path, manifest_path)}
    metas = graph["layers"]
    require(len(metas) == 80 and len({x["layer_id"] for x in metas}) == 80, "80 unique layers required")
    rows = {}
    for model_index, name in enumerate(("board", "detector", "classifier")):
        mm = manifest["models"][name]
        path = models / mm["file"]
        data = path.read_bytes()
        require(sha(data) == mm["sha256"] and len(data) == mm["bytes"], "native file identity")
        sources[rel(path)] = sha(data)
        require(data[:8] == b"XQGRPH1\0", "native magic")
        h = struct.unpack_from("<10I", data, 8)
        require(h[0] in (1, 2) and h[1] == model_index and h[2] == mm["nodes"], "native header")
        body = data[48:]
        require(len(body) == h[8] and zlib.crc32(body) == h[9], "native body CRC")
        desc = 16 if h[0] == 2 else 0
        nodes = [struct.unpack_from("<32i", body, desc + i * 128) for i in range(h[2])]
        blob = body[desc + h[2] * 128:]
        require(len(blob) == h[7], "native blob size")
        for ni, n in enumerate(nodes):
            if n[0] != 1:
                continue
            meta = metas[n[9]]
            ident = meta["layer_id"]
            require(ident == mm["labels"][ni] and meta["model_name"] == name and ident not in rows, "native layer mapping")
            parent = n[5]
            require(-1 <= parent < ni and n[4] == 1, "native qop parent")
            cin, ih, iw = mm["input_shape"] if parent == -1 else nodes[parent][1:4]
            cout, oh, ow = n[1:4]
            kh, kw, sh, sw, ph, pw, dh, dw = n[10:18]
            linear = meta["kind"] == "linear"
            require(n[25] == int(linear) and meta.get("groups", 1) == 1, "kind/groups")
            expected_shape = [cout, cin] if linear else [cout, cin, kh, kw]
            require(meta["weight_shape"] == expected_shape, "weight geometry")
            require([sh, sw] == meta.get("stride", [1, 1]) and [ph, pw] == meta.get("padding", [0, 0])
                    and [dh, dw] == meta.get("dilation", [1, 1]), "source geometry")
            require(oh == (ih + 2 * ph - dh * (kh - 1) - 1) // sh + 1
                    and ow == (iw + 2 * pw - dw * (kw - 1) - 1) // sw + 1, "output geometry")
            tensor_path = candidate / "int8" / (ident + ".npz")
            tensor_sha = sha(tensor_path.read_bytes())
            require(tensor_sha == mm["source_tensors"][ident], "source parameter identity")
            sources[rel(tensor_path)] = tensor_sha
            with zipfile.ZipFile(tensor_path) as z:
                tensors = {key: npy(z.read(key + ".npy")) for key in ("weight", "bias", "right_shifts", "activation_lut")}
            sizes = [cout * cin * kh * kw, cout * 4, cout * 8, n[24]]
            for key, offset, size in zip(tensors, n[20:24], sizes):
                require(0 <= offset <= len(blob) - size, "parameter range")
                require(tensors[key]["raw"] == blob[offset:offset + size], "packed/source tensor mismatch: " + ident + "/" + key)
            require(tensors["weight"]["shape"] == expected_shape, "NPZ weight shape")
            require(tensors["bias"]["shape"] == [cout] and tensors["right_shifts"]["shape"] == [cout], "per-channel tensors")
            shifts = tensors["right_shifts"]["values"]
            exps = meta["weight_exponents"]
            inp_exp = meta["input_exponent"]
            pre_exp = meta["preactivation_S16_exponent"]
            has_lut = n[24] == 65536
            require(n[24] in (0, 65536) and n[18] == inp_exp, "LUT/input exponent")
            out_exp = meta["output_exponent"] if has_lut else pre_exp
            require(n[19] == out_exp and len(exps) == cout and shifts == meta["right_shifts"], "quantization metadata")
            require(all(0 <= v <= 62 for v in shifts) and shifts == [pre_exp - inp_exp - e for e in exps], "shift equation")
            weight = tensors["weight"]["values"]
            bias = tensors["bias"]["values"]
            k = cin * kh * kw
            bounds = [abs(bias[c]) + 128 * sum(abs(w) for w in weight[c * k:(c + 1) * k]) for c in range(cout)]
            require(max(bounds) <= 2147483647, "I32 overflow bound")
            batch = 1
            row = dict(index=n[9], layer_id=ident, model=name, kind=meta["kind"], native_node=ni,
                       input_shape_NCHW=[batch, cin, ih, iw], output_shape_NCHW=[batch, cout, oh, ow],
                       Cin=cin, Cout=cout, H=ih, W=iw, Hout=oh, Wout=ow,
                       kernel=[kh, kw], stride=[sh, sw], padding=[ph, pw], dilation=[dh, dw], groups=1,
                       weight_shape=expected_shape,
                       quantization=dict(input_dtype="int8", weight_dtype="int8", zero_point=0,
                           input_exponent=inp_exp, input_scale=2.0 ** inp_exp,
                           weight_exponents=exps, weight_scales=[2.0 ** e for e in exps],
                           bias_dtype="int32", bias=bias, bias_scales=[2.0 ** (inp_exp + e) for e in exps],
                           accumulator_dtype="int32", per_channel_safe_abs_bound=bounds,
                           preactivation_dtype="int16", preactivation_exponent=pre_exp,
                           preactivation_scale=2.0 ** pre_exp, right_shifts=shifts,
                           rounding="nearest_ties_to_even_signed_magnitude", preactivation_clip=[-32768, 32767],
                           activation=meta["activation"], lut_entries=n[24],
                           lut_dtype="int8" if has_lut else None,
                           lut_index="preactivation_s16 + 32768" if has_lut else None,
                           lut_raw_sha256=sha(tensors["activation_lut"]["raw"]) if has_lut else None,
                           output_dtype=meta["output_dtype"], effective_output_exponent=out_exp,
                           effective_output_scale=2.0 ** out_exp,
                           metadata_output_exponent=meta["output_exponent"]),
                       parameters=dict(npz=rel(tensor_path), npz_sha256=tensor_sha,
                           native_file=rel(path), native_blob_file_offset=48 + desc + len(nodes) * 128,
                           blob_offsets=dict(zip(tensors, n[20:24])),
                           raw_sha256={key: sha(t["raw"]) for key, t in tensors.items()}),
                       dense_bank64=dense_plan(cin, cout, kh, kw, oh, ow, batch),
                       CPU80_measured_busy_cycles=None)
            if name == "classifier":
                row["dense_bank64_batch211_historical_shape_reference"] = dense_plan(cin, cout, kh, kw, oh, ow, 211)
            rows[n[9]] = row
    require(set(rows) == set(range(80)), "native graph coverage")
    rows = [rows[i] for i in range(80)]
    require(collections.Counter(r["model"] for r in rows) == dict(board=12, detector=60, classifier=8), "model layer counts")
    old_path = REPO / "docs/validation/picture-p20-combined-20261020/dense-plan-bank64.json"
    old = {r["layer"]: r for r in load(old_path)["layers"]}
    sources[rel(old_path)] = sha(old_path.read_bytes())
    for row in rows:
        ref = old[row["layer_id"]]
        plan = row.get("dense_bank64_batch211_historical_shape_reference", row["dense_bank64"])
        require((plan["M"], plan["K"], plan["N"], plan["jobs"], plan["MACs"]) ==
                (ref["m"], ref["k"], ref["n"], ref["dense_jobs"], ref["MACs"]), "historical shape/job disagreement")
    totals = {}
    for name in ("board", "detector", "classifier"):
        rr = [r for r in rows if r["model"] == name]
        totals[name] = dict(layers=len(rr), batch1_jobs=sum(r["dense_bank64"]["jobs"] for r in rr),
                            batch1_MACs=sum(r["dense_bank64"]["MACs"] for r in rr))
    return dict(schema_version=1, scope="Upstream raw-I32/shape interface design input; graph/parameters only; no board or accuracy acceptance",
                profile="working-r14", default_backend="fp32", quantized_gate=False, production_ready=False,
                hardware_identity=dict(bitstream_sha256="30d8f0d5ccdefcf9225780965df3efd399b9b9f27eb390d849754fcd57d526f1",
                                       CPU_Hz=80000000, SYS_MAC_Hz=49500000),
                model_sha256=graph["model_SHA256"], source_graph_sha256=sha(graph_path.read_bytes()),
                sources=sources, totals=totals, layers=rows,
                contract=dict(layer_count=80, convolution_layers=77, linear_layers=3,
                    shape_layout="NCHW; linear also normalized to [B,C,1,1]", weight_layout="OIHW or OI",
                    dense_K_order="input_channel, kernel_y, kernel_x",
                    dense_tiling="M<=16, K<=256, Cout step=min(256,32*floor(64/ceil(min(K,256)/4))); joint bank guard retained",
                    partial_sum="exact S8*S8 raw I32 for each K tile, no shift/clipping; I64 host merge, bias once, I32 range check",
                    requantization="sat_s16(round_ties_even(acc_with_bias / 2**shift[oc])); optional exhaustive S8 LUT; dequantize to FP32",
                    classifier_batch="inventory B=1; runtime candidate batch varies (1..256); exact plan B=211 retained only as historical shape reference",
                    busy_cycles="sum successful job.cycles (MAC49.5MHz), excludes CPU/packing/driver/IPC/capture/refine; no CPU80/r14 per-layer measurement exists",
                    ABI3_eligible_layers=0, gray_default="off",
                    timeout_cancel_audio="retain per-job timeout/error, cancellable tiles and safe drain; upstream must specify abort/reset/restart and audio-yield semantics; no new ioctl assigned here"))


def write_inventory(report, out):
    out.mkdir(parents=True, exist_ok=True)
    jp = out / "layers.json"
    jp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    columns = ["index", "model", "layer_id", "kind", "Cin", "Cout", "H", "W", "Hout", "Wout", "kernel", "stride", "padding", "dilation",
               "input_exponent", "weight_exponents", "preactivation_exponent", "right_shifts", "activation", "lut_entries", "effective_output_exponent", "batch1_jobs", "CPU80_measured_busy_cycles"]
    with (out / "layers.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, columns)
        writer.writeheader()
        for r in report["layers"]:
            q = r["quantization"]
            row = {k: r[k] for k in columns if k in r}
            row.update({k: q[k] for k in columns if k in q})
            row["batch1_jobs"] = r["dense_bank64"]["jobs"]
            writer.writerow({k: json.dumps(v, separators=(",", ":")) if isinstance(v, list) else v for k, v in row.items()})
    totals = report["totals"]
    lines = ["# 80 层逐层形状与量化参数清单（2026-10-23）", "",
             "供上游第二轮 raw-I32 / 形状及分块接口设计使用。绑定 working-r14；未改变模型、默认 FP32、PN02 或验收门槛。", "",
             "完整逐通道 exponent/scale/shift、bias、LUT SHA 与偏移、精确作业形状直方图见 [layers.json](layers.json)；表格导入见 [layers.csv](layers.csv)。", "",
             "## 身份与范围", "",
             "- board192：12 层；detector640：60 层；classifier32-v3d-QAT：8 层。共 80 个量化算子，77 Conv + 3 Linear（不是 80 个卷积）。",
             "- 源 integer_graph SHA256：`" + report["source_graph_sha256"] + "`。",
             "- 图结构和参数包与当前 native .xqm 逐字节核对；只读模型图/参数，不读取照片、帧数据、game2 标注或预测。",
             "- 形状为 NCHW；表中 batch=1，Linear 规范为 C×1×1。分类器候选数随拍摄变化，不能把 32×32 输入大小当作 batch=32。", ""]
    for name, digest in report["model_sha256"].items():
        lines.append("- " + name + " 模型 SHA256：`" + digest + "`。")
    lines += ["", "## 精确量化与接口要求", "",
              "输入 q=sat_s8(round_ties_even(x/2^input_exp))，权重逐输出通道 scale=2^weight_exp，zero_point=0。",
              "raw-I32 必须保留每个 K 块的精确 S8×S8 部分和，不做激活、shift、舍入或饱和。主机以 I64 合并、bias 只加一次，再检查 I32 范围。",
              "shift[oc]=pre_exp-input_exp-weight_exp[oc]；pre=sat_s16(round_ties_even(acc/2^shift[oc]))。",
              "SiLU/ReLU 使用原始 65536 项 S8 LUT，索引 pre+32768，随后按 output_exp 反量化；Identity 保留 S16，实际反量化指数是 pre_exp，不能套用元数据 output_exp。",
              "JSON 保留逐通道 bias 与保守绝对累加界限，并标明 OIHW/OI 排列。ABI3 的 NHWC4/tap-interleaved 排列不能直接复制 OIHW；新接口由上游明确布局。",
              "超时、取消、安全排空、复位后重启和音频让出边界由上游明确；本清单不擅自定义 ioctl 编号或扩大现有 bank64/1MiB。", "",
              "## dense 参考与忙周期口径", "",
              "K=Cin×Kh×Kw；M=B×Hout×Wout；N=Cout。M 分块≤16、K 分块≤256；Cout 步长=min(256,32×floor(64/ceil(min(K,256)/4)))。",
              "每个块严格满足 ceil(Ktile/4)×ceil(Ntile/32)≤64。作业数=ceil(M/16)×ceil(K/256)×ceil(N/Cout_step)，包括尾块。",
              "busy cycles 只按成功作业 job.cycles 累加，除以 49,500,000 得忙秒；不含采集、准备、CPU 图/精修、锁等待、驱动或 IPC。",
              "当前 CPU80/r14 尚无逐层实测忙周期，JSON 的对应字段为 null；ideal_compute_cycles 仅为 128 MAC/cycle 的运算量下界，绝非 busy 测量或时延预测。", "",
              "| 模型 | 层数 | batch=1 作业数 | batch=1 MAC |", "|---|---:|---:|---:|"]
    for name, t in totals.items():
        lines.append(f"| {name} | {t['layers']} | {t['batch1_jobs']} | {t['batch1_MACs']} |")
    lines += ["", "历史 E8/v1 三模型忙周期是 board=13,133,090、detector=327,732,335、classifier(batch211)=201,560,921，",
              "来源为 [旧板测绑定](../picture-p21-runtime-20261020/device-golden-binding.json)，不是 CPU80/r14 的逐层数据。",
              "JSON 另给 classifier 的 B=211 形状参考（28,499 作业）；不据此外推当前权重忙周期或整拍 P50/P95。", "",
              "## 逐层表", "",
              "e 列依次为 input/pre/effective output 指数；shift 范围仅便于阅读，完整逐通道数组以 JSON/CSV 为准。", "",
              "| # | 模型 / layer id | kind | Cin / Cout | H×W → Hout×Wout | k / s / p | e(in/pre/out) | shift范围 | LUT | B1 jobs |",
              "|---:|---|---|---|---|---|---|---|---|---:|"]
    for r in report["layers"]:
        q = r["quantization"]
        geom = " / ".join("×".join(map(str, r[k])) for k in ("kernel", "stride", "padding"))
        lines.append(f"| {r['index']} | {r['layer_id']} | {r['kind']} | {r['Cin']}/{r['Cout']} | {r['H']}×{r['W']} → {r['Hout']}×{r['Wout']} | {geom} | {q['input_exponent']}/{q['preactivation_exponent']}/{q['effective_output_exponent']} | {min(q['right_shifts'])}..{max(q['right_shifts'])} | {q['activation']} ({q['lut_entries']}) | {r['dense_bank64']['jobs']} |")
    (out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=REPO / "build/picture-merge-20261023/r14/v3dQAT/candidate_r14_e_v3dqat")
    parser.add_argument("--models", type=Path, default=REPO / "build/picture-merge-20261023/native-models")
    parser.add_argument("--out", type=Path, default=REPO / "docs/validation/picture-conv-handoff-20261023")
    args = parser.parse_args()
    report = collect(args.candidate, args.models)
    kinds = collections.Counter(r["kind"] for r in report["layers"])
    require(kinds == dict(conv=77, linear=3), "operator counts")
    write_inventory(report, args.out)
    receipt = dict(status="PASS", layers=80, models=report["totals"], source_graph_sha256=report["source_graph_sha256"],
                   source_files=len(report["sources"]), source_unchanged=all(sha((REPO / p).read_bytes()) == h for p, h in report["sources"].items()),
                   checks=["80 unique source/native layer ids", "all native body CRCs/SHA256", "all 80 NPZ SHA256 and packed parameter bytes",
                           "all shapes/strides/padding/dilation", "all per-channel shift equations and I32 safe bounds", "all exact dense job histograms vs historical bank64 shape plan"],
                   hardware_used=False, photos_or_frame_payloads_opened=False, production_ready=False,
                   generator_sha256=sha(Path(__file__).read_bytes()),
                   outputs={p.name: dict(bytes=p.stat().st_size, sha256=sha(p.read_bytes())) for p in (args.out / "README.md", args.out / "layers.json", args.out / "layers.csv")})
    require(receipt["source_unchanged"], "source changed during export")
    (args.out / "verification.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: receipt[k] for k in ("status", "layers", "models", "source_unchanged")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
