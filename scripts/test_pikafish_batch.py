"""Actual shared AXI batch, dependent S16 oracle, C score and failure recovery."""
import argparse,hashlib,json,subprocess,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def linux(p):
 s=Path(p).resolve().as_posix();return '/mnt/'+s[0].lower()+s[2:]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
 p.add_argument('--reference',type=Path,required=True);a=p.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 ref=a.reference.resolve();assert json.loads((ref.parent/'result.json').read_text())['status']=='PIKAFISH_DEDICATED_C_REFERENCE_CACHE_AND_RECOVERY_PASS_NOT_BOARD'
 (out/'nnue-model.hex').write_text(''.join((ref/'model.hex').read_text().splitlines(keepends=True)[16384:32768]))
 (out/'nnue-golden.hex').write_text((ref/'golden.hex').read_text().splitlines()[131]+'\n')
 src=[ROOT/'rtl/soc/axi_2x1_arbiter.v',*sorted((ROOT/'rtl/mac_accel').glob('*.v')),ROOT/'sim/gtp_apm_e2_perf_sim.v',ROOT/'sim/axi_shared_ram.sv',ROOT/'sim/tb_soc_mac_accel.sv']
 before={x.relative_to(ROOT).as_posix():hashlib.sha256(x.read_bytes()).hexdigest() for x in src}
 cmd=f"set -eu; cd '{linux(out)}'; iverilog -g2012 -DPIKAFISH_BOOT_MIN_DRM -s tb_soc_mac_accel -Ptb_soc_mac_accel.H128_ENABLED=0 -Ptb_soc_mac_accel.PIKAFISH_ONLY=1 -Ptb_soc_mac_accel.NNUE_ENABLED=1 -Ptb_soc_mac_accel.BATCH_ENABLED=1 -o test.vvp "+' '.join("'"+linux(x)+"'" for x in src)+"; vvp test.vvp"
 r=subprocess.run(['wsl.exe','-d','pikafish-verify','--','sh','-c',cmd],capture_output=True,timeout=600)
 log=out/'simulation.log';log.write_bytes(r.stdout+r.stderr)
 assert r.returncode==0,log.read_text(errors='replace')[-3500:]
 for marker in [b'PIKAFISH_BATCH_DEPENDENT_PASS',b'PIKAFISH_BATCH_REJECT_DRAIN_RECOVERY_PASS',b'NNUE_SOC_DIRECT_PIPELINE_PASS',b'ACCUM_RESIDENT_CROSS_BATCH_S16_SCORE_INPLACE_AND_INVALIDATION_PASS']:
  assert marker in r.stdout,marker
 assert before=={x.relative_to(ROOT).as_posix():hashlib.sha256(x.read_bytes()).hexdigest() for x in src},'Source changed during test'
 report=dict(status='PIKAFISH_BATCH_SHARED_AXI_DEPENDENCY_EXPORT_SCORE_RECOVERY_PASS_NOT_BOARD',source_sha256=before,log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
 match=re.search(rb'ACCUM_RESIDENT_CYCLES external=(\d+) resident=(\d+) external_base_words=1024 resident_base_words=0',r.stdout);assert match
 report.update(external_cycles=int(match[1]),resident_cycles=int(match[2]),base_ddr_words_saved=1024,additional_context_ram_bytes=0)
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
