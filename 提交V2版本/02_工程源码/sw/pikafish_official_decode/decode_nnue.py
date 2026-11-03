#!/usr/bin/env python3
"""
Decode official Pikafish pikafish.nnue (ZSTD) into Stage A/B packs.

Exports (default outdir):
  manifest.json
  ft_biases.i16.bin
  ft_psq_weights.i8.bin      # feature-major [psq_dims][L1], file order (unpermuted)
  ft_threat_weights.i8.bin   # feature-major [threat_dims][L1]
  ft_psqt.i32.bin            # [PSQTBuckets * psq_dims]
  ft_threat_psqt.i32.bin     # [threat_dims * PSQTBuckets]
  official_psq.pfa1          # PFA1 for Stage A (PSQ table only)
  mlp_stackXX.pfb1           # Stage B packs, row-major = official file order

Limits (see README.md):
  - FT Packus permute is identity on scalar builds; AVX2 order not applied.
  - MLP export uses file-order as row-major (matches conceptual W[out][in]).
  - Pair-activation input interleave for fc1/fc2 is NOT remapped; Stage B
    uses [sqr|clip] concat. Full bit-exact vs AVX2 Pikafish needs extra work.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path

try:
    import zstandard as zstd
except ImportError:
    zstd = None

VERSION = 0x6A448AFA
LEB_MAGIC = b"COMPRESSED_LEB128"

L1 = 1024
L2 = 32
L3 = 32
PSQT_BUCKETS = 16
LAYER_STACKS = 16
PSQ_DIMS = 6 * 4 * 689  # 16536
THREAT_DIMS = 45547
MAX_SIMD = 32

THREAT_HASH = 0x2E6B9D04
PSQ_HASH = 0x7F234CB8

PFA1_MAGIC = 0x31414650  # 'PFA1'
PFB1_MAGIC = 0x31424650  # 'PFB1'
PACK_VERSION = 0x00010000

# Fully decoded, page-aligned model image.  Unlike the upstream .nnue file this
# container has neither an outer ZSTD frame nor inner COMPRESSED_LEB128 arrays.
# The board loader can validate the small fixed header and copy every section
# directly into Pikafish's already allocated NNUE arrays.
PFF1_MAGIC = b"PFF1"
PFF1_VERSION = 0x00010000
PFF1_HEADER_BYTES = 4096
PFF1_FLAGS = 0x00000007  # little-endian | fully decoded | scalar/file order
PFF1_HEADER_FORMAT = "<4sIIIIIIIHHHHIIIIQII32s"
PFF1_SECTION_FORMAT = "<4sIQQII"
PFF1_SECTION_NAMES = (b"FTBI", b"FTTW", b"FTTP", b"FTPW", b"FTPP", b"MLPS")


def u32(x: int) -> int:
    return x & 0xFFFFFFFF


def combine_hash(hashes: list[int]) -> int:
    h = 0
    for c in hashes:
        h = u32((h << 1) | (h >> 31))
        h ^= c
    return h


def ft_hash() -> int:
    return combine_hash([THREAT_HASH, PSQ_HASH]) ^ (L1 * 2)


def affine_hash(prev: int, out_dims: int) -> int:
    hv = u32(0xCC03DAE4 + out_dims)
    hv ^= u32(prev >> 1)
    hv ^= u32(prev << 31)
    return hv


def clip_hash(prev: int) -> int:
    return u32(0x538D24C7 + prev)


def arch_hash() -> int:
    hv = u32(0xEC42E90D ^ (L1 * 2))
    hv = affine_hash(hv, L2)  # fc0
    hv = clip_hash(hv)  # ac0 (sqr omitted)
    hv = affine_hash(hv, L3)  # fc1
    hv = clip_hash(hv)  # ac1
    hv = affine_hash(hv, 1)  # fc2
    return hv


def net_hash() -> int:
    return ft_hash() ^ arch_hash()


def ceil_to_multiple(n: int, base: int) -> int:
    return (n + base - 1) // base * base


def align_up(n: int, alignment: int) -> int:
    return (n + alignment - 1) // alignment * alignment


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_flat_nnue(
    path: Path,
    decoded_stream: bytes,
    biases: bytes,
    threat_weights: bytes,
    threat_psqt: bytes,
    psq_weights: bytes,
    psqt: bytes,
    mlp_stacks: list[bytes],
) -> dict:
    """Write and self-verify a no-decompression PFF1 image."""
    if len(mlp_stacks) != LAYER_STACKS:
        raise ValueError(f"PFF1 needs {LAYER_STACKS} MLP stacks, got {len(mlp_stacks)}")
    mlp_stack_bytes = len(mlp_stacks[0])
    if any(len(stack) != mlp_stack_bytes for stack in mlp_stacks):
        raise ValueError("PFF1 MLP stack sizes differ")

    payloads = (
        biases,
        threat_weights,
        threat_psqt,
        psq_weights,
        psqt,
        b"".join(mlp_stacks),
    )
    sections = []
    offset = PFF1_HEADER_BYTES
    for name, payload in zip(PFF1_SECTION_NAMES, payloads):
        offset = align_up(offset, 4096)
        sections.append(
            {
                "name": name,
                "index": 0,
                "offset": offset,
                "size": len(payload),
                "crc32": zlib.crc32(payload) & 0xFFFFFFFF,
                "flags": 0,
            }
        )
        offset += len(payload)
    file_bytes = offset

    header_fixed = struct.pack(
        PFF1_HEADER_FORMAT,
        PFF1_MAGIC,
        PFF1_VERSION,
        PFF1_HEADER_BYTES,
        PFF1_FLAGS,
        VERSION,
        net_hash(),
        ft_hash(),
        arch_hash(),
        L1,
        L2,
        L3,
        LAYER_STACKS,
        PSQ_DIMS,
        THREAT_DIMS,
        PSQT_BUCKETS,
        len(sections),
        file_bytes,
        mlp_stack_bytes,
        0,
        hashlib.sha256(decoded_stream).digest(),
    )
    descs = b"".join(
        struct.pack(
            PFF1_SECTION_FORMAT,
            section["name"],
            section["index"],
            section["offset"],
            section["size"],
            section["crc32"],
            section["flags"],
        )
        for section in sections
    )
    if len(header_fixed) + len(descs) > PFF1_HEADER_BYTES:
        raise ValueError("PFF1 header overflow")
    header = header_fixed + descs
    header += bytes(PFF1_HEADER_BYTES - len(header))

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(header)
        for section, payload in zip(sections, payloads):
            if f.tell() > section["offset"]:
                raise ValueError(f"PFF1 section overlap: {section['name']!r}")
            f.write(bytes(section["offset"] - f.tell()))
            f.write(payload)
        if f.tell() != file_bytes:
            raise ValueError(f"PFF1 size {f.tell()} != planned {file_bytes}")

    # Re-read the file rather than trusting the in-memory plan.  This catches
    # short writes, descriptor mistakes, truncation and section corruption.
    with path.open("rb") as f:
        disk_header = f.read(PFF1_HEADER_BYTES)
        if disk_header != header:
            raise ValueError("PFF1 header readback mismatch")
        for section, payload in zip(sections, payloads):
            f.seek(section["offset"])
            disk_payload = f.read(section["size"])
            if len(disk_payload) != section["size"]:
                raise ValueError(f"PFF1 section truncated: {section['name']!r}")
            if (zlib.crc32(disk_payload) & 0xFFFFFFFF) != section["crc32"]:
                raise ValueError(f"PFF1 section CRC mismatch: {section['name']!r}")
            if disk_payload != payload:
                raise ValueError(f"PFF1 section readback mismatch: {section['name']!r}")
        f.seek(0, 2)
        if f.tell() != file_bytes:
            raise ValueError(f"PFF1 disk size {f.tell()} != {file_bytes}")

    return {
        "file": path.name,
        "bytes": file_bytes,
        "sha256": sha256_file(path),
        "header_bytes": PFF1_HEADER_BYTES,
        "format_version": f"0x{PFF1_VERSION:08X}",
        "flags": f"0x{PFF1_FLAGS:08X}",
        "mlp_stack_bytes": mlp_stack_bytes,
        "sections": [
            {
                "name": section["name"].decode("ascii"),
                "offset": section["offset"],
                "bytes": section["size"],
                "crc32": f"{section['crc32']:08x}",
            }
            for section in sections
        ],
    }


class Reader:
    def __init__(self, data: memoryview):
        self.data = data
        self.pos = 0

    def remaining(self) -> int:
        return len(self.data) - self.pos

    def read(self, n: int) -> memoryview:
        if self.pos + n > len(self.data):
            raise EOFError(f"need {n} bytes at {self.pos}, have {self.remaining()}")
        mv = self.data[self.pos : self.pos + n]
        self.pos += n
        return mv

    def u32(self) -> int:
        return struct.unpack_from("<I", self.read(4))[0]

    def i32(self) -> int:
        return struct.unpack_from("<i", self.read(4))[0]

    def bytes(self, n: int) -> bytes:
        return bytes(self.read(n))

    def little_endian_array(self, fmt: str, count: int) -> bytes:
        size = struct.calcsize(fmt)
        return self.bytes(size * count)

    def leb128_signed(self, count: int, elem_bits: int = 32) -> list[int]:
        magic = self.bytes(len(LEB_MAGIC))
        if magic != LEB_MAGIC:
            raise ValueError(f"LEB128 magic mismatch: {magic!r}")
        bytes_left = self.u32()
        start = self.pos
        out: list[int] = []
        result = 0
        shift = 0
        while len(out) < count:
            if self.pos - start >= bytes_left and bytes_left > 0:
                # allow reading exactly bytes_left
                pass
            if self.pos >= start + bytes_left:
                raise ValueError("LEB128 truncated")
            byte = self.data[self.pos]
            self.pos += 1
            result |= (byte & 0x7F) << (shift % 32)
            shift += 7
            if (byte & 0x80) == 0:
                if shift < 32 and (byte & 0x40) != 0:
                    result |= ~((1 << shift) - 1)
                # sign-extend into Python int, then narrow
                if elem_bits == 16:
                    result = struct.unpack("<h", struct.pack("<H", result & 0xFFFF))[0]
                else:
                    result = struct.unpack("<i", struct.pack("<I", result & 0xFFFFFFFF))[0]
                out.append(result)
                result = 0
                shift = 0
        consumed = self.pos - start
        if consumed != bytes_left:
            raise ValueError(f"LEB128 bytes_left={bytes_left} consumed={consumed}")
        return out


def decompress_nnue(path: Path) -> bytes:
    raw = path.read_bytes()
    if raw[:4] == b"\x28\xb5\x2f\xfd":
        if zstd is None:
            raise RuntimeError("pip install zstandard  (or provide already-decompressed .nnue.bin)")
        dctx = zstd.ZstdDecompressor()
        return dctx.decompress(raw, max_output_size=512 << 20)
    # already raw
    return raw


def write_pfa1(path: Path, weights: bytes, feature_rows: int, max_active: int = 32) -> None:
    assert len(weights) == feature_rows * L1
    hdr = struct.pack(
        "<IIHHHHIIII",
        PFA1_MAGIC,
        PACK_VERSION,
        L1,
        256,  # tile_width
        4,  # tile_count
        max_active,
        feature_rows,
        1,  # flags: row-major int8
        feature_rows * L1,
        0,  # crc32 skip
    )
    path.write_bytes(hdr + weights)


def write_pfb1(
    path: Path,
    fc0_w: bytes,
    fc0_b: bytes,
    fc1_w: bytes,
    fc1_b: bytes,
    fc2_w: bytes,
    fc2_b: bytes,
) -> None:
    hdr = struct.pack(
        "<IIHHHHII",
        PFB1_MAGIC,
        PACK_VERSION,
        L1,
        L2,
        L3,
        6,  # weight_scale_bits
        1,  # flags row-major
        0,  # crc32
    )
    path.write_bytes(hdr + fc0_w + fc0_b + fc1_w + fc1_b + fc2_w + fc2_b)


def read_affine_i8(r: Reader, out_dims: int, in_dims: int) -> tuple[bytes, bytes]:
    padded_in = ceil_to_multiple(in_dims, MAX_SIMD)
    biases = r.little_endian_array("<i", out_dims)  # i32
    weights = r.bytes(out_dims * padded_in)  # i8 file order = conceptual row-major
    # Stage B uses exact in_dims (no pad) for fc0/fc1/fc2 dims that already align.
    if padded_in != in_dims:
        # strip pad columns if any
        rows = []
        for o in range(out_dims):
            rows.append(weights[o * padded_in : o * padded_in + in_dims])
        weights = b"".join(rows)
    return weights, biases


def decode(
    data: bytes,
    outdir: Path,
    stacks: int | None = None,
    flat_output: Path | None = None,
    source_sha256: str | None = None,
) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    raw_path = outdir / "pikafish.nnue.raw"
    raw_path.write_bytes(data)
    r = Reader(memoryview(data))

    version = r.u32()
    if version != VERSION:
        raise ValueError(f"bad Version {version:#x}, expected {VERSION:#x}")
    file_hash = r.u32()
    desc_len = r.u32()
    desc = r.bytes(desc_len).decode("utf-8", errors="replace")
    expect = net_hash()
    if file_hash != expect:
        raise ValueError(f"net hash {file_hash:#x} != expected {expect:#x}")

    # Feature transformer
    ft_hdr = r.u32()
    if ft_hdr != ft_hash():
        raise ValueError(f"FT hash {ft_hdr:#x} != {ft_hash():#x}")

    biases = r.leb128_signed(L1, elem_bits=16)
    threat_w = r.bytes(THREAT_DIMS * L1)
    threat_psqt = r.leb128_signed(THREAT_DIMS * PSQT_BUCKETS, elem_bits=32)
    psq_w = r.bytes(PSQ_DIMS * L1)
    psqt = r.leb128_signed(PSQT_BUCKETS * PSQ_DIMS, elem_bits=32)

    biases_b = struct.pack(f"<{L1}h", *biases)
    psqt_b = struct.pack(f"<{len(psqt)}i", *psqt)
    threat_psqt_b = struct.pack(f"<{len(threat_psqt)}i", *threat_psqt)

    (outdir / "ft_biases.i16.bin").write_bytes(biases_b)
    (outdir / "ft_psq_weights.i8.bin").write_bytes(psq_w)
    (outdir / "ft_threat_weights.i8.bin").write_bytes(threat_w)
    (outdir / "ft_psqt.i32.bin").write_bytes(psqt_b)
    (outdir / "ft_threat_psqt.i32.bin").write_bytes(threat_psqt_b)

    write_pfa1(outdir / "official_psq.pfa1", psq_w, PSQ_DIMS, max_active=32)
    # Threat table is large (~46MB); still emit for Stage A experiments.
    write_pfa1(outdir / "official_threat.pfa1", threat_w, THREAT_DIMS, max_active=64)

    n_stacks = LAYER_STACKS if stacks is None else stacks
    arch_expect = arch_hash()
    mlp_info = []
    mlp_payloads = []

    for s in range(LAYER_STACKS):
        stack_hdr = r.u32()
        if stack_hdr != arch_expect:
            raise ValueError(f"stack {s} hash {stack_hdr:#x} != {arch_expect:#x}")

        # fc0: sparse affine 1024 -> 32
        fc0_w, fc0_b = read_affine_i8(r, L2, L1)
        # ac0: no params (sqr also no params in file)
        # fc1: 64 -> 32
        fc1_w, fc1_b = read_affine_i8(r, L3, L2 * 2)
        # ac1: no params
        # fc2: 128 -> 1
        fc2_w, fc2_b = read_affine_i8(r, 1, L2 * 2 + L3 * 2)
        # PFF1 stores each layer exactly in Pikafish read_parameters() order so
        # the runtime can feed the fixed-size span directly to the existing
        # layer loaders: bias first, then row-major/file-order weights.
        mlp_payloads.append(fc0_b + fc0_w + fc1_b + fc1_w + fc2_b + fc2_w)

        if s < n_stacks:
            name = f"mlp_stack{s:02d}.pfb1"
            write_pfb1(outdir / name, fc0_w, fc0_b, fc1_w, fc1_b, fc2_w, fc2_b)
            mlp_info.append(
                {
                    "stack": s,
                    "file": name,
                    "fc0_w": len(fc0_w),
                    "fc1_w": len(fc1_w),
                    "fc2_w": len(fc2_w),
                }
            )

    if r.remaining() != 0:
        raise ValueError(f"trailing {r.remaining()} bytes after parse")

    if flat_output is None:
        flat_output = outdir / "pikafish.nnue.flat"
    flat_info = write_flat_nnue(
        flat_output,
        data,
        biases_b,
        threat_w,
        threat_psqt_b,
        psq_w,
        psqt_b,
        mlp_payloads,
    )

    manifest = {
        "source_desc": desc,
        "version": f"0x{VERSION:08X}",
        "net_hash": f"0x{file_hash:08X}",
        "ft_hash": f"0x{ft_hash():08X}",
        "arch_hash": f"0x{arch_expect:08X}",
        "l1": L1,
        "psq_dims": PSQ_DIMS,
        "threat_dims": THREAT_DIMS,
        "psqt_buckets": PSQT_BUCKETS,
        "layer_stacks": LAYER_STACKS,
        "exported_stacks": n_stacks,
        "ft_unpermuted": True,
        "mlp_row_major_file_order": True,
        "mlp_parameter_order": "bias_then_weights_per_layer",
        "pair_activation_interleave": False,
        "runtime_decompression_required": False,
        "artifacts": {
            "zstd_unpacked_stream": raw_path.name,
            "fully_decoded_flat": flat_info,
            "ft_biases": "ft_biases.i16.bin",
            "ft_psq_weights": "ft_psq_weights.i8.bin",
            "ft_threat_weights": "ft_threat_weights.i8.bin",
            "ft_psqt": "ft_psqt.i32.bin",
            "ft_threat_psqt": "ft_threat_psqt.i32.bin",
            "official_psq_pfa1": "official_psq.pfa1",
            "official_threat_pfa1": "official_threat.pfa1",
            "mlp_stacks": mlp_info,
        },
        "sizes": {
            "source_zstd_bytes": None,
            "decompressed_bytes": len(data),
            "fully_decoded_bytes": flat_info["bytes"],
            "psq_weight_bytes": len(psq_w),
            "threat_weight_bytes": len(threat_w),
        },
        "hashes": {
            "source_zstd_sha256": source_sha256,
            "zstd_unpacked_stream_sha256": hashlib.sha256(data).hexdigest(),
            "fully_decoded_flat_sha256": flat_info["sha256"],
        },
    }
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description="Decode official pikafish.nnue")
    ap.add_argument(
        "--nnue",
        type=Path,
        default=Path(__file__).resolve().parents[3]
        / "xiangqi_oss"
        / "Pikafish"
        / "pikafish.nnue",
    )
    ap.add_argument(
        "--outdir",
        type=Path,
        default=Path(__file__).resolve().parent / "out",
    )
    ap.add_argument(
        "--stacks",
        type=int,
        default=16,
        help="How many MLP stacks to write as PFB1 (always parse all 16)",
    )
    ap.add_argument(
        "--flat-output",
        type=Path,
        help="PFF1 output path (default: OUTDIR/pikafish.nnue.flat)",
    )
    args = ap.parse_args()

    if not args.nnue.is_file():
        # try performance_soc_linux-relative
        alt = Path(__file__).resolve().parents[2] / "xiangqi_oss" / "Pikafish" / "pikafish.nnue"
        # workspace root
        alt2 = Path(r"g:\fpga\xiangqi_oss\Pikafish\pikafish.nnue")
        for cand in (alt, alt2):
            if cand.is_file():
                args.nnue = cand
                break
        else:
            print(f"FAIL nnue not found: {args.nnue}", file=sys.stderr)
            return 1

    print(f"NNUE {args.nnue}")
    source_bytes = args.nnue.stat().st_size
    source_sha256 = sha256_file(args.nnue)
    print("decompressing...")
    data = decompress_nnue(args.nnue)
    print(f"decompressed {len(data)} bytes")
    print(f"export -> {args.outdir}")
    man = decode(
        data,
        args.outdir,
        stacks=args.stacks,
        flat_output=args.flat_output,
        source_sha256=source_sha256,
    )
    man["sizes"]["source_zstd_bytes"] = source_bytes
    (args.outdir / "manifest.json").write_text(
        json.dumps(man, indent=2), encoding="utf-8"
    )
    print(f"PASS desc={man['source_desc']!r}")
    print(f"PASS net_hash={man['net_hash']} stacks={man['exported_stacks']}")
    print(f"PASS psq_rows={man['psq_dims']} threat_rows={man['threat_dims']}")
    print(
        "PASS flat="
        f"{man['artifacts']['fully_decoded_flat']['bytes']} bytes "
        f"sha256={man['artifacts']['fully_decoded_flat']['sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
