"""Build matched driver-backed NNUE, search, GUI and latency programs in WSL."""
from pathlib import Path
import argparse,hashlib,json,subprocess,tarfile,uuid
ROOT=Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0,str(ROOT/"scripts"))
from workspace_paths import workspace_path,wsl_path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def linux(p):
 s=p.resolve().as_posix();return '/mnt/'+s[0].lower()+s[2:]
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
 ap.add_argument('--baseline',type=Path,default=Path('G:/fpga/performance_soc_voice_hw/build/pikafish-rv32/source'));ap.add_argument('--baseline-wsl');ap.add_argument('--local-build',action='store_true');a=ap.parse_args()
 out=workspace_path(a.output);assert not out.exists();out.parent.mkdir(parents=True,exist_ok=True)
 baseline=workspace_path(a.baseline)
 assert not any(p.is_symlink() for sub in ('src','scripts') for p in (baseline/sub).rglob('*')), 'Prepared source must not traverse links'
 if a.baseline_wsl:
  assert a.baseline_wsl.startswith('/mnt/g/fpga/') and '..' not in a.baseline_wsl.split('/')
 paths=[p for group in ['linux/pikafish','linux/voice','linux/mac_accel','sw'] for p in (ROOT/group).rglob('*') if p.is_file() and p.suffix in ['.cpp','.c','.h','.sh','.patch','.py']]
 hashes={p.relative_to(ROOT).as_posix():sha(p) for p in paths}
 cmd=['wsl.exe','-d','pikafish-verify','--','timeout','--kill-after=30s','1800','sh',linux(ROOT/'linux/pikafish/build_voice_nnue75.sh'),linux(ROOT),a.baseline_wsl or linux(a.baseline),linux(out)]
 local=None
 if a.local_build:
  assert a.baseline_wsl and a.baseline_wsl.startswith('/mnt/g/fpga/')
  local=linux(workspace_path(out.parent/(out.name+'-inputs')))
  stage=subprocess.Popen(['wsl.exe','-d','pikafish-verify','--','sh','-c','set -eu; mkdir '+local+'; tar -xf - -C '+local],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  with tarfile.open(fileobj=stage.stdin,mode='w|') as archive:
   for p in paths:archive.add(p,arcname=p.relative_to(ROOT).as_posix(),recursive=False)
  stage.stdin.close();stage.stdin=None
  so,se=stage.communicate(timeout=120);assert stage.returncode==0,(so+se).decode(errors='replace')
  cmd=['wsl.exe','-d','pikafish-verify','--','env','PATH=/opt/toolchain/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','timeout','--kill-after=30s','1800','sh',local+'/linux/pikafish/build_voice_nnue75.sh',local,a.baseline_wsl,local+'/out']
 log=out.parent/(out.name+'.log')
 with log.open('xb') as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=1840)
 assert r.returncode==0,(r.returncode,log)
 assert all(sha(ROOT/n)==h for n,h in hashes.items()),'Runtime input changed during build'
 names=['pikafish-rv32','pikafish-pipeline-search','xiangqi-pikafish-gui-display','pikafish-nnue-pipeline-latency']
 if local:
  out.mkdir()
  for n in names+['pipeline-integration.json','feature-updates-integration.json']:
   with (out/n).open('xb') as target:
    copy=subprocess.run(['wsl.exe','-d','pikafish-verify','--','cat',local+'/out/'+n],stdout=target,stderr=subprocess.PIPE,timeout=60)
   assert copy.returncode==0,copy.stderr
 integration=json.loads((out/'pipeline-integration.json').read_text());assert integration['status']=='ALL_THREE_NNUE_PIPELINE_HOOKS_VERIFIED'
 direct=json.loads((out/'feature-updates-integration.json').read_text())
 assert direct['status']=='DIRECT_FEATURE_DESCRIPTORS_AND_SCALAR_GUARDS_VERIFIED'
 assert direct['source_sha256']==integration['patched_sources_sha256']['src/nnue/nnue_accumulator.cpp']
 record=dict(status='PIKAFISH75_PIPELINE_SEARCH_AND_GUI_RV32_BUILD_PASS_NOT_BOARD',sources_sha256=hashes,commands=cmd,artifacts_sha256={n:sha(out/n) for n in names},log_sha256=sha(log),pipeline_integration=integration,pipeline_integration_sha256=sha(out/'pipeline-integration.json'),scope='Dedicated paired software; board acceptance pending')
 (out/'result.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
 print(record['status'])
if __name__=='__main__':main()
