"""Read-back/negative checks of a private RAM kit; no board or media access."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import prepare_xinyi_cpu60_kit as kit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    require = kit.require
    output = args.out.resolve()
    require(output.is_relative_to((kit.ROOT / "build").resolve()) and not output.exists(), "Fresh build/ report required")
    before = {str(path): kit.digest(path.read_bytes()) for path in
              [Path(__file__), Path(kit.__file__), args.kit / "manifest.json"]}
    report = json.loads((args.kit / "manifest.json").read_text())
    require(not any(report[key] for key in ["hardware_used", "sd_written", "flash_written", "loader_ready", "installed"]), "Invalid scope")
    names = {value["role"]: name for name, value in report["files"].items()}
    require(set(names) == {"sbi", "kernel", "rootfs", "dtb", "nnue", "attack"}, "Expected six RAM payloads")
    for name, expected in report["files"].items():
        require(kit.identity((args.kit / "ram-payloads" / name).read_bytes()) ==
                {key: expected[key] for key in ["bytes", "sha256", "crc32"]}, "Payload read-back mismatch")
    raw = (args.kit / "ram-payloads" / names["rootfs"]).read_bytes()
    rows = kit.cpio_read(raw)
    contract = report.get("coach_contract", {})
    require(contract.get("source_verified") is True and contract.get("release_ack_status") == 9 and
            contract.get("idle_required") is True and contract.get("unknown_drain_rejected") is True and
            contract.get("geometry_native_statuses") == [2, 5, 6] and
            contract.get("geometry_wire_status") == 5 and
            contract.get("worker_sha256") == kit.digest(rows["usr/bin/xq-coach-worker"][1]),
            "Selected coach must match its tested lifecycle/producer receipt")
    require(len(raw) <= kit.APERTURE, "Rootfs aperture exceeded")
    for name, expected in report["selected_rootfs_payloads"].items():
        fields, content = rows[name]
        require(oct(fields[1]) == expected["mode"] and kit.identity(content) ==
                {key: expected[key] for key in ["bytes", "sha256", "crc32"]}, "CPIO payload mismatch")
    require(not {"etc/init.d/S95pikafish", "etc/init.d/S96xqvoice"} & set(rows), "Legacy startup returned")
    require(b"tmpfs\t\t/run\t\ttmpfs" in rows["etc/fstab"][1], "Explicit /run tmpfs missing")
    launcher = rows["usr/bin/start-xinyi"][1]
    require(launcher.index(b'run_is_tmpfs ||') < launcher.index(b'gzip -dc') and
            b'</proc/mounts' in launcher, "Tmpfs check must precede extraction")
    require(b'</dev/null' in rows["etc/init.d/S95xinyi"][1] and
            b'</dev/console' not in rows["etc/init.d/S95xinyi"][1], "UART maintenance shell must keep input")
    require(sum(name.startswith("opt/xq-picture/pcm/") and name.endswith(".pcm") for name in rows) == 37,
            "Missing PCM asset")
    require(report["sbi_ratio"] == [33, 40] and report["input_git_sbi_sha256"] == kit.SBI_SHA, "Wrong firmware")
    from prepare_picture_candidate import tokens
    _, props, _ = tokens((args.kit / "ram-payloads" / names["dtb"]).read_bytes())
    import struct
    require(props["/chosen/linux,initrd-end"][0] == struct.pack(">I", 0x03000000 + len(raw)), "DTB initrd end mismatch")
    negatives = []

    def rejects(label, call):
        try:
            call()
        except (ValueError, KeyError):
            negatives.append(label)
            return
        raise ValueError("Negative check accepted: " + label)

    fields = [1, 0o100644, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
    trailer = kit.cpio_entry("TRAILER!!!", fields, b"")
    rejects("unsafe-path", lambda: kit.cpio_read(kit.cpio_entry("../escape", fields, b"x") + trailer))
    one = kit.cpio_entry("one", fields, b"x")
    rejects("duplicate-cpio", lambda: kit.cpio_read(one + one + trailer))
    rejects("hidden-tail", lambda: kit.cpio_read(one + trailer + b"070701"))
    rejects("truncated-body", lambda: kit.cpio_read(one[:-4]))
    rejects("16MiB-aperture", lambda: kit.cpio_write({"huge": (fields.copy(), bytes(kit.APERTURE))}))
    rejects("parent-file", lambda: kit.cpio_write({"a": (fields.copy(), b"x"), "a/b": (fields.copy(), b"y")}))
    changed = bytearray((args.kit / "ram-payloads" / names["dtb"]).read_bytes())
    changed[-1] ^= 1
    rejects("foreign-dtb", lambda: kit.bind_dtb(bytes(changed), len(raw)))
    rejects("not-rv32-elf", lambda: kit.elf32(b"stub", "negative-only"))
    # A mutated actual ELF tests PT_INTERP rejection without a fake deliverable.
    elf = bytearray(rows["usr/bin/xinyi-coremark"][1])
    phoff, = struct.unpack_from("<I", elf, 28)
    struct.pack_into("<I", elf, phoff, 3)
    rejects("dynamic-interpreter", lambda: kit.elf32(bytes(elf), "negative-only"))
    rejects("coach-without-release-proof", lambda: kit.coach_binding(rows["usr/bin/xq-coach-worker"][1], {}))
    proof_paths = [Path(name) for name, item in report["input_files"].items()
                   if item["sha256"] == contract["proof_sha256"]]
    require(len(proof_paths) == 1, "Coach receipt identity missing")
    proof = json.loads(proof_paths[0].read_text(encoding="utf-8"))
    require(kit.coach_binding(rows["usr/bin/xq-coach-worker"][1], proof)["source_verified"],
            "Current coach source verification failed")
    wrong = bytearray(rows["usr/bin/xq-coach-worker"][1]); wrong[-1] ^= 1
    rejects("coach-foreign-elf", lambda: kit.coach_binding(bytes(wrong), proof))
    require(before == {name: kit.digest(Path(name).read_bytes()) for name in before}, "Check sources changed")
    result = dict(status="PASS", hardware_used=False, board_validated=False, source_stable=True,
                  source_sha256=before, kit_manifest_sha256=kit.digest((args.kit / "manifest.json").read_bytes()),
                  entries=len(rows), raw_rootfs_bytes=len(raw), headroom_bytes=kit.APERTURE-len(raw),
                  negatives=negatives, strict_driver=True, full_voice=True,
                  limitations="Host byte/structure checks only; native extraction/QEMU config smoke is separate.")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print("XINYI_RAM_KIT_HOST_READBACK_NEGATIVES_PASS_NOT_BOARD", len(negatives))


if __name__ == "__main__":
    main()
