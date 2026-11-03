"""Actual C++ runtime with an independent descriptor/S16 transaction oracle."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from workspace_paths import workspace_path,wsl_path
ROOT=Path(__file__).resolve().parents[1]
def linux(p):
 s=p.resolve().as_posix();return '/mnt/'+s[0].lower()+s[2:]
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 out=workspace_path(a.output);out.mkdir(parents=True,exist_ok=False)
 files=[ROOT/'sim/test_pikafish_batch_runtime.cpp',ROOT/'linux/pikafish/pikafish_mac_runtime.cpp',ROOT/'linux/pikafish/pikafish_stagea_accel.cpp',ROOT/'linux/mac_accel/pango_mac_uapi.h',ROOT/'linux/pikafish/pango_mac_uapi.h']
 assert files[-1].read_bytes()==files[-2].read_bytes(),'Port UAPI differs'
 sources=files+[ROOT/'linux/pikafish/pikafish_feature_updates.h',ROOT/'linux/pikafish/pikafish_stagea_accel.h',ROOT/'linux/pikafish/pikafish_mac_runtime.h']
 before={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
 temporary=wsl_path(out/'tmp')
 cmd=f"set -eu; mkdir '{temporary}'; export TMPDIR='{temporary}' TMP='{temporary}' TEMP='{temporary}'; g++ -std=c++17 -O2 -Wall -Wextra -Werror -pthread -DPIKAFISH_STAGEA_ACCEL -DPIKAFISH_STAGEB_ACCEL -iquote '{linux(ROOT/'linux/pikafish')}' "+' '.join("'"+linux(p)+"'" for p in files[:3])+f" -Wl,--wrap=open,--wrap=close,--wrap=mmap,--wrap=munmap,--wrap=ioctl -o '{linux(out/'test')}'; '{linux(out/'test')}'"
 cmd+='; TEST_OLD_COPYOUT_DRIVER=1 '+"'"+linux(out/'test')+"'"
 cmd+='; TEST_SINGLE_GATHER=1 '+"'"+linux(out/'test')+"'"
 cmd+='; TEST_RESIDENT_DRIVER=1 PIKAFISH_ACCUM_RESIDENT=1 '+"'"+linux(out/'test')+"'"
 cmd+='; TEST_RESIDENT_DRIVER=1 PIKAFISH_ACCUM_RESIDENT=0 '+"'"+linux(out/'test')+"'"
 r=subprocess.run(['wsl.exe','-d','pikafish-verify','--','sh','-c',cmd],capture_output=True,timeout=120)
 (out/'test.log').write_bytes(r.stdout+r.stderr)
 assert r.returncode==0 and b'PIKAFISH_BATCH_RUNTIME_' in r.stdout,(r.stdout+r.stderr).decode(errors='replace')[-3500:]
 assert before=={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
 report=dict(status='PIKAFISH_BATCH_REAL_RUNTIME_ORACLE_PASS_NOT_BOARD',sources_sha256=before,log_sha256=hashlib.sha256(r.stdout+r.stderr).hexdigest())
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'])
if __name__=='__main__':main()
