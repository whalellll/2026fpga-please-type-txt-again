"""Register r09 and reconstruct its omitted release copy under build/ only."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delivery', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    delivery, out = args.delivery.resolve(), args.out.resolve()
    assert out.is_relative_to(REPO / 'build') and not out.exists()
    intake = json.loads((args.evidence / 'intake.json').read_text(encoding='utf-8'))
    assert sha(delivery / 'manifest.json') == intake['manifest_sha256']
    manifest = json.loads((delivery / 'manifest.json').read_text(encoding='utf-8'))
    for name, item in manifest['files'].items():
        assert sha(delivery / name) == item['sha256'] and (delivery / name).stat().st_size == item['bytes']
    frozen = HERE.parent / 'vision-model-20261020'
    fm = json.loads((frozen / 'manifest.json').read_text(encoding='utf-8'))
    for name, item in fm['files'].items():
        assert sha(frozen / name) == (item if isinstance(item, str) else item['sha256'])
    det = next(delivery.glob('P0E-B*/det416_run/weights/best.pt'))
    candidate = next(delivery.glob('P0E-B*/quantization_r09/candidate_r09_det416'))
    cls = next((REPO / 'build/picture-r08-20261021/delivery').glob('P0-1*/training/v2_run_band/best.pt'))
    graph = json.loads((candidate / 'integer_graph.json').read_text(encoding='utf-8'))
    assert sha(det).startswith('00ee3784')
    assert graph['model_SHA256'] == dict(board=sha(frozen / 'golden/software/weights/board.pt'),
                                        detector=sha(det), classifier=sha(cls))
    before = json.loads((candidate / 'source_hashes_before.json').read_text(encoding='utf-8'))
    after = json.loads((candidate / 'source_hashes_after.json').read_text(encoding='utf-8'))
    assert before == after
    # The live identity never enters the published receipt.
    live = REPO / 'build/picture-p21-native/live-sd-r01/frame.rgb565'
    old_live_summary = next((REPO / 'build/picture-r08-20261021/delivery').rglob('p01_live_v2_band_final.json'))
    assert sha(live) in ''.join(p.read_text(encoding='utf-8') for p in (REPO / 'build/picture-r08-20261021/delivery').rglob('*.json'))
    assert json.loads(old_live_summary.read_text(encoding='utf-8'))['summary']['v2_sha'] == sha(cls)
    software = out / 'r09_release_416/software'
    shutil.copytree(frozen / 'golden/software', software,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copyfile(det, software / 'weights/detector.pt')
    shutil.copyfile(cls, software / 'weights/classifier.pt')
    runtime = software / 'runtime/live_two_stage.py'
    original = runtime.read_text(encoding='utf-8')
    assert original.count('input_size=640') == 1 and original.count('input_size in [320,640]') == 1
    changed = original.replace('input_size=640', 'input_size=416').replace('input_size in [320,640]', 'input_size in [320,416,640]')
    runtime.write_text(changed, encoding='utf-8', newline='\n')
    sm = json.loads((software / 'manifest.json').read_text(encoding='utf-8'))
    for name in ('detector', 'classifier'):
        sm['models'][name]['sha256'] = sha(software / sm['models'][name]['path'])
    for name in sm['files']:
        sm['files'][name] = sha(software / name)
    sm['candidate_lineage'] = 'r09 det416 best@39 + r08 v2-band + frozen board; adapter reconstruction, not a delivered release directory'
    write(software / 'manifest.json', sm)
    reg = dict(schema_version=1, candidate='det416-v2-band-r09', acceptance_status='待 P0-4 独立验收',
               selected_for_work=True, production_ready=False, full_integer_pipeline=False,
               detector_epoch=39, detector_input=416, model_sha256=graph['model_SHA256'],
               local_release=software.relative_to(REPO).as_posix(),
               local_quantized_candidate=candidate.relative_to(REPO).as_posix(),
               source_manifest_sha256=intake['manifest_sha256'],
               release_reconstructed=True, refinement='B_trials80_bbox', candidate_filter=True,
               numeric_reference='r08-exact-int64', rollback='frozen640-v1 or r08 v2-band; original assets retained')
    write(HERE / 'candidates/det416-r09/registration.json', reg)
    write(HERE / 'candidates/det320-r09-negative/registration.json', dict(schema_version=1,
          candidate='det320-r09-negative', selected_for_work=False, deployable=False,
          reason='Strict usable 99/135=73.3%, below accepted working combination',
          model_sha256=sha(next(delivery.glob('P0E-B*/det320_run_v2/weights/best.pt'))),
          first_round_strict_usable='75/135=55.6%', second_round_strict_usable='99/135=73.3%',
          production_ready=False))
    write(HERE / 'working_combination.json', dict(schema_version=1, selected='det416-v2-band-r09',
          registration='candidates/det416-r09/registration.json', detector_input=416,
          candidate_filter=True, refinement='B_trials80_bbox', reference='exact-int64',
          rollback_detector_input=640, production_ready=False, board_deployed=False))
    for pattern, target in [('pe_budget_r09.json', 'training-budget.json'),
                            ('task3_refine_downgrade.json', 'training-refinement.json'),
                            ('task2_batch_filter_quantized.json', 'training-filter.json')]:
        shutil.copyfile(next(delivery.rglob(pattern)), args.evidence / target)
    for suffix in ('det416_v2band_fp32', 'det416_v1cls_fp32', 'det320v2_v2band_fp32', 'det320_v2band_fp32'):
        path = next(delivery.glob('P0E-B*/evidence_' + suffix))
        write(args.evidence / ('delivered-' + suffix + '.json'), json.loads((path / 'metrics_summary.json').read_text(encoding='utf-8')))
    write(args.evidence / 'identity-and-adaptations.json', dict(status='PASS', frozen_r2_files_verified=len(fm['files']),
          frozen_models_unchanged=True, v2_band_unchanged=True, private_live_frame_identity_unchanged=True,
          source_hashes_before_after_equal=True, release_directory_missing_in_zip=True,
          release_reconstructed_from_verified_inputs=True,
          textual_discrepancies=['run_det416_regression docstring/print and detector_input_size annotation retain 320; actual input_size assignment is 416',
                                'requantize_det416 lineage mentions 320; graph/checkpoint detector SHA is authoritative'],
          adapted_file='runtime/live_two_stage.py', adaptation='default input_size=416; whitelist 416; copied release manifest hashes refreshed',
          candidate=reg, hardware_used=False))
    print('R09_REGISTERED_AND_RELEASE_RECONSTRUCTED', flush=True)


if __name__ == '__main__':
    main()
