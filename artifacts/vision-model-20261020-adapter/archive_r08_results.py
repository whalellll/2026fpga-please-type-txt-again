"""Archive exact evaluation and PC replay results without live payloads."""
import argparse
import hashlib
import json
import re
import shutil
import statistics
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
    parser.add_argument('--evaluation', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--delivery', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    exact = args.evaluation / 'exact'
    metric = json.loads((exact / 'metrics_summary.json').read_text(encoding='utf-8'))
    assert metric['n_frames'] == 135 and metric['integer_oracle'] == 'r08-exact-int64'
    assert metric['end_to_end']['strict_usable_exact'] == 120
    assert metric['end_to_end']['status_counts'] == dict(candidate_board=133, cell_conflict=1, orientation_unknown=1)
    strict = json.loads((exact / 'end_to_end_per_frame.json').read_text(encoding='utf-8'))
    delivered = json.loads(next(args.delivery.glob('P0-3*/evidence_exact*/end_to_end_per_frame.json')).read_text(encoding='utf-8'))
    for left, right in zip(strict, delivered, strict=True):
        assert all(left[key] == right[key] for key in ('frame', 'status', 'usable_exact', 'candidate_exact', 'usable_fen', 'candidate_fen'))
    assert [r['frame'] for r in strict if r['status'] == 'cell_conflict'] == ['IMG00970']
    assert [r['frame'] for r in strict if r['status'] == 'orientation_unknown'] == ['IMG00993']
    for name in ('metrics_summary.json', 'per_frame.json', 'end_to_end_per_frame.json', 'inputs.json'):
        target = args.evidence / 'exact-pc-rerun' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(exact / name, target)
    shutil.copyfile(args.evaluation / 'probe.json', args.evidence / 'platform-probe.json')
    write(args.evidence / 'exact-pc-rerun/prediction-hashes.json',
          {p.name: sha(p) for p in sorted((exact / 'predictions').glob('*.json'))})
    write(args.evidence / 'M0.json', dict(schema_version=1, m0_accepted=False, independent_test=False,
          production_ready=False, full_integer_pipeline=False,
          current_pc_reference='r08-exact-int64', numeric_pc_gate_passed=metric['requested_numeric_gate_pass'],
          whole_board_exact=metric['whole_board_exact'], strict_usable=dict(correct=120, total=135, rate=120 / 135),
          status_counts=metric['end_to_end']['status_counts'], receiver_matches_training_r08=True,
          history=dict(path='docs/validation/picture-p20-original-labels-20261020-r03/M0.json',
                       original_noisy_int_mm_strict_correct=77, total=135, rate=77 / 135,
                       percent=100 * 77 / 135, golden=False, original_evidence_preserved=True),
          conflict_separation=dict(original_conflicts=54, noise_only=53, exact_conflicts=1,
                                   conflict_training_frame='IMG00970', orientation_unknown_training_frame='IMG00993'),
          candidate_v2_band='待新隔离局独立验收', p0_1_resolved=False,
          live_playable=False, hardware_validation='pending equipment return'))
    runtime = json.loads(args.runtime.read_text(encoding='utf-8'))
    assert runtime['status'] == 'PASS' and runtime['frame_count'] == 135 and runtime['packet_byte_identical']
    rows = runtime['frames']
    stages = ('board_ms', 'detector_ms', 'classifier_ms', 'refine_ms', 'assign_ms', 'total_ms')
    before = sum(row['before']['classifier_batch'] for row in rows)
    after = sum(row['after']['classifier_batch'] for row in rows)
    historical = REPO / 'docs/validation/picture-p21-runtime-20261020/native-device-replay.log.txt'
    r07 = dict(re.findall(r'(\w+)=(\d+)', historical.read_text(encoding='utf-8')))
    write(args.evidence / 'latency-offline.json', dict(status='PASS',
          scope='PC native A/B benchmark; not RV32, live accuracy, clean board P50/P95 or 5-second acceptance',
          variant_order='alternating before/after by training frame',
          concurrent_work='exact PC evaluation and isolated functional suites; PC timings are descriptive',
          batch=dict(before=before, after=after, retained_ratio=after / before, reduction_percent=100 * (1 - after / before)),
          examples=[row for row in rows if row['frame'] in ('IMG00908', 'IMG00917')],
          current_pc_median_ms={variant: {stage: statistics.median(row[variant][stage] for row in rows)
                                      for stage in stages} for variant in ('before', 'after')},
          r07_device_reference_ms={stage: int(r07[stage]) for stage in stages},
          r07_device_receipt_sha256=sha(historical),
          r07_and_pc_wall_times_directly_comparable=False,
          graph_and_driver_numeric_kernels_modified=False, board_validation='pending'))
    print('R08_EXACT_MATCHES_DELIVERY_135 NATIVE_FILTER_EQUIVALENT_135', flush=True)


if __name__ == '__main__':
    main()
