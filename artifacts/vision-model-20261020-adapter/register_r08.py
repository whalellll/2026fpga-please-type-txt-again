"""Register the isolated candidate and archive redacted/training-only evidence."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delivery', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    r = args.delivery.resolve()
    manifest = json.loads((r / 'manifest.json').read_text(encoding='utf-8'))
    # Recheck extracted inputs, including private evidence, without publishing it.
    for name, identity in manifest['files'].items():
        path = r / name
        assert path.stat().st_size == identity['bytes'] and sha(path) == identity['sha256'], name
    g = HERE.parent / 'vision-model-20261020'
    frozen = json.loads((g / 'manifest.json').read_text(encoding='utf-8'))
    assert frozen['release_version'] == '3.0.0-contract'
    for name, identity in frozen['files'].items():
        expected = identity if isinstance(identity, str) else identity['sha256']
        assert sha(g / name) == expected, name
    live = json.loads(next(r.rglob('p01_live_v2_band_final.json')).read_text(encoding='utf-8'))
    v1 = sha(g / 'golden/software/weights/classifier.pt')
    assert v1 == live['summary']['v1_sha']
    candidate = next(r.glob('P0-1*/training/v2_run_band/best.pt'))
    assert sha(candidate) == live['summary']['v2_sha'] and sha(candidate) != v1
    # Compare the private frame identity to hash occurrences in the verified r08
    # analysis. Never put its path, hash or result payload into tracked receipts.
    capture = REPO / 'build/picture-p21-native/live-sd-r01/frame.rgb565'
    digest = sha(capture)
    json_material = [p.read_text(encoding='utf-8') for p in r.rglob('*.json')]
    assert any(digest in text for text in json_material), 'private capture identity absent from r08'
    registration = dict(schema_version=1, candidate='classifier-v2-band-r08',
                        acceptance_status='待新隔离局独立验收', selected=False,
                        production_ready=False, full_integer_pipeline=False,
                        p0_1_resolved=False, independent_test=False,
                        source_manifest_sha256=sha(r / 'manifest.json'),
                        original_v1_classifier_sha256=v1, checkpoint_sha256=sha(candidate),
                        local_checkpoint=candidate.relative_to(REPO).as_posix(),
                        local_quantized_candidate=next(r.glob('P0-1*/quantization_v2/candidate_v2')).relative_to(REPO).as_posix(),
                        restore='Run receive_r08.py against the original ZIP; build/ payloads are not Git model delivery.')
    write(HERE / 'candidates/v2-band-r08/registration.json', registration)
    metric = next(r.glob('P0-1*/evidence_v2band_fp32_20261020'))
    for name in ('metrics_summary.json', 'per_frame.json', 'end_to_end_per_frame.json'):
        dest = args.evidence / 'v2-band-protocol' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(metric / name, dest)
    write(args.evidence / 'v2-band-live-analysis-redacted.json',
          dict(scope='Training-side failure analysis only; no live acceptance',
               black_pawns_correct=5, black_pawns_expected=5, black_general_present=False,
               playable=False, p0_1_resolved=False, production_ready=False,
               source_manifest_verified=True, private_payload_archived=False))
    write(args.evidence / 'frozen-identity.json', dict(status='PASS',
          release_version=frozen['release_version'], files_verified=len(frozen['files']),
          frozen_manifest_sha256=sha(g / 'manifest.json'),
          original_v1_classifier_sha256=v1, private_live_frame_identity_match=True,
          candidate_separate=True, frozen_files_modified=False))
    for name in ('p03_noise_separation.json', 'pe_candidate_filter_validation.json'):
        shutil.copyfile(next(r.rglob(name)), args.evidence / name)
    # Source arithmetic code is copied byte-for-byte; the probe adaptation only
    # moves its output to a caller-chosen receipt path.
    write(args.evidence / 'pc-reference-provenance.json', dict(
          exact_source_sha256=sha(next(r.rglob('exact_mm_int64_reference.py'))),
          exact_adapter_sha256=sha(HERE / 'exact_mm_int64_reference.py'),
          exact_copy_unchanged=sha(next(r.rglob('exact_mm_int64_reference.py'))) == sha(HERE / 'exact_mm_int64_reference.py'),
          probe_source_sha256=sha(next(r.glob('P0-2*/probe_mm_char.py'))),
          probe_adaptation='Explicit --out; original numerical probe unchanged'))
    print('R08_CANDIDATE_REGISTERED_PENDING_INDEPENDENT_ACCEPTANCE')


if __name__ == '__main__':
    main()
