#!/usr/bin/env python3
"""Independent structural and CRC verifier for a fully decoded PFF1 model."""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
import zlib
from pathlib import Path


MAGIC = b"PFF1"
FORMAT_VERSION = 0x00010000
HEADER_BYTES = 4096
HEADER_FORMAT = "<4sIIIIIIIHHHHIIIIQII32s"
SECTION_FORMAT = "<4sIQQII"
EXPECTED_HEADER = {
    "flags": 0x00000007,
    "source_version": 0x6A448AFA,
    "net_hash": 0x40C70FA6,
    "ft_hash": 0x23F47EB0,
    "arch_hash": 0x63337116,
    "l1": 1024,
    "l2": 32,
    "l3": 32,
    "layer_stacks": 16,
    "psq_dims": 16536,
    "threat_dims": 45547,
    "psqt_buckets": 16,
    "section_count": 6,
    "mlp_stack_bytes": 35204,
}
EXPECTED_SECTIONS = {
    b"FTBI": (2048, "ft_biases.i16.bin"),
    b"FTTW": (45547 * 1024, "ft_threat_weights.i8.bin"),
    b"FTTP": (45547 * 16 * 4, "ft_threat_psqt.i32.bin"),
    b"FTPW": (16536 * 1024, "ft_psq_weights.i8.bin"),
    b"FTPP": (16536 * 16 * 4, "ft_psqt.i32.bin"),
    b"MLPS": (16 * 35204, None),
}


def fail(message: str) -> None:
    raise ValueError(message)


def stream_region(path: Path, offset: int, size: int) -> tuple[int, str]:
    crc = 0
    digest = hashlib.sha256()
    left = size
    with path.open("rb") as f:
        f.seek(offset)
        while left:
            block = f.read(min(left, 1 << 20))
            if not block:
                fail(f"truncated region at {offset:#x}, missing {left} bytes")
            crc = zlib.crc32(block, crc)
            digest.update(block)
            left -= len(block)
    return crc & 0xFFFFFFFF, digest.hexdigest()


def sha256_file(path: Path) -> str:
    return stream_region(path, 0, path.stat().st_size)[1]


def sha256_file_bytes(path: Path) -> bytes:
    return bytes.fromhex(sha256_file(path))


