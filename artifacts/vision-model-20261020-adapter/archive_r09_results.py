"""Archive training-only r09 results and audit immutable inputs after all gates."""
import ast
import hashlib
import json
import shutil
import statistics
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BASE = REPO / 'build/picture-r09-20261021'
EVIDENCE = REPO / 'docs/validation/picture-r09-offline-20261021'


def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def write(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def normalized(rows, keys):
    return [{k: row[k] for k in keys} for row in rows]


def main():
    reports = {}
    for name in ('fp32', 'quantized-mac', 'quantized-control'):
        src = BASE / ('evaluation-' + name) / 'results'
        report = read(src / 'metrics_summary.json'); assert report['n_frames'] == 135
        dst = EVIDENCE / name; dst.mkdir(exist_ok=True)
        for filename in ('metrics_summary.json', 'per_frame.json', 'end_to_end_per_frame.json', 'inputs.json'):
            shutil.copyfile(src / filename, dst / filename)
        reports[name] = report
    delivered = next((BASE / 'delivery').glob('P0E-B*/evidence_det416_v2band_fp32'))
    fp_keys = ('frame', 'status', 'candidate_exact', 'usable_exact', 'can_use_as_candidate', 'candidate_fen', 'usable_fen', 'gt_fen')
    fp32_equal = normalized(read(delivered/'end_to_end_per_frame.json'), fp_keys) == normalized(read(EVIDENCE/'fp32/end_to_end_per_frame.json'), fp_keys)
    assert fp32_equal, 'FP32 delivered strict output mismatch'
    scoring_keys = ('frame', 'board_exact', 'errors')
    active_rows = read(EVIDENCE/'quantized-mac/per_frame.json')
    control_rows = read(EVIDENCE/'quantized-control/per_frame.json')
    scores_equal = normalized(active_rows, scoring_keys) == normalized(control_rows, scoring_keys)
    assert scores_equal, 'Reference-grid detection difference vs full/unfiltered control needs investigation'
    active_strict = read(EVIDENCE/'quantized-mac/end_to_end_per_frame.json')
    control_strict = read(EVIDENCE/'quantized-control/end_to_end_per_frame.json')
    strict_diffs = [dict(frame=a['frame'], working_status=a['status'], control_status=b['status'],
                         candidate_fen_equal=a['candidate_fen']==b['candidate_fen'], usable_fen_equal=a['usable_fen']==b['usable_fen'])
                    for a,b in zip(active_strict, control_strict) if any(a[k]!=b[k] for k in fp_keys)]
    diagnosis = dict(status='DIFFERENCE_CONFIRMED', fp32_vs_delivered_strict_outputs_equal=fp32_equal,
                     quantized_working_vs_full_unfiltered_reference_grid_equal=scores_equal,
                     quantized_working_vs_full_unfiltered_strict_differences=strict_diffs,
                     quantized_reference_errors=[r for r in active_rows if not r['board_exact']],
                     fp32_reference_errors=[r for r in read(EVIDENCE/'fp32/per_frame.json') if not r['board_exact']],
                     conclusion='131/135 is already present in unchanged full/unfiltered exact PTQ control; it is not caused by Scheme A or refinement B reference-grid scoring',
                     delivery_quantization_scope='37 development images, zero measured drop; not 135 test frames',
                     integer_133_target_met=False, weights_or_labels_changed=False, threshold_contract_changed=False)
    write(EVIDENCE/'quantized-gap.json', diagnosis)
    write(EVIDENCE/'M0.json', dict(status='UNACCEPTED', independent_test=False, production_ready=False,
          full_integer_pipeline=False, fp32=reports['fp32'], quantized_exact=reports['quantized-mac'],
          quantized_full_unfiltered_control=reports['quantized-control'], integer_133_target_met=False,
          historical_r08='r08 v1 exact 133/135 reference-grid, 120/135 strict; preserved with its combination identity'))
    for sub, name in (('layers','native-layers.json'), ('graphs','native-graphs.json')):
        src = BASE/'native-tests-r01'/sub/'result.json'
        assert read(src)['status']=='PASS'; shutil.copyfile(src,EVIDENCE/name)
    shutil.copyfile(BASE/'models-r01/native_manifest.json', EVIDENCE/'native-manifest.json')
    shutil.copyfile(BASE/'native-tests-r01/dump-manifest.json', EVIDENCE/'native-dump-manifest.json')
    candidate = next((BASE/'delivery').glob('P0E-B*/quantization_r09/candidate_r09_det416'))
    shutil.copyfile(candidate/'summary.json', EVIDENCE/'delivered-quantization-development.json')
    shutil.copyfile(BASE/'evaluation-quantized-mac/probe.json', EVIDENCE/'platform-probe.json')
    gates = read(EVIDENCE/'offline-gates-r01.json'); assert gates['status']=='PASS'
    for name in ('linux-host', 'rv32', 'formats-pixels'):
        shutil.copyfile(BASE/'offline-gates-r01'/(name+'.log'), EVIDENCE/(name+'.txt'))
    for name in ('elf-inspection.txt', 'compiler.txt', 'source-before.sha256', 'source-after.sha256'):
        shutil.copyfile(BASE/'offline-gates-r01/rv32'/name, EVIDENCE/('rv32-'+name))
    refinement = read(EVIDENCE/'refinement-B-r03.json'); assert refinement['vectors']==45 and refinement['status']=='PASS'
    replay = read(EVIDENCE/'native-replay-r02.json'); assert replay['frames']==135 and replay['status']=='PASS'
    assert read(EVIDENCE/'entrypoints.json')['status']=='PASS'
    budget = read(EVIDENCE/'training-budget.json')['scenarios']['det416_planA']
    write(EVIDENCE/'budget-scope.json', dict(status='PREDICTION_ONLY', model_busy_s=budget['total_busy_s'],
          total_busy_cycles=budget['total_busy_cycles'], frequency_hz=49500000, predicted_jobs=budget['total_jobs'],
          measured_device_jobs=None, measured_end_to_end_s=None, end_to_end_5s_passed=False,
          detector_scaling='(416/640)^2 area scaling of frozen baseline', classifier_ratio=.208,
          task2_scope='15-frame frozen640 + v1 exact sample; mean filtered batch 23.1333, not det416 evidence',
          native_416_replay_batches=replay['classifier_batches'], native_replay_batch_reduction=replay['batch_reduction'],
          native_replay_average_batch={k:v/135 for k,v in replay['classifier_batches'].items()},
          excluded='host preprocessing/non-MAC graph/refinement/scheduling/transfer/GUI; no board measurement',
          refinement_45_pc_median_ms={key:statistics.median(r[key] for r in refinement['vectors_detail']) for key in ('native_full_ms','native_B_ms')},
          pc_times_are_descriptive_only=True))
    # Recheck raw delivery and frozen inputs. No private frame hashes published.
    raw = BASE/'delivery'; manifest=read(raw/'manifest.json')
    assert sha(raw/'manifest.json')==read(EVIDENCE/'intake.json')['manifest_sha256']
    for name,item in manifest['files'].items():
        assert sha(raw/name)==item['sha256'] and (raw/name).stat().st_size==item['bytes']
    frozen=HERE.parent/'vision-model-20261020'; original=read(frozen/'manifest.json')
    for name,item in original['files'].items():
        assert sha(frozen/name)==(item if isinstance(item,str) else item['sha256'])
    r08=REPO/'build/picture-r08-20261021/delivery'
    r08_manifest=read(r08/'manifest.json')
    for name,item in r08_manifest['files'].items():
        assert sha(r08/name)==item['sha256']
    private_digest=sha(REPO/'build/picture-p21-native/live-sd-r01/frame.rgb565')
    assert any(private_digest in p.read_text(encoding='utf-8') for p in r08.rglob('*.json'))
    # Native numeric/transport kernels remain byte-identical to HEAD.
    unchanged = ['artifacts/vision-model-20261020-adapter/runtime/xq_int8_layer.c',
                 'artifacts/vision-model-20261020-adapter/runtime/xq_resident_matrix.c',
                 'linux/vision/xq_mac_linux.c','linux/mac_accel/pango_mac_uapi.h']
    for name in unchanged:
        assert subprocess.check_output(['git','show','HEAD:'+name],cwd=REPO)==(REPO/name).read_bytes()
    files = subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=REPO).decode().split('\0')
    source_hashes = {}
    for name in set(files)-{''}:
        p=REPO/name
        if p.is_file() and (p.suffix in ('.py','.c','.h','.sh','.ps1','.json') and
                            (name.startswith(HERE.relative_to(REPO).as_posix()+'/') or name in ('linux/vision/xq_roi.c','linux/vision/test_roi.c','scripts/test_picture_roi_cv.py'))):
            source_hashes[name]=sha(p)
        if p.is_file() and (name.startswith('docs/validation/picture-r09-offline-20261021/') or name.startswith('docs/validation/picture-r08-offline-20261021/')):
            assert private_digest.encode() not in p.read_bytes(), 'Private live identity leaked into published evidence'
        if p.suffix=='.py' and p.is_file() and name.startswith(HERE.relative_to(REPO).as_posix()+'/'):
            ast.parse(p.read_text(encoding='utf-8'))
    result = dict(status='OFFLINE_ENGINEERING_COMPLETE_WITH_ACCURACY_GAP', hardware_used=False,
                  raw_r09_files_verified=len(manifest['files']), raw_r08_files_verified=len(r08_manifest['files']),
                  frozen_r2_files_verified=len(original['files']), frozen_and_private_live_identities_unchanged=True,
                  integer_kernels_and_driver_unchanged=True, private_live_identity_absent_from_published_evidence=True,
                  model_manifest_sha256=sha(BASE/'models-r01/native_manifest.json'),
                  source_hashes=source_hashes, production_ready=False, full_integer_pipeline=False,
                  m0_accepted=False, integer_133_target_met=False, full_suite_passed=False,
                  pending=['quantized 133/135 parity / training followup','P0-4 fresh independent acceptance',
                           'PN01 update and CRC / actual driver jobs / <=5s end-to-end / 640 board control',
                           'piece_fit/manual/moved-board/M5/three games and speech board acceptance',
                           'restore required GCC LTO toolchain and full regression','SCCB NACK root cause'],
                  no_push_or_tag=True, no_hardware_or_flash_writes=True)
    write(EVIDENCE/'closeout.json',result)
    print('R09_OFFLINE_ENGINEERING_ARCHIVED_WITH_ACCURACY_GAP',flush=True)


if __name__=='__main__':
    main()
