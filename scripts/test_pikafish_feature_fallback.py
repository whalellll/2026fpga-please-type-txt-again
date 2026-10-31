"""Run actual descriptor wrapper through its legacy dense backend and S16 oracle."""
from pathlib import Path
import argparse, hashlib, json, subprocess
from picture_workspace import workspace_path,wsl_path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
out=workspace_path(a.output);out.mkdir(parents=True,exist_ok=False);(out/'tmp').mkdir()
files=[ROOT/'sim/test_pikafish_feature_fallback.cpp',ROOT/'linux/pikafish/pikafish_stagea_accel.cpp',ROOT/'linux/pikafish/pikafish_mac_runtime.cpp']
cmd="set -eu; ulimit -c 0; export TMPDIR='"+wsl_path(out/'tmp')+"'; g++ -std=c++17 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined -fno-omit-frame-pointer -pthread -DPIKAFISH_STAGEA_ACCEL -iquote '"+wsl_path(ROOT/'linux/pikafish')+"' "+' '.join("'"+wsl_path(f)+"'" for f in files)+" -Wl,--wrap=open,--wrap=close,--wrap=mmap,--wrap=munmap,--wrap=ioctl -o '"+wsl_path(out/'test')+"'; '"+wsl_path(out/'test')+"'"
r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',cmd],capture_output=True,timeout=150)
(out/'test.log').write_bytes(r.stdout+r.stderr)
assert r.returncode==0 and b'DIRECT_INDEX_LEGACY_DENSE_FALLBACK' in r.stdout,(r.stdout+r.stderr).decode(errors='replace')[-2500:]
(out/'result.json').write_text(json.dumps(dict(status='FEATURE_UPDATES_LEGACY_DENSE_DIFFERENTIAL_ASAN_UBSAN_PASS_NOT_BOARD',command=cmd,sources_sha256={f.relative_to(ROOT).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in files+[ROOT/'linux/pikafish/pikafish_feature_updates.h']}),indent=2)+'\n')
print('FEATURE_UPDATES_LEGACY_DENSE_DIFFERENTIAL_ASAN_UBSAN_PASS_NOT_BOARD')
