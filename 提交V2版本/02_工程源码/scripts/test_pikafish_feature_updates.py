"""Differential descriptor construction against the old actual encoder, with sanitizers."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from workspace_paths import workspace_path, wsl_path

ROOT = Path(__file__).resolve().parents[1]

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--expect-red', action='store_true')
    ap.add_argument('--rv32', action='store_true')
    a = ap.parse_args()
    out = workspace_path(a.output)
    out.mkdir(parents=True, exist_ok=False)
    (out / 'tmp').mkdir()
    files = [ROOT/'sim/test_pikafish_feature_updates.cpp',
             ROOT/'linux/pikafish/pikafish_stagea_accel.cpp',
             ROOT/'linux/pikafish/pikafish_mac_runtime.cpp']
    cmd = 'set -eu; ulimit -c 0; export TMPDIR=\'' + wsl_path(out/'tmp') + '\'; '
    compiler=('/opt/toolchain/bin/riscv32-linux-musl-g++ -march=rv32ima -mabi=ilp32 -static -O2 '
              if a.rv32 else 'g++ -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer ')
    cmd += compiler + '-std=c++17 -Wall -Wextra -Werror -pthread '
    cmd += '-iquote \'' + wsl_path(ROOT/'linux/pikafish') + '\' '
    cmd += ' '.join("'"+wsl_path(p)+"'" for p in files)
    cmd += " -o '" + wsl_path(out/'test') + "'; " + ('qemu-riscv32 ' if a.rv32 else '') + "'" + wsl_path(out/'test') + "'"
    r = subprocess.run(['wsl.exe', '-d', 'pikafish-verify', '--', 'sh', '-c', cmd], capture_output=True, timeout=150)
    (out/'test.log').write_bytes(r.stdout+r.stderr)
    if a.expect_red:
        assert r.returncode != 0 and b'pikafish_feature_updates.h' in r.stderr, r.stderr
        status = 'FEATURE_UPDATES_RED_BEFORE_IMPLEMENTATION'
    else:
        assert r.returncode == 0 and b'FEATURE_UPDATES_ALL_ROWS' in r.stdout, (r.stdout+r.stderr).decode(errors='replace')[-4000:]
        status = ('FEATURE_UPDATES_RV32_DIFFERENTIAL_PASS_NOT_BOARD' if a.rv32 else
                  'FEATURE_UPDATES_DIFFERENTIAL_ASAN_UBSAN_PASS_NOT_BOARD')
    sources = files + list((ROOT/'linux/pikafish').glob('pikafish_feature_updates.h'))
    (out/'result.json').write_text(json.dumps(dict(status=status, sources_sha256={p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}, command=cmd), indent=2)+'\n')
    print(status)

if __name__ == '__main__':
    main()
