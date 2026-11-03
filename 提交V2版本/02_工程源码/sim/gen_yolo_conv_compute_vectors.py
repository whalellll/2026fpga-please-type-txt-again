"""Generate deterministic signed W8A8 convolution and compact S8 vectors."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vision"))
from stage2_contract import WindowDescriptor, conv2d_nhwc4_int32, iter_windows_nhwc4

OUT = ROOT / "sim" / "vectors"
CASES = (
    ("point_tail", WindowDescriptor(2, 2, 4, 1, 1, 0), 5),
    ("border", WindowDescriptor(3, 3, 4, 3, 1, 1), 8),
    ("first_kernel", WindowDescriptor(7, 7, 3, 6, 2, 2), 16),
    ("baseline", WindowDescriptor(1, 1, 4, 1, 1, 0), 16),
    ("partial", WindowDescriptor(1, 1, 4, 1, 1, 0), 5),
)


def s8(value: int) -> int:
    return value - 256 if value >= 128 else value


def requant(value: int, shift: int) -> int:
    """Round half away from zero, then saturate into signed eight bits."""
    if not 0 <= shift <= 30:
        raise ValueError("invalid shift")
    magnitude = (abs(value) + ((1 << (shift - 1)) if shift else 0)) >> shift
    rounded = -magnitude if value < 0 else magnitude
    return max(-128, min(127, rounded))


def build_case(number: int, name: str, desc: WindowDescriptor, cout: int) -> dict:
    if desc.channels > 4 or cout > 16:
        raise ValueError("test exceeds initial compute tile")
    source = bytes((i * 29 + (i // 7) * 13 + number * 17) & 255
                   for i in range(desc.input_bytes))
    weights = bytes((((i * 11 + (i // (desc.channels * desc.kernel**2)) * 3)
                      & 15) - 8) & 255
                    for i in range(cout * desc.channels * desc.kernel**2))
    bias = [oc * 13 - 50 for oc in range(cout)]
    shift = [(oc % 4) + 2 for oc in range(cout)]
    scalar_count = desc.channels * desc.kernel**2
    lines = (scalar_count + 3) // 4
    rows = bytearray(lines * 128)
    for oc in range(cout):
        for scalar in range(scalar_count):
            tap, channel = divmod(scalar, desc.channels)
            ky, kx = divmod(tap, desc.kernel)
            source_index = ((oc * desc.channels + channel) * desc.kernel + ky)
            source_index = source_index * desc.kernel + kx
            rows[(scalar // 4) * 128 + oc * 4 + scalar % 4] = weights[source_index]
    taps = [tap for *_, tap in iter_windows_nhwc4(source, desc)]
    raw = conv2d_nhwc4_int32(source, desc, weights, cout, bias)
    packed = bytes(requant(value, shift[i % cout]) & 255
                   for i, value in enumerate(raw))
    prefix = f"yolo_compute_{name}"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{prefix}_source.hex").write_text(
        "".join(f"{int.from_bytes(source[i:i+4], 'little'):08x}\n"
                for i in range(0, len(source), 4)), encoding="ascii")
    (OUT / f"{prefix}_taps.hex").write_text(
        "".join(f"{int.from_bytes(tap, 'little'):08x}\n" for tap in taps),
        encoding="ascii")
    (OUT / f"{prefix}_weights.hex").write_text(
        "".join(f"{int.from_bytes(rows[i:i+4], 'little'):08x}\n"
                for i in range(0, len(rows), 4)), encoding="ascii")
    (OUT / f"{prefix}_expected.hex").write_text(
        "".join(f"{value:02x}\n" for value in packed), encoding="ascii")
    return {
        "name": name,
        "width": desc.width,
        "height": desc.height,
        "channels": desc.channels,
        "kernel": desc.kernel,
        "stride": desc.stride,
        "padding": desc.padding,
        "output_channels": cout,
        "output_width": desc.output_width,
        "output_height": desc.output_height,
        "weight_lines": lines,
        "tap_count": len(taps),
        "output_bytes": len(packed),
        "bias": bias,
        "shift": shift,
        "tap_sha256": hashlib.sha256(b"".join(taps)).hexdigest(),
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "weight_sha256": hashlib.sha256(rows).hexdigest(),
        "output_sha256": hashlib.sha256(packed).hexdigest(),
    }


def main() -> None:
    assert requant(127 * 4, 2) == 127
    assert requant(-129 * 4, 2) == -128
    assert requant(5, 1) == 3
    assert requant(-5, 1) == -3
    # More than one K tile must retain INT32 partial sums until final scaling.
    assert requant(7 + 7, 4) == 1
    assert requant(7, 4) + requant(7, 4) == 0
    rows = [build_case(i, *case) for i, case in enumerate(CASES)]
    (OUT / "yolo_compute_manifest.json").write_text(
        json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print("YOLO_CONV_COMPUTE_ORACLE_PASS",
          "cases=" + str(len(rows)),
          "taps=" + str(sum(row["tap_count"] for row in rows)),
          "output_bytes=" + str(sum(row["output_bytes"] for row in rows)))


if __name__ == "__main__":
    main()
