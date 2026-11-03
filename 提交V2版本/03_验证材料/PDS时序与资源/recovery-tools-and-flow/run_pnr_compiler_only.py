"""Route only after exact native hardware and complete boot INIT qualification."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,ctypes,hashlib,importlib.util,json,os,re,shutil,subprocess,sys,time
B=Path(__file__).resolve().parent;S=B/'source';P=S/'pds';A=B.parent/'pds25-cpu125-20261101-04'
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--attempt',type=int,default=2)
parser.add_argument('--check-only',action='store_true')
args=parser.parse_args();assert 2<=args.attempt<=999
f=read(B/'frozen-inputs.json');q=read(B/'status.json')
assert q['status'] in ['PDS25_FIXED_CPU125_NATIVE_MAP_AND_CONNECTIVITY_INVENTORY_PASS_NOT_STA',
 'CPU125_CM60_COMPILER_AND_ZERO_RESOURCE_NATIVE_PASS_CANDIDATE_PRESERVED_STA_BOARD_PENDING']
proof=read(B/'native-identity-03/result.json')
assert proof['status']=='EXACT_NATIVE_PACKED_CONTROL_AND_BOOT1048576_BITS_PASS'
assert proof['netlist_sha256']==sha(P/'prj_tasks/syn_1/synthesize/soc_top_syn.vm')
assert all(x==0 for x in proof['hardware_delta'].values())
for group in ['native_inputs_sha256','verification_inputs_sha256']:
    for name,value in f[group].items():assert sha(S/name)==value,name
for name in ['pds/soc.fdc','config/clocks.json']:
    assert sha(S/name)==sha(A/'source'/name),name
if args.check_only:
    print(json.dumps(dict(status='FROZEN_NATIVE_AND_VERIFICATION_INPUTS_CURRENT_NATIVE_IDENTITY_PASS_NO_TOOL_STARTED',
        source_commit=f['source_commit'],native_run=q['native_run'],attempt=args.attempt,native_inputs=523,
        verification_inputs=len(f['verification_inputs_sha256']))),flush=True)
    raise SystemExit(0)
parent=read(A/'pnr-preflight-05/result.json')
O=B/'pnr-preflight-05';O.mkdir(exist_ok=True)
rcf=O/'native-priority.rcf';pcf=O/'native-placement.pcf'
for source,target in [(Path(parent['native_priority_rcf']),rcf),(Path(parent['native_placement_pcf']),pcf)]:
    if target.exists():assert sha(source)==sha(target),'Preserved physical policy changed'
    else:shutil.copyfile(source,target)
placements=parent['placements_retained'];priorities=parent['priority_constraints_kept']
assert len(placements)==30 and len(priorities)==39
normalize=lambda n:re.sub(r'\s+','',n)
need_nets={normalize(n) for n in priorities};need_insts={re.search(r'\{([^}]+)\}',line)[1] for line in placements}
seen_nets=set();seen_insts=set()
inventory=B/'map-01/inventory/packed-info.txt';assert sha(inventory)==q['inventory_sha256']
with inventory.open() as stream:
    for line in stream:
        m=re.fullmatch(r'(.*), (?:cfg|sig) port (.*) value : (.*)\n',line)
        if not m:continue
        if m[1] in need_insts:seen_insts.add(m[1])
        net=normalize(m[3])
        if net in need_nets:seen_nets.add(net)
assert seen_nets==need_nets and seen_insts==need_insts,(need_nets-seen_nets,need_insts-seen_insts)
mapped=P/'prj_tasks/pnr_1/device_map/soc_top_map.adf'
pre=dict(status='COMPILER_ONLY_NATIVE_IDENTITY_AND_ALL_BOOT_BITS_PASS_READY_PNR',source_commit=f['source_commit'],
    native_run=q['native_run'],native_inputs_verified=len(f['native_inputs_sha256']),cpu_hz=125000000,
    sys_hz=49500000,sta_cpu_period_ns=7.992,cdc_limit_ns=7.192,resources=proof['resources']['candidate'],
    native_priority_rcf=str(rcf),native_placement_pcf=str(pcf),placements_retained=placements,
    priority_constraints_kept=priorities,map_adf_sha256=sha(mapped),
    native_identity_sha256=sha(B/'native-identity-03/result.json'),parent_preflight_sha256=sha(A/'pnr-preflight-05/result.json'),
    route_constraint_sha256={str(rcf):sha(rcf),str(pcf):sha(pcf)},scope='Exact193 native module connectivity except verified boot INIT. Existing bounded native CPU/CDC proofs preserve original scope. Fresh map actual30 sites/39 nets, unchanged strict125FDC and original pin constraints. Final timing/physical/board remain separate.')
if (O/'result.json').exists():assert read(O/'result.json')==pre,'Preserved preflight receipt changed'
else:(O/'result.json').write_text(json.dumps(pre,indent=2)+'\n')
N=B/f'pnr-{args.attempt:02}';N.mkdir(exist_ok=False)
memory=[]
query="$m=Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory; @{free_commit=[long]$m.CommitLimit-[long]$m.CommittedBytes; free_physical=[long]$m.AvailableMBytes*1048576; commit_limit=[long]$m.CommitLimit}|ConvertTo-Json -Compress"
stable=0
while stable<2:
    p=subprocess.run(['powershell.exe','-NoProfile','-Command',query],capture_output=True,timeout=25)
    assert p.returncode==0
    sample=json.loads(p.stdout.decode('utf-8-sig'));sample['observed_utc']=datetime.now(timezone.utc).isoformat();memory.append(sample)
    ready=sample['free_commit']>=8*1024**3 and sample['free_physical']>=2.5*1024**3
    stable=stable+1 if ready else 0
    (N/'launch-memory-receipt.json').write_text(json.dumps(dict(stable_samples=stable,samples=memory),indent=2)+'\n')
    if stable<2:time.sleep(5 if ready else 20)
I=Path('G:/fpga/PDS_2025.2-ads-win64/pango/PDS_2025.2-ads')
T=Path('G:/fpga/pds_mcp_portable_20260905/pds_mcp_portable')
os.environ.update(PDS_MCP_SERVER_ROOT=str(T/'pds-ai-extension/server/python'),PDS_MCP_PYTHON=sys.executable,
 PDS_PATH=str(I/'bin/pds_shell.exe'),PDS_ROOT=str(I),PANGOPATH=str(I),PDS_WORKSPACE_ROOT=str(B),
 PDS_MCP_LOG_DIR=str(N/'mcp-logs'),PDS_MCP_PORT='0',TEMP=str(B/'tmp'),TMP=str(B/'tmp'),TMPDIR=str(B/'tmp'),PYTHONDONTWRITEBYTECODE='1')
commands=['remove_constraint {ddr3_test.rcf}',
 'add_constraint {'+rcf.as_posix()+'} -pnr_set pnr_1',
 'add_constraint {'+pcf.as_posix()+'} -pnr_set pnr_1',
 'pnr -input_db_file {'+mapped.as_posix()+'} -plc_decongestion 4 -gplace_seed 3 -mode normal -fix_hold_violation_in_route TRUE -fix_hold_violation_threshold_for_clock_path_cross_srb 200 -fix_hold_violation_threshold_for_clk_tree 200',
 'report_timing -report_max_skew']
binding=dict(source_commit=f['source_commit'],current_cpu_source_commit=f['cpu_source_commit'],commands=commands,
    native_identity_sha256=sha(B/'native-identity-03/result.json'),preflight_sha256=sha(O/'result.json'),
    controller_sha256=sha(Path(__file__)),pds_shell_sha256=sha(I/'bin/pds_shell.exe'),
    actual_route_constraint_sha256=pre['route_constraint_sha256'],fdc_sha256=sha(P/'soc.fdc'),
    snapshot_sha256=sha(P/'build_snapshot.json'),native_map_adf_sha256=sha(mapped),
    launch_memory_receipt_sha256=sha(N/'launch-memory-receipt.json'),single_job_timeout_seconds=14400)
(N/'input-binding.json').write_text(json.dumps(binding,indent=2)+'\n')
q.update(status='RUNNING_PDS25_FIXED_CPU125_FULL_PLACE_ROUTE',owner_pid=os.getpid(),
    pnr_started_utc=datetime.now(timezone.utc).isoformat(),current_command='starting native PnR session')
def save():
    (B/'status.json').write_text(json.dumps(q,indent=2)+'\n')
    (N/'result.json').write_text(json.dumps(q,indent=2)+'\n')
save()
spec=importlib.util.spec_from_file_location('client',T/'clients/mcp_probe_flow.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
c=m.McpClient(str(N/'rpc.log'))
try:
    c.initialize();started=c.tool('pds_start',dict(workdir=P.as_posix(),project=(P/'soc25_synth.pds').as_posix(),mock=False),120)
    q['pds_session_pid']=started['pid'];save()
    # Bound only this freshly created owned PDS process to at most four logical CPUs.
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.restype=ctypes.c_void_p
    handle=kernel.OpenProcess(0x0600,False,started['pid']);assert handle
    try:
        process_mask=ctypes.c_size_t();system_mask=ctypes.c_size_t()
        kernel.GetProcessAffinityMask.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_size_t),ctypes.POINTER(ctypes.c_size_t)]
        kernel.SetProcessAffinityMask.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        assert kernel.GetProcessAffinityMask(handle,ctypes.byref(process_mask),ctypes.byref(system_mask))
        chosen=sum(1<<bit for bit in [i for i in range(8*ctypes.sizeof(ctypes.c_size_t)) if process_mask.value&(1<<i)][:4])
        assert chosen and kernel.SetProcessAffinityMask(handle,chosen)
        (N/'owned-affinity.json').write_text(json.dumps(dict(pid=started['pid'],previous_mask=process_mask.value,selected_mask=chosen,max_logical_cpus=4),indent=2)+'\n')
    finally:kernel.CloseHandle(handle)
    for command in commands:
        q['current_command']=command;save()
        result=c.tool('pds_execute',dict(command=command,timeout_ms=14400000 if command.startswith('pnr ') else 600000),14490 if command.startswith('pnr ') else 630)
        assert result['ok'],command
        (N/('report-timing-response.json' if command.startswith('report_timing ') else 'last-response.json')).write_text(json.dumps(result,indent=2)+'\n')
    c.tool('pds_stop',{},120)
    assert sha(mapped)==pre['map_adf_sha256']
    for name,value in f['native_inputs_sha256'].items():assert sha(S/name)==value,name
    q.update(status='PDS25_CPU125_PLACE_ROUTE_AND_TIMING_REPORT_COMPLETED_REVIEW_ALL_CORNERS',completed_utc=datetime.now(timezone.utc).isoformat())
except Exception as error:
    q.update(status='PDS25_CPU125_FULL_PNR_FAILED_PRESERVED',error=repr(error),completed_utc=datetime.now(timezone.utc).isoformat())
finally:
    c.close();save()
print(q['status'],flush=True)
raise SystemExit(0 if q['status']=='PDS25_CPU125_PLACE_ROUTE_AND_TIMING_REPORT_COMPLETED_REVIEW_ALL_CORNERS' else 2)
