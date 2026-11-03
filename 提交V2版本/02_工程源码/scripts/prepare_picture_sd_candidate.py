"""Stage a new, namespaced Picture SD candidate. This script never writes media."""
import argparse
import gzip
import hashlib
import json
import re
import struct
from pathlib import Path

from prepare_picture_candidate import align4, identity, prepare, tokens


def boot_clock(blob, clock):
    if clock == "riscv":
        return blob
    h, props, _ = tokens(blob)
    old, pos = props["/chosen/bootargs"]
    if not old.endswith(b"\0") or b"clocksource=" in old:
        raise ValueError("unexpected base clocksource")
    new = old[:-1] + b" clocksource=jiffies\0"
    tree = bytearray(blob[h[2]:h[2] + h[9]])
    struct.pack_into(">I", tree, pos - 8, len(new))
    tree[pos:pos + align4(len(old))] = new + b"\0" * (-len(new) % 4)
    result = bytearray(blob[:h[2]]) + tree + blob[h[3]:h[3] + h[8]]
    header = list(h)
    header[1], header[3], header[9] = len(result), h[2] + len(tree), len(tree)
    struct.pack_into(">10I", result, 0, *header)
    _, after, _ = tokens(result)
    expected = {k: v[0] for k, v in props.items()}
    expected["/chosen/bootargs"] = new
    if {k: v[0] for k, v in after.items()} != expected:
        raise ValueError("unexpected DTB property change")
    return bytes(result)


def stage(repo, raw_path, output, prefix, clock, background_camera=False, hardware_root=None):
    if not re.fullmatch(r"[A-Z][A-Z0-9]{1,3}", prefix):
        raise ValueError("prefix must be 2-4 uppercase letters/digits")
    if output.exists() or not output.resolve().is_relative_to((repo / "build").resolve()):
        raise ValueError("choose a fresh directory inside ignored build/")
    raw = raw_path.read_bytes()
    if raw[:6] not in (b"070701", b"070702") or len(raw) > 0x01000000:
        raise ValueError("expected bounded newc rootfs")
    output.mkdir(parents=True)
    rootfs = output / (prefix + "FS.BIN")
    packed = gzip.compress(raw, compresslevel=6, mtime=0)
    if gzip.decompress(packed) != raw:
        raise ValueError("gzip roundtrip failed")
    rootfs.write_bytes(packed)
    manifest = prepare(repo, rootfs, output, background_camera, hardware_root)
    dtb = output / (prefix + ".DTB")
    dtb.write_bytes(boot_clock((output / "br.dtb").read_bytes(), clock))
    (output / "br.dtb").unlink()
    del manifest["files"]["brfs2.bin"], manifest["files"]["br.dtb"]
    manifest["files"][rootfs.name] = identity(rootfs)
    manifest["files"][dtb.name] = identity(dtb)
    manifest["scope"] = ("Namespaced Picture background hardware/software candidate; NOT BoardRelease"
                         if background_camera else "Namespaced Picture SD software candidate; NOT BoardRelease")
    manifest["deployment"] = {"prefix": prefix, "clocksource": clock,
                              "rootfs_encoding": "gzip", "raw_rootfs": identity(raw_path),
                              "existing_files_preserved": True,
                              "loader_name": prefix + "BOOT.BIN"}
    for value in manifest["files"].values():
        path = Path(value["path"])
        if not path.is_absolute():
            path = repo/path
        value["path"] = path.resolve().relative_to(repo.resolve()).as_posix()
    (output / "sd_contract.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    header = '/* Generated new-file SD candidate; original boot files stay intact. */\n'
    for macro, path in (("PICTURE_INITRD", rootfs), ("PICTURE_DTB", dtb)):
        item = identity(path)
        header += '#define %s_NAME "%s"\n#define %s_BYTES %du\n#define %s_CRC 0x%su\n' % (
            macro, path.name, macro, item["bytes"], macro, item["crc32"])
    (output / "picture_payloads.h").write_text(header, encoding="ascii")
    return manifest


def install_contract(repo, output, sectors, partition):
    manifest = json.loads((output / "sd_contract.json").read_text(encoding="utf-8"))
    prefix = manifest["deployment"]["prefix"]
    loader = output / manifest["deployment"]["loader_name"]
    source = output / "loader-picture-candidate.bin"
    if loader.exists() and loader.read_bytes() != source.read_bytes():
        raise ValueError("existing staged loader differs")
    loader.write_bytes(source.read_bytes())
    manifest["sd_loader"] = identity(loader)
    contract = output / (prefix + ".JSN")
    contract.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    entries = []
    for name, address in ((prefix + "FS.BIN", 0x03000000), (prefix + ".DTB", 0x1A000000),
                          (loader.name, 0x01400000), (contract.name, 0x01500000)):
        path = output / name
        value = identity(path)
        entries.append(dict(name=name, address=address, **value))
    result = {"schema_version": 1, "scope": "SD create-only install, NOT BoardRelease",
              "media_sectors": sectors, "partition_lba": partition, "files": entries,
              "sd_written": False, "flash_written": False}
    (output / "install_contract.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    header = "/* Generated exact sizes/CRCs and media geometry; never edits old files. */\n"
    header += "#define INSTALL_MEDIA_SECTORS %du\n#define INSTALL_PARTITION_LBA %du\n" % (sectors, partition)
    header += "#define INSTALL_PAYLOADS { \\\n"
    for item in entries:
        stem, ext = item["name"].split(".")
        short = stem.ljust(8) + ext.ljust(3)
        header += ' {"%s","%s",0x%08xu,%du,0x%su}, \\\n' % (
            item["name"], short, item["address"], item["bytes"], item["crc32"])
    header += "}\n"
    (output / "picture_install_payloads.h").write_text(header, encoding="ascii")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rootfs", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prefix", default="P17")
    parser.add_argument("--clocksource", choices=("riscv", "jiffies"), default="riscv")
    parser.add_argument("--finish-install", action="store_true")
    parser.add_argument("--media-sectors", type=int)
    parser.add_argument("--partition-lba", type=int)
    parser.add_argument("--background-camera", action="store_true")
    parser.add_argument("--hardware-root", type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parent.parent
    try:
        if args.finish_install:
            if not args.media_sectors or args.partition_lba is None:
                raise ValueError("explicit target geometry required")
            install_contract(repo, args.output, args.media_sectors, args.partition_lba)
        else:
            if not args.rootfs:
                raise ValueError("explicit rootfs required")
            stage(repo, args.rootfs, args.output, args.prefix, args.clocksource,
                  args.background_camera, args.hardware_root)
        print("PICTURE_SD_STAGE_PASS sd_written=false")
    except (OSError, ValueError, KeyError, struct.error) as exc:
        parser.exit(2, "PICTURE_SD_STAGE_FAIL %s\n" % exc)
