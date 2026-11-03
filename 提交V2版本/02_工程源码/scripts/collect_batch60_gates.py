"""Bind completed candidate gates and exact sources; no build/board action."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,shutil,gzip
ROOT=Path(__file__).resolve().parents[1]
NATIVE=Path('G:/pfb60s1')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def main():
 files={};checks={}
 expected={
 'build/batch60-rtl-02/result.json':'PIKAFISH_BATCH_SHARED_AXI_DEPENDENCY_EXPORT_SCORE_RECOVERY_PASS_NOT_BOARD',
 'build/batch60-runtime-01/result.json':'PIKAFISH_BATCH_REAL_RUNTIME_ORACLE_PASS_NOT_BOARD',
 'build/batch60-driver-02/result.json':'ACTUAL_BATCH_DRIVER_TRANSACTION_STUB_PASS_NOT_KERNEL_OR_BOARD',
 'build/batch60-open-service-02/result.json':'ACTUAL_MAC_OPEN_PRIVATE_CLEAR_COOPERATIVE_SERVICE_PASS_NOT_KERNEL_OR_BOARD',
 'build/batch60-runtime-legacy-01/result.json':'VOICE_NNUE_REAL_RUNTIME_MOCK_DEVICE_CONTEXT_AND_POOLING_PASS_NOT_BOARD',
 'build/batch60-pll-01/result.json':'CPU60_PLL_VENDOR_WAVEFORM_PASS_NOT_STA_OR_BOARD',
 'build/batch60-official-0/result.json':'PIKAFISH_DEDICATED_C_REFERENCE_CACHE_AND_RECOVERY_PASS_NOT_BOARD',
 'build/batch60-official-1/result.json':'PIKAFISH_DEDICATED_C_REFERENCE_CACHE_AND_RECOVERY_PASS_NOT_BOARD',
 'build/batch60-runtime-rv32-01/result.json':'PIKAFISH75_PIPELINE_SEARCH_AND_GUI_RV32_BUILD_PASS_NOT_BOARD',
 'build/batch60-kernel-01/build.json':'VOICE_NNUE_FROZEN_KERNEL_BUILD_PASS_NOT_BOARD',
 'build/batch60-native-clock-02.json':'DEDICATED_CPU_PLL_ADS_PASS_NOT_STA_OR_BOARD',
 'build/batch60-native-cpu-01.json':'PASS',
 'build/batch60-pma-faults-03/result.json':'BATCH60_NATIVE_PMA_EXPORT_FAULTS_PASS_NOT_STA_OR_BOARD',
 'build/batch60-scope-tests-02/result.json':'PIXEL_SCOPE_ADAPTER_MUTATIONS_PASS_NOT_HARDWARE',
 }
 for name,status in expected.items():
  result=read(ROOT/name);assert result['status']==status,(name,result.get('status'))
  checks[name]=status;files[name]=sha(ROOT/name)
  for group in ('source_sha256','sources_sha256','inputs_sha256'):
   for path,h in result.get(group,{}).items():
    p=Path(path) if Path(path).is_absolute() else ROOT/path
    assert sha(p)==h,('Gate source changed',name,p)
    if p.is_relative_to(ROOT):files[p.relative_to(ROOT).as_posix()]=h
 # The complete Windows regression's final marker is authoritative only after
 # the caller has observed the process exit; retain its explicit exit receipt.
 full=read(ROOT/'build/batch60-full-regression-02.json')
 assert full['exit_code']==0 and full['status']=='SOC_ALL_TESTS_PASS_NOT_BOARD'
 assert full['log_sha256']==sha(ROOT/'build/batch60-full-regression-02.log')
 assert full['sources_unchanged'] and all(sha(ROOT/p)==h for p,h in full['sources_sha256'].items())
 files.update(full['sources_sha256'])
 text=(ROOT/'build/batch60-full-regression-02.log').read_bytes().replace(b'\0',b'')
 assert b'SOC_ALL_TESTS_PASS' in text
 for name in ('build/batch60-full-regression-02.json','build/batch60-full-regression-02.log'):files[name]=sha(ROOT/name)
 for name in ('scripts/build_pikafish_batch_pnr.ps1','scripts/collect_batch60_gates.py'):files[name]=sha(ROOT/name)
 cpu=read(ROOT/'build/batch60-native-cpu-01.json');faults=read(ROOT/'build/batch60-pma-faults-03/result.json')
 assert cpu['batch_cpu_adapter_sha256']==faults['adapter_sha256']==sha(ROOT/'scripts/audit_pikafish_batch60_ads.py')
 assert cpu['netlist_sha256']==faults['netlist_sha256']==sha(Path('G:/pfb60p1/pds/synthesize/soc_top_syn.vm'))
 assert len(faults['faults'])==5 and all(x['rejected'] for x in faults['faults'].values())
 assert faults['test_sha256']==sha(ROOT/'scripts/test_batch60_cpu_ads.py')
 scope=read(ROOT/'build/batch60-scope-tests-02/result.json')
 assert scope['production_sha256']==sha(ROOT/'scripts/timing_scope.ps1') and len(scope['checks'])==9
 for name in ('audit_pikafish_batch60_ads.py','test_batch60_cpu_ads.py','test_batch60_pixel_scope.ps1','timing_scope_pixel_grid.ps1'):
  files['scripts/'+name]=sha(ROOT/'scripts'/name)
 pre=read(NATIVE/'resource-evidence/result.json');assert pre['status']=='SYNTHESIS_COMPLETE_RESOURCE_REVIEW_ONLY'
 tool_changes={}
 for name,h in pre['inputs'].items():
  current=sha(ROOT/name)
  if current!=h:
   assert name in ('scripts/audit_cpu_dedicated_pll_ads.py','scripts/build_cpu_ads_gate.ps1','scripts/build_fpga.ps1','scripts/build_snapshot.ps1','scripts/timing_scope.ps1'),('Changed preflight input',name)
   # Only whitespace normalization after the native preflight; executable
   # checker tokens and all RTL/clock/firmware/constraints must be identical.
   if name=='scripts/audit_cpu_dedicated_pll_ads.py':
    assert [line.rstrip() for line in (ROOT/name).read_text().splitlines()]==[line.rstrip() for line in (NATIVE/name).read_text().splitlines()]
   tool_changes[name]=dict(preflight=h,current=current,reason='Reviewed checker-only change; actual native CPU proof plus PMA fault and pixel-scope mutation tests; no RTL/clock/firmware/constraint change')
  files[name]=current
 evidence=ROOT/'docs/validation/pikafish-batch60-20261024';evidence.mkdir(parents=True,exist_ok=True)
 for name in expected:
  shutil.copy2(ROOT/name,evidence/(Path(name).parent.name+'-'+Path(name).name))
 shutil.copy2(NATIVE/'resource-evidence/result.json',evidence/'native-synthesis.json')
 report=(NATIVE/'pds/synthesize/soc_top.snr').read_text()
 counts={key:float(re.search(pattern,report).group(1)) for key,pattern in [
  ('lut',r'Total LUTs:\s+(\d+)'),('ff',r'Total Registers:\s+(\d+)'),('drm',r'Total DRM =\s+([\d.]+)'),('apm',r'Total APMs =\s+([\d.]+)')]}
 assert counts==dict(lut=45152.,ff=33202.,drm=138.,apm=64.)
 resource=dict(status='BATCH60_NATIVE_RESOURCE_PASS_NOT_STA_OR_BOARD',total=counts,
  parent_total=dict(lut=44073,ff=32305,drm=134,apm=64),controller=dict(lut=952,ff=889,drm=4,apm=0),
  report_sha256=sha(NATIVE/'pds/synthesize/soc_top.snr'))
 (evidence/'resources.json').write_text(json.dumps(resource,indent=2)+'\n')
 with gzip.open(evidence/'native-synthesis.snr.gz','wb') as f:f.write((NATIVE/'pds/synthesize/soc_top.snr').read_bytes())
 result=dict(status='BATCH60_CORRECTNESS_RESOURCE_GATES_PASS_NOT_STA_OR_BOARD',created_utc=datetime.now(timezone.utc).isoformat(),
  checks=checks,files=files,preflight_tool_changes=tool_changes,resources=resource)
 target=ROOT/'build/batch60-gates-02.json';assert not target.exists()
 target.write_text(json.dumps(result,indent=2)+'\n')
 shutil.copy2(target,evidence/'gates-02.json')
 print(result['status'])
if __name__=='__main__':main()
