"""Bounded host correctness oracle using unchanged, hash-pinned CoreMark C."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

PINNED_CORE = {
    "core_list_join.c": "e6c82700c2e422dc23962bf838f7d1cd3558fe825095fe832beb63f2f8412b14",
    "core_main.c": "bafcc71c2cca06d7e15ac27e58e17f7f0bcb3c8c92404d9fa7039020de46091f",
    "core_matrix.c": "7b8c44ee71d3a1a66dbf15d711861762852a45d6ec0c3c8aca6b780742ce3507",
    "core_state.c": "74d5dfcdc2a2f4a9af5b1d6d0240d60522a24dbc55df20320e30d6d33ee79501",
    "core_util.c": "3c73f46d7ddc066f92a811aad511808395549f8d67d626612064ebc1b2477290",
    "coremark.h": "2da505dae03d07a259509a3b6dfde873cf5d64b120acba93236346f94eab0a9b",
}


class CrcReference:
    def __init__(self, root, compiler):
        self.root = Path(root)
        self.compiler = str(compiler)
        self.temp = None
        self.cache = {}

    def __enter__(self):
        core = self.root / "sw/coremark"
        upstream = json.loads((core / "upstream.json").read_text(encoding="utf-8-sig"))
        if upstream.get("commit") != "cfa9ab377835911f23d9b0831c7be302ed1f58de" or upstream.get("files") != PINNED_CORE:
            raise ValueError("CoreMark upstream identity/algorithm hash manifest changed")
        for name, expected in upstream["files"].items():
            if hashlib.sha256((core / name).read_bytes()).hexdigest() != expected:
                raise ValueError(f"CRC oracle upstream source changed: {name}")
        self.temp = tempfile.TemporaryDirectory(prefix="soc_crc_reference_")
        self.exe = Path(self.temp.name) / "reference.exe"
        command = [self.compiler, "-O2", "-ffunction-sections", "-fdata-sections",
                   "-Wl,--gc-sections", "-I", str(core),
                   str(self.root / "scripts/coremark_crc_reference.c")]
        command += [str(core / name) for name in
                    ("core_list_join.c", "core_matrix.c", "core_state.c", "core_util.c")]
        command += ["-o", str(self.exe)]
        self.env = os.environ.copy()
        self.env["PATH"] = str(Path(self.compiler).resolve().parent) + os.pathsep + self.env.get("PATH", "")
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=60, env=self.env)
        except Exception:
            self.temp.cleanup()
            raise
        return self

    def get(self, mode, iterations):
        key = (mode, iterations)
        if key not in self.cache:
            if mode not in ("performance", "validation") or type(iterations) is not int or not 1 <= iterations <= 1_000_000:
                raise ValueError("Invalid bounded CRC reference request")
            result = subprocess.run([str(self.exe), mode, str(iterations)], check=True,
                                    capture_output=True, text=True, timeout=60, env=self.env)
            values = result.stdout.strip().split()
            if len(values) != 4 or any(not re.fullmatch(r"[0-9a-f]{4}", value) for value in values):
                raise ValueError("Malformed CRC reference output")
            self.cache[key] = dict(zip(("[0]crclist", "[0]crcmatrix", "[0]crcstate", "[0]crcfinal"), values))
        return self.cache[key]

    def __exit__(self, *_):
        if self.temp:
            self.temp.cleanup()
