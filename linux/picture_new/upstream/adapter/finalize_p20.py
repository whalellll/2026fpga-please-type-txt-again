"""Bind the completed P20 replay to immutable inputs; never accept M0 here."""
import collections
import csv
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = REPO / 'docs/validation/picture-p20-combined-20261020'
R2 = HERE.parent / 'vision-model-20261020'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(name, data):
    with (OUT / name).open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    sys.path.insert(0, str(REPO / 'scripts'))
    from verify_picture_model import verify
    official = verify(R2, adapter=HERE)
    write('official-verifier.json', official)
    command = [sys.executable, '-B', str(R2 / 'tools/verify_package.py'), '--root', str(R2)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=True)
    write('package-verifier.json', dict(command=command, exit_code=result.returncode,
                                      result=json.loads(result.stdout), stderr=result.stderr))

    intake = read(OUT / 'intake.json')
    immutable = {}
    for name, package in intake.items():
        root = Path(package['destination'])
        expected = package['files']
        actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
        assert actual == set(expected), (name, 'tree changed')
        for rel, identity in expected.items():
            p = root / rel
            assert p.stat().st_size == identity['bytes'] and sha(p) == identity['sha256'], (name, rel)
        assert sha(Path(package['archive'])) == package['archive_sha256']
        immutable[name] = dict(files_verified=len(actual), archive_sha256=package['archive_sha256'],
                               manifest_sha256=sha(root / 'manifest.json'), unchanged=True)
    write('immutable-recheck.json', immutable)

    corrections = read(HERE / 'dataset_corrections.json')['corrections']
    rows = read(OUT / 'fp32/per_frame.json')
    quant = read(OUT / 'quantized-mac/per_frame.json')
    assert [r['errors'] for r in rows] == [r['errors'] for r in quant]
    cases = []
    counts = collections.Counter()
    for row in rows:
        for error in row['errors']:
            assert error['type'] == 'wrong_class'
            matches = [c for c in corrections if c['frame'] == row['frame'] and c['type'] == 'class_fixed'
                       and c['corrected']['grid'] == error['cell']]
            assert len(matches) == 1
            correction = matches[0]
            assert error['gt'] == correction['corrected']['label']
            assert error['pred'] == correction['original']['label']
            counts[error['gt'] + ' -> ' + error['pred']] += 1
            cases.append(dict(frame=row['frame'], file=error['cell'][0], rank=error['cell'][1],
                              expected=error['gt'], actual_fp32=error['pred'],
                              actual_quantized_mac=error['pred'],
                              matches_original_uncorrected_label=True,
                              correction=correction))
    assert len(cases) == 77 and sum(not r['board_exact'] for r in rows) == 77
    write('classification-correction-mismatches.json', dict(count=77, counts=dict(counts), cases=cases))
    with (OUT / 'classification-correction-mismatches.csv').open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=[k for k in cases[0] if k != 'correction'])
        writer.writeheader()
        writer.writerows({k:v for k,v in row.items() if k != 'correction'} for row in cases)

    for original, name in [('p20-original-requirements-dry-run.log', 'original-requirements-conflict.txt'),
                           ('p20-fp32-evaluation.log', 'fp32-evaluation.stdout.txt'),
                           ('p20-quantized-mac-evaluation.log', 'quantized-mac-evaluation.stdout.txt')]:
        assert not (OUT / name).exists()
        shutil.copyfile(REPO / 'build' / original, OUT / name)
    shutil.copyfile(HERE / 'requirements-pc-reference.txt', OUT / 'requirements-pc-reference.txt')
    metrics = {name:read(OUT / name / 'metrics_summary.json') for name in ('fp32','quantized-mac')}
    assert all(not r['requested_numeric_gate_pass'] and not r['m0_accepted'] for r in metrics.values())
    graph = read(R2 / 'golden/quantization/candidate_v1/integer_graph.json')
    training = read(R2 / 'training_manifest.json')
    assert training['independent_test'] is False
    write('M0.json', dict(
        schema_version=1, evaluated_utc=datetime.now(timezone.utc).isoformat(),
        branch='Picture_new', base_commit='86d19666bfd0c7c9e655b15b03fdeeb4713e9cc8',
        scheme='board-detect-v2', format_profile=official['format_profile'],
        status='FAIL', m0_accepted=False, main_chain_switch_allowed=False,
        immutable_packages=immutable, adapter_manifest_sha256=sha(HERE / 'adapter_manifest.json'),
        model_sha256=graph['model_SHA256'], protocol=dict(frames='IMG00908..IMG01042', n=135,
            evaluator='R1 tools/test_eval_t1.py (unchanged copy, scoring API)',
            inference='R2 golden/recognize.py model factory/public predict API; CLI equivalence checked',
            corrections='R1 report/dataset_corrections.json: all 81 entries',
            conf=.05, iou=.5, class_aware_nms=.6, reference_geometry_used_for_inference=False),
        metrics=metrics, error_summary=dict(count=77, by_class=dict(counts),
            all_match_R1_class_corrections=True, training_root_cause_established=False),
        production_ready=False, independent_test=False,
        independence_reason=training['test_history'],
        strict_uncertain_frames=['IMG00862','IMG00863','IMG00864'],
        full_integer_pipeline=False,
        operator_partition=dict(
            MAC='All 80 Conv/Linear: S8 x S8, INT32 accumulation; existing dense DDR-DMA tiling planned, not deployed',
            numeric_tail='Bias once, per-channel shift ties-to-even, S16 saturation, exported S8 LUT; Identity heads retain S16',
            host_non_MAC=graph['protocol']['non_MAC_host'],
            host_other=['RGB565 preprocessing/resize', 'pooling', 'line_refinement',
                        'homography/assignment/FEN', 'automatic_orientation'],
            RV32_float='Current RV32IMA has no F extension; host FP32 needs software implementation and measured timing',
            RV32_implemented=False, device_bit_exact=False),
        corner_truth=dict(source='1042 AI-reviewed labels', human_spot_check_receipt=None,
                          independent_metrology=False),
        historical_123_of_125_is_independent=False,
        fallback=dict(R1_C_reference_host_cases_passed=30, enabled=False,
                      RV32_port_and_device_comparison_pending=True),
        host_C_integer_cases_passed=323, golden_dump_files_verified=80,
        environment=dict(python='/home/dogandlamb/picture-p20-20261020/venv/bin/python',
                         version='3.10.12', torch='2.5.1+cpu', torchvision='0.20.1+cpu',
                         original_requirements_installable=False,
                         deviation='Omit unused optional SAHI 0.12.8; pin both OpenCV packages to 4.10.0.84',
                         pip_check_pass=True, freeze='pip-freeze.txt', picture_tools_environment_unchanged=True),
        pending=['Resolve classifier/correction inconsistency without editing received artifacts',
                 'Deliver genuinely independent evaluation and human corner spot-check record',
                 'Resolve original requirements dependency conflict',
                 'P21 three-model RV32 runtime, line refinement/orientation ports and 80-layer device comparison',
                 'P22 fallback activation and full UI switch', 'P23 complete games/moved-board/latency/voice acceptance',
                 'P24 demonstration/SD-rootfs contract and final archival'],
        evidence_sha256={p.relative_to(OUT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file()},
        adapter_code_sha256={p.relative_to(HERE).as_posix():sha(p) for p in sorted(HERE.rglob('*.py'))
                             if 'validation' not in p.parts}))
    print('P20_FINALIZED M0=FAIL board_exact=58/135 strict_exact=57/135 both_backends')


if __name__ == '__main__':
    main()
