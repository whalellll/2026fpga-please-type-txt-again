"""Verify the real dense PE's new on-chip input/weight/result path without DDR."""
from pathlib import Path
import argparse,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[1]
def linux(p):
 p=Path(p).resolve().as_posix();return '/mnt/'+p[0].lower()+p[2:]
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 x=[(i*7+3)&127 for i in range(256)]
 w=[[((c*3+i*5)%255)-127 for i in range(256)] for c in range(32)]
 inputs=[sum(x[i+j]<<(16*j) for j in range(4)) for i in range(0,256,4)]
 weights=[]
 for line in range(64):
  for word in range(32):
   c=word//2*2;k=line*4+word%2*2
   weights.append((w[c][k]&255)|((w[c+1][k]&255)<<8)|((w[c][k+1]&255)<<16)|((w[c+1][k+1]&255)<<24))
 golden=[sum(x[i]*w[c][i] for i in range(256))&0xffffffff for c in range(32)]
 for name,values,digits in [('input.hex',inputs,16),('weight.hex',weights,8),('golden.hex',golden,8)]:
  (out/name).write_text(''.join(f'{v:0{digits}x}\n' for v in values))
 sources=[ROOT/'sim/tb_nnue_local_link.sv',ROOT/'sim/gtp_apm_e2_perf_sim.v',ROOT/'rtl/mac_accel/MacAccelCore.v',ROOT/'rtl/mac_accel/mac_accel_dma_kernel.v']
 src=' '.join("'"+linux(p)+"'" for p in sources)
 cmd=f"set -eu; cd '{linux(out)}'; iverilog -g2012 -DPIKAFISH_BOOT_MIN_DRM -s tb_nnue_local_link -o test.vvp {src}; vvp test.vvp"
 r=subprocess.run(['wsl','-d','pikafish-verify','--','sh','-c',cmd],capture_output=True)
 (out/'rtl.log').write_bytes(r.stdout+r.stderr);assert r.returncode==0,(out/'rtl.log').read_text(errors='replace')[-3000:]
 assert b'NNUE_LOCAL_LINK_PASS' in r.stdout
 result=dict(status='NNUE_LOCAL_LINK_REAL_PE_PASS_NOT_BOARD',outputs=32,ddr_requests=0,source_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
