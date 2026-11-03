"""Exact Picture_new epilogue on real RTL, independent NumPy integer oracle."""
import argparse,json,hashlib,subprocess
from pathlib import Path
from workspace_paths import workspace_path,wsl_path
from test_vision32 import fixture
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--soc',action='store_true');a=p.parse_args()
o=workspace_path(a.output);o.mkdir(parents=True,exist_ok=False)
jobs=[]
for flags in [4,5]:
 for shift in range(63):
  jobs.append(dict(w=1,h=1,ci=1,co=14,k=1,s=1,p=0,exact_edges=True,exact_shift=shift,flags=flags,name='exact_shift_'+str(shift)))
 for base in [dict(w=1,h=1,ci=1,co=256,k=1,s=1,p=0,exact_edges=True),
              dict(w=5,h=3,ci=7,co=9,k=1,s=1,p=0),
              dict(w=5,h=3,ci=4,co=17,k=3,s=2,p=1),
              dict(w=3,h=3,ci=128,co=9,k=3,s=1,p=0),
              dict(w=3,h=1,ci=1,co=9,k=1,s=1,p=0,half_ties=True),
              dict(w=5,h=3,ci=7,co=9,k=1,s=1,p=0,cross=True),
              dict(w=1,h=1,ci=1,co=2,k=1,s=1,p=0,overflow=True)]:
  jobs.append(dict(base,flags=flags,name='exact_'+str(flags)+'_'+str(len(jobs))))
 for fault in [1,2,3,4,5]: jobs.append(dict(w=5,h=3,ci=4,co=9,k=3,s=1,p=1,flags=flags,fault=fault,name='exact_fault_'+str(fault)))
 for bad in ['overlap','out_of_range','bad_shift']:
  jobs.append(dict(w=3,h=1,ci=4,co=9,k=1,s=1,p=0,flags=flags,bad=bad,name='exact_bad_'+bad))
vectors=[fixture(j,i,o) for i,j in enumerate(jobs)]
(o/'vectors.json').write_text(json.dumps(vectors,indent=2)+'\n')
sources=[R/'rtl/mac_accel/vision32_pe.v',R/'rtl/mac_accel/vision32_layer.v',R/'sim/tb_vision32_layer.sv']
if a.soc:sources=sorted((R/'rtl/mac_accel').glob('*.v'))+[R/'sim/tb_vision32_layer.sv',R/'sim/gtp_apm_e2_perf_sim.v']
tb=R/'sim/tb_vision32_layer.sv';body=tb.read_text();needle='  if(rd!==32\'h56333231)$fatal(1,"ID %h",rd);'
assert body.count(needle)==1
generated=o/'tb_exact.sv';generated.write_text(body.replace(needle,needle+'\n  ra=8\'h6c;#1;if(rd!==32\'h00010001)$fatal(1,"EXACT_CAP_VERSION %h",rd);'))
sources=[generated if f==tb else f for f in sources]
hashes={f.relative_to(R).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in sources}
temporary=o/'tmp';temporary.mkdir()
cmd="set -eu; export TMPDIR='"+wsl_path(temporary)+"'; cd '"+wsl_path(o)+"'; iverilog -g2012 -s tb_vision32_layer -Ptb_vision32_layer.CASES="+str(len(jobs))+" -Ptb_vision32_layer.SOC="+str(int(a.soc))+" -o exact.vvp "+' '.join("'"+wsl_path(f)+"'" for f in sources)+"; vvp exact.vvp"
with (o/'simulation.log').open('wb') as log:r=subprocess.run(['wsl.exe','-d','pikafish-verify','--','sh','-c',cmd],stdout=log,stderr=subprocess.STDOUT,timeout=1200)
passed=r.returncode==0 and b'VISION32_ALL_PASS' in (o/'simulation.log').read_bytes()
record=dict(status='VISION32_EXACT_S16_LUT65536_RTL_PASS_NOT_BOARD' if passed else 'FAILED_PRESERVED_NOT_BOARD',cases=len(jobs),soc=a.soc,exit_code=r.returncode,inputs_sha256=hashes)
(o/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(record['status'],flush=True)
assert passed,(o/'simulation.log').read_text(errors='replace')[-2500:]
