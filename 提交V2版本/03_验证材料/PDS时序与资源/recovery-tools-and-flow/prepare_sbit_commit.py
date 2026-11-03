"""Export the newly generated candidate and compact native evidence for review."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, shutil

B = Path(__file__).resolve().parent
S = B / 'source'
P = S / 'pds'
E = S / 'docs/validation/cpu125-cm60-small-20261102/routed-sbit'
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
    with Path(p).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()
def dump(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

assert not E.exists(), 'Keep previous evidence; use a new export directory'
q = read(B / 'status.json')
f = read(B / 'frozen-inputs.json')
flow = read(B / 'finish-native-flow02.json')
sta = read(B / 'final-review-02/result.json')
physical = read(B / 'physical-verification-01/result.json')
bit = read(B / 'bitstream-01/result.json')
assert q['final_sta_pass'] and q['new_bitstream_sta_pass']
assert flow['status'] == 'CPU125_CM60_ZERO_HARDWARE_DELTA_NATIVE_STA_PHYSICAL_BITSTREAM_PASS_BOARD_PENDING'
assert len(flow['steps']) == 5 and all(x['exit_code'] == 0 for x in flow['steps'])
assert sta['final_sta_pass'] and not sta['violating_summary_rows'] and not sta['exception_violations']
assert sta['pnr_attempt'] == 'pnr-02'
assert physical['final_sta_pass'] and physical['slots_verified'] == 30 and physical['pins_verified'] == 165
assert physical['priority_nets_verified'] == 39 and physical['max_skew_rows_verified'] == 20
assert bit['status'] == 'LOCAL_STA_PASSING_CANDIDATE_BITSTREAM_GENERATED_NOT_BOARD_OR_DELIVERY'
assert bit['pnr_adf_sha256'] == physical['pnr_adf_sha256']
assert sha(P / 'prj_tasks/pnr_1/place_route/soc_top_pnr.adf') == bit['pnr_adf_sha256']
for group in ('native_inputs_sha256', 'verification_inputs_sha256'):
    for name, digest in f[group].items():
        assert sha(S / name) == digest, name
        assert not name.startswith('docs/validation/cpu125-cm60-small-20261102/routed-sbit/')
changed = ['artifacts/soc_top.sbit', 'artifacts/soc_v2_top.sbit', 'artifacts/soc_top.bin',
           'README.md', 'docs/CPU125_CM60_Preserved_20261102.md',
           'docs/CPU125_CoreMark60_Small_20261102.md']
assert not set(changed) & (set(f['native_inputs_sha256']) | set(f['verification_inputs_sha256']))
native_bits = [Path(n) for n in bit['artifact_sha256'] if n.endswith('.sbit')]
native_bins = [Path(n) for n in bit['artifact_sha256'] if n.endswith('.bin')]
assert len(native_bits) == len(native_bins) == 1
assert sha(native_bits[0]) != 'bf31b974d060a462654769e2896bcbb33fe596c9d59c13357a8ce27fe7fc8bbf', 'Inherited CPU120 bitstream is not this candidate'
for name, digest in bit['artifact_sha256'].items():
    path = Path(name)
    assert path.resolve().is_relative_to(B.resolve())
    assert sha(path) == digest and path.stat().st_size > 1000000
    assert datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) >= datetime.fromisoformat(bit['started_utc'])

E.mkdir()
copied = {}
def copy(src, dest):
    assert src.is_file() and not dest.exists(), (src, dest)
    assert src.resolve().is_relative_to(B.resolve())
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    assert sha(src) == sha(dest)
    copied[str(dest.relative_to(S)).replace('\\', '/')] = sha(dest)

for src, target in [(native_bits[0], 'artifacts/soc_top.sbit'),
                    (native_bits[0], 'artifacts/soc_v2_top.sbit'),
                    (native_bins[0], 'artifacts/soc_top.bin')]:
    # Existing tracked CPU120 files remain in Git history; this is an explicit replacement.
    dest = S / target
    shutil.copyfile(src, dest)
    assert sha(dest) == bit['artifact_sha256'][str(src)]

for group, files in {
    'pnr-02': ['input-binding.json', 'launch-memory-receipt.json', 'owned-affinity.json', 'result.json'],
    'final-review-02': ['result.json', 'summary-rows.json'],
    'physical-readback-01': ['result.json', 'csr-final.pcf', 'tage-final.pcf', 'io-final.pcf', 'stdout.log', 'stderr.log'],
    'physical-verification-01': ['result.json'],
    'bitstream-01': ['input-binding.json', 'response.json', 'result.json'],
    'pnr-preflight-05': ['result.json', 'native-priority.rcf', 'native-placement.pcf'],
}.items():
    for name in files:
        copy(B / group / name, E / group / name)
for name in ['soc_top.rtr', 'soc_top_exception.rtr']:
    copy(P / 'prj_tasks/pnr_1/report_timing' / name, E / 'native-report' / name)
for corner in ['slow', 'fast']:
    name = 'report_timing_' + corner + '_path_max_skew.db'
    copy(P / 'prj_tasks/pnr_1/report_timing/report_db' / name, E / 'native-report' / name)
for name in ['run_place.log', 'run_route.log', 'run_route_optimize.log']:
    copy(P / 'prj_tasks/pnr_1/place_route' / name, E / 'native-report' / name)
for name in ['resume_native.py', 'run_pnr_compiler_only.py', 'collect_final_attempt02.py',
             'export_physical.py', 'verify_physical.py', 'generate_candidate_bitstream.py',
             'finish-native-flow02.json', 'prepare_sbit_commit.py']:
    copy(B / name, E / 'recovery-tools-and-flow' / name)
copy(P / 'build_snapshot.json', E / 'build_snapshot.json')

artifacts = {name: sha(S / name) for name in [
    'artifacts/soc_top.sbit', 'artifacts/soc_v2_top.sbit', 'artifacts/soc_top.bin',
    'artifacts/bootloader.bin', 'artifacts/bootloader.build.json', 'artifacts/bootrom.hex',
    'rtl/cpu/CoreTop.sv', 'rtl/cpu/source.json']}
manifest = dict(
    status='CPU125_CM60_ROUTED_ALL_CORNER_STA_PHYSICAL_BITSTREAM_PASS_BOARD_PENDING',
    source_commit=f['source_commit'], cpu_source_commit=f['cpu_source_commit'],
    implementation_commit='a6e0009b', native_run=q['native_run'], pnr_attempt='pnr-02',
    tool_version=sta['tool_version'], cpu_hz=125000000, sys_hz=49500000,
    compiler_profile='cm60-unroll2-lto-branch1', cpu_period_ns=7.992, cdc_limit_ns=7.192,
    cpu_timing=sta['cpu_timing'], final_sta_pass=True, physical_readback_pass=True,
    resources=read(B / 'native-identity-03/result.json')['resources']['candidate'],
    hardware_resource_delta=dict(lut=0, ff=0, lutram=0, drm=0, apm=0),
    short_diagnostic_coremark_per_mhz=dict(performance=6.031419124381113, validation=6.011920910447731),
    diagnostic_iterations=100, formal_board_coremark=False,
    pnr_adf_sha256=bit['pnr_adf_sha256'], artifact_sha256=artifacts,
    evidence_root='docs/validation/cpu125-cm60-small-20261102/routed-sbit',
    branch='candidate/cpu125-coremark60-20261102-01',
    authorization='2026-11-02: 推送到独立分支; 生成sbit并提交',
    board_tested=False, board_deferred_by_user=True, main_promoted=False, formal_delivery=False,
    evidence_scope='Fresh full routed STA and physical readback for this boot ROM; not board acceptance. Historical CPU120 delivery evidence and generic old reports retain their original identities. Use the current manifest and routed-sbit reports for this candidate.',
    recorded_utc=datetime.now(timezone.utc).isoformat())
dump(S / 'artifacts/CPU125_CM60_BITSTREAM.json', manifest)
copied['artifacts/CPU125_CM60_BITSTREAM.json'] = sha(S / 'artifacts/CPU125_CM60_BITSTREAM.json')
dump(E / 'evidence-index.json', dict(
    status='EXACT_COPIED_NATIVE_REPORTS_AND_NEW_BITSTREAM_EXPORT_PASS_BOARD_PENDING',
    source_commit=f['source_commit'], native_run=q['native_run'],
    artifact_sha256=artifacts, files_sha256=copied, board_tested=False,
    formal_delivery=False, recorded_utc=datetime.now(timezone.utc).isoformat()))

cpu = {(x['check'], x['corner']): x['wns_ns'] for x in sta['cpu_timing']}
note = f'''# CPU125/CoreMark candidate sbit, 2026-11-02

Fresh PDS2025.2 routing, all-corner STA and physical readback pass for the
new boot ROM. CPU slow setup/hold: +{cpu['Setup', 'Slow']:.3f}/+{cpu['Hold', 'Slow']:.3f}ns;
fast setup/hold: +{cpu['Setup', 'Fast']:.3f}/+{cpu['Hold', 'Fast']:.3f}ns.
Strict CPU7.992ns, SYS20.202ns and CDC7.192ns constraints are unchanged.
All summary and non-false-path exception checks pass. The actual final database
preserves30 CSR placements,165 pins,39 priority nets and20 max-skew path checks.

`artifacts/soc_top.sbit` and `artifacts/soc_v2_top.sbit` now contain this new
CPU125 candidate, replacing the inherited CPU120 aliases on this branch.
SHA256: `{artifacts['artifacts/soc_top.sbit']}`.
The matching native BIN is `artifacts/soc_top.bin`.

Implementation freeze `{f['source_commit']}`, CPU `{f['cpu_source_commit']}`,
native run `{q['native_run']}`, attempt `pnr-02`. No CPU/ISA/hardware changes:
all five synthesis resource deltas are zero. Compiler-only100-iteration RTL
diagnostics reach6.031419/6.011921 CoreMark/MHz; these short runs do not replace
formal-duration board measurements.

The user requested generation and commit to the existing independent branch.
Board connection remains deferred. CoreMark3+1, official model/concurrent tests
and direct SD boot remain pending; there is no main promotion or formal delivery.
No JTAG/UART/SD/Flash operation has occurred.

Current binding: [bitstream manifest](../artifacts/CPU125_CM60_BITSTREAM.json).
Raw final reports and compact proof receipts:
[`routed-sbit/`](validation/cpu125-cm60-small-20261102/routed-sbit/).
Previous preservation and stopped-wait records remain historical evidence.
Existing `docs/CPU_Frequency_Handoff.md` remains an immutable frozen verification
input; this note and the workspace root handoff record the latest state.
'''
(S / 'docs/CPU125_CM60_Sbit_20261102.md').write_text(note, encoding='utf-8')
for name in ['docs/CPU125_CM60_Preserved_20261102.md', 'docs/CPU125_CoreMark60_Small_20261102.md']:
    path = S / name
    text = path.read_text(encoding='utf-8')
    path.write_text('> Historical state below. Fresh routed STA/physical/bitstream now pass; board remains pending. '
                    'See [current sbit and evidence](CPU125_CM60_Sbit_20261102.md).\n\n' + text, encoding='utf-8')
path = S / 'README.md'
text = path.read_text(encoding='utf-8')
start = text.index('New routing/STA is pending')
end = text.index('\n\nSee [implementation', start)
text = text[:start] + ('Fresh routing, all-corner STA and actual physical readback now pass.\n'
    'The new CPU125 sbit is committed on the independent candidate branch;\n'
    'board connection remains deferred and board acceptance is pending.\n'
    '[New sbit, timing and hashes](docs/CPU125_CM60_Sbit_20261102.md).') + text[end:]
path.write_text(text, encoding='utf-8')
for group in ('native_inputs_sha256', 'verification_inputs_sha256'):
    for name, digest in f[group].items():
        assert sha(S / name) == digest, name
dump(B / 'sbit-local-export.json', dict(status=manifest['status'], artifact_sha256=artifacts,
    evidence_index_sha256=sha(E / 'evidence-index.json'),
    files_to_stage=changed + ['artifacts/CPU125_CM60_BITSTREAM.json', 'docs/CPU125_CM60_Sbit_20261102.md', str(E.relative_to(S)).replace('\\', '/')]))
print(manifest['status'])
