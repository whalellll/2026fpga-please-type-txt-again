"""Prepare isolated Picture DTB/SD contract; never write a card or release files.

The frozen base DTB is patched structurally, preserving its other properties.
This avoids reserializing the board-qualified tree with a different dtc build.
Use Python 3.14.4 for release evidence. No third-party modules are required.
"""
import argparse
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path


def align4(value):
    return (value + 3) & ~3


def tokens(blob):
    header = struct.unpack_from(">10I", blob)
    magic, total, off_struct, off_strings, _, version, compatible, _, strings_size, structure_size = header
    if magic != 0xD00DFEED or total != len(blob) or version != 17 or compatible > 17:
        raise ValueError("unsupported or truncated DTB")
    if off_struct + structure_size > total or off_strings + strings_size > total:
        raise ValueError("DTB block out of bounds")
    strings = blob[off_strings:off_strings + strings_size]
    position, stack, properties, ends = off_struct, [], {}, {}
    while position < off_struct + structure_size:
        offset = position - off_struct
        token, = struct.unpack_from(">I", blob, position)
        position += 4
        if token == 1:
            end = blob.index(b"\0", position, off_struct + structure_size)
            stack.append(blob[position:end].decode("ascii"))
            position = align4(end + 1)
        elif token == 2:
            ends["/".join(stack)] = offset
            stack.pop()
        elif token == 3:
            length, nameoff = struct.unpack_from(">II", blob, position)
            position += 8
            end = strings.index(b"\0", nameoff)
            name = strings[nameoff:end].decode("ascii")
            key = "/".join(stack) + "/" + name
            if key in properties or position + length > off_struct + structure_size:
                raise ValueError("invalid/duplicate DTB property")
            properties[key] = (blob[position:position + length], position - off_struct)
            position = align4(position + length)
        elif token == 4:
            pass
        elif token == 9:
            if stack:
                raise ValueError("unbalanced DTB")
            return header, properties, ends
        else:
            raise ValueError("invalid DTB token")
    raise ValueError("missing DTB END")


def snapshot_dtb(blob, initrd_bytes, background_camera=False):
    header, props, ends = tokens(blob)
    required = {"/reserved-memory/#address-cells": b"\0\0\0\1",
                "/reserved-memory/#size-cells": b"\0\0\0\1",
                "/reserved-memory/ranges": b"",
                "/chosen/linux,initrd-start": struct.pack(">I", 0x03000000)}
    if any(props.get(key, (None,))[0] != value for key, value in required.items()):
        raise ValueError("base DTB layout differs from V2.1")
    if not 0 < initrd_bytes <= 0x01000000:
        raise ValueError("rootfs exceeds frozen loader aperture")
    if any(key.startswith("/reserved-memory/snapshot@") for key in props):
        raise ValueError("base DTB already contains a snapshot node")
    if any(key.startswith("/reserved-memory/camera-capture@") for key in props):
        raise ValueError("base DTB already contains a private camera node")
    structure = bytearray(blob[header[2]:header[2] + header[9]])
    initrd = props["/chosen/linux,initrd-end"]
    if len(initrd[0]) != 4:
        raise ValueError("invalid initrd end")
    struct.pack_into(">I", structure, initrd[1], 0x03000000 + initrd_bytes)
    strings = bytearray(blob[header[3]:header[3] + header[8]])

    def prop(name, value):
        encoded = name.encode("ascii") + b"\0"
        # Append a complete string; do not accidentally match a name suffix.
        offset = len(strings)
        strings.extend(encoded)
        return struct.pack(">III", 3, len(value), offset) + value + b"\0" * (-len(value) % 4)

    # CLINT is decoded inside the advertised DRAM bank. Without a no-map
    # reservation the kernel can allocate objects/stacks at 0x0200xxxx and
    # corrupt timer registers or issue unsupported AMOs to a peripheral.
    reservations = (("clint-mmio@2000000", 0x02000000, 0x00010000),
                    ("snapshot@1b600000", 0x1B600000, 0x00200000))
    if background_camera:
        reservations += (("camera-capture@1b800000", 0x1B800000, 0x00400000),)
    node = b""
    for name, address, length in reservations:
        existing = "/reserved-memory/" + name + "/"
        if existing + "reg" in props:
            if (props[existing + "reg"][0] != struct.pack(">II", address, length)
                    or props.get(existing + "no-map", (None,))[0] != b""):
                raise ValueError("conflicting existing reservation: " + name)
            continue
        child = struct.pack(">I", 1) + name.encode("ascii") + b"\0"
        child += b"\0" * (-len(child) % 4)
        child += prop("reg", struct.pack(">II", address, length))
        node += child + prop("no-map", b"") + struct.pack(">I", 2)
    end = ends["/reserved-memory"]
    structure[end:end] = node
    # Preserve the original header-to-structure prefix (reservation map).
    out = bytearray(blob[:header[2]]) + structure + strings
    updated = list(header)
    updated[1], updated[3], updated[8], updated[9] = len(out), header[2] + len(structure), len(strings), len(structure)
    struct.pack_into(">10I", out, 0, *updated)
    _, after, _ = tokens(out)
    expected = {key: value[0] for key, value in props.items()}
    expected["/chosen/linux,initrd-end"] = struct.pack(">I", 0x03000000 + initrd_bytes)
    for name, address, length in reservations:
        expected["/reserved-memory/" + name + "/reg"] = struct.pack(">II", address, length)
        expected["/reserved-memory/" + name + "/no-map"] = b""
    if {key: value[0] for key, value in after.items()} != expected:
        raise ValueError("unexpected property change")
    return bytes(out)


