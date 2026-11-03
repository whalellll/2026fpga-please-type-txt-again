"""Run legacy dense/gather/conv checks plus StageA-to-score on the actual AXI fabric."""
from pathlib import Path
import argparse,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[1]
def linux(p):
 p=Path(p).resolve().as_posix();return '/mnt/'+p[0].lower()+p[2:]
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
 ap.add_argument('--vectors',type=Path,required=True);ap.add_argument('--dense-profile',type=int,choices=[0,1,2],default=1);ap.add_argument('--dedicated',action='store_true');a=ap.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);v=a.vectors.resolve()
 r=json.loads((v/'result.json').read_text());assert r['status']=='NNUE_MLP_CHAIN_C_REFERENCE_REAL_PE_PASS_NOT_BOARD'
 (out/'nnue-model.hex').write_text(''.join((v/'model.hex').read_text().splitlines(keepends=True)[16384:32768]))
 (out/'nnue-golden.hex').write_text((v/'golden.hex').read_text().splitlines()[131]+'\n')
 sources=[ROOT/'rtl/soc/axi_2x1_arbiter.v',*sorted((ROOT/'rtl/mac_accel').glob('*.v')),
          ROOT/'sim/gtp_apm_e2_perf_sim.v',ROOT/'sim/axi_shared_ram.sv',ROOT/'sim/tb_soc_mac_accel.sv']
 before={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
 src=' '.join("'"+linux(p)+"'" for p in sources);logs={}
 for conv in (0,1):
  cmd=f"set -eu; cd '{linux(out)}'; iverilog -g2012 -DPIKAFISH_BOOT_MIN_DRM -s tb_soc_mac_accel -Ptb_soc_mac_accel.H128_ENABLED=0 -Ptb_soc_mac_accel.HALF_DENSE={a.dense_profile} -Ptb_soc_mac_accel.PIKAFISH_ONLY={int(a.dedicated)} -Ptb_soc_mac_accel.NNUE_ENABLED=1 -Ptb_soc_mac_accel.CONV_ENABLED={conv} -o test-{conv}.vvp {src}; vvp test-{conv}.vvp"
  r=subprocess.run(['wsl','-d','pikafish-verify','--','sh','-c',cmd],capture_output=True,timeout=300)
  p=out/f'conv-{conv}.log';p.write_bytes(r.stdout+r.stderr)
  assert r.returncode==0,p.read_text(errors='replace')[-3000:]
  markers=(b'PIKAFISH_GENERIC_DENSE_REJECT_PASS',b'PIKAFISH_SOC_CACHE_PASS') if a.dedicated else (b'S16_MAX_OUTPUT_PASS',)
  for marker in (b'NNUE_SOC_DIRECT_PIPELINE_PASS',b'SOC_STAGEA_GATHER_PASS',*markers):
   assert marker in r.stdout,(conv,marker)
  logs[p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
 after={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
 assert before==after,'source changed during simulation'
 report=dict(status='NNUE_SOC_STAGEA_TO_SCORE_AXI_AND_LEGACY_PASS_NOT_BOARD',conv_profiles=[0,1],logs_sha256=logs,
             dense_profile=a.dense_profile,dedicated=a.dedicated,source_sha256=before,inputs_unchanged=True)
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
