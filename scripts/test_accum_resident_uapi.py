"""Check ABI size, clobber restrictions and old/new flag validation on native and RV32."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from workspace_paths import workspace_path,wsl_path
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();o=workspace_path(a.output);o.mkdir(parents=True,exist_ok=False);(o/'tmp').mkdir()
files=[R/'sim/test_accum_resident_uapi.c',R/'linux/mac_accel/pango_mac_uapi.h',R/'linux/pikafish/pango_mac_uapi.h'];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();bound={str(p):sha(p) for p in files};assert files[1].read_bytes()==files[2].read_bytes()
for name,cc,extra,runner in [('native','gcc','-fsanitize=address,undefined',''),('rv32','/opt/toolchain/bin/riscv32-linux-musl-gcc','-static','qemu-riscv32 ')]:
 script=f'''set -eu
export TMPDIR='{wsl_path(o/'tmp')}'
{cc} -std=c11 -O2 -Wall -Wextra -Werror {extra} -I'{wsl_path(files[1].parent)}' '{wsl_path(files[0])}' -o '{wsl_path(o/name)}'
{runner}'{wsl_path(o/name)}'
''';(o/(name+'.sh')).write_text(script,newline='\n')
 q=subprocess.run(['wsl.exe','-d','pikafish-verify','--','sh',wsl_path(o/(name+'.sh'))],capture_output=True,timeout=120);(o/(name+'.log')).write_bytes(q.stdout+q.stderr);assert q.returncode==0 and b'RESERVED_PASS cases=288 bytes=144' in q.stdout,(q.stdout+q.stderr)[-2000:]
assert all(sha(Path(n))==h for n,h in bound.items())
(o/'result.json').write_text(json.dumps(dict(status='ACCUM_RESIDENT_ABI_PARENT_CLOBBER_NATIVE_SANITIZERS_RV32_PASS_NOT_BOARD',sources_sha256=bound),indent=2)+'\n');print('ACCUM_RESIDENT_UAPI_PASS')
