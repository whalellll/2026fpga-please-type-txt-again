"""Retarget the frozen half-output experiment to exact80MHz, then native PnR.

No board access, remote publication or delivery packaging. Every attempt is new.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, os, subprocess, traceback

root = Path(__file__).resolve().parents[1]
work = Path('G:/fpga/performance_soc_voice_hw/build/cpu80-halfmac-gui1080-20261023/attempt-02')
native = Path('G:/fpga/c80h1080p2')
baseline = Path('G:/fpga/c85h1080p2')
previous = Path('G:/fpga/performance_soc_voice_hw/build/cpu80-gui1080-accept-20261023')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
assert not work.exists() and not native.exists(), 'Never overwrite an earlier attempt'
work.mkdir(parents=True)
record = dict(status='CPU80_HALF_PRECHECKS_RUNNING', owner_pid=os.getpid(),
              source_root=str(root), native_root=str(native), phases=[],
              started_utc=datetime.now(timezone.utc).isoformat(),
              pnr_started=False, board_accessed=False, remote_pushed=False, delivery_created=False)

def save():
    record['updated_utc'] = datetime.now(timezone.utc).isoformat()
    (work/'flow.json').write_text(json.dumps(record, indent=2)+'\n')

def run(name, command, cwd=root, timeout=1200):
    item = dict(name=name, command=list(map(str, command)), cwd=str(cwd),
                started_utc=datetime.now(timezone.utc).isoformat())
    record['phases'].append(item); record['phase'] = name; save()
    log = work/(name+'.log')
    with log.open('xb') as output:
        process = subprocess.Popen(item['command'], cwd=cwd, stdout=output, stderr=subprocess.STDOUT)
        item['pid'] = process.pid; save()
        try:
            code = process.wait(timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
            raise
    item.update(exit_code=code, log_sha256=sha(log), completed_utc=datetime.now(timezone.utc).isoformat())
    save()
    raw = log.read_bytes()
    text = raw.decode('utf-16' if raw.startswith(b'\xff\xfe') else 'utf-8-sig', errors='replace')
    assert code == 0, (name, text[-2500:])
    print('CPU80_HALF_PHASE_PASS '+name, flush=True)
    return text

ps = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File']
py = ['G:/py/ana/python.exe', '-X', 'utf8']
try:
    old = read(baseline/'pds/build_snapshot.json')
    allowed = {'config/clocks.json', 'linux/soc.dts', 'pds/soc.fdc', 'rtl/soc/soc_top.v',
               'scripts/coremark_fixed_bootloader.ps1', 'scripts/measure_coremark.ps1',
               'scripts/run_coremark_production_sim.ps1', 'sim/tb_cpu_integration.sv',
               'sw/bootloader/soc.h', 'linux/boot/soc.dtb', 'scripts/update_cpu_handoff.py',
               'scripts/build_fpga.ps1', 'scripts/build_cpu_ads_gate.ps1', 'artifacts/bootloader.build.json'}
    changed = {name for name, value in old['inputs'].items() if sha(root/name) != value}
    assert changed <= allowed, changed-allowed
    oldtop = (baseline/'rtl/soc/soc_top.v').read_text()
    newtop = (root/'rtl/soc/soc_top.v').read_text()
    assert oldtop.replace('parameter integer CPU_CLOCK_MODE = 5', 'parameter integer CPU_CLOCK_MODE = 4') == newtop
    assert '.HALF_OUTPUT(1)' in newtop
    record['retarget_delta_from_85'] = sorted(changed)
    record['baseline_run'] = old['run_id']
    record['baseline_snapshot_sha256'] = sha(baseline/'pds/build_snapshot.json')
    proofs = {'halfmac-correctness-04/result.json': 'MAC_HALF_OUTPUT_DIFFERENTIAL_PASS',
              'halfmac-s16-golden-02.json': 'HALF_S16_DOT_AND_SQUARE_INTEGER_GOLDEN_PASS_NOT_STA',
              'halfmac-soc-02/result.json': 'HALF_OUTPUT_DENSE_GATHER_DDR_CONV_ISOLATION_PASS_NOT_STA_OR_BOARD'}
    for name, status in proofs.items():
        result = read(previous/name); assert result['status'] == status
        if 'core_sha256' in result:
            assert result['core_sha256'] == sha(root/'rtl/mac_accel/MacAccelCore.v')
        for path, value in result.get('sources', result.get('source_sha256', {})).items():
            assert sha(root/path) == value, path
    record['unchanged_mac_correctness_proofs'] = {name: sha(previous/name) for name in proofs}
    run('clock-config', ps+[root/'scripts/check_clock_config.ps1', '-Root', root])
    run('clock-mutations', ps+[root/'scripts/test_cpu80_frac_clock.ps1', '-ReportPath', work/'clock-policy.json'])
    run('pll-waveform', py+[root/'scripts/test_cpu80_pll.py', '--fractional', '--wsl-distro', 'pikafish-verify',
        '--vendor-models', 'G:/fpga/PDS_2022.2-SP6.4/arch/vendor/pango/verilog/simulation', '--output', work/'pll'])
    # Attempt01 completed the full80MHz regression; only two host audit entry
    # selectors change. Revalidate every frozen input and retain its raw log.
    first = Path('G:/fpga/c80h1080p1')
    first_snapshot = read(first/'pds/build_snapshot.json')
    selector_delta = {p for p,h in first_snapshot['inputs'].items() if sha(root/p)!=h}
    assert selector_delta == {'scripts/build_fpga.ps1', 'scripts/build_cpu_ads_gate.ps1'}, selector_delta
    first_flow = read(work.parent/'attempt-01/flow.json')
    phase = next(x for x in first_flow['phases'] if x['name']=='full-regression')
    log = work.parent/'attempt-01/full-regression.log'; raw=log.read_bytes()
    assert phase['exit_code']==0 and sha(log)==phase['log_sha256'] and b'SOC_ALL_TESTS_PASS' in raw
    audit = read(work.parent/'standard-audit-01.json')
    assert audit['status']=='PASS' and audit['netlist_sha256']==sha(first/'pds/synthesize/soc_top_syn.vm')
    assert audit['frontend_cases']==85760 and audit['return_cases']==10240 and audit['pma_address_cases']==2144 and audit['rsmem_hint_cases']==17152
    record['full_regression_reuse'] = dict(log_sha256=sha(log), source_commit=first_flow['source_commit'],
        baseline_run=first_snapshot['run_id'], changed_host_inputs=sorted(selector_delta), standard_audit_sha256=sha(work.parent/'standard-audit-01.json'))
    run('selector-fixtures', py+[root/'scripts/test_half_pma_selection.py', '--output', work/'selector-fixtures.json'])
    run('build-flow-fixtures', py+[root/'scripts/test_synthesis_only.py'])
    # The full regression rebuilds firmware and validates its CPU-source binding.
    run('freeze-tracked', ['git', 'add', '-u'])
    run('freeze-new', ['git', 'add', 'scripts/run_cpu80_halfmac_flow.py',
                      'scripts/test_half_pma_selection.py', 'docs/CPU80_Half_MAC_Retarget_20261023.md', 'docs/validation/frequency-search/candidates/V2.1'])
    run('freeze-commit', ['git', 'commit', '-m', 'Freeze exact80MHz half-output MAC and 1080p PnR candidate after regression'])
    record['source_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root).decode().strip()
    run('stage', ps+[root/'scripts/stage_cpu_timing_candidate.ps1', '-SourceRoot', root, '-OutputRoot', native,
                    '-Divisor', '27', '-CpuClockSource', 'dedicated1080frac',
                    '-DtcPath', 'G:/fpga/performance_soc_voice_hw/build/dtc_proxy.cmd'])
    stage = read(native/'candidate-stage.json')
    for name, value in stage['prepared_inputs'].items():
        assert sha(root/name) == value, name
    assert stage['firmware_cpu_binding']['matches']
    record['stage_receipt_sha256'] = sha(native/'candidate-stage.json')
    record['status'] = 'CPU80_HALF_NATIVE_BUILD_RUNNING'; save()
    run('native-build', ps+[native/'scripts/build_fpga.ps1', '-UseExistingFirmware',
        '-PythonPath', 'G:/py/ana/python.exe', '-PdsTimeoutSeconds', '14400',
        '-CampaignLog', work/'pnr-history.json', '-AttemptPurpose', 'final'], cwd=native, timeout=15000)
    record['status'] = 'CPU80_HALF_NATIVE_GATES_PASS_BOARD_PENDING'
except BaseException:
    record['status'] = 'CPU80_HALF_FAILED_PRESERVED_NO_PROMOTION'
    record['error'] = traceback.format_exc()
    print(record['error'], flush=True)
finally:
    snapshot = read(native/'pds/build_snapshot.json') if (native/'pds/build_snapshot.json').is_file() else {}
    record['native_run_id'] = snapshot.get('run_id'); record['input_count'] = len(snapshot.get('inputs', {}))
    record['pnr_started'] = (work/'pnr-history.json').is_file()
    record['finished_utc'] = datetime.now(timezone.utc).isoformat(); save()
if record['status'].endswith('NO_PROMOTION'):
    raise SystemExit(1)
