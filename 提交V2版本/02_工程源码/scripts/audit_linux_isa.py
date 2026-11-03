"""Inspect bundled Linux inputs without executing or changing those inputs.

The evidence describes build metadata, not an exhaustive instruction proof.
Python 3 standard library only; output is deterministic for identical inputs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib


def digest(data):
    return hashlib.sha256(data).hexdigest()


def cpio_files(data):
    offset = 0
    while offset + 110 <= len(data):
        header = data[offset:offset + 110]
        if header[:6] not in (b"070701", b"070702"):
            raise ValueError("Expected a newc/CRC cpio archive")
        size = int(header[54:62], 16)
        namesize = int(header[94:102], 16)
        name = data[offset + 110:offset + 110 + namesize - 1].decode("utf-8")
        start = (offset + 110 + namesize + 3) & ~3
        if start + size > len(data):
            raise ValueError("Truncated cpio payload")
        offset = (start + size + 3) & ~3
        if name == "TRAILER!!!":
            return
        yield name, data[start:start + size]
    raise ValueError("Missing cpio trailer")


def elf_evidence(name, data):
    if data[4:6] != b"\x01\x01":
        raise ValueError("Expected little-endian ELF32: " + name)
    flags = struct.unpack_from("<I", data, 36)[0]
    machine = struct.unpack_from("<H", data, 18)[0]
    shoff = struct.unpack_from("<I", data, 32)[0]
    shsize, shcount, strindex = struct.unpack_from("<HHH", data, 46)
    attributes = b""
    if shcount:
        headers = [struct.unpack_from("<10I", data, shoff + n * shsize)
                   for n in range(shcount)]
        strings = headers[strindex]
        names = data[strings[4]:strings[4] + strings[5]]
        for header in headers:
            section_name = names[header[0]:].split(b"\0", 1)[0]
            if section_name == b".riscv.attributes":
                attributes = data[header[4]:header[4] + header[5]]
    arches = sorted(set(value.decode("ascii") for value in
                        re.findall(rb"rv(?:32|64)[a-z0-9_]+", attributes)))
    return {
        "path": name, "bytes": len(data), "sha256": digest(data),
        "elf_class": 32, "machine": machine, "e_flags": flags,
        "ef_riscv_rvc": bool(flags & 1),
        "riscv_attributes_present": bool(attributes),
        "riscv_arch_attributes": arches,
    }


def audit(root):
    image_path = "linux/boot/Image"
    image = (root / image_path).read_bytes()
    marker = image.find(b"IKCFG_ST")
    if marker < 0:
        raise ValueError("Image lacks embedded IKCONFIG")
    config = zlib.decompress(image[marker + 8:], 31).decode("utf-8")
    symbols = ("CONFIG_32BIT", "CONFIG_MMU", "CONFIG_RISCV_ISA_C", "CONFIG_FPU")
    lines = [line for line in config.splitlines()
             if any(line.startswith(symbol + "=") or
                    line == "# " + symbol + " is not set" for symbol in symbols)]
    archives = []
    for path in ("linux/boot/rootfs.cpio",
                 "linux/images/prebuilt_2022_03_23/rootfs.cpio"):
        data = (root / path).read_bytes()
        elfs = [elf_evidence(name, payload) for name, payload in cpio_files(data)
                if payload.startswith(b"\x7fELF")]
        archives.append({"path": path, "sha256": digest(data),
                         "elf_count": len(elfs), "elf_files": elfs})
    opensbi_path = "linux/boot/fw_jump.bin"
    opensbi = (root / opensbi_path).read_bytes()
    return {
        "scope": "Bundled Linux binary build metadata; no Linux boot performed",
        "kernel": {"path": image_path, "bytes": len(image), "sha256": digest(image),
                   "evidence": "IKCONFIG embedded in this exact Image",
                   "configuration": lines},
        "rootfs": archives,
        "opensbi": {"path": opensbi_path, "bytes": len(opensbi),
                    "sha256": digest(opensbi), "format": "raw binary",
                    "complete_isa_build_record_available": False},
        "interpretation": [
            "The kernel configuration above comes from this exact Image and records its build-time C and FPU settings.",
            "Each rootfs ELF entry records its actual e_flags, EF_RISCV_RVC declaration and any available ISA attributes.",
            "ELF flags and configuration are metadata evidence, not a proof that every executable byte excludes C or other extensions.",
            "OpenSBI is a raw .bin without ELF ISA attributes or a complete build record; its full ISA requirements remain unverified.",
            "current CPU machine mode does not establish the supervisor/Sv32/MMU and platform support required for Linux, regardless of the C extension setting.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.root / "docs/linux_isa_evidence.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(audit(args.root), stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print("LINUX_ISA_METADATA_AUDIT_COMPLETE " + str(output))
