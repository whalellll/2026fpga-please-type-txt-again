#!/usr/bin/env python3
"""Independent CPU oracle for the extra 1x1 and 3x3 board jobs."""

import binascii
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
CASES = (("pointwise", 5, 4, 1, 1, 0, 17),
         ("three_by_three", 5, 5, 3, 2, 1, 53))


def signed(value: int) -> int:
    return value - 256 if value >= 128 else value


def requant(value: int, shift: int) -> int:
    magnitude = (abs(value) + (1 << (shift - 1))) >> shift
    rounded = -magnitude if value < 0 else magnitude
    return min(127, max(-128, rounded)) & 255


def expected_vector(width: int, height: int, kernel: int, stride: int,
                    padding: int, seed: int) -> bytes:
    channels = 3
    lines = (channels * kernel * kernel + 3) // 4
    image = bytes((((i * 7 + (i // 11) * 3 + seed) % 15) - 7) & 255
                  for i in range(width * height * 4))
    weights = bytearray(lines * 128)
    bias = [oc * 3 - 20 + seed // 3 for oc in range(16)]
    shifts = [2 + oc % 4 for oc in range(16)]
    for scalar in range(channels * kernel * kernel):
        for oc in range(16):
            weights[(scalar // 4) * 128 + oc * 4 + scalar % 4] = (
                ((scalar * 5 + oc * 3 + seed) % 11) - 5) & 255
    out_width = (width + 2 * padding - kernel) // stride + 1
    out_height = (height + 2 * padding - kernel) // stride + 1
    output = bytearray()
    for oy in range(out_height):
        for ox in range(out_width):
            for oc in range(16):
                total = bias[oc]
                for ky in range(kernel):
                    for kx in range(kernel):
                        for ci in range(channels):
                            x = ox * stride + kx - padding
                            y = oy * stride + ky - padding
                            scalar = (ky * kernel + kx) * channels + ci
                            activation = (signed(image[(y * width + x) * 4 + ci])
                                          if 0 <= x < width and 0 <= y < height
                                          else 0)
                            weight = signed(weights[(scalar // 4) * 128
                                                    + oc * 4 + scalar % 4])
                            total += activation * weight
                output.append(requant(total, shifts[oc]))
    return bytes(output)


def expected_crc(width: int, height: int, kernel: int, stride: int,
                 padding: int, seed: int) -> tuple[int, int]:
    output = expected_vector(width, height, kernel, stride, padding, seed)
    return len(output), binascii.crc32(output) & 0xFFFFFFFF


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        binary = Path(temp) / "compute-test"
        subprocess.run(("gcc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                        str(ROOT / "linux/mac_accel/pango_mac_conv_compute_test.c"),
                        "-o", str(binary)), check=True)
        output = subprocess.run((str(binary), "--oracle-shapes"),
                                capture_output=True, text=True, check=True).stdout
    for name, width, height, kernel, stride, padding, seed in CASES:
        size, crc = expected_crc(width, height, kernel, stride, padding, seed)
        marker = f"PANGO_MAC_CONV_ORACLE_PASS case={name} bytes={size} crc32={crc:08x}"
        if marker not in output:
            raise AssertionError(f"missing {marker!r} in {output!r}")
    print("MAC_CONV_BOARD_SHAPES_ORACLE_PASS")


if __name__ == "__main__":
    main()
