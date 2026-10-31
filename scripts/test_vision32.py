"""Independent NHWC/OIHW integer oracle and whole-layer DMA stress fixtures."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import subprocess
import numpy as np
from workspace_paths import workspace_path,wsl_path

ROOT = Path(__file__).resolve().parents[1]


def linux(path):
    return wsl_path(path)


def round_shift(value, shift):
    if not shift:
        return value
    return ((value + (1 << (shift - 1))) >> shift) if value >= 0 else -((-value + (1 << (shift - 1))) >> shift)

def round_even(value, shift):
    q, r = divmod(abs(value), 1 << shift)
    if shift and (r > 1 << (shift-1) or (r == 1 << (shift-1) and q & 1)):
        q += 1
    return -q if value < 0 else q


def cases():
    shapes = json.loads((ROOT / 'sim/vectors/vision32_shapes.json').read_text())
    jobs = [dict(name='signed_tail', w=3, h=2, ci=3, co=5, k=1, s=1, p=0, flags=2),
            dict(name='quant_round', w=3, h=2, ci=7, co=9, k=1, s=1, p=0, flags=0),
            dict(name='silu_table', w=3, h=3, ci=4, co=16, k=3, s=1, p=1, flags=1),
            dict(name='cross_4k', w=8, h=3, ci=64, co=57, k=1, s=1, p=0, flags=0, cross=True)]
    for i, x in enumerate(shapes['layers']):
        k, s, p = x['kernel'][0], x['stride'][0], x['padding'][0]
        jobs.append(dict(name=x['name'], w=max(k, 3), h=max(k, 3), ci=x['input_shape'][1],
                         co=x['output_shape'][1], k=k, s=s, p=p, flags=2 if i % 3 == 0 else i % 2))
    for fault in (1, 2, 3, 4, 5):
        jobs.append(dict(name='fault_' + str(fault), w=5, h=3, ci=16, co=9,
                         k=3, s=1, p=1, flags=0, fault=fault))
    for bad in ('zero_width', 'high_channel', 'too_deep', 'overlap', 'out_of_range', 'bad_scale', 'bad_shift'):
        jobs.append(dict(name=bad, w=3, h=3, ci=4, co=9, k=1, s=1, p=0, flags=0, bad=bad))
    jobs += [dict(name='detector640_first', w=640, h=6, ci=3, co=16, k=6, s=2, p=2, flags=0),
             dict(name='width_above511', w=640, h=1, ci=1, co=1, k=1, s=1, p=0, flags=2),
             dict(name='height_above511', w=1, h=640, ci=1, co=1, k=1, s=1, p=0, flags=2),
             dict(name='wide_first', w=320, h=6, ci=3, co=16, k=6, s=2, p=2, flags=0),
             dict(name='min_pixel', w=1, h=1, ci=1, co=1, k=1, s=1, p=0, flags=1),
             dict(name='k1152_extreme', w=3, h=3, ci=128, co=17, k=3, s=1, p=0, flags=2, extreme=True)]
    return jobs


def fixture(job, index, out):
    rng = np.random.default_rng(0x563332 + index)
    w, h, ci, co, k, s, p = (job[x] for x in ('w', 'h', 'ci', 'co', 'k', 's', 'p'))
    oh, ow = (h + 2*p-k)//s+1, (w + 2*p-k)//s+1
    x = rng.integers(-128, 128, (h, w, ci), dtype=np.int16).astype(np.int8)
    wt = rng.integers(-16, 17, (co, ci, k, k), dtype=np.int16).astype(np.int8)
    if job.get('extreme'):
        x.fill(-128)
        wt.fill(-128)
    bias = rng.integers(-1000, 1001, co, dtype=np.int32)
    scale = rng.integers(1, 32, co, dtype=np.int32)
    shift = rng.integers(8, 15, co, dtype=np.int32)
    if job.get('quant_edges'):
        x.fill(0)
        bias = np.array([(-2147483648 if i % 2 else 2147483647) for i in range(co)], dtype=np.int32)
        scale.fill(2147483647)
        shift = np.array([i % 63 for i in range(co)], dtype=np.int32)
    if job.get('half_ties'):
        x.fill(0)
        bias = np.array([(-1 if i % 2 else 1) for i in range(co)], dtype=np.int32)
        scale.fill(1)
        shift.fill(1)
    if job.get('exact_edges'):
        x.fill(0)
        edges=[-2147483648,2147483647,-32769,-32768,32767,32768,-7,-5,-3,-1,1,3,5,7]
        bias=np.array([edges[i%len(edges)] for i in range(co)],dtype=np.int32)
        scale.fill(1)
        shift=np.array([(i//len(edges))%63 for i in range(co)],dtype=np.int32)
        if 'exact_shift' in job:shift.fill(job['exact_shift'])
    if job.get('overflow'):
        x.fill(-128);wt.fill(-128);bias.fill(2147483647);scale.fill(1)
    if job['flags'] & 4:
        scale.fill(1)
    # Dense lookup is deliberately non-monotonic: catches signed index bugs.
    lut = bytes(((i * 73 + (i>>8)*29 + 19) & 255) for i in range(65536 if job['flags'] & 4 else 256))
    padded = np.pad(x.astype(np.int64), ((p, p), (p, p), (0, 0)))
    raw = np.zeros((oh, ow, co), dtype=np.int64)
    for y in range(oh):
        for xx in range(ow):
            patch = padded[y*s:y*s+k, xx*s:xx*s+k, :]
            raw[y, xx] = np.einsum('yxi,oiyx->o', patch, wt.astype(np.int64))
    if job['flags'] == 2:
        golden = raw.astype('<i4').tobytes()
    elif job['flags'] & 4:
        values=[]
        for n,v in enumerate(raw.reshape(-1)):
            oc=n%co
            q=min(32767,max(-32768,round_even(int(v)+int(bias[oc]),int(shift[oc]))))
            if job['flags'] & 1:
                q=lut[q+32768];q=q-256 if q>=128 else q
            values.append(q)
        golden=np.array(values,dtype='<i2').tobytes()
    else:
        values = []
        for n, v in enumerate(raw.reshape(-1)):
            oc = n % co
            q = min(127, max(-128, round_shift((int(v)+int(bias[oc]))*int(scale[oc]), int(shift[oc]))))
            values.append(lut[q & 255] if job['flags'] & 1 else q & 255)
        golden = bytes(values)
    ci4 = (ci+3)//4*4
    nhwc = np.zeros((h, w, ci4), dtype=np.int8)
    nhwc[:, :, :ci] = x
    packed_w, params = bytearray(), bytearray()
    for oc in range(0, co, 8):
        for ky in range(k):
            for kx in range(k):
                for ic in range(ci):
                    packed_w.extend((int(wt[o, ic, ky, kx]) & 255) if o < co else 0 for o in range(oc, oc+8))
        for o in range(oc, oc+8):
            for v in ((int(bias[o]), int(scale[o]), int(shift[o])) if o < co else (0, 1, 0)):
                params.extend((v & 0xffffffff).to_bytes(4, 'little'))
    src, weights, pars, table, dst = 0x1000, 0x20000, 0x80000, 0x82000, 0x90000
    if job['flags'] & 4:table=0x60000
    if job.get('cross'):
        src, weights, pars, dst = 0x1ffc, 0x20ffc, 0x80ff4, 0x90ffc
    cfg = [src, weights, dst, pars, table, w, h, ci, co, k, s, p, job['flags'], 20_000_000, index, index+100]
    bad = job.get('bad')
    if bad == 'zero_width': cfg[5] = 0
    if bad == 'high_channel': cfg[7] = 0x10004
    if bad == 'too_deep': cfg[7], cfg[9] = 512, 3
    if bad == 'overlap': cfg[2] = cfg[0]
    if bad == 'out_of_range': cfg[2] = 0xffffc
    if bad == 'bad_scale': params[4:8] = (0x80000000).to_bytes(4, 'little')
    if bad == 'bad_shift': params[8:12] = (63).to_bytes(4, 'little')
    # Addresses in the config are relative; device guard sees physical DDR.
    cfg[:5] = [v+0x1b000000 for v in cfg[:5]]
    sections = [(src, nhwc.tobytes()), (weights, bytes(packed_w)), (pars, bytes(params)), (table, lut)]
    text = []
    for addr, data in sections:
        data += bytes((-len(data)) % 4)
        text.append('@%x\n' % (addr//4))
        text.extend('%08x\n' % int.from_bytes(data[j:j+4], 'little') for j in range(0, len(data), 4))
    (out / f'case-{index}.mem').write_text(''.join(text))
    (out / f'case-{index}.cfg').write_text(''.join('%08x\n' % v for v in cfg))
    (out / f'case-{index}.gold').write_text(''.join('%02x\n' % b for b in golden))
    ctl = [len(golden), int(bool(bad or job.get('fault') or job.get('overflow'))), job.get('fault', 0),
           math.ceil(oh*ow/4)*math.ceil(co/8)*ci*k*k, oh*ow*co, len(packed_w)]
    (out / f'case-{index}.ctl').write_text(''.join('%08x\n' % v for v in ctl))
    return dict(index=index, name=job['name'], original=job, output_bytes=len(golden),
                raw_sha256=hashlib.sha256(raw.astype('<i4').tobytes()).hexdigest(),
                output_sha256=hashlib.sha256(golden).hexdigest(), expected_error=bool(ctl[1]))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--quick', action='store_true')
    ap.add_argument('--soc', action='store_true')
    ap.add_argument('--edges', action='store_true')
    ap.add_argument('--raw-only',action='store_true')
    ap.add_argument('--layer-source',type=Path)
    a = ap.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    jobs = cases()
    if a.raw_only:
        jobs=[j for j in jobs if j['flags']==2]
        jobs += [dict(name='raw_fault_'+str(f),w=5,h=3,ci=16,co=9,k=3,s=1,p=1,flags=2,fault=f) for f in (1,2,3,4,5)]
    if a.quick:
        jobs = jobs[:4] + jobs[-3:]
    if a.edges:
        jobs = [dict(name='all63_shifts', w=1, h=1, ci=1, co=64, k=1, s=1, p=0, flags=0, quant_edges=True),
                dict(name='half_away', w=3, h=1, ci=1, co=9, k=1, s=1, p=0, flags=0, half_ties=True)]
    manifest = [fixture(j, i, out) for i, j in enumerate(jobs)]
    (out / 'vectors.json').write_text(json.dumps(manifest, indent=2)+'\n')
    sources = [ROOT/'rtl/mac_accel/vision32_pe.v', ROOT/'rtl/mac_accel/vision32_layer.v', ROOT/'sim/tb_vision32_layer.sv']
    if a.soc:
        sources = sorted((ROOT/'rtl/mac_accel').glob('*.v')) + [ROOT/'sim/tb_vision32_layer.sv', ROOT/'sim/gtp_apm_e2_perf_sim.v']
    if a.layer_source:sources=[a.layer_source.resolve() if p.name=='vision32_layer.v' else p for p in sources]
    before = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    temporary=out/"tmp";temporary.mkdir()
    cmd = "set -eu; export TMPDIR='"+linux(temporary)+"'; cd '"+linux(out)+"'; iverilog -g2012 -s tb_vision32_layer -Ptb_vision32_layer.CASES="+str(len(jobs))+" -Ptb_vision32_layer.SOC="+str(int(a.soc))+" -o vision.vvp "+' '.join("'"+linux(p)+"'" for p in sources)+"; vvp vision.vvp"
    with (out/'simulation.log').open('wb') as log:
        r = subprocess.run(['wsl', '-d', 'pikafish-verify', '--', 'sh', '-c', cmd], stdout=log, stderr=subprocess.STDOUT, timeout=1800)
    log_bytes = (out/'simulation.log').read_bytes()
    assert r.returncode == 0 and b'VISION32_ALL_PASS' in log_bytes, (out/'simulation.log').read_text(errors='replace')[-4000:]
    assert before == {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    result = dict(status='VISION32_NUMPY_DIFFERENTIAL_DMA_PASS_NOT_BOARD', cases=len(jobs), soc=a.soc,
                  source_sha256=before, vector_sha256=hashlib.sha256((out/'vectors.json').read_bytes()).hexdigest(),
                  log_sha256=hashlib.sha256((out/'simulation.log').read_bytes()).hexdigest())
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: result[k] for k in ('status', 'cases', 'soc')}), flush=True)


if __name__ == '__main__':
    main()