def verify(model: Path, raw: Path | None, components: Path | None) -> None:
    actual_size = model.stat().st_size
    with model.open("rb") as f:
        header = f.read(HEADER_BYTES)
    if len(header) != HEADER_BYTES:
        fail(f"header is {len(header)} bytes, expected {HEADER_BYTES}")

    values = struct.unpack_from(HEADER_FORMAT, header, 0)
    (
        magic,
        format_version,
        header_bytes,
        flags,
        source_version,
        net_hash,
        ft_hash,
        arch_hash,
        l1,
        l2,
        l3,
        layer_stacks,
        psq_dims,
        threat_dims,
        psqt_buckets,
        section_count,
        file_bytes,
        mlp_stack_bytes,
        reserved,
        raw_sha256,
    ) = values
    if magic != MAGIC:
        fail(f"magic {magic!r} != {MAGIC!r}")
    if format_version != FORMAT_VERSION:
        fail(f"format version {format_version:#x}")
    if header_bytes != HEADER_BYTES:
        fail(f"header bytes {header_bytes}")
    if file_bytes != actual_size:
        fail(f"file size {actual_size} != header {file_bytes}")
    if reserved != 0:
        fail(f"reserved header field is {reserved:#x}")

    actual_header = {
        "flags": flags,
        "source_version": source_version,
        "net_hash": net_hash,
        "ft_hash": ft_hash,
        "arch_hash": arch_hash,
        "l1": l1,
        "l2": l2,
        "l3": l3,
        "layer_stacks": layer_stacks,
        "psq_dims": psq_dims,
        "threat_dims": threat_dims,
        "psqt_buckets": psqt_buckets,
        "section_count": section_count,
        "mlp_stack_bytes": mlp_stack_bytes,
    }
    for name, expected in EXPECTED_HEADER.items():
        if actual_header[name] != expected:
            fail(f"header {name}={actual_header[name]} != {expected}")

    desc_size = struct.calcsize(SECTION_FORMAT)
    desc_offset = struct.calcsize(HEADER_FORMAT)
    sections = {}
    last_end = HEADER_BYTES
    for index in range(section_count):
        name, section_index, offset, size, crc32, section_flags = struct.unpack_from(
            SECTION_FORMAT, header, desc_offset + index * desc_size
        )
        if name in sections:
            fail(f"duplicate section {name!r}")
        if name not in EXPECTED_SECTIONS:
            fail(f"unknown section {name!r}")
        if section_index != 0 or section_flags != 0:
            fail(f"section {name!r} has nonzero index/flags")
        if offset % 4096:
            fail(f"section {name!r} offset {offset:#x} is not page aligned")
        if offset < last_end or offset + size > actual_size:
            fail(f"section {name!r} overlaps or is outside the file")
        expected_size, _ = EXPECTED_SECTIONS[name]
        if size != expected_size:
            fail(f"section {name!r} size {size} != {expected_size}")
        actual_crc, section_sha = stream_region(model, offset, size)
        if actual_crc != crc32:
            fail(f"section {name!r} CRC {actual_crc:08x} != {crc32:08x}")
        sections[name] = (offset, size, crc32, section_sha)
        last_end = offset + size
        print(
            f"PASS section={name.decode('ascii')} offset={offset:#x} "
            f"bytes={size} crc32={crc32:08x}"
        )

    if set(sections) != set(EXPECTED_SECTIONS):
        fail("section set is incomplete")
    if last_end != actual_size:
        fail(f"unexpected trailing bytes: last end {last_end}, file {actual_size}")

    if raw is not None:
        if not raw.is_file():
            fail(f"raw stream not found: {raw}")
        if sha256_file_bytes(raw) != raw_sha256:
            fail("raw stream SHA-256 does not match PFF1 header")
        print(f"PASS raw_stream bytes={raw.stat().st_size} sha256={sha256_file(raw)}")

    if components is not None:
        for name, (_, component_name) in EXPECTED_SECTIONS.items():
            if component_name is None:
                continue
            component = components / component_name
            if not component.is_file():
                fail(f"component not found: {component}")
            _, expected_size, _, section_sha = sections[name]
            if component.stat().st_size != expected_size:
                fail(f"component {component_name} size mismatch")
            if sha256_file(component) != section_sha:
                fail(f"component {component_name} content mismatch")
            print(f"PASS component={component_name} bytes={expected_size}")

        mlps_offset, mlps_size, _, _ = sections[b"MLPS"]
        if mlps_size != layer_stacks * mlp_stack_bytes:
            fail("MLPS section is not an exact array of fixed-size stacks")
        with model.open("rb") as flat:
            for stack_index in range(layer_stacks):
                pfb1 = components / f"mlp_stack{stack_index:02d}.pfb1"
                if not pfb1.is_file():
                    fail(f"MLP component not found: {pfb1}")
                packed = pfb1.read_bytes()
                if len(packed) != 24 + mlp_stack_bytes:
                    fail(f"MLP component {pfb1.name} size mismatch")
                payload = packed[24:]
                fc0_w = payload[0:32768]
                fc0_b = payload[32768:32896]
                fc1_w = payload[32896:34944]
                fc1_b = payload[34944:35072]
                fc2_w = payload[35072:35200]
                fc2_b = payload[35200:35204]
                runtime_order = fc0_b + fc0_w + fc1_b + fc1_w + fc2_b + fc2_w
                flat.seek(mlps_offset + stack_index * mlp_stack_bytes)
                if flat.read(mlp_stack_bytes) != runtime_order:
                    fail(f"MLP component {pfb1.name} content mismatch")
        print(f"PASS component=mlp_stack00..15 payload_bytes={mlps_size}")

    print(f"PASS PFF1 model={model} bytes={actual_size} sha256={sha256_file(model)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--raw", type=Path)
    parser.add_argument("--components", type=Path)
    args = parser.parse_args()
    try:
        verify(args.model, args.raw, args.components)
    except (OSError, ValueError, struct.error) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
