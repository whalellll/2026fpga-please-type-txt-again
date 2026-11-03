"""Source-bound correctness, SYN gates and full PnR for the SD ROM repair.

No UART/JTAG/Flash/media/remote access. Preserve every failed stage.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,shutil,subprocess,time,traceback

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--work',type=Path,required=True)
args=parser.parse_args()
work=args.work.resolve()
assert work.parent==Path('G:/fpga/performance_soc_voice_hw/build/cpu80-conv-sdboot-fix-20261022').resolve()
assert not work.exists();work.mkdir()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
r=dict(status='CORRECTNESS_RUNNING',pid=os.getpid(),started_utc=datetime.now(timezone.utc).isoformat(),
       root=str(root),work=str(work),phases=[],board_accessed=False,remote_pushed=False,pnr_started=False)
def save():(work/'flow.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
def run(name,cmd,cwd=root,timeout=900,marker=None):
    item=dict(name=name,command=list(map(str,cmd)),cwd=str(cwd),started_utc=datetime.now(timezone.utc).isoformat())
    r['phases'].append(item);r['phase']=name;save()
    log=work/(name+'.log')
    with log.open('xb') as f:
        p=subprocess.Popen(item['command'],cwd=cwd,stdout=f,stderr=subprocess.STDOUT)
        item['pid']=p.pid;save()
        try:code=p.wait(timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True);raise
    item.update(exit_code=code,completed_utc=datetime.now(timezone.utc).isoformat(),log_sha256=sha(log));save()
    assert code==0,(name,log.read_text(errors='replace')[-3000:])
    if marker:assert marker.encode() in log.read_bytes(),(name,'missing marker',marker)
    print('RECOVERY_PHASE_PASS '+name,flush=True)
py=['G:/py/ana/python.exe','-X','utf8'];ps=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File']
try:
    # Freeze the parent hardware identity and require all CPU/RTL/PLL/IP inputs unchanged.
    parent=Path('G:/fpga/c80cvunpack_fold_20261022_r2/SOC_CANDIDATE')
    old=read(parent/'artifacts/build_snapshot.json')['inputs']
    changed={}
    for n,h in old.items():
        if n.startswith(('rtl/','ip/','config/')):assert sha(root/n)==h,('Unexpected hardware edit',n)
        if (root/n).is_file() and sha(root/n)!=h:changed[n]=dict(parent=h,current=sha(root/n))
    r['parent_run']='8f05785e3ff0461caa69af2d35620f40';r['initial_changed_inputs']=changed;save()
    run('zero-stage',py+[root/'scripts/test_sd_zero_stage.py','--gcc','G:/fpga/workspace/tools/msys64/mingw64/bin/gcc.exe','--output',work/'zero-stage'],marker='SD_ZERO_STAGE_HOST_PASS_NOT_BOARD')
    run('full-soc',ps+[root/'scripts/run_all_tests.ps1','-IcarusBin','G:/fpga/workspace/tools/msys64/ucrt64/bin',
        '-MsysRoot','G:/fpga/workspace/tools/msys64','-ToolchainBin','G:/fpga/workspace/tools/riscv32-gcc16/bin',
        '-PythonPath','G:/py/ana/python.exe','-HostGccPath','G:/fpga/workspace/tools/msys64/mingw64/bin/gcc.exe',
        '-PdsRoot','G:/fpga/PDS_2022.2-SP6.4','-PllWslDistro','pikafish-verify',
        '-PolicyFixtureRoot',parent/'prebuilt/cpu80-policy-fixture'],timeout=7200,marker='SOC_ALL_TESTS_PASS')
    r['status']='CORRECTNESS_PASS_STAGING_SYNTHESIS';save()
    resource=Path('G:/fpga/c80sdbr1');native=Path('G:/fpga/c80sdbp1')
    for name,target in [('resource-stage',resource)]:
        assert not target.exists()
        run(name,ps+[root/'scripts/stage_cpu_timing_candidate.ps1','-SourceRoot',root,'-OutputRoot',target,
                      '-Divisor','27','-CpuClockSource','dedicated1080frac','-DtcPath','G:/fpga/performance_soc_voice_hw/build/dtc_proxy.cmd'])
    run('resource-build',ps+[resource/'scripts/build_fpga.ps1','-SynthesisOnly','-UseExistingFirmware',
                            '-PythonPath','G:/py/ana/python.exe','-PdsTimeoutSeconds','14400'],cwd=resource,timeout=15000)
    snapshot=read(resource/'pds/build_snapshot.json')
    proof=read(resource/'pds/input-snapshots'/snapshot['run_id']/'synthesis-only.json')
    assert proof['pnr_started'] is False
    for n,h in snapshot['inputs'].items():assert sha(root/n)==sha(resource/n)==h,n
    r.update(status='CORRECTNESS_SYNTHESIS_GATES_PASS_FREEZING',resource_run=snapshot['run_id'],resources=proof['resources']);save()
    run('freeze-add',['git','add','-u'])
    run('freeze-add-new',['git','add','sw/bootloader/sd_boot_load.h','sim/sd_zero_stage_host_test.c',
                          'scripts/test_sd_zero_stage.py','scripts/run_cpu80_sdboot_recovery.py'])
    run('freeze-commit',['git','commit','-m','Freeze CPU80 convolution ROM zero-address SD bootstrap repair after correctness and synthesis gates'])
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root).decode().strip()
    for n,h in snapshot['inputs'].items():assert sha(root/n)==h,n
    r.update(soc_implementation_commit=commit);save()
    (work/'soc-freeze.json').write_text(json.dumps(dict(soc_implementation_commit=commit,inputs=snapshot['inputs'],resources=proof['resources'],board_tested=False),indent=2)+'\n')
    assert not native.exists()
    run('native-stage',ps+[root/'scripts/stage_cpu_timing_candidate.ps1','-SourceRoot',root,'-OutputRoot',native,
                           '-Divisor','27','-CpuClockSource','dedicated1080frac','-DtcPath','G:/fpga/performance_soc_voice_hw/build/dtc_proxy.cmd'])
    for n,h in snapshot['inputs'].items():assert sha(native/n)==h,n
    r.update(status='NATIVE_BUILD_RUNNING',native_root=str(native),pnr_started=True);save()
    run('native-build',ps+[native/'scripts/build_fpga.ps1','-UseExistingFirmware','-PythonPath','G:/py/ana/python.exe',
                           '-PdsTimeoutSeconds','14400','-CampaignLog',work/'pnr-history.json','-AttemptPurpose','search'],cwd=native,timeout=15000)
    actual=read(native/'pds/build_snapshot.json');evidence=read(native/'artifacts/build_evidence.json')
    assert actual['inputs']==snapshot['inputs']
    assert evidence['timing']=='All Constraints Met' and evidence['max_skew_verified'] and evidence['timing_scope_verified']
    r.update(status='REPAIRED_SD_ROM_NATIVE_ALL_GATES_PASS_BOARD_PENDING',run_id=actual['run_id'],
             bitstream_sha256=sha(native/'artifacts/soc_top.sbit'))
except Exception:
    r.update(status='FAILED_PRESERVED_NO_PROMOTION',error=traceback.format_exc());raise
finally:
    r['updated_utc']=datetime.now(timezone.utc).isoformat();save();print(r['status'],flush=True)
