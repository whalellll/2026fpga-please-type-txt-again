"""P0-2 characterization: torch._int_mm exactness vs shape/capability (extended probe).

Original probe (seed 20261020, 32x32 @ 32x16) + shape sweep over the paddings actually used
by integer_ops.exact_mm (K%32, N%16, M chunks of 4096) + first-layer real shapes.
"""
import json
import os
import platform
import sys
from pathlib import Path

import numpy as np
import torch

import argparse
_parser = argparse.ArgumentParser(description=__doc__)
_parser.add_argument('--out', type=Path, required=True)
OUT = None


def probe(m, k, n, seed):
    r = np.random.default_rng(seed)
    a = r.integers(0, 65, (m, k), dtype=np.int8)
    b = r.integers(-127, 128, (k, n), dtype=np.int16).astype(np.int8)
    y = torch._int_mm(torch.from_numpy(a), torch.from_numpy(b)).numpy()
    z = a.astype(np.int64) @ b.astype(np.int64)
    bad = int(np.count_nonzero(y != z))
    return dict(m=m, k=k, n=n, mismatches=bad,
                max_error=int(np.max(np.abs(y - z))) if bad else 0,
                exact=bad == 0), y, z, a, b


def main():
    global OUT
    OUT = _parser.parse_args().out
    if OUT.exists():
        raise ValueError('choose a fresh probe receipt')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(1)
    results = dict(python=platform.python_version(), torch=torch.__version__,
                   capability=torch.backends.cpu.get_cpu_capability(),
                   aten_env=os.getenv('ATEN_CPU_CAPABILITY'), dnnl_env=os.getenv('DNNL_MAX_CPU_ISA'),
                   cpu=platform.processor(), machine=platform.machine())
    # 1) original probe
    p, y, z, a, b = probe(32, 32, 16, 20261020)
    results['original_probe'] = p
    examples = []
    for row, col in np.argwhere(y != z)[:3]:
        examples.append(dict(row=int(row), column=int(col), input=a[row].tolist(),
                             weight=b[:, col].tolist(), torch_accumulator=int(y[row, col]),
                             independent_int64=int(z[row, col])))
    results['original_probe_examples'] = examples
    # 2) shape sweep
    sweep = []
    for k in (8, 16, 32, 64, 128, 256, 512, 1024, 4096):
        for n in (16, 64):
            for m in (16, 128, 4096):
                s, _, _, _, _ = probe(m, k, n, 20261021 + k * 100 + n + m)
                sweep.append(s)
    results['shape_sweep'] = sweep
    # 3) all-negative inputs (no zero values)
    r = np.random.default_rng(99)
    a = r.integers(-128, 0, (256, 256), dtype=np.int8)
    b = r.integers(-127, 0, (256, 16), dtype=np.int8)
    y = torch._int_mm(torch.from_numpy(a), torch.from_numpy(b)).numpy()
    z = a.astype(np.int64) @ b.astype(np.int64)
    results['all_negative_256x256x16'] = dict(mismatches=int(np.count_nonzero(y != z)),
                                              max_error=int(np.max(np.abs(y - z))) if (y != z).any() else 0)
    # 4) mixed sign with extremes
    a = r.integers(-128, 128, (256, 256), dtype=np.int8)
    b = r.integers(-127, 128, (256, 16), dtype=np.int8)
    a = np.ascontiguousarray(a)
    b = np.ascontiguousarray(b)
    y = torch._int_mm(torch.from_numpy(a), torch.from_numpy(b)).numpy()
    z = a.astype(np.int64) @ b.astype(np.int64)
    results['mixed_extreme_256x256x16'] = dict(mismatches=int(np.count_nonzero(y != z)),
                                               max_error=int(np.max(np.abs(y - z))) if (y != z).any() else 0)
    OUT.write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in results.items() if k not in ('shape_sweep', 'original_probe_examples')}, indent=2))
    print('sweep summary:', {f"{s['m']}x{s['k']}x{s['n']}": ('EXACT' if s['exact'] else f"BAD({s['mismatches']},max {s['max_error']})") for s in sweep})


if __name__ == '__main__':
    main()
