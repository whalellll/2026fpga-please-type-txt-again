#!/usr/bin/env python3
"""Build a PFSB v2 MAC image directly from one verified PFF1 model."""

from __future__ import annotations

import argparse
import hashlib
import struct
import zlib
from pathlib import Path

PACK_MAGIC = 0x42534650  # PFSB
PACK_VERSION = 0x00020000
STACK_MAGIC = 0x31534650  # PFS1
PFB1_MAGIC = 0x31424650
PFB1_VERSION = 0x00010000

STACK_COUNT = 16
HEADER_BYTES = 0x1000
SLOT_BYTES = 0x9000
STACK_HEADER_BYTES = 0x100
FC0_OFFSET = 0x100
FC0_TILE_BYTES = 0x2000
FC0_TILES = 4
FC0_BYTES = 0x8000
FC0_BIAS_OFFSET = 0x8100
FC0_BIAS_BYTES = 0x80
FC1_WEIGHT_OFFSET = 0x8180
FC1_WEIGHT_BYTES = 0x800
FC1_BIAS_OFFSET = 0x8980
FC1_BIAS_BYTES = 0x80
FC2_WEIGHT_OFFSET = 0x8A00
FC2_WEIGHT_BYTES = 0x80
FC2_BIAS_OFFSET = 0x8A80
FC2_BIAS_BYTES = 4
STACK_DATA_END = 0x8A84
USED_BYTES = HEADER_BYTES + STACK_COUNT * SLOT_BYTES
DDR_BYTES = 0x100000

L1 = 1024
L2 = 32
L3 = 32


PFF1_HEADER_BYTES = 4096
PFF1_VERSION = 0x00010000
PFF1_SECTION_COUNT = 6
PFF1_SECTION_OFFSET = 104
PFF1_SECTION_BYTES = 32
PFF1_MLP_STACK_BYTES = 35204


def split_pff1_stack(data: bytes) -> tuple[bytes, bytes, bytes, bytes, bytes, bytes]:
    if len(data) != PFF1_MLP_STACK_BYTES:
        raise ValueError(f"PFF1 MLP stack: expected {PFF1_MLP_STACK_BYTES} bytes, got {len(data)}")
    pos = 0

    def take(size: int) -> bytes:
        nonlocal pos
        value = data[pos : pos + size]
        if len(value) != size:
            raise ValueError(f"PFF1 MLP stack truncated at {pos}")
        pos += size
        return value

    fc0_b, fc0_w, fc1_b, fc1_w, fc2_b, fc2_w = (
        take(L2 * 4),
        take(L2 * L1),
        take(L3 * 4),
        take(L3 * 64),
        take(4),
        take(128),
    )
    if pos != len(data):
        raise ValueError("PFF1 MLP stack has trailing bytes")
    return fc0_w, fc0_b, fc1_w, fc1_b, fc2_w, fc2_b


def read_pff1(path: Path) -> tuple[list[bytes], bytes, int, int]:
    data = path.read_bytes()
    if len(data) < PFF1_HEADER_BYTES or data[:4] != b"PFF1":
        raise ValueError(f"{path}: missing PFF1 header")
    if struct.unpack_from("<I", data, 4)[0] != PFF1_VERSION:
        raise ValueError(f"{path}: unsupported PFF1 version")
    if struct.unpack_from("<I", data, 8)[0] != PFF1_HEADER_BYTES:
        raise ValueError(f"{path}: wrong PFF1 header size")
    if struct.unpack_from("<I", data, 52)[0] != PFF1_SECTION_COUNT:
        raise ValueError(f"{path}: wrong PFF1 section count")
    if struct.unpack_from("<Q", data, 56)[0] != len(data):
        raise ValueError(f"{path}: PFF1 file size mismatch")
    if struct.unpack_from("<I", data, 64)[0] != PFF1_MLP_STACK_BYTES:
        raise ValueError(f"{path}: wrong PFF1 MLP stack size")
    decoded_sha = data[72:104]
    mlps = None
    mlps_crc = 0
    for index in range(PFF1_SECTION_COUNT):
        desc = PFF1_SECTION_OFFSET + index * PFF1_SECTION_BYTES
        name, reserved, offset, size, section_crc, flags = struct.unpack_from(
            "<4sIQQII", data, desc
        )
        if reserved != 0 or flags != 0 or offset + size > len(data):
            raise ValueError(f"{path}: invalid PFF1 section descriptor {index}")
        payload = data[offset : offset + size]
        if zlib.crc32(payload) & 0xFFFFFFFF != section_crc:
            raise ValueError(f"{path}: bad PFF1 section CRC {name!r}")
        if name == b"MLPS":
            mlps = payload
            mlps_crc = section_crc
    expected_bytes = STACK_COUNT * PFF1_MLP_STACK_BYTES
    if mlps is None or len(mlps) != expected_bytes:
        raise ValueError(f"{path}: missing or wrong-size MLPS section")
    stacks = [
        mlps[i * PFF1_MLP_STACK_BYTES : (i + 1) * PFF1_MLP_STACK_BYTES]
        for i in range(STACK_COUNT)
    ]
    return stacks, decoded_sha, len(mlps), mlps_crc


