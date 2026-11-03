"""Preserve this candidate's completed native result; never publish a release."""
from pathlib import Path
from datetime import datetime, timezone
import gzip
import hashlib
import json
import shutil

root = Path(__file__).resolve().parents[1]
native = Path('G:/i60pnr3')
evidence = root / 'docs/validation/integrated60-physical-20261024'
candidate = root / 'artifacts/integrated60_20261024'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
launch = read(native / 'physical-launch.json')
assert launch['status'] in ('ROUTED_FULL_STA_PASS_NOT_BOARD', 'ROUTED_STA_FAILED_NOT_BOARD', 'FAILED'), launch['status']
assert launch.get('pnr_complete'), 'Native route did not complete'
report_path = root / 'build/integrated-physical-03.json'
report = read(report_path)
assert report['run_id'] == launch['run_id'] == '866e820244ee4303a0295d68fe190076'
assert report['status'] == launch['status']
assert not evidence.exists() and not (candidate / 'manifest.json').exists(), 'Keep previous evidence immutable'
bit = native / 'pds/generate_bitstream/soc_top.sbit'
assert bit.is_file() and bit.stat().st_size > 0
assert sha(bit) == launch['reports']['generate_bitstream/soc_top.sbit']
strict_pass = launch['status'] == 'ROUTED_FULL_STA_PASS_NOT_BOARD'
review_path = root / 'build/integrated-reviewed-scope-03.json'
review_pass = False
if not strict_pass and review_path.exists():
    review = read(review_path)
    assert review['status'] == 'ROUTED_STA_AND_REVIEWED_PIXEL_SCOPE_PASS_NOT_BOARD'
    assert review['run_id'] == launch['run_id']
    assert review['original_flow_status'] == launch['status'] == 'FAILED'
    assert review['original_scope_error'] == launch['error'] == 'Native STA clock definition differs: pix_clk'
    assert review['original_frozen_receipt_unchanged'] and review['native_pds_operations_without_errors']
    for name, digest in review['inputs_sha256'].items():
        assert sha(Path(name)) == digest, name
    review_pass = True
passed = strict_pass or review_pass
if passed:
    assert not report['violations']
if strict_pass:
    proof = read(native / 'artifacts/build_evidence.json')
    assert proof['run_id'] == launch['run_id']
    assert proof['max_skew_verified'] and proof['timing_scope_verified']
    assert proof['timing'] == 'All Constraints Met'
evidence.mkdir(parents=True)
candidate.mkdir(parents=True, exist_ok=True)
shutil.copyfile(bit, candidate / bit.name)
assert sha(candidate / bit.name) == sha(bit)
files = {
    'physical-launch.json': native / 'physical-launch.json',
    'physical-summary.json': report_path,
    'build_snapshot.json': native / 'pds/build_snapshot.json',
    'pnr-history.json': native / 'pnr-history.json',
}
if strict_pass:
    files['build_evidence.json'] = native / 'artifacts/build_evidence.json'
    files['timing_summary.txt'] = native / 'artifacts/timing_summary.txt'
if review_pass:
    files['independent-reviewed-scope.json'] = review_path
    files['pixel-scope-mutation-tests.json'] = root / 'build/integrated-pixel-scope-01/result.json'
    files['original-controller.log'] = root / 'build/integrated-pnr-03.log'
    files['original-controller-exit.json'] = root / 'build/integrated-pnr-03.exit.json'
run_dir = native / 'pds/input-snapshots' / launch['run_id']
for name, source in {
    'preflight_gate.json': run_dir / 'preflight_gate.json',
    'cpu_ads_controls.json': native / 'artifacts/cpu_ads_controls.json',
    'gui1080_placement.json': native / 'artifacts/gui1080_placement.json',
    'cpu-sys-cdc-pre-route.json': run_dir / 'cpu-sys-cdc-ads.json',
    'cpu-sys-cdc-post-route.json': run_dir / 'cpu-sys-cdc-post-route.json',
}.items():
    files[name] = source
for name, source in files.items():
    shutil.copyfile(source, evidence / name)
    assert sha(source) == sha(evidence / name)
compressed = {}
for rel in ['report_timing/soc_top.rtr', 'report_timing/rtr.db', 'synthesize/soc_top.snr']:
    source = native / 'pds' / rel
    assert sha(source) == launch['reports'][rel]
    name = source.name + '.gz'
    (evidence / name).write_bytes(gzip.compress(source.read_bytes(), mtime=0))
    assert gzip.decompress((evidence / name).read_bytes()) == source.read_bytes()
    compressed[name] = {'source': source.as_posix(), 'uncompressed_sha256': sha(source)}
manifest = dict(
    status='INTEGRATED60_SBIT_GENERATED_' + ('FULL_STA_PASS_NOT_BOARD' if strict_pass else 'STA_REVIEW_PASS_ORIGINAL_FLOW_FAILED_NOT_BOARD' if review_pass else 'VALIDATION_FAILED_NOT_BOARD'),
    completed_utc=datetime.now(timezone.utc).isoformat(),
    run_id=launch['run_id'], native_root=native.as_posix(),
    hardware_implementation_commit='a9f69eaa4fcf5662308aa0c7abc3b02e3ddf2a88',
    physical_source_commit=launch['source_commit'],
    cpu_hz=60000000, sys_hz=49500000, display='1080p30',
    voice_model='voice_2 balanced24 included',
    picture_models=['board192', 'detector640', 'classifier32'],
    picture_weights='DEFERRED_BY_USER_INTERFACE_ONLY',
    bitstream={'path': bit.name, 'bytes': bit.stat().st_size, 'sha256': sha(bit)},
    physical_status=launch['status'], strict_original_flow_pass=strict_pass,
    independent_review_pass=review_pass, sta_pass=passed,
    sta_focus=report['focus'], violations=report['violations'],
    evidence_root=evidence.relative_to(root).as_posix(),
    evidence_sha256={p.name: sha(p) for p in evidence.iterdir()}, compressed_reports=compressed,
    runtime_inputs_manifest_sha256=sha(candidate / 'runtime-inputs/manifest.json'),
    collector_sha256=sha(Path(__file__)),
    board=False, sd=False, flash=False, pushed=False, formal_delivery=False,
    scope='Candidate bitstream and matched runtime inputs; not a complete bootable SD kit or board acceptance')
payload = json.dumps(manifest, indent=2) + '\n'
(candidate / 'manifest.json').write_text(payload, encoding='utf-8')
(evidence / 'summary.json').write_text(payload, encoding='utf-8')
print(json.dumps({'status': manifest['status'], 'bitstream': manifest['bitstream'], 'evidence': manifest['evidence_root']}))