def identity(path):
    blob = path.read_bytes()
    return {"path": str(path.resolve()), "bytes": len(blob),
            "sha256": hashlib.sha256(blob).hexdigest(),
            "crc32": "%08x" % (zlib.crc32(blob) & 0xffffffff)}


def prepare(repo, rootfs, output, background_camera=False, hardware_root=None):
    if background_camera and hardware_root is None:
        raise ValueError("background camera requires a completed, audited hardware build")
    output.mkdir(parents=True, exist_ok=True)
    target = output / "br.dtb"
    production = (repo / "linux/boot/soc.dtb").resolve()
    if target.resolve() == production or output.resolve() == (repo / "linux/boot").resolve():
        raise ValueError("candidate output must not overwrite production")
    fixed_sbit = identity(repo / "artifacts/soc_top.sbit")
    fixed_hash = "a3f288b30991b111c3a840c03aae18694c748529ea57278c228b7d277c408b33"
    if fixed_sbit["sha256"] != fixed_hash:
        raise ValueError("current bitstream is not frozen snapshot 5f802f47")
    hardware = None
    if background_camera:
        if hardware_root is None:
            raise ValueError("background camera requires a completed, audited hardware build")
        # Run the ordinary release gates against the isolated hardware build,
        # then compare all frozen source/recipe bytes with this source tree.
        # Never accept a caller-supplied bitstream hash as a gate substitute.
        with tempfile.TemporaryDirectory(prefix="picture-hardware-check-") as folder:
            result_path = Path(folder) / "hardware.json"
            completed = subprocess.run([
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                str(repo / "scripts/check_picture_background_candidate.ps1"),
                "-HardwareRoot", str(hardware_root), "-Output", str(result_path)],
                capture_output=True, timeout=300)
            if completed.returncode:
                raise ValueError("background hardware build gates failed: " +
                                 completed.stderr.decode(errors="replace")[-1500:])
            hardware = json.loads(result_path.read_text(encoding="utf-8"))
        fixed_hash = hardware["sbit_sha256"]
    elif hardware_root is not None:
        raise ValueError("hardware root is only valid with background camera mode")
    base_blob = production.read_bytes()
    if len(base_blob) != 2335 or "%08x" % (zlib.crc32(base_blob) & 0xffffffff) != "cf189f13":
        raise ValueError("base DTB is not the V2.1 board-qualified DTB")
    target.write_bytes(snapshot_dtb(base_blob, rootfs.stat().st_size, background_camera))
    inputs = {"brfw.bin": repo / "linux/boot/fw_jump.bin", "Image": repo / "linux/boot/Image",
              "brfs2.bin": rootfs, "br.dtb": target,
              "pikafish.pff": repo / "linux/boot/pikafish.pff", "pikafish.atk": repo / "linux/boot/pikafish.atk"}
    manifest = {"schema_version": 1, "scope": "Picture software candidate; NOT BoardRelease",
                "board_validated": False, "sd_written": False,
                "python": sys.version, "fixed_sbit_sha256": fixed_hash,
                "base_dtb": identity(production),
                "files": {name: identity(path) for name, path in inputs.items()}}
    if hardware is not None:
        manifest["scope"] = "Picture background capture hardware/software candidate; NOT BoardRelease"
        manifest["hardware_build"] = hardware
        manifest["background_camera"] = True
    for item in [manifest["base_dtb"]] + list(manifest["files"].values()):
        try:
            item["path"] = Path(item["path"]).relative_to(repo.resolve()).as_posix()
        except ValueError:
            pass
    (output / "sd_contract.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    values = manifest["files"]
    text = "/* Generated from sd_contract.json; do not edit. */\n"
    for prefix, name in (("PICTURE_INITRD", "brfs2.bin"), ("PICTURE_DTB", "br.dtb")):
        text += "#define %s_BYTES %du\n#define %s_CRC 0x%su\n" % (
            prefix, values[name]["bytes"], prefix, values[name]["crc32"])
    (output / "picture_payloads.h").write_text(text, encoding="ascii")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rootfs", type=Path)
    parser.add_argument("--output", type=Path, default=Path("build/picture-candidate"))
    parser.add_argument("--background-camera", action="store_true")
    parser.add_argument("--hardware-root", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    try:
        result = prepare(root, args.rootfs or root / "linux/boot/rootfs.cpio", args.output,
                         args.background_camera, args.hardware_root)
        print("PICTURE_DTB_CANDIDATE_PASS bytes=%s crc32=%s board_validated=false" % (
            result["files"]["br.dtb"]["bytes"], result["files"]["br.dtb"]["crc32"]))
    except (OSError, ValueError, KeyError, struct.error) as exc:
        parser.exit(2, "PICTURE_DTB_CANDIDATE_FAIL %s\n" % exc)
