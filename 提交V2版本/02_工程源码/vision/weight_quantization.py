"""Weight-only precision experiments; this is not a device quantization ABI."""
import numpy as np


def quantize_per_output_channel(weights, bits):
    """Return symmetric signed Conv2d weights and one float64 scale per output.

    Excludes the asymmetric minimum (-8/-128). Rounding is ties-to-even.
    Float64 scales keep float32 subnormal weights representable.
    """
    w = np.asarray(weights)
    if bits not in (4, 8):
        raise ValueError("weight precision must be 4 or 8 bits")
    if w.ndim != 4 or any(d == 0 for d in w.shape):
        raise ValueError("weights must be nonempty OIHW Conv2d tensors")
    if not np.issubdtype(w.dtype, np.floating) or not np.all(np.isfinite(w)):
        raise ValueError("weights must be finite floating point values")
    w64 = w.astype(np.float64)
    qmax = (1 << (bits - 1)) - 1
    maximum = np.max(np.abs(w64), axis=(1, 2, 3), keepdims=True)
    scale = np.where(maximum == 0, 1.0, maximum / qmax)
    q = np.clip(np.rint(w64 / scale), -qmax, qmax).astype(np.int8)
    return q, scale


def dequantize(weights, scales):
    """Restore float32 weights for a PC weight-only sensitivity experiment."""
    q = np.asarray(weights)
    s = np.asarray(scales, dtype=np.float64)
    if q.ndim != 4 or s.shape != (q.shape[0], 1, 1, 1):
        raise ValueError("scales must contain one OIHW output channel scale")
    if not np.all(np.isfinite(s)) or not np.all(s > 0):
        raise ValueError("scales must be finite and positive")
    return (q.astype(np.float64) * s).astype(np.float32)
