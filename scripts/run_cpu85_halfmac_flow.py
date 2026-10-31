"""Exact85/half-output offline native experiment. No board, remote or delivery."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,traceback

root=Path(__file__).resolve().parents[1]
work=Path('G:/fpga/performance_soc_voice_hw/build/cpu85-halfmac-gui1080-20261023/attempt-03')
previous=Path('G:/fpga/performance_soc_voice_hw/build/cpu80-gui1080-accept-20261023')
native=Path('G:/fpga/c85h1080p2')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
assert not work.exists();work.mkdir()
r=dict(status='CPU85_HALF_OUTPUT_PRECHECKS_RUNNING',owner_pid=os.getpid(),source_root=str(root),native_root=str(native),phases=[],started_utc=datetime.now(timezone.utc).isoformat(),pnr_started=False,board_accessed=False,remote_pushed=False,delivery_created=False)
def save():
 r['updated_utc']=datetime.now(timezone.utc).isoformat()
 (work/'flow.json').write_text(json.dumps(r,indent=2)+'\n')
def run(name,cmd,cwd=root,timeout=1200):
 item=dict(name=name,command=list(map(str,cmd)),cwd=str(cwd),started_utc=datetime.now(timezone.utc).isoformat());r['phases'].append(item);r['phase']=name;save()
 log=work/(name+'.log')
 with log.open('xb') as f:
  proc=subprocess.Popen(item['command'],cwd=cwd,stdout=f,stderr=subprocess.STDOUT);item['pid']=proc.pid;save()
  try:code=proc.wait(timeout)
  except subprocess.TimeoutExpired:
   subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True);raise
 item.update(exit_code=code,log_sha256=sha(log),completed_utc=datetime.now(timezone.utc).isoformat());save()
 assert code==0,(name,log.read_text(errors='replace')[-2500:])
 print('CPU85_HALF_PHASE_PASS '+name,flush=True)
ps=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File']
py=['G:/py/ana/python.exe','-X','utf8']
try:
 proofs={
  'halfmac-correctness-04/result.json':'MAC_HALF_OUTPUT_DIFFERENTIAL_PASS',
  'halfmac-s16-golden-02.json':'HALF_S16_DOT_AND_SQUARE_INTEGER_GOLDEN_PASS_NOT_STA',
  'halfmac-soc-02/result.json':'HALF_OUTPUT_DENSE_GATHER_DDR_CONV_ISOLATION_PASS_NOT_STA_OR_BOARD',
  'cpu85-pll-02/result.json':'CPU85_FRAC_PLL_VENDOR_WAVEFORM_PASS',
  'cpu85-clock-policy.json':'PASS',
 }
 for n,status in proofs.items():
  x=read(previous/n);assert x['status']==status
  if n.startswith('halfmac-correctness'):
   assert x['core_sha256']==sha(root/'rtl/mac_accel/MacAccelCore.v')
   for p,h in x['sources'].items():assert sha(root/p)==h,p
  elif n.startswith('halfmac-s16') or n.startswith('halfmac-soc'):
   for p,h in x['source_sha256'].items():assert sha(root/p)==h,p
  elif n.startswith('cpu85-pll'):
   for p,h in x['source_sha256'].items():
    local=Path('G:'+p[6:]) if p.startswith('/mnt/g/') else Path(p)
    assert sha(local)==h,p
 r['prerequisite_proofs']={n:sha(previous/n) for n in proofs}
 log=previous/'cpu85-full-regression-02.log';raw=log.read_bytes();assert 'SOC_ALL_TESTS_PASS' in raw.decode('utf-16' if raw.startswith(b'\xff\xfe') else 'utf-8-sig');r['full_regression_log_sha256']=sha(log)
 r['source_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root).decode().strip()
 # A native-only checker extension does not change the previously tested RTL.
 old=Path('G:/fpga/c85h1080p1');old_snap=read(old/'pds/build_snapshot.json')
 changed={n for n,h in old_snap['inputs'].items() if sha(root/n)!=h}
 assert changed=={'scripts/build_snapshot.ps1','scripts/build_cpu_ads_gate.ps1','scripts/build_fpga.ps1'},changed
 pf=read(work.parent/'pma-faults-01.json');assert pf['status']=='NATIVE_PMA_PAGE_1024_CASES_AND_THREE_FAULTS_PASS_NOT_STA'
 assert pf['adapter_sha256']==sha(root/'scripts/audit_cpu85_half_ads.py') and pf['netlist_sha256']==sha(old/'pds/synthesize/soc_top_syn.vm')
 r['parser_only_delta_from_first_synthesis']=sorted(changed);r['pma_fault_proof_sha256']=sha(work.parent/'pma-faults-01.json')
 if not native.exists():
  run('stage',ps+[root/'scripts/stage_cpu_timing_candidate.ps1','-SourceRoot',root,'-OutputRoot',native,'-Divisor','27','-CpuClockSource','dedicated1147p5frac','-DtcPath','G:/fpga/performance_soc_voice_hw/build/dtc_proxy.cmd'])
 # This destination has only been staged; no prior native snapshot may exist.
 assert native.is_dir() and not (native/'pds/build_snapshot.json').exists()
 stage=read(native/'candidate-stage.json');assert stage['source_root']==str(root)
 # Reconcile the mutable, not-yet-frozen stage with the final reviewed source.
 # Preserve the original stage receipt; record every new copy and changed hash.
 names=set(stage['prepared_inputs'])
 for directory in ['scripts','config','sim']:
  names.update(p.relative_to(root).as_posix() for p in (root/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
 import shutil
 changes={}
 for n in sorted(names):
  src=root/n;dst=native/n;assert src.is_file(),n
  old=sha(dst) if dst.is_file() else None;new=sha(src)
  if old!=new:
   dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst);changes[n]=dict(before=old,after=new)
 (native/'stage-final-reconciliation.json').write_text(json.dumps(dict(status='SOURCE_STAGE_RECONCILED_BEFORE_ANY_NATIVE_BUILD',source_commit=r['source_commit'],original_stage_sha256=sha(native/'candidate-stage.json'),changes=changes),indent=2)+'\n')
 r['stage_reconciliation_sha256']=sha(native/'stage-final-reconciliation.json')
 run('exact-clock',ps+[native/'scripts/check_clock_config.ps1','-Root',native],cwd=native)
 run('clock-negative-fixtures',ps+[native/'scripts/test_cpu85_frac_clock.ps1','-ReportPath',work/'clock-policy.json'],cwd=native)
 r['status']='CPU85_HALF_OUTPUT_NATIVE_BUILD_RUNNING';save()
 run('native-build',ps+[native/'scripts/build_fpga.ps1','-UseExistingFirmware','-PythonPath','G:/py/ana/python.exe','-PdsTimeoutSeconds','14400','-CampaignLog',work/'pnr-history.json','-AttemptPurpose','final'],cwd=native,timeout=15000)
 r['status']='CPU85_HALF_OUTPUT_NATIVE_BUILD_PASS_NOT_BOARD_OR_DELIVERY'
except BaseException:
 r['status']='CPU85_HALF_OUTPUT_FAILED_PRESERVED_NO_PROMOTION';r['error']=traceback.format_exc()
 print(r['status'],flush=True);print(r['error'],flush=True)
finally:
 snap=read(native/'pds/build_snapshot.json') if (native/'pds/build_snapshot.json').is_file() else {}
 r['native_run_id']=snap.get('run_id');r['input_count']=len(snap.get('inputs',{}))
 r['pnr_started']=(work/'pnr-history.json').is_file()
 r['finished_utc']=datetime.now(timezone.utc).isoformat();save()
if r['status'].endswith('NO_PROMOTION'):raise SystemExit(1)
