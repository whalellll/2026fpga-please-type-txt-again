"""Official scalar transform arithmetic, two tagged StageA views and backpressure."""
from pathlib import Path
import argparse,hashlib,json,random,subprocess
ROOT=Path(__file__).resolve().parents[1]
def linux(p):
 p=Path(p).resolve().as_posix();return '/mnt/'+p[0].lower()+p[2:]
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 rng=random.Random(4950075);edge=[-32768,-256,-1,0,1,127,128,254,255,256,32767]
 cases=[[[edge[(i+c)%len(edge)] for i in range(1024)] for _ in range(2)] for c in range(8)]
 cases += [[[rng.randrange(-32768,32768) for _ in range(1024)] for _ in range(2)] for _ in range(16)]
 words=[];golden=[]
 for views in cases:
  for v in views:
   words += [(v[i]&65535)|((v[i+1]&65535)<<16) for i in range(0,1024,2)]
   f=[min(255,max(0,v[i]))*min(255,max(0,v[i+512]))//512 for i in range(512)]
   golden += [f[i]|(f[i+1]<<8) for i in range(0,512,2)]
 (out/'accum.hex').write_text(''.join(f'{x:08x}\n' for x in words))
 (out/'golden.hex').write_text(''.join(f'{x:04x}\n' for x in golden))
 tb=ROOT/'sim/tb_nnue_stream_transform.sv';rtl=ROOT/'rtl/mac_accel/nnue_stream_transform.v'
 cmd=f"set -eu; cd '{linux(out)}'; iverilog -g2012 -s tb_nnue_stream_transform -Ptb_nnue_stream_transform.CASES={len(cases)} -o test.vvp '{linux(tb)}' '{linux(rtl)}'; vvp test.vvp"
 r=subprocess.run(['wsl','-d','pikafish-verify','--','sh','-c',cmd],capture_output=True)
 (out/'rtl.log').write_bytes(r.stdout+r.stderr);assert r.returncode==0,(out/'rtl.log').read_text(errors='replace')[-2000:]
 assert b'NNUE_STREAM_TRANSFORM_PASS' in r.stdout
 result=dict(status='NNUE_STREAM_TRANSFORM_ARITHMETIC_AND_CONTEXT_PASS_NOT_BOARD',cases=len(cases),features=len(golden)*2,rtl_sha256=hashlib.sha256(rtl.read_bytes()).hexdigest())
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
