"""Build private CPU60 RAM materials, never an installer or a board receipt.

The six payloads retain the loader RAM addresses. A matching loader, current
CRAM assignment and actual SD installation are deliberately separate steps.
--inspect validates and assembles in memory without writing any output.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import struct
import subprocess
import tarfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "127ff9a5b517f0f298ab91492d07ef2a1cf44f5b"
SBI_SOURCE = "artifacts/integrated60_20261024/runtime-inputs/fw_jump.bin"
SBI_SHA = "e709883480124396dddb68ab353c86afbac17e4da99393cfafd765ec379b5f2b"
BASE_SHA = "6b06ecb4da84007459ea94571602a9ea31d16bbbea4e5df10d263fccebf38caa"
VOICE_BASE_SHA = "1a58a1cbb6e9acee4ee0e28a4504a5fcb539bc17e284e05733516b4f55919d33"
KERNEL_SHA = "be890ef8ff275721abf8e4267292521467bd16189a4acbe2113369fc9fbc188f"
DTB_SHA = "7532b76ebdc06d93f2ebd99148af0a62fcb157ace3f2a4d248ea0b8bf9f51c12"
P3_TARGET = "6565ad378524f3e2a34f6cdba6fcc46b2f928eb3677c0fe80971e05e8ec2ebdd"
VOICE_ARCHIVE_REF = "1d293e9287e69f18f93305a8ce7efd7d1d3b8b03"
MODEL_HASHES = {
    "board.xqm": "fbd8a4e8bcd78918a44674eb69225f7d82ac4547ac24a777ea4b4b11cf495efe",
    "detector.xqm": "d65b4b8686520ae1546d0a207c1bcb9f30efe0d40e7f5c8245c4dd11ff9ca09d",
    "classifier.xqm": "fc03674b9f73f8c0d0fffd1cbdd10b4edebccd2056740d8aeec7e472b522697f",
    "refinement_rng.bin": "646265b1052977ad5fc3aca0f7da40716a5f1a3ad08d845478c7e95109be8e63",
}
BALANCED_SHA = "3e43041fd3e531ce130b56c0a460a1c7375420eea0e07afdf533012ae41da973"
PFF_SHA = "de0906fa1bea82248523eb39fc6b2956613b02ae675ccf67eef3f392de939260"
ATK_SHA = "2235f0b1cca2e447a828bf1c7c7247237580603026d6152954da07efca2d474c"
STAGEB_SHA = "9707836b14e84c74e05921f0872ff2c17391e879a06f569c542f485c09834197"
APERTURE = 0x01000000


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def identity(data: bytes) -> dict:
    return dict(bytes=len(data), sha256=digest(data), crc32=f"{zlib.crc32(data):08x}")


def safe_name(name: str) -> str:
    while name.startswith("./"):
        name = name[2:]
    if name in ("", "."):
        return "."
    path = PurePosixPath(name)
    require(not path.is_absolute() and ".." not in path.parts and "\\" not in name,
            "Unsafe archive path")
    require(str(path) == name, "Noncanonical archive path")
    return name


def cpio_read(data: bytes, *, historical_overlay: bool = False) -> dict[str, tuple[list[int], bytes]]:
    """Read complete newc, rejecting duplicate paths and hidden tail archives."""
    offset, rows = 0, {}
    while offset + 110 <= len(data):
        require(data[offset:offset + 6] == b"070701", "Expected raw newc")
        fields = [int(data[offset + 6 + i * 8:offset + 14 + i * 8], 16) for i in range(13)]
        size, namesize = fields[6], fields[11]
        require(0 < namesize <= 4096, "Invalid newc name size")
        name_start = offset + 110
        require(name_start + namesize <= len(data) and
                data[name_start + namesize - 1] == 0, "Invalid newc name")
        raw_name = data[name_start:name_start + namesize - 1].decode("utf-8")
        start = (name_start + namesize + 3) & ~3
        end = (start + size + 3) & ~3
        require(end <= len(data), "Truncated newc body")
        if raw_name == "TRAILER!!!":
            require(size == 0 and not any(data[end:]), "Hidden data after newc trailer")
            return rows
        name = safe_name(raw_name)
        require(historical_overlay or name not in rows, "Duplicate newc path: " + name)
        rows[name] = fields, data[start:start + size]
        offset = end
    raise ValueError("Missing newc trailer")


def cpio_entry(name: str, fields: list[int], data: bytes) -> bytes:
    encoded = name.encode("utf-8") + b"\0"
    f = fields.copy()
    f[6], f[11], f[12] = len(data), len(encoded), 0
    raw = b"070701" + b"".join(f"{value:08x}".encode("ascii") for value in f) + encoded
    raw += b"\0" * (-len(raw) % 4)
    raw += data
    return raw + b"\0" * (-len(raw) % 4)


def cpio_write(rows: dict[str, tuple[list[int], bytes]]) -> bytes:
    """Keep baseline inode/device metadata; create parents before children."""
    next_inode = max((fields[0] for fields, _ in rows.values()), default=0) + 1
    for name in list(rows):
        for parent in reversed(PurePosixPath(name).parents):
            key = str(parent)
            if key not in rows and key != ".":
                rows[key] = [next_inode, 0o40755, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0], b""
                next_inode += 1
            elif key in rows:
                require(rows[key][0][1] & 0o170000 == 0o040000, "CPIO parent is not a directory")
    ordered = sorted(rows, key=lambda name: (name != ".", name.count("/"), name))
    for name, (fields, content) in rows.items():
        fields[6], fields[11], fields[12] = len(content), len(name.encode("utf-8")) + 1, 0
    data = b"".join(cpio_entry(name, *rows[name]) for name in ordered)
    data += cpio_entry("TRAILER!!!", [next_inode, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0], b"")
    data += b"\0" * (-len(data) % 512)
    require(len(data) <= APERTURE, f"Raw rootfs exceeds 16 MiB aperture: {len(data)}")
    require(cpio_read(data) == rows, "CPIO round-trip mismatch")
    return data


def elf32(data: bytes, label: str) -> None:
    require(len(data) >= 52 and data[:7] == b"\x7fELF\x01\x01\x01" and
            struct.unpack_from("<H", data, 18)[0] == 243 and
            struct.unpack_from("<I", data, 36)[0] == 0,
            "Expected RV32 little-endian soft-float/no-C ELF: " + label)
    phoff, = struct.unpack_from("<I", data, 28)
    phsize, phcount = struct.unpack_from("<HH", data, 42)
    require(phsize >= 32 and phcount > 0 and phoff + phsize * phcount <= len(data), "Invalid ELF program headers")
    require(all(struct.unpack_from("<I", data, phoff + i * phsize)[0] != 3
                for i in range(phcount)), "Product tools must be static: " + label)


def bind_dtb(data: bytes, rootfs_bytes: int) -> bytes:
    from prepare_picture_candidate import tokens
    require(digest(data) == DTB_SHA, "Use the frozen kernel-cpu60-r01 DT template")
    header, properties, _ = tokens(data)
    old = {name: value[0] for name, value in properties.items()}
    require(old["/cpus/timebase-frequency"] == struct.pack(">I", 60000000) and
            old["/cpus/cpu@0/clock-frequency"] == struct.pack(">I", 60000000), "Wrong CPU/TIME CSR clock")
    require(old["/reserved-memory/clint-mmio@2000000/reg"] == struct.pack(">II", 0x02000000, 0x10000) and
            "/reserved-memory/clint-mmio@2000000/no-map" in old, "CLINT reservation missing")
    require(old["/chosen/linux,initrd-start"] == struct.pack(">I", 0x03000000), "Wrong initrd base")
    result = bytearray(data)
    struct.pack_into(">I", result, header[2] + properties["/chosen/linux,initrd-end"][1],
                     0x03000000 + rootfs_bytes)
    _, after, _ = tokens(result)
    expected = dict(old)
    expected["/chosen/linux,initrd-end"] = struct.pack(">I", 0x03000000 + rootfs_bytes)
    require({name: value[0] for name, value in after.items()} == expected, "Unexpected DT mutation")
    return bytes(result)


def model_archive(files: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0, compresslevel=9) as zipped:
        with tarfile.open(fileobj=zipped, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            directory = tarfile.TarInfo("xinyi-models")
            directory.type, directory.mode = tarfile.DIRTYPE, 0o755
            archive.addfile(directory)
            for name, content in sorted(files.items()):
                info = tarfile.TarInfo("xinyi-models/" + safe_name(name))
                info.size, info.mode = len(content), 0o644
                archive.addfile(info, io.BytesIO(content))
    result = stream.getvalue()
    with tarfile.open(fileobj=io.BytesIO(result), mode="r:gz") as archive:
        members = [member for member in archive if member.isfile()]
        require({member.name: archive.extractfile(member).read() for member in members} ==
                {"xinyi-models/" + name: data for name, data in files.items()}, "Model archive round-trip failed")
    return result


def coach_binding(data: bytes, proof: dict) -> dict:
    """Bind the selected ELF to the tested producer/lifecycle, not its filename."""
    require(proof.get("status") == "PASS" and proof.get("source_stable") is True and
            proof.get("release_ack_status") == 9 and
            proof.get("release_requires_same_identity_and_idle") is True and
            proof.get("timeout_busy_or_unknown_drain_withholds_ack") is True,
            "Coach release9/IDLE/drain validation required")
    marker = "XQCOACH_ACTUAL_PRODUCER_GEOMETRY_2_5_6_TO_5_ONLY_DIAGNOSTICS_UNCHANGED_PASS"
    require(marker in proof.get("tests", []), "Coach geometry-retake producer validation required")
    expected = proof.get("outputs_sha256", {}).get("worker-coach-qemu/xq-coach-worker")
    require(isinstance(expected, str) and digest(data) == expected,
            "Coach ELF differs from the validated RV32 producer")
    sources = proof.get("sources_sha256", {})
    require(sources and "artifacts/vision-model-20261020-adapter/runtime/xq_native_worker.c" in sources and
            "linux/picture_new/coach_protocol.c" in sources, "Coach proof has no source binding")
    for name, expected_hash in sources.items():
        require(safe_name(name) == name, "Invalid coach proof source path")
        path = ROOT / name
        require(path.is_file() and digest(path.read_bytes()) == expected_hash,
                "Coach proof source differs: " + name)
    return dict(worker_sha256=digest(data), source_files=len(sources), release_ack_status=9,
                idle_required=True, unknown_drain_rejected=True, geometry_native_statuses=[2, 5, 6],
                geometry_wire_status=5, source_verified=True)


def prepare(args: argparse.Namespace) -> dict:
    inputs: dict[str, dict] = {}

    def read(path: Path, expected: str | None = None) -> bytes:
        path = path.resolve()
        require(path.is_file(), "Missing input: " + str(path))
        data = path.read_bytes()
        require(expected is None or digest(data) == expected, "Frozen input mismatch: " + str(path))
        inputs[str(path)] = identity(data)
        return data

    read(Path(__file__))
    read(ROOT / "scripts/prepare_picture_candidate.py")
    base = read(args.base_rootfs, BASE_SHA)
    rows = cpio_read(base)
    require("init" in rows and b"devtmpfs" in rows["init"][1], "Base init must mount devtmpfs")
    require(b"tmpfs\t\t/run" in rows["etc/fstab"][1], "Product IPC requires tmpfs /run")
    extra: dict[str, tuple[int, bytes]] = {}
    for parameter, target in (("product", "xinyi-one"), ("coach", "xq-coach-worker"),
                              ("speech", "xinyi-speech-worker"), ("coremark", "xinyi-coremark"),
                              ("voice", "xqvoice-small-cnn"), ("engine", "xinyi-engine")):
        data = read(getattr(args, parameter))
        elf32(data, parameter)
        extra["usr/bin/" + target] = 0o100755, data
    coach_proof_bytes = read(args.coach_proof)
    coach_proof = json.loads(coach_proof_bytes)
    coach_contract = coach_binding(extra["usr/bin/xq-coach-worker"][1], coach_proof)
    coach_contract["proof_sha256"] = digest(coach_proof_bytes)
    models = {name: read(args.models / name, sha) for name, sha in MODEL_HASHES.items()}
    models["native_manifest.json"] = read(args.models / "native_manifest.json")
    bundle = model_archive(models)
    extra["opt/xinyi/models.tar.gz"] = 0o100644, bundle
    extra["opt/xinyi/balanced24.bin"] = 0o100644, read(args.balanced, BALANCED_SHA)
    extra["opt/pikafish/stageb-mac.bin"] = 0o100644, read(args.stageb_pack, STAGEB_SHA)

    audio_receipt = json.loads(read(ROOT / "docs/validation/picture-merge-20261023/rootfs-audio-preservation.json"))
    # This exact historical archive appended overlays (including S95 twice).
    # Resolve its effective entries only to recover the seven recorded assets;
    # no startup entry is imported, and the resulting new rootfs forbids duplicates.
    if args.base_voice_rootfs:
        voice_archive=read(args.base_voice_rootfs,VOICE_BASE_SHA)
    else:
        voice_archive=subprocess.check_output(["git","show",VOICE_ARCHIVE_REF+":linux/boot/rootfs.cpio"],cwd=ROOT,timeout=30)
        require(digest(voice_archive)==VOICE_BASE_SHA,"Frozen historical voice SDK archive mismatch")
    sdk = cpio_read(voice_archive, historical_overlay=True)
    base_voice = audio_receipt["base_voice_SDK_files"]
    require(len(base_voice) == 7, "Expected seven immutable base voice SDK assets")
    for name, recorded in base_voice.items():
        fields, content = sdk[name]
        require(identity(content)["sha256"] == recorded["sha256"] and len(content) == recorded["bytes"],
                "Base voice asset mismatch: " + name)
        extra[name] = fields[1], content
    pcm_manifest = read(args.pcm / "manifest.json")
    pcm = json.loads(pcm_manifest)
    require(pcm["contract_version"] == 1 and pcm["format"] == "s16le" and
            pcm["sample_rate"] == 16000 and pcm["channels"] == 1 and len(pcm["files"]) == 37,
            "Expected complete 37-PCM contract")
    for name, record in pcm["files"].items():
        require(re.fullmatch(r"[a-z_]+\.pcm", name) is not None, "Invalid PCM name")
        content = read(args.pcm / name, record["sha256"])
        require(len(content) == record["bytes"] and len(content) % 2 == 0 and
                all(record[key] == audio_receipt["picture_PCMs"][name][key]
                    for key in ("bytes", "sha256")), "PCM identity/format mismatch")
        extra["opt/xq-picture/pcm/" + name] = 0o100644, content
    extra["opt/xq-picture/pcm/manifest.json"] = 0o100644, pcm_manifest
    require(set(audio_receipt["picture_PCMs"]) == set(pcm["files"]), "PCM coverage mismatch")

    # Only the existing generic init/profile entries are reused. The old GUI
    # launcher and S95/S96 microphone daemons never enter the selected boot flow.
    for name in ("etc/inittab", "etc/profile", "etc/init.d/rcS"):
        content = read(ROOT / "linux/rootfs_overlay" / name).replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        extra[name] = (0o100755 if "/init.d/" in name else 0o100644), content
    config = {
        "XINYI_COACH_WORKER": "/usr/bin/xq-coach-worker", "XINYI_MODELS": "/run/xinyi-models",
        "XINYI_ENGINE": "/usr/bin/xinyi-engine", "XINYI_SPEECH_WORKER": "/usr/bin/xinyi-speech-worker",
        "XINYI_PCM": "/opt/xq-picture/pcm", "XINYI_COREMARK": "/usr/bin/xinyi-coremark",
        "XQVOICE_RUNTIME": "/usr/bin/xqvoice-small-cnn", "XQVOICE_MODEL": "/opt/xinyi/balanced24.bin",
        "XQVOICE_BACKEND": "mac", "XQVOICE_AUDIO_DEVICE": "/dev/pango-audio0",
        "XQVOICE_STREAM_FEATURES": "1", "XQVOICE_PROFILE": "0",
        "PIKAFISH_EMBEDDED_MODEL": "pff1-view:0x10000000:68122688",
        "PIKAFISH_STAGEB_PACK": "/opt/pikafish/stageb-mac.bin", "PIKAFISH_MAC_BACKEND": "driver",
        "PIKAFISH_MAC_REQUIRE_DRIVER": "1", "PIKAFISH_MAC_REQUIRE_FEATURES": "2531" if args.bitstream_sha256==P3_TARGET else "483",
        "PIKAFISH_STAGEA_ACCEL": "1", "PIKAFISH_STAGEB_ACCEL": "1", "PIKAFISH_NNUE_PIPELINE": "1",
        "PIKAFISH_NNUE_BATCH": "1" if args.bitstream_sha256==P3_TARGET else "0",
        "XQ_PICTURE_VOICE": "full", "XQ_PICTURE_PCM": "/opt/xq-picture/pcm", "XQ_PICTURE_VOLUME": "100",
    }
    extra["etc/xinyi.conf"] = 0o100644, ("# Private CPU60 functional candidate; not board acceptance.\n" +
        "".join(f"export {key}={shlex.quote(value)}\n" for key, value in config.items())).encode()
    hashes = {name: identity(content) for name, (_, content) in extra.items()}
    sums = "".join(f"{item['sha256']}  /{name}\n" for name, item in sorted(hashes.items()))
    extra["opt/xinyi/runtime.sha256"] = 0o100644, sums.encode("ascii")
    model_sums = "".join(f"{digest(content)}  /run/xinyi-models/{name}\n" for name, content in sorted(models.items()))
    extra["opt/xinyi/models.sha256"] = 0o100644, model_sums.encode("ascii")
    require(re.fullmatch(r"[a-f0-9]{64}", args.bitstream_sha256) is not None, "Expected target bitstream SHA-256")
    receipt = PurePosixPath(args.cram_receipt)
    require(str(receipt).startswith("/run/") and ".." not in receipt.parts and
            re.fullmatch(r"/run/[a-zA-Z0-9_./-]+", str(receipt)) is not None, "CRAM receipt must be a simple /run path")
    launcher = f'''#!/bin/sh
set -eu
sha256sum -c /opt/xinyi/runtime.sha256 >/dev/null || {{ echo XINYI_RUNTIME_HASH_REJECTED >&2; exit 1; }}
. /etc/xinyi.conf
unset XQVOICE_REPLAY_WAV XINYI_CURRENT_CRAM_SHA256
test -d /run
run_is_tmpfs() {{
 while read -r source mountpoint kind options remainder; do
  if test "$mountpoint" = /run && test "$kind" = tmpfs; then return 0; fi
 done </proc/mounts
 return 1
}}
run_is_tmpfs || {{ echo XINYI_RUN_NOT_TMPFS >&2; exit 1; }}
if test ! -f /run/xinyi-models/board.xqm; then
 gzip -dc /opt/xinyi/models.tar.gz | tar -xf - -C /run
fi
sha256sum -c /opt/xinyi/models.sha256 >/dev/null || {{ echo XINYI_MODEL_HASH_REJECTED >&2; exit 1; }}
# A target hash in this kit is not a measurement of the currently loaded FPGA.
# Only the separately audited, volatile assignment receipt enables CoreMark.
if test -f {shlex.quote(str(receipt))}; then
 current=$(cat {shlex.quote(str(receipt))})
 test "$current" = {shlex.quote(args.bitstream_sha256)} || {{ echo XINYI_CRAM_RECEIPT_REJECTED >&2; exit 1; }}
 export XINYI_CURRENT_CRAM_SHA256="$current"
fi
exec /usr/bin/xinyi-one "$@"
'''
    extra["usr/bin/start-xinyi"] = 0o100755, launcher.encode("ascii")
    startup = '''#!/bin/sh
set -eu
case "${1:-}" in
 start)
  test ! -s /run/xinyi.pid || { echo XINYI_ALREADY_STARTED >&2; exit 1; }
  /usr/bin/start-xinyi </dev/null >/dev/console 2>&1 &
  echo "$!" >/run/xinyi.pid
  ;;
 stop)
  if test -s /run/xinyi.pid; then kill -TERM "$(cat /run/xinyi.pid)"; fi
  ;;
 *) exit 1 ;;
esac
'''
    extra["etc/init.d/S95xinyi"] = 0o100755, startup.encode("ascii")
    next_inode = max(fields[0] for fields, _ in rows.values()) + 1
    for name, (mode, content) in sorted(extra.items()):
        rows[name] = [next_inode, mode, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0], content
        next_inode += 1
    require("etc/init.d/S95pikafish" not in rows and "etc/init.d/S96xqvoice" not in rows,
            "Legacy GUI/microphone autostart must not be present")
    raw = cpio_write(rows)
    kernel_record = json.loads(read(args.kernel_dir / "result.json"))
    if args.bitstream_sha256==P3_TARGET:
        from verify_integrated_opt60_main import verify
        verified=verify()
        require(verified['bitstream_sha256']==P3_TARGET,"Current main P3 publication verification failed")
        # Bind every recorded kernel input to current bytes; not just a claimed
        # PASS or an arbitrary Image SHA. Legacy fixed-hash contract stays below.
        binding=kernel_record.get('inputs_sha256',{})
        require(binding and kernel_record.get('hardware_used') is False,"Missing private kernel input binding")
        for name,expected in binding.items():
            require(digest(read(Path(name)))==expected,"Kernel input changed: "+name)
        for relative in ['linux/mac_accel/kernel/pango_mac.c','linux/mac_accel/pango_mac_uapi.h',
                         'linux/voice_accel/kernel/pango_voice.c','linux/picture_new/platform/cpu60.dts']:
            require(str((ROOT/relative).resolve()) in binding,"Kernel source omitted: "+relative)
        kernel=read(args.kernel_dir/'Image',kernel_record['outputs_sha256']['Image'])
        dtb_raw=read(args.kernel_dir/'contract.dtb',kernel_record['outputs_sha256']['contract.dtb'])
    else:
        kernel=read(args.kernel_dir/'Image',KERNEL_SHA)
        dtb_raw=read(args.kernel_dir/'contract.dtb',DTB_SHA)
    dtb = bind_dtb(dtb_raw, len(raw))
    require(kernel_record["status"] == "PASS" and kernel_record["source_stable"] and
            kernel_record["outputs_sha256"]["Image"] == digest(kernel), "Kernel build binding missing")
    config_data = read(args.kernel_dir / "kernel.config")
    require(all((name + "=y\n").encode() in config_data.replace(b"\r\n", b"\n") for name in
                ["CONFIG_PANGO_MAC_ACCEL", "CONFIG_PANGO_AUDIO_CAPTURE", "CONFIG_PANGO_VOICE_ACCEL", "CONFIG_BLK_DEV_INITRD"]),
            "Kernel driver/initrd config missing")
    if args.sbi:
        sbi = read(args.sbi, SBI_SHA)
        sbi_source = str(args.sbi.resolve())
    else:
        sbi = subprocess.check_output(["git", "show", UPSTREAM + ":" + SBI_SOURCE], cwd=ROOT, timeout=30)
        require(digest(sbi) == SBI_SHA, "Frozen CPU60 33/40 SBI mismatch")
        sbi_source = "git:" + UPSTREAM + ":" + SBI_SOURCE
    pff, atk = read(args.nnue, PFF_SHA), read(args.attack, ATK_SHA)
    require(len(pff) == 68122688 and len(atk) == 34603072, "External model sizes changed")
    require(re.fullmatch(r"PN[0-9A-Z]{2}", args.prefix) is not None and args.prefix not in ("PN00", "PN01", "PN02"),
            "Choose a fresh private Picture prefix, e.g. PN03; preserve PN00/01/02")
    require(args.bitstream_sha256!=P3_TARGET or args.prefix=='PN04',"P3 product uses PN04; preserve installed PN03")
    layout = {"sbi": (args.prefix + "SBI.BIN", 0x18000000, sbi),
              "kernel": (args.prefix + "K.BIN", 0x00400000, kernel),
              "rootfs": (args.prefix + "FS.BIN", 0x03000000, raw),
              "dtb": (args.prefix + ".DTB", 0x1a000000, dtb),
              "nnue": (args.prefix + "NN.PFF", 0x10000000, pff),
              "attack": (args.prefix + "ATK.BIN", 0x15000000, atk)}
    # No device access and no output writes occur before every input has passed.
    for path, recorded in inputs.items():
        require(identity(Path(path).read_bytes()) == recorded, "Input changed during packaging: " + path)
    record = dict(schema_version=1, status="XINYI_CPU60_RAM_INPUTS_VERIFIED_NOT_BOOTABLE_SD_KIT_NOT_BOARD",
        software_only=True, hardware_used=False, sd_written=False, flash_written=False,
        production_ready=False, board_validated=False, loader_ready=False, installed=False,
        cpu_hz=60000000, sys_hz=49500000, sbi_ratio=[33, 40], sbi_source=sbi_source,
        target_bitstream_sha256=args.bitstream_sha256, current_hardware_identity_assumed=False,
        current_cram_receipt=str(receipt), prefix=args.prefix, raw_rootfs_bytes=len(raw),
        rootfs_aperture_bytes=APERTURE, rootfs_headroom_bytes=APERTURE-len(raw),
        packed_models=identity(bundle), unpacked_model_bytes=sum(map(len, models.values())),
        full_voice=True, volume_percent=100, picture_pcm_count=37, base_voice_sdk_files=base_voice,
        coach_contract=coach_contract,
        runtime_environment=config, input_files=inputs, input_git_sbi_sha256=digest(sbi),
        selected_rootfs_payloads={name: dict(mode=oct(mode), **identity(content)) for name, (mode, content) in extra.items()},
        files={name: dict(role=role, address=hex(address), **identity(content))
               for role, (name, address, content) in layout.items()},
        limitations=["No loader binary, shared selector/config, media installation or fake receipt.",
                     "No board boot/audio/ADC/GUI/recognition/CoreMark/latency acceptance.",
                     "Current CRAM receipt must be supplied in RAM after exact hardware assignment audit.",
                     "Formal hardware candidate needs its own final STA; functional trial is not a release."])
    if args.inspect:
        return record
    output = args.output.resolve()
    require(output.is_relative_to((ROOT / "build").resolve()) and output != (ROOT / "build").resolve() and
            not output.exists(), "Choose a fresh output directory strictly under build/")
    output.mkdir(parents=True)
    private = output / "ram-payloads"
    private.mkdir()
    for name, _, content in layout.values():
        (private / name).write_bytes(content)
        require((private / name).read_bytes() == content, "Payload write/readback mismatch")
    (output / "rootfs-contents.json").write_text(json.dumps({name: dict(mode=oct(fields[1]), **identity(content))
        for name, (fields, content) in rows.items()}, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    header = "/* Private CPU60 payload CRCs; no boot loader or installation implied. */\n"
    for role, (name, address, content) in layout.items():
        macro = "XINYI_" + role.upper()
        header += f'#define {macro}_NAME "{name}"\n#define {macro}_ADDR 0x{address:08x}u\n'
        header += f'#define {macro}_BYTES {len(content)}u\n#define {macro}_CRC 0x{zlib.crc32(content):08x}u\n'
    (output / "xinyi_payloads.h").write_text(header, encoding="ascii")
    sums = "".join(f"{digest(p.read_bytes())}  {p.relative_to(output).as_posix()}\n"
                   for p in sorted(output.rglob("*")) if p.is_file())
    (output / "SHA256SUMS.txt").write_text(sums, encoding="ascii")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("product", "coach", "speech", "coremark", "voice", "engine", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--coach-proof", type=Path, required=True,
                        help="PASS producer/lifecycle receipt binding this exact RV32 worker and current sources")
    parser.add_argument("--inspect", action="store_true", help="validate and size in memory; write nothing")
    parser.add_argument("--prefix", default="PN03")
    parser.add_argument("--bitstream-sha256", required=True, help="planned target, never a current-hardware receipt")
    parser.add_argument("--cram-receipt", default="/run/xinyi/current-cram.sha256")
    parser.add_argument("--base-rootfs", type=Path, default=ROOT / "linux/images/prebuilt_2022_03_23/rootfs.cpio")
    parser.add_argument("--base-voice-rootfs", type=Path, help="exact historical SDK archive; default reads its frozen Git object")
    parser.add_argument("--kernel-dir", type=Path, default=ROOT / "build/xinyi-one-20261024/kernel-cpu60-r01")
    parser.add_argument("--models", type=Path, default=ROOT / "build/picture-merge-20261023/native-models")
    parser.add_argument("--balanced", type=Path, default=ROOT / "linux/voice_ctc/balanced24.bin")
    parser.add_argument("--stageb-pack", type=Path, default=ROOT / "linux/boot/v2_1_sd/rootfs_payloads/pikafish-stageb-mac.bin")
    parser.add_argument("--pcm", type=Path, default=ROOT / "linux/boot/v2_1_sd/rootfs_payloads/picture/pcm")
    parser.add_argument("--nnue", type=Path, default=ROOT / "linux/boot/pikafish.pff")
    parser.add_argument("--attack", type=Path, default=ROOT / "linux/boot/pikafish.atk")
    parser.add_argument("--sbi", type=Path, help="optional explicit file; must match the exact CPU60 33/40 firmware")
    args = parser.parse_args()
    record = prepare(args)
    print(json.dumps(dict(status=record["status"], inspect_only=args.inspect,
        raw_rootfs_bytes=record["raw_rootfs_bytes"], headroom_bytes=record["rootfs_headroom_bytes"],
        sbi_sha256=record["input_git_sbi_sha256"], loader_ready=False, sd_written=False), indent=2))


if __name__ == "__main__":
    main()
