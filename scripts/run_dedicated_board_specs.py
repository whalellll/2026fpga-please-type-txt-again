"""Run current-board command specifications and preserve every UART receipt."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,hashlib,subprocess,sys
S=Path(__file__).resolve().parents[1]
B=S/'build/board-trial-dedicated-02'
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
ap=argparse.ArgumentParser();ap.add_argument('--spec',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
B=a.spec.resolve().parent
trial=read(B/'result.json');boot=read(B/'sdboot.result.json')
assert trial['status']=='DEDICATED_PIKAFISH_TRIAL_CRAM_PASS_BOOT_INSPECTION_PENDING'
assert boot['status']=='PRODUCTION_SD_BOOT_CRC_LINUX_ROOT_PASS_APPLICATIONS_PENDING'
assert sha(B/'sdboot.uart')==boot['uart_sha256']
assert sha(Path(trial['bitstream_path']))==trial['bitstream_sha256']
out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
r={'status':'RUNNING','started_utc':datetime.now(timezone.utc).isoformat(),'run_id':trial['run_id'],'bitstream_sha256':trial['bitstream_sha256'],'master_spec_sha256':sha(a.spec),'checks':[]}
save=lambda:(out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
save()
try:
 for item in read(a.spec):
  name=item['name'];assert name.replace('-','').replace('_','').isalnum()
  rows=item['rows'];p=out/(name+'-spec.json');p.write_text(json.dumps(rows,indent=2)+'\n')
  r['current_check']=name;save();print('BOARD_CHECK '+name,flush=True)
  cmd=[sys.executable,'-X','utf8',str(S/'scripts/board_console.py'),'commands','--port','COM17','--log',str(out/(name+'.uart')),'--spec',str(p)]
  with (out/(name+'.host.log')).open('xb') as log:
   child=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=sum(row.get('timeout',90) for row in rows)+60)
  result=read(out/(name+'.result.json'))
  r['checks'].append({'name':name,'status':result['status'],'exit':child.returncode,'receipt_sha256':sha(out/(name+'.result.json'))});save()
  print('CHECK_RESULT '+name+' '+result['status'],flush=True)
  if child.returncode or result['status']!='BOARD_COMMAND_SPEC_PASS':
   print((out/(name+'.host.log')).read_text(errors='replace')[-3500:],flush=True)
   raise RuntimeError(name)
 r['status']='DEDICATED_BOARD_SPEC_BATCH_PASS'
except Exception as e:
 r.update(status='DEDICATED_BOARD_SPEC_BATCH_FAILED_PRESERVED',error=repr(e));raise
finally:
 r['completed_utc']=datetime.now(timezone.utc).isoformat();save();print(r['status'],flush=True)
