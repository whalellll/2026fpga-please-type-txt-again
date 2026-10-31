"""Formal EXACT integer matmul reference (P0-2 deliverable).

Mathematical contract: S8 x S8 -> INT32, one accumulation over K, no intermediate
rounding. int64 accumulation is exact for all layer shapes in candidate_v1/v2
(export proves 128*sum(|w|)+|bias| < 2^31, so int64 never overflows).

torch._int_mm MUST NOT be used as a golden: on the AVX2-capability int8 GEMM path
of torch 2.5.1 (verified on +cu118 and +cpu builds, x86-64 Skylake), it deviates
from exact integer math with mixed-sign inputs (287/512 mismatches, max |err|
12538 on the 32x32x16 probe; up to 169374 at 4096x4096x64). Deviation is
capability-flag independent and data-value dependent (all-positive-product inputs
verified exact). See ../probe findings.
"""
from __future__ import annotations

import numpy as np


def exact_mm_int64_numpy(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Canonical reference. a: int8 (M,K); b: int8 (K,N) -> int32 (M,N)."""
    a = np.asarray(a)
    b = np.asarray(b)
    if a.dtype != np.int8 or b.dtype != np.int8:
        raise ValueError('S8_required')
    m, k = a.shape
    kb, n = b.shape
    if k != kb:
        raise ValueError('K_mismatch')
    return (a.astype(np.int64) @ b.astype(np.int64)).astype(np.int32)


def exact_mm_int64_torch(a, b):
    """Same contract for torch tensors; patch into integer_ops before runtime load:
        import integer_ops; integer_ops.exact_mm = exact_mm_int64_torch
    """
    import torch
    if a.dtype != torch.int8 or b.dtype != torch.int8:
        raise ValueError('S8_required')
    m, k = a.shape
    kb, n = b.shape
    if k != kb:
        raise ValueError('K_mismatch')
    return (a.to(torch.int64) @ b.to(torch.int64)).to(torch.int32)


if __name__ == '__main__':
    rng = np.random.default_rng(20261020)
    a = rng.integers(0, 65, (32, 32), dtype=np.int8)
    b = rng.integers(-127, 128, (32, 16), dtype=np.int16).astype(np.int8)
    y = exact_mm_int64_numpy(a, b)
    z = (a.astype(np.int64) @ b.astype(np.int64)).astype(np.int32)
    assert (y == z).all()
    print('SELFTEST_OK exact int64 reference')
