"""Exact WAV/live-stream frontend comparison, including pause/abort/overflow."""
from pathlib import Path
import argparse,hashlib,json,subprocess
from test_voice2_model import command,lin
R=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--rv32',action='store_true');a=ap.parse_args()
o=a.output.resolve();o.mkdir(parents=True,exist_ok=False);u=R/'linux/voice2/upstream'
src=[u/'xqvoice_capture.c',u/'xqvoice_frontend.c',u/'xqvoice_profile.c',R/'sim/test_voice2_stream_frontend.c']
bound=src+list(u.glob('*.h'))+[u/'xqvoice_stream.inc']
hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in bound}
cc='/opt/toolchain/bin/riscv32-linux-musl-gcc -static -march=rv32ima -mabi=ilp32' if a.rv32 else 'gcc'
cmd=cc+" -std=gnu11 -O2 -fwrapv -Wall -Wextra -Werror -DXQV_HOP_SAMPLES=320u -pthread -I'"+lin(u)+"' "+' '.join("'"+lin(p)+"'" for p in src)+" -Wl,--wrap=open,--wrap=close,--wrap=flock,--wrap=read,--wrap=ioctl -o '"+lin(o/'test')+"'"
result=dict(status='RUNNING',inputs_sha256=hashes,rv32=a.rv32)
try:
 command(cmd,o,'build')
 command(('qemu-riscv32 ' if a.rv32 else '')+"'"+lin(o/'test')+"'",o,'run')
 assert b'VOICE2_STREAM_FRONTEND_EXACT_BOUNDARIES_PAUSE_TRIM_CANCEL_OVERFLOW_PASS' in (o/'run.log').read_bytes()
 assert hashes=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in bound}
 result['status']='VOICE2_STREAM_FRONTEND_EXACT_PAUSE_TRIM_ABORT_OVERFLOW_PASS_NOT_BOARD'
except Exception as e:result.update(status='FAILED_PRESERVED',error=repr(e));raise
finally:(o/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(result['status'])
