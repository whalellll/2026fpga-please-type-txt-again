"""Exercise the real userspace backends with intercepted device transactions."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def wsl(p):
 p=Path(p).resolve().as_posix();return '/mnt/'+p[0].lower()+p[2:]
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 paths=['linux/pikafish/pikafish_mac_runtime.cpp','linux/pikafish/pikafish_mac_runtime.h',
 'linux/pikafish/pikafish_mmio_shadow.h','linux/mac_accel/pango_mac_uapi.h',
 'linux/pikafish/pikafish_stagea_accel.cpp','linux/pikafish/pikafish_stagea_accel.h',
 'linux/voice/xqvoice_accel.c','linux/voice/xqvoice_accel.h','linux/audio/pango_voice_uapi.h','linux/pikafish/pango_mac_uapi.h',
 'sim/test_nnue_pipeline_runtime.cpp','sim/test_voice_stream_runtime.c']
 hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
 base=wsl(ROOT);target=wsl(out)
 commands={
 'nnue':f'''g++ -std=c++17 -O2 -Wall -Wextra -Werror -pthread -DPIKAFISH_STAGEA_ACCEL -DPIKAFISH_STAGEB_ACCEL -iquote '{base}/linux/pikafish' -iquote '{base}/linux/mac_accel' '{base}/sim/test_nnue_pipeline_runtime.cpp' '{base}/linux/pikafish/pikafish_mac_runtime.cpp' '{base}/linux/pikafish/pikafish_stagea_accel.cpp' -Wl,--wrap=open,--wrap=close,--wrap=mmap,--wrap=munmap,--wrap=ioctl -o '{target}/nnue-test'; '{target}/nnue-test' ''',
 'voice':f'''gcc -std=gnu11 -O2 -Wall -Wextra -Werror -I'{base}/linux/voice' -I'{base}/linux/audio' '{base}/sim/test_voice_stream_runtime.c' '{base}/linux/voice/xqvoice_accel.c' -Wl,--wrap=ioctl -o '{target}/voice-test'; '{target}/voice-test' '''}
 logs={}
 for name,cmd in commands.items():
  p=subprocess.run(['wsl','-d','pikafish-verify','--','sh','-c','set -eu; '+cmd],capture_output=True)
  (out/(name+'.log')).write_bytes(p.stdout+p.stderr)
  assert p.returncode==0,(name,(p.stdout+p.stderr).decode(errors='replace')[-5000:])
  assert b'_PASS' in p.stdout
  if name=='nnue':
   q=subprocess.run(['wsl','-d','pikafish-verify','--','sh','-c',f"MOCK_PIKAFISH_DEDICATED=1 '{target}/nnue-test'"],capture_output=True,timeout=90)
   (out/'nnue-dedicated.log').write_bytes(q.stdout+q.stderr)
   assert q.returncode==0 and b'_PASS' in q.stdout,(q.stdout+q.stderr).decode(errors='replace')[-5000:]
   logs['nnue-dedicated']=hashlib.sha256(q.stdout+q.stderr).hexdigest()
  logs[name]=hashlib.sha256((out/(name+'.log')).read_bytes()).hexdigest()
 assert hashes=={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
 result=dict(status='VOICE_NNUE_REAL_RUNTIME_MOCK_DEVICE_CONTEXT_AND_POOLING_PASS_NOT_BOARD',sources_sha256=hashes,logs_sha256=logs,commands=commands)
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
if __name__=='__main__':main()
