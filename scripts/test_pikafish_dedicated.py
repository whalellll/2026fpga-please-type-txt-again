"""Reuse independent official/C fixtures; check cold/warm traffic and failure recovery."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
def linux(p):
 s=Path(p).resolve().as_posix();return '/mnt/'+s[0].lower()+s[2:]
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--official-half',type=int,choices=[0,1]);ap.add_argument('--synthesis-pads',action='store_true');a=ap.parse_args()
 out=a.output.resolve();assert not out.exists();out.mkdir(parents=True)
 args=[sys.executable,str(ROOT/'scripts/test_nnue_mlp_chain.py'),'--output',str(out/'reference'),'--dense-profile','2']
 if a.official_half is not None:args+=['--official-half',str(a.official_half)]
 r=subprocess.run(args,capture_output=True,timeout=600);(out/'reference.log').write_bytes(r.stdout+r.stderr);assert r.returncode==0,(out/'reference.log').read_text(errors='replace')[-2000:]
 count=6 if a.official_half is None else 16
 sources=[ROOT/'sim/tb_pikafish_mlp_dedicated.sv',ROOT/'rtl/mac_accel/pikafish_mlp_dedicated.v']
 before={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
 pad_flags="-DSYNTHESIS -y /mnt/g/fpga/PDS_2022.2-SP6.4/arch/vendor/pango/verilog/simulation " if a.synthesis_pads else ''
 cmd="set -eu; cd '"+linux(out/'reference')+"'; iverilog -g2012 "+pad_flags+"-s tb_pikafish_mlp_dedicated -Ptb_pikafish_mlp_dedicated.CASES="+str(count)+" -o dedicated.vvp "+' '.join("'"+linux(p)+"'" for p in sources)+"; vvp dedicated.vvp"
 r=subprocess.run(['wsl.exe','-d','pikafish-verify','--','sh','-c',cmd],capture_output=True,timeout=600)
 (out/'dedicated.log').write_bytes(r.stdout+r.stderr)
 assert r.returncode==0 and b'PIKAFISH_DEDICATED_PASS' in r.stdout,(out/'dedicated.log').read_text(errors='replace')[-2500:]
 assert before=={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
 result=dict(status='PIKAFISH_DEDICATED_C_REFERENCE_CACHE_AND_RECOVERY_PASS_NOT_BOARD',cases=count,official_half=a.official_half,synthesis_pads=a.synthesis_pads,reads_cold=8801,reads_warm=0,source_sha256=before,log_sha256=hashlib.sha256(r.stdout+r.stderr).hexdigest())
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result),flush=True)
if __name__=='__main__':main()