def pack_fc0_native(fc0: bytes) -> bytes:
    packed = bytearray(FC0_BYTES)
    for tile in range(FC0_TILES):
        base = tile * 256
        tile_base = tile * FC0_TILE_BYTES
        for ci_tile in range(64):
            line = tile_base + ci_tile * 128
            for pair in range(16):
                low = pair * 2
                high = low + 1
                for ci in range(4):
                    feature = ci_tile * 4 + ci
                    slot = line + (pair * 4 + ci) * 2
                    packed[slot] = fc0[low * L1 + base + feature]
                    packed[slot + 1] = fc0[high * L1 + base + feature]
    return bytes(packed)


def verify_fc0_native(fc0: bytes, packed: bytes) -> None:
    for output in range(L2):
        pair = output // 2
        parity = output & 1
        for feature in range(L1):
            tile = feature // 256
            within = feature & 255
            ci_tile = within // 4
            ci = within & 3
            offset = (
                tile * FC0_TILE_BYTES
                + ci_tile * 128
                + (pair * 4 + ci) * 2
                + parity
            )
            if packed[offset] != fc0[output * L1 + feature]:
                raise ValueError(
                    f"native fc0 mismatch output={output} feature={feature}"
                )


def build(pff1: Path, nnue: Path, output: Path) -> None:
    if not nnue.is_file():
        raise FileNotFoundError(nnue)
    if not pff1.is_file():
        raise FileNotFoundError(pff1)
    model_sha = hashlib.sha256(nnue.read_bytes()).digest()
    stacks, decoded_sha, mlps_bytes, mlps_crc = read_pff1(pff1)
    image = bytearray(USED_BYTES)

    for stack in range(STACK_COUNT):
        fc0_w, fc0_b, fc1_w, fc1_b, fc2_w, fc2_b = split_pff1_stack(stacks[stack])
        fc0_native = pack_fc0_native(fc0_w)
        verify_fc0_native(fc0_w, fc0_native)
        base = HEADER_BYTES + stack * SLOT_BYTES
        image[base + FC0_OFFSET : base + FC0_OFFSET + FC0_BYTES] = fc0_native
        image[base + FC0_BIAS_OFFSET : base + FC0_BIAS_OFFSET + FC0_BIAS_BYTES] = fc0_b
        image[base + FC1_WEIGHT_OFFSET : base + FC1_WEIGHT_OFFSET + FC1_WEIGHT_BYTES] = fc1_w
        image[base + FC1_BIAS_OFFSET : base + FC1_BIAS_OFFSET + FC1_BIAS_BYTES] = fc1_b
        image[base + FC2_WEIGHT_OFFSET : base + FC2_WEIGHT_OFFSET + FC2_WEIGHT_BYTES] = fc2_w
        image[base + FC2_BIAS_OFFSET : base + FC2_BIAS_OFFSET + FC2_BIAS_BYTES] = fc2_b
        slot_crc = zlib.crc32(image[base + STACK_HEADER_BYTES : base + STACK_DATA_END])
        fc0_crc = zlib.crc32(
            image[base + FC0_OFFSET : base + FC0_BIAS_OFFSET + FC0_BIAS_BYTES]
        ) & 0xFFFFFFFF
        slot_header = struct.pack(
            "<17I",
            STACK_MAGIC,
            stack,
            SLOT_BYTES,
            FC0_OFFSET,
            FC0_BYTES,
            FC0_BIAS_OFFSET,
            FC0_BIAS_BYTES,
            FC1_WEIGHT_OFFSET,
            FC1_WEIGHT_BYTES,
            FC1_BIAS_OFFSET,
            FC1_BIAS_BYTES,
            FC2_WEIGHT_OFFSET,
            FC2_WEIGHT_BYTES,
            FC2_BIAS_OFFSET,
            FC2_BIAS_BYTES,
            slot_crc,
            fc0_crc,
        )
        image[base : base + len(slot_header)] = slot_header

    payload_crc = zlib.crc32(image[HEADER_BYTES:USED_BYTES])
    pack_header = struct.pack(
        "<12I32s32sIII",
        PACK_MAGIC,
        PACK_VERSION,
        HEADER_BYTES,
        USED_BYTES,
        STACK_COUNT,
        SLOT_BYTES,
        HEADER_BYTES,
        FC0_OFFSET,
        FC0_TILE_BYTES,
        FC0_TILES,
        3,  # native fc0 plus row-major fc1/fc2
        payload_crc,
        model_sha,
        decoded_sha,
        mlps_bytes,
        mlps_crc,
        0,
    )
    image[: len(pack_header)] = pack_header
    struct.pack_into("<I", image, 120, zlib.crc32(image[:120]) & 0xFFFFFFFF)
    if len(image) > DDR_BYTES:
        raise ValueError(f"pack is larger than reserved DDR: {len(image)}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image)
    print(
        f"PF_STAGEB_MAC_PACK_PASS bytes={len(image)} "
        f"crc32={payload_crc:08x} mlps_crc32={mlps_crc:08x} "
        f"decoded_sha256={decoded_sha.hex()} model_sha256={model_sha.hex()}"
    )


def main() -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pff1",
        type=Path,
        default=here / "out" / "pikafish.nnue.flat",
    )
    parser.add_argument(
        "--nnue",
        type=Path,
        default=here.parents[2] / "xiangqi_oss" / "Pikafish" / "pikafish.nnue",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=here.parents[1] / "artifacts" / "pikafish-stageb-mac.bin",
    )
    args = parser.parse_args()
    build(args.pff1, args.nnue, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
