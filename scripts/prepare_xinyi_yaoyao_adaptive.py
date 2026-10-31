"""Separate finite native-rate candidate; preserve the complete1.2 asset set.

Copy original <=960ms clips exactly; synthesize only the1070 over-budget clips
at1.25/1.30/1.35/1.40, stopping per phrase as soon as it fits. No resampling,
interior clipping, automatic playback, unbounded tuning or failure retries.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import wave

from picture_workspace import ROOT, workspace_path

SHA = lambda b: hashlib.sha256(b).hexdigest()
RATES = [1.25, 1.30, 1.35, 1.40]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--reference', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    source, out = workspace_path(a.reference), workspace_path(a.output)
    assert out.is_relative_to((ROOT / 'build/picture-e42-20261025').resolve())
    out.mkdir(parents=True, exist_ok=False)
    for n in ['whole', 'preview', 'audition-pairs', 'evidence', 'source/scripts']:
        (out / n).mkdir(parents=True)
    mb = (source / 'manifest.json').read_bytes()
    reference = json.loads(mb)
    assert reference['complete'] and len(reference['files']) == 5103
    assert reference['native_rate'] == 1.2 and reference['sample_rate'] == 16000
    assert reference['voice'] == 'Microsoft Yaoyao' and not reference['resampled']
    (out / 'evidence/reference-manifest.json').write_bytes(mb)
    inputs = {}
    for n in ['scripts/prepare_xinyi_yaoyao_adaptive.py',
              'scripts/generate_xinyi_yaoyao_phrase_batch.ps1', 'scripts/xinyi_yaoyao_common.ps1']:
        b = (ROOT / n).read_bytes()
        inputs[n] = SHA(b)
        (out / 'source' / n).write_bytes(b)
    result = dict(status='FAILED_OR_INCOMPLETE_PRESERVED', physical_1000ms_pass=False,
                  automatically_played=False, hardware_used=False, installed=False)
    selected, pending, tries = {}, [], {}
    began = time.monotonic()

    def copy_selected(row, data, rate):
        n = row['path']
        assert n not in selected and SHA(data) == row['sha256']
        q = out / n
        with q.open('xb') as f:
            f.write(data)
        selected[n] = {**row, 'native_rate': rate,
                       'reference_samples': reference['files'][n]['samples'],
                       'reference_sha256': reference['files'][n]['sha256']}

    try:
        for n, row in reference['files'].items():
            data = (source / n).read_bytes()
            assert SHA(data) == row['sha256'] and len(data) == row['bytes']
            if row['samples'] <= 15360:
                copy_selected(row, data, 1.2)
            else:
                pending.append(row)
        assert len(selected) == 4033 and len(pending) == 1070
        original_short = len(selected)
        for rate in RATES:
            if not pending:
                break
            rate_id = f'{round(rate * 100):03d}'
            stage = out / ('attempts/rate' + rate_id)
            for n in ['whole', 'preview', 'batches']:
                (stage / n).mkdir(parents=True)
            later = []
            for start in range(0, len(pending), 100):
                batch_id = f'{start // 100 + 1:03d}'
                rows = [{**row, 'preview': False} for row in pending[start:start + 100]]
                plan = dict(batch=batch_id, native_rate=rate, rows=rows)
                plan_path = stage / ('batches/' + batch_id + '.input.json')
                plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
                left = 600 - (time.monotonic() - began)
                assert left > 1, 'Finite10-minute adaptive budget exhausted'
                with (stage / ('batches/' + batch_id + '.log')).open('xb') as log:
                    q = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                        '-File', str(ROOT / 'scripts/generate_xinyi_yaoyao_phrase_batch.ps1'),
                        '-BatchJson', str(plan_path), '-OutputRoot', str(stage)],
                        stdout=log, stderr=subprocess.STDOUT, timeout=min(60, left))
                assert q.returncode == 0, f'Preserve failed batch{rate_id}/{batch_id}; no retry'
                rb = (stage / ('batches/' + batch_id + '.result.json')).read_bytes()
                actual = json.loads(rb)
                assert actual['status'] == 'BATCH_COMPLETE_NO_AUTOPLAY' and actual['native_rate'] == rate
                assert len(rows) == len(actual['files'])
                for expected, row in zip(rows, actual['files']):
                    assert all(row[k] == expected[k] for k in ['path', 'tokens', 'text', 'spoken_text'])
                    data = (stage / row['path']).read_bytes()
                    assert SHA(data) == row['sha256'] and len(data) == row['bytes']
                    tries.setdefault(row['path'], []).append(dict(native_rate=rate,
                        path=f'attempts/rate{rate_id}/' + row['path'], samples=row['samples'],
                        sha256=row['sha256'], source_samples=row['source_samples'],
                        first=row['first'], last=row['last']))
                    if row['samples'] <= 15360 or rate == RATES[-1]:
                        copy_selected(row, data, rate)
                    else:
                        later.append(row)
                print('ADAPTIVE_BATCH', rate_id, batch_id, 'count', len(rows), flush=True)
            pending = later
        assert not pending and len(selected) == 5103
        assert (source / 'manifest.json').read_bytes() == mb, 'Reference manifest changed'
        longest = sorted(selected.values(), key=lambda r: r['samples'], reverse=True)
        preview_names = {r['path'] for r in reference['worst20']}
        preview_names |= {'whole/22-02-27-05.pcm', 'whole/20-02-25-03.pcm', 'whole/21-09-25-01.pcm',
                          'whole/28-21-25-01.pcm', 'whole/17-05-27-04.pcm', 'whole/16-05-27-04.pcm'}
        for n in sorted(preview_names):
            key = Path(n).stem
            for label, p in [('reference', source / n), ('adaptive', out / n)]:
                with wave.open(str(out / 'audition-pairs' / (label + '-' + key + '.wav')), 'wb') as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(16000)
                    w.writeframes(p.read_bytes())
            shutil.copyfile(out / 'audition-pairs' / ('adaptive-' + key + '.wav'), out / 'preview' / (key + '.wav'))
        histogram = {str(rate): sum(r['native_rate'] == rate for r in selected.values()) for rate in [1.2, *RATES]}
        manifest = dict(schema='xinyi-whole-phrase-adaptive-candidate/1', format='s16le', sample_rate=16000,
            channels=1, voice='Microsoft Yaoyao', native_rate='per-file', expected_entries=5103,
            complete=True, files=selected, source_sha256=inputs, source_manifest_sha256=SHA(mb),
            resampled=False, interior_clipped=False, edge_context_samples=240,
            automatically_played=False, hearing_verified=False, installed=False, board_tested=False,
            physical_1000ms_pass=False, proposed_wire_kind=9, max_format_samples=32000,
            native_rate_histogram=histogram, adaptive_rates=RATES, maximum_native_rate=1.4,
            original_short_clips_byte_identical=original_short,
            over960ms=sum(r['samples'] > 15360 for r in selected.values()),
            over1000ms=sum(r['samples'] > 16000 for r in selected.values()),
            over2000ms=sum(r['samples'] > 32000 for r in selected.values()),
            maximum_samples=longest[0]['samples'], worst20=longest[:20],
            pcm_bytes=sum(r['bytes'] for r in selected.values()),
            timing_scope='PCM only; excludes result scheduling/startup/device/cleanup; no physical1s pass.')
        (out / 'attempts.json').write_text(json.dumps(tries, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        assert all(SHA((out / 'source' / n).read_bytes()) == h for n, h in inputs.items())
        result.update(status='YAOYAO_FINITE_ADAPTIVE_5103_COMPLETE_NOT_HEARING_OR_PHYSICAL_1S',
            complete_count=5103, pcm_bytes=manifest['pcm_bytes'], over960ms=manifest['over960ms'],
            over1000ms=manifest['over1000ms'], over2000ms=manifest['over2000ms'],
            maximum_ms=longest[0]['duration_ms'], native_rate_histogram=histogram,
            source_manifest_sha256=SHA(mb), original_short_clips_byte_identical=original_short)
    finally:
        result.update(completed=len(selected), elapsed_seconds=time.monotonic() - began)
        (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(result['status'])


if __name__ == '__main__':
    main()
