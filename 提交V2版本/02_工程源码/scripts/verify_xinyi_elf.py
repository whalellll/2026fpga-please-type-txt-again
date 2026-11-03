"""Inspect private RV32 product/engine ELF files; never accesses a device."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def inspect(path):
    data = path.read_bytes()
    assert data[:7] == b"\x7fELF\x01\x01\x01", "ELF32 little-endian required"
    h = struct.unpack_from("<HHIIIIIHHHHHH", data, 16)
    kind, machine, _, entry, phoff, shoff, flags, _, phsize, phnum, shsize, shnum, names = h
    assert kind == 2 and machine == 243 and flags == 0, "static RV32IMA/soft-float/no C required"
    assert phsize == 32 and shsize == 40
    assert phoff + phnum * phsize <= len(data) and shoff + shnum * shsize <= len(data)
    programs = [struct.unpack_from("<8I", data, phoff + i * phsize) for i in range(phnum)]
    assert all(p[0] != 3 for p in programs), "dynamic interpreter not permitted"
    sections = [struct.unpack_from("<10I", data, shoff + i * shsize) for i in range(shnum)]
    strings = sections[names]
    table = data[strings[4]:strings[4] + strings[5]]
    allocated = {}
    for s in sections:
        if not s[2] & 2:
            continue
        name = table[s[0]:table.index(b"\0", s[0])].decode("ascii")
        raw = b"" if s[1] == 8 else data[s[4]:s[4] + s[5]]
        assert s[1] == 8 or len(raw) == s[5]
        allocated[name] = dict(address=s[3], size=s[5], type=s[1], flags=s[2],
                               sha256=hashlib.sha256(raw).hexdigest())
    assert allocated and entry
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                entry=entry, flags=flags, allocated=allocated)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--product", type=Path, required=True)
    p.add_argument("--engine", type=Path, required=True)
    p.add_argument("--engine-debug", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    assert not a.output.exists(), "preserve existing evidence"
    files = {name: inspect(getattr(a, name)) for name in ("product", "engine", "engine_debug")}
    assert files["engine"]["allocated"] == files["engine_debug"]["allocated"], "strip changed loadable data"
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(dict(status="PASS", actual_board=False,
        scope="Static ELF identity and unchanged allocated engine sections after strip", files=files),
        indent=2) + "\n", encoding="utf-8")
    print("XINYI_ELF_RV32_AND_ENGINE_ALLOCATED_SECTIONS_PASS_NOT_BOARD")


if __name__ == "__main__":
    main()
