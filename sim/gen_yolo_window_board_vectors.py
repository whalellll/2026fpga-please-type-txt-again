"""Check fixed seed 1x1, 3x3, 6x6 board harness vectors against CPU oracle."""

import argparse
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vision"))
from stage2_contract import WindowDescriptor, iter_windows_nhwc4  # noqa: E402

VECTOR_DIR = ROOT / "sim" / "vectors"
SEED = 0x5A17E2
JOBS = (
    (WindowDescriptor(4, 3, 3, 1, 1, 0), 0),
    (WindowDescriptor(5, 4, 5, 3, 2, 1), 0),
    (WindowDescriptor(5, 4, 5, 3, 2, 1), 1),
    (WindowDescriptor(7, 7, 3, 6, 2, 2), 0),
)


def make_vectors() -> dict[str, str]:
    rng = random.Random(SEED)
    source = []
    expected = []
    previous = None
    pixels = b""
    for desc, tile in JOBS:
        if desc != previous:
            values = bytearray(desc.input_bytes)
            for pixel in range(desc.width * desc.height):
                for channel_tile in range(desc.channel_tiles):
                    for lane in range(4):
                        offset = ((pixel * desc.channel_tiles + channel_tile)
                                  * 4 + lane)
                        if channel_tile * 4 + lane < desc.channels:
                            values[offset] = rng.randrange(256)
            pixels = bytes(values)
            previous = desc
        for pixel in range(desc.width * desc.height):
            offset = (pixel * desc.channel_tiles + tile) * 4
            source.append(pixels[offset:offset + 4])
        expected.extend(tap for _, _, got_tile, _, _, tap in
                        iter_windows_nhwc4(pixels, desc) if got_tile == tile)
    return {
        "yolo_window_board_source.hex": "".join(
            f"{int.from_bytes(word, 'little'):08x}\n" for word in source
        ),
        "yolo_window_board_expected.hex": "".join(
            f"{int.from_bytes(word, 'little'):08x}\n" for word in expected
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    files = make_vectors()
    for name, content in files.items():
        path = VECTOR_DIR / name
        if args.write:
            VECTOR_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="ascii")
        elif not path.is_file() or path.read_text(encoding="ascii") != content:
            raise SystemExit(f"missing or stale board vector: {path}")
    print("YOLO_WINDOW_BOARD_VECTORS_PASS seed=0x5a17e2 "
          "jobs=4 source_words=101 expected_taps=444")


if __name__ == "__main__":
    main()
