"""Verify real-layer accumulators/rounding/LUTs and stress vectors independently."""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def even(x, shift):
    if shift == 0:
        return x
    q, r = divmod(abs(x), 1 << shift)
    half = 1 << (shift - 1)
    q += r > half or (r == half and q % 2)
    return -q if x < 0 else q


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delivery', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--tensor-reference', action='store_true')
    args = parser.parse_args()
    root = HERE.parent / 'vision-model-20261020/golden/quantization/candidate_v1'
    cases = json.loads((root / 'golden_mac_vectors.json').read_text(encoding='utf-8'))
    assert len(cases) == 316
    if args.tensor_reference:
        import numpy as np
        import torch
        from pc_exact import characterize
        from exact_mm_int64_reference import exact_mm_int64_numpy, exact_mm_int64_torch
        characterize()
    # Each exact result is constructed with unbounded Python integers. These
    # vectors also include post-bias INT32 bounds, S16 ties-even and signed LUT.
    luts = {}
    for case in cases:
        acc = sum(int(a) * int(b) for a, b in zip(case['input'], case['weight'])) + case['bias']
        assert -(1 << 31) <= acc < (1 << 31)
        pre = max(-32768, min(32767, even(acc, case['shift'])))
        name = case.get('lut')
        if name and name not in luts:
            luts[name] = (root / 'int8' / name).read_bytes()
        output = luts[name][pre + 32768] if name else pre
        if name and output >= 128:
            output -= 256
        assert (acc, pre, output) == (case['accumulator'], case['preactivation'], case['output'])
        if args.tensor_reference:
            a = np.array(case['input'], dtype=np.int8).reshape(1, -1)
            b = np.array(case['weight'], dtype=np.int8).reshape(-1, 1)
            assert int(exact_mm_int64_numpy(a, b)[0, 0]) + case['bias'] == acc
            assert int(exact_mm_int64_torch(torch.from_numpy(a), torch.from_numpy(b))[0, 0]) + case['bias'] == acc
    stress_path = next(args.delivery.rglob('exact_golden_vectors.json'))
    stress = json.loads(stress_path.read_text(encoding='utf-8'))['stress_vectors']
    for case in stress:
        acc = sum(int(a) * int(b) for a, b in zip(case['input'], case['weight'])) + case['bias']
        pre = max(-32768, min(32767, even(acc, case['shift'])))
        assert (acc, pre) == (case['expected_accumulator'], case['expected_preactivation'])
    graph = json.loads((root / 'integer_graph.json').read_text(encoding='utf-8'))
    assert all(0 <= row['max_INT32_absolute_bound'] < (1 << 31) for row in graph['layers'])
    report = dict(status='PASS', reference='independent Python unbounded integers',
                  real_layer_vectors=len(cases), stress_vectors=len(stress), layer_bounds=len(graph['layers']),
                  delivered_numpy_and_torch_references_checked=args.tensor_reference,
                  vectors_sha256=hashlib.sha256((root / 'golden_mac_vectors.json').read_bytes()).hexdigest(),
                  stress_sha256=hashlib.sha256(stress_path.read_bytes()).hexdigest(), hardware_used=False)
    args.receipt.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
