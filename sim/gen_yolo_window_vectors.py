"""Generate or verify deterministic Python-oracle vectors for window RTL.

The two channel tiles are submitted as independent descriptors. This tests
per-tile RTL order; cross-tile interleaving remains an integration task.
"""

import argparse
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vision"))

from stage2_contract import WindowDescriptor, iter_windows_nhwc4  # noqa: E402

OUT = ROOT / "sim" / "vectors"
DESC = WindowDescriptor(5, 4, 5, 3, 2, 1)


def make_vectors() -> dict[str, str]:
    rng = random.Random(0x5A17E2)
    pixels = bytearray(DESC.input_bytes)
    for pixel in range(DESC.width * DESC.height):
        for tile in range(DESC.channel_tiles):
            base = (pixel * DESC.channel_tiles + tile) * 4
            for lane in range(4):
                if tile * 4 + lane < DESC.channels:
                    pixels[base + lane] = rng.randrange(256)
    source = []
    expected = []
    for tile in range(DESC.channel_tiles):
        for pixel in range(DESC.width * DESC.height):
            offset = (pixel * DESC.channel_tiles + tile) * 4
            source.append(pixels[offset:offset + 4])
        for oy, ox, got_tile, ky, kx, tap in iter_windows_nhwc4(
            bytes(pixels), DESC
        ):
            if got_tile == tile:
                expected.append(tap)
    return {
        "yolo_window_source.hex": "".join(
            f"{int.from_bytes(word, 'little'):08x}\n" for word in source
        ),
        "yolo_window_expected.hex": "".join(
            f"{int.from_bytes(word, 'little'):08x}\n" for word in expected
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="replace checked-in golden files")
    args = parser.parse_args()
    for name, content in make_vectors().items():
        path = OUT / name
        if args.write:
            OUT.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="ascii")
        elif not path.is_file() or path.read_text(encoding="ascii") != content:
            raise SystemExit(f"stale or missing vector: {path}")
    print("YOLO_WINDOW_VECTORS_PASS seed=0x5a17e2 tiles=2 "
          "source_words=40 expected_taps=108")


if __name__ == "__main__":
    main()
