"""One evidence-driven80MHz hold/issue-route candidate; offline gates first."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,traceback
root=Path(__file__).resolve().parents[1]
work=Path('G:/fpga/performance_soc_voice_hw/build/cpu80-halfmac-gui1080-20261023/attempt-03')
native=Path('G:/fpga/c80h1080p3');baseline=Path('G:/fpga/c80h1080p2')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
assert not work.exists() and not native.exists();work.mkdir()
r=dict(status='CPU80_HALF_HOLD_FIX_CORRECTNESS_RUNNING',owner_pid=os.getpid(),source_root=str(root),native_root=str(native),phases=[],
       started_utc=datetime.now(timezone.utc).isoformat(),pnr_started=False,board_accessed=False,remote_pushed=False,delivery_created=False,
       final_sta_filename='final-sta-03.json',route_audit_filename='final-native-route-audit-03.json',
       purpose='One retained identity LUT on conv write bits120/121; replace invalid MDU31 priority with measured ALU1 issueUsesFast and add measured N1294[0]. CPU/clock/cache/cycles unchanged.')
def save():
 r['updated_utc']=datetime.now(timezone.utc).isoformat();(work/'flow.json').write_text(json.dumps(r,indent=2)+'\n')
def run(name,cmd,cwd=root,timeout=1200):
 item=dict(name=name,command=list(map(str,cmd)),cwd=str(cwd),started_utc=datetime.now(timezone.utc).isoformat());r['phase']=name;r['phases'].append(item);save()
 log=work/(name+'.log')
 with log.open('xb') as output:
  p=subprocess.Popen(item['command'],cwd=cwd,stdout=output,stderr=subprocess.STDOUT);item['pid']=p.pid;save()
  try:code=p.wait(timeout)
  except subprocess.TimeoutExpired:
   subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True);raise
 item.update(exit_code=code,completed_utc=datetime.now(timezone.utc).isoformat(),log_sha256=sha(log));save()
 raw=log.read_bytes();text=raw.decode('utf-16' if raw.startswith(b'\xff\xfe') else 'utf-8-sig',errors='replace')
 assert code==0,(name,text[-2500:]);print('CPU80_HOLD_FIX_PHASE_PASS '+name,flush=True);return text
ps=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File'];py=['G:/py/ana/python.exe','-X','utf8']
iv='G:/fpga/workspace/tools/msys64/ucrt64/bin'
try:
 old=read(baseline/'pds/build_snapshot.json')
 allowed={'rtl/mac_accel/mac_conv_weight_dma.v','pds/ddr3_test.rcf','scripts/build_snapshot.ps1','scripts/build_cpu_ads_gate.ps1','scripts/build_fpga.ps1'}
 changed={p for p,h in old['inputs'].items() if sha(root/p)!=h};assert changed==allowed,changed
 r['baseline_run']=old['run_id'];r['changed_existing_inputs']=sorted(changed)
 assert sha(root/'pds/soc.fdc')==old['inputs']['pds/soc.fdc']
 assert sha(root/'rtl/cpu/CoreTop.sv')==old['inputs']['rtl/cpu/CoreTop.sv']
 proof=read(work.parent/'optimization-03/stream-vendor/result.json')
 assert proof['status']=='CONV_STREAM_FOLD_RAW_AND_FOLDED_FULL_PROTOCOL_CYCLE_MITERS_PASS_NOT_NATIVE_STA_OR_BOARD' and proof['source_sha256']==sha(root/'rtl/mac_accel/mac_conv_weight_dma.v')
 r['synthesis_vendor_full_protocol_proof_sha256']=sha(work.parent/'optimization-03/stream-vendor/result.json')
 run('route-fixtures',ps+[root/'scripts/test_gui1080_placement.ps1','-ReportPath',work/'route-fixtures.json'])
 run('hold-proof-fixtures',py+[root/'scripts/test_conv_weight_hold_ads.py','--baseline-vm',baseline/'pds/synthesize/soc_top_syn.vm','--output',work/'hold-proof-fixtures.json'])
 run('half-soc',py+[root/'scripts/test_mac_half_soc.py','--icarus-bin',iv,'--output',work/'half-soc'])
 regression=run('full-regression',ps+[root/'scripts/run_all_tests.ps1','-IcarusBin',iv,
  '-MsysRoot','G:/fpga/workspace/tools/msys64','-ToolchainBin','G:/fpga/workspace/tools/riscv32-gcc16/bin',
  '-PythonPath','G:/py/ana/python.exe','-HostGccPath','G:/fpga/workspace/tools/msys64/mingw64/bin/gcc.exe',
  '-PdsRoot','G:/fpga/PDS_2022.2-SP6.4','-PllWslDistro','pikafish-verify','-PolicyFixtureRoot',root/'prebuilt/cpu80-policy-fixture'],timeout=3600)
 assert 'SOC_ALL_TESTS_PASS' in regression
 run('freeze-tracked',['git','add','-u'])
 run('freeze-new',['git','add','scripts/run_cpu80_halfmac_fix_flow.py','scripts/audit_conv_weight_hold_ads.py','scripts/test_conv_weight_hold_ads.py','docs/CPU80_Half_MAC_Hold_Route_20261023.md'])
 run('freeze-commit',['git','commit','-m','Freeze80MHz convolution write hold pad and measured ALU1 route candidate after correctness'])
 r['source_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root).decode().strip();save()
 run('stage',ps+[root/'scripts/stage_cpu_timing_candidate.ps1','-SourceRoot',root,'-OutputRoot',native,'-Divisor','27','-CpuClockSource','dedicated1080frac','-DtcPath','G:/fpga/performance_soc_voice_hw/build/dtc_proxy.cmd'])
 stage=read(native/'candidate-stage.json')
 for p,h in stage['prepared_inputs'].items():assert sha(root/p)==h,p
 r['status']='CPU80_HALF_NATIVE_BUILD_RUNNING';save()
 run('native-build',ps+[native/'scripts/build_fpga.ps1','-UseExistingFirmware','-PythonPath','G:/py/ana/python.exe','-PdsTimeoutSeconds','14400','-CampaignLog',work/'pnr-history.json','-AttemptPurpose','final'],cwd=native,timeout=15000)
 r['status']='CPU80_HALF_NATIVE_GATES_PASS_BOARD_PENDING'
except BaseException:
 r['status']='CPU80_HALF_FAILED_PRESERVED_NO_PROMOTION';r['error']=traceback.format_exc();print(r['error'],flush=True)
finally:
 snap=read(native/'pds/build_snapshot.json') if (native/'pds/build_snapshot.json').is_file() else {}
 r['native_run_id']=snap.get('run_id');r['input_count']=len(snap.get('inputs',{}));r['pnr_started']=(work/'pnr-history.json').is_file()
 r['finished_utc']=datetime.now(timezone.utc).isoformat();save()
if r['status'].endswith('NO_PROMOTION'):raise SystemExit(1)
