#!/usr/bin/env python3
"""Check that a no-config stage-2 initrd avoids the boot sysctl pipeline."""

import argparse
import gzip
from pathlib import Path


def entries(path: Path) -> dict[str, bytes]:
    data = path.read_bytes()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    result = {}
    offset = 0
    while offset + 110 <= len(data):
        header = data[offset : offset + 110]
        if header[:6] not in (b"070701", b"070702"):
            raise AssertionError(f"bad cpio header at {offset}")
        size = int(header[54:62], 16)
        name_size = int(header[94:102], 16)
        offset += 110
        name = data[offset : offset + name_size - 1].decode()
        offset = (offset + name_size + 3) & ~3
        if name == "TRAILER!!!":
            return result
        result[name.removeprefix("./")] = data[offset : offset + size]
        offset = (offset + size + 3) & ~3
    raise AssertionError("cpio trailer missing")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    source = entries(args.source)
    candidate = entries(args.candidate)
    config_dirs = (
        "etc/sysctl.d/",
        "usr/local/lib/sysctl.d/",
        "usr/lib/sysctl.d/",
        "lib/sysctl.d/",
    )
    for name in source:
        if name == "etc/sysctl.conf" or (
            name.endswith(".conf") and name.startswith(config_dirs)
        ):
            raise AssertionError(f"source has a sysctl config: {name}")
    original = source["etc/init.d/S02sysctl"]
    assert candidate["etc/init.d/X02sysctl"] == original
    stub = candidate["etc/init.d/S02sysctl"]
    assert stub.startswith(b"#!/bin/sh\n")
    assert b"SYSCTL_NO_CONFIGS_SKIP" in stub
    assert b"Running sysctl: OK" in stub
    assert b"xargs" not in stub
    print("MAC_CONV_ROOTFS_SYSCTL_GUARD_PASS")


if __name__ == "__main__":
    main()
