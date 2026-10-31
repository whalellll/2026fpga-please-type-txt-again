"""Bind passing offline checks to current sources; never assert board acceptance."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,shutil,subprocess
R=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();out=a.output.resolve();assert not out.exists()
 paths={'unit':'build/voice-cnn-rtl-02/result.json','mmio':'build/voice-cnn-mmio-01/result.json','model':'build/voice2-model-bound-01/result.json','rv32_model':'build/voice2-rv32-bound-01/result.json','wav':'build/voice2-wav-01/result.json','legacy':'build/voice2-legacy-mmio-01/result.json','runtime':'build/voice2-rv32-build-02/result.json','kernel':'build/voice2-kernel-01/build.json','full_regression':'build/voice2-full-regression-02/result.json'}
 results={name:read(R/p) for name,p in paths.items()}
 for name,result in results.items():assert 'PASS' in result['status'],(name,result['status'])
 assert results['unit']['rtl_sha256']==results['mmio']['rtl_sha256']==sha(R/'rtl/audio/voice_cnn_tile_core.v')
 for name in ['model','rv32_model','runtime','wav','kernel']:
  for path,h in results[name]['inputs_sha256'].items():
   p=Path(path);p=p if p.is_absolute() else R/p;assert sha(p)==h,(name,path)
 assert results['model']['cases']==results['rv32_model']['cases']
 manifest=read(R/'linux/voice2/SOURCE.json')
 for p,h in manifest['files_sha256'].items():assert sha(R/'linux/voice2'/p)==h,p
 full=results['full_regression'];assert full['exit_code']==0
 assert sha(R/'build/voice2-full-regression-02/run.log')==full['log_sha256']
 assert b'SOC_ALL_TESTS_PASS' in (R/'build/voice2-full-regression-02/run.log').read_bytes()
 native=Path('G:/v2vsyn1');receipt=read(native/'resource-evidence/result.json')
 assert receipt['status']=='SYNTHESIS_COMPLETE_RESOURCE_REVIEW_ONLY'
 tool_differences=[];missing_source=[];hardware_count=0
 for p,h in receipt['inputs'].items():
  assert sha(native/p)==h,('native changed',p)
  source=R/p
  if not source.exists():missing_source.append(p);continue
  if p.split('/')[0] in ['rtl','ip','config','sw','artifacts','pds']:
   assert sha(source)==h,('hardware/source changed',p);hardware_count+=1
  elif sha(source)!=h:tool_differences.append(p)
 assert not missing_source,('Unbound source inputs',missing_source)
 out.mkdir(parents=True)
 checks={}
 for root,label in [(native,'new-profile'),(Path('G:/pfdsyn2'),'legacy-profile')]:
  p=subprocess.run(['G:/py/ana/python.exe','-X','utf8',str(R/'scripts/test_pikafish_dedicated_resource_contract.py'),'--native-root',str(root)],capture_output=True,timeout=60)
  log=out/(label+'.log');log.write_bytes(p.stdout+p.stderr);assert p.returncode==0,p.stdout+p.stderr
  checks[label]=sha(log)
 for name,p in paths.items():shutil.copyfile(R/p,out/(name+'.json'))
 for name in ['soc_top.snr','soc_top_syn.vm']:
  checks['native-'+name]=sha(native/'pds/synthesize'/name)
 shutil.copyfile(native/'pds/synthesize/soc_top.snr',out/'candidate.snr')
 shutil.copyfile(R/'build/voice2-resources-01.json',out/'resources.json')
 result={'status':'VOICE2_SMALL_ACCEL_OFFLINE_ADAPTATION_VERIFIED_PHYSICAL_BOARD_PENDING','updated_utc':datetime.now(timezone.utc).isoformat(),'source_root':str(R),'source_head_at_audit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=R).decode().strip(),'checks':{k:{'path':p,'sha256':sha(R/p),'status':results[k]['status']} for k,p in paths.items()},'native_checks_sha256':checks,'hardware_inputs_equal':hardware_count,'source_missing_staged_aliases':missing_source,'source_tool_differences_since_synthesis':tool_differences,'model_sha256':sha(R/'linux/voice2/balanced24.bin'),'scope':'CPU frontend, bias/requant andCTC; all CNN dots in small4-lane voice accelerator. Offline integer parity, not recognition accuracy, PnR/STA or speedup. Dedicated Pikafish software combination remains separate.','board':False,'pnr':False,'push':False,'delivery':False}
 (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'hardware_inputs_equal':hardware_count,'source_missing':missing_source,'tool_differences':tool_differences}))
if __name__=='__main__':main()
