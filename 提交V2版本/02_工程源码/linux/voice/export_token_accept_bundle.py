#!/usr/bin/env python3
"""Export validation/test PCM into a small C-runtime acceptance bundle."""

import argparse
import csv
import struct
import wave
from pathlib import Path


TOKENS = [
    "<blank>", "ju", "ma", "pao", "bing", "zu", "shuai", "jiang",
    "shi", "xiang", "yi", "er", "san", "si", "wu", "liu", "qi",
    "ba", "jiu", "jin", "tui", "ping", "chonglai", "quxiao", "tuichu",
]
TOKEN_IDS = {token: index for index, token in enumerate(TOKENS)}
SPLIT_IDS = {"validation": 1, "test": 2}
MAX_SAMPLES = 400 + 199 * 160


def read_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as source:
        actual = (source.getnchannels(), source.getsampwidth(), source.getframerate())
        if actual != (1, 2, 16000) or source.getcomptype() != "NONE":
            raise ValueError(f"{path}: expected mono S16_LE PCM at 16 kHz")
        frames = source.getnframes()
        if frames < 400 or frames > MAX_SAMPLES:
            raise ValueError(f"{path}: invalid sample count {frames}")
        pcm = source.readframes(frames)
        if len(pcm) != frames * 2:
            raise ValueError(f"{path}: truncated PCM")
        return pcm


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    records = []
    with args.manifest.open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            split = row["split"].strip().lower()
            if split not in SPLIT_IDS:
                continue
            token_names = row["tokens"].split()
            if len(token_names) != 1 or token_names[0] not in TOKEN_IDS or token_names[0] == "<blank>":
                raise ValueError(f"invalid single token: {row['tokens']}")
            path = Path(row["path"])
            if not path.is_absolute():
                path = args.manifest.parent / path
            pcm = read_pcm(path)
            records.append((SPLIT_IDS[split], TOKEN_IDS[token_names[0]], pcm))
    if not records or not any(item[0] == 1 for item in records) or not any(item[0] == 2 for item in records):
        raise ValueError("manifest needs validation and test records")

    output = bytearray(b"XQA1" + struct.pack("<I", len(records)))
    for split, token, pcm in records:
        output += struct.pack("<III", len(pcm) // 2, token, split)
        output += pcm
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    print(f"XQVOICE_ACCEPT_BUNDLE_READY path={args.output} records={len(records)} bytes={len(output)}")


if __name__ == "__main__":
    main()
