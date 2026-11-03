#!/usr/bin/env python3

import argparse
import mmap
import struct
import sys
import zlib


HEADER = struct.Struct("<4s15I")
EXPECTED_ENTRIES = 0x108000
EXPECTED_ENTRY_BYTES = 16


def crc32(data):
    return zlib.crc32(data) & 0xFFFFFFFF


def verify(path):
    with open(path, "rb") as stream:
        with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as image:
            if len(image) < HEADER.size:
                raise ValueError("file is shorter than the PFA1 header")
            fields = HEADER.unpack_from(image)
            (
                magic,
                version,
                header_bytes,
                entry_bytes,
                rook_offset,
                rook_entries,
                cannon_offset,
                cannon_entries,
                rook_crc,
                cannon_crc,
                payload_crc,
                magics_crc,
                file_bytes,
                square_count,
                flags,
                header_crc,
            ) = fields

            if magic != b"PFA1" or version != 1:
                raise ValueError("unexpected magic or format version")
            if header_bytes != HEADER.size or entry_bytes != EXPECTED_ENTRY_BYTES:
                raise ValueError("unexpected header or entry size")
            if rook_entries != EXPECTED_ENTRIES or cannon_entries != EXPECTED_ENTRIES:
                raise ValueError("unexpected table entry count")
            expected_cannon_offset = rook_offset + rook_entries * entry_bytes
            expected_file_bytes = cannon_offset + cannon_entries * entry_bytes
            if rook_offset != header_bytes or cannon_offset != expected_cannon_offset:
                raise ValueError("table offsets are not contiguous")
            if file_bytes != expected_file_bytes or len(image) != file_bytes:
                raise ValueError("file size does not match the header")
            if square_count != 90 or flags != 1:
                raise ValueError("unsupported square count or bitboard layout")
            if crc32(image[: HEADER.size - 4]) != header_crc:
                raise ValueError("header CRC mismatch")

            rook_end = rook_offset + rook_entries * entry_bytes
            cannon_end = cannon_offset + cannon_entries * entry_bytes
            if crc32(image[rook_offset:rook_end]) != rook_crc:
                raise ValueError("rook table CRC mismatch")
            if crc32(image[cannon_offset:cannon_end]) != cannon_crc:
                raise ValueError("cannon table CRC mismatch")
            if crc32(image[rook_offset:cannon_end]) != payload_crc:
                raise ValueError("payload CRC mismatch")

            print(
                "PIKAFISH_ATTACK_TABLE_VERIFY_PASS "
                f"bytes={file_bytes} rook_entries={rook_entries} "
                f"cannon_entries={cannon_entries} rook_crc={rook_crc:08x} "
                f"cannon_crc={cannon_crc:08x} payload_crc={payload_crc:08x} "
                f"magics_crc={magics_crc:08x}"
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    args = parser.parse_args()
    try:
        verify(args.image)
    except (OSError, ValueError) as error:
        print(f"PIKAFISH_ATTACK_TABLE_VERIFY_FAIL {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
