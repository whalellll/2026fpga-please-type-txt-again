"""Finite independent900ms native-rate candidate, reusing frozen old clips.

Only over900ms phrases are synthesized, with at most six explicitly bounded
rates through1.50. No resampling, truncation, playback or old-file overwrite.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import time
import wave

from picture_workspace import ROOT, workspace_path
from check_xinyi_yaoyao_phrases import validate_row

SHA = lambda b: hashlib.sha256(b).hexdigest()
RATES = [1.20, 1.25, 1.30, 1.35, 1.40, 1.45, 1.50]
CAP = 14400


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
    old = json.loads(mb)
    assert old['complete'] and len(old['files']) == 5103 and old['native_rate'] == 'per-file'
    (out / 'evidence/reference-manifest.json').write_bytes(mb)
    previous = json.loads((source / 'attempts.json').read_text(encoding='utf8'))
    pool, history, selected = {}, {}, {}
    for n, row in old['files'].items():
        pool[n] = [{**row, 'origin_path': str(source / n)}]
        for trial in previous.get(n, []):
            if trial['sha256'] == row['sha256']:
                continue
            pool[n].append({**row, **trial, 'path': n, 'origin_path': str(source / trial['path']),
                            'bytes': trial['samples'] * 2, 'duration_ms': trial['samples'] / 16,
                            'over960ms': trial['samples'] > 15360, 'over1000ms': trial['samples'] > 16000,
                            'over2000ms': trial['samples'] > 32000})
    inputs = {}
    for n in ['scripts/prepare_xinyi_yaoyao_budget900.py', 'scripts/generate_xinyi_yaoyao_phrase_batch.ps1',
              'scripts/xinyi_yaoyao_common.ps1', 'scripts/check_xinyi_yaoyao_phrases.py']:
        data = (ROOT / n).read_bytes()
        inputs[n] = SHA(data)
        (out / 'source' / n).write_bytes(data)
    result = dict(status='FAILED_OR_INCOMPLETE_PRESERVED', automatically_played=False,
                  hardware_used=False, physical_1000ms_pass=False, installed=False)
    began = time.monotonic()

    def pick(n, row, path):
        data = Path(path).read_bytes()
        assert SHA(data) == row['sha256'] and len(data) == row['samples'] * 2
        q = out / n
        with q.open('xb') as f:
            f.write(data)
        selected[n] = {**row, 'path': n, 'origin_path': str(path),
                       'bytes': len(data), 'duration_ms': len(data) / 32,
                       'over900ms': len(data) > 28800}

    try:
        pending = {}
        for n, variants in pool.items():
            fitting = sorted((r for r in variants if r['samples'] <= CAP), key=lambda r: r['native_rate'])
            if fitting:
                pick(n, fitting[0], fitting[0]['origin_path'])
            else:
                pending[n] = max(variants, key=lambda r: r['native_rate'])
        reused = len(selected)
        assert reused == 1373 and len(pending) == 3730
        for rate in RATES[1:]:
            names = [n for n, row in pending.items() if row['native_rate'] < rate]
            if not names:
                continue
            stage = out / ('attempts/rate' + f'{round(rate * 100):03d}')
            for n in ['whole', 'preview', 'batches']:
                (stage / n).mkdir(parents=True)
            for start in range(0, len(names), 100):
                batch = f'{start // 100 + 1:03d}'
                keys = names[start:start + 100]
                rows = [{**pending[n], 'path': n, 'preview': False} for n in keys]
                plan_path = stage / ('batches/' + batch + '.input.json')
                plan_path.write_text(json.dumps(dict(batch=batch, native_rate=rate, rows=rows),
                                               ensure_ascii=False, indent=2) + '\n', encoding='utf8')
                left = 900 - (time.monotonic() - began)
                assert left > 1, 'Finite15-minute generation limit; preserve all completed data'
                with (stage / ('batches/' + batch + '.log')).open('xb') as log:
                    p = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                        '-File', str(ROOT / 'scripts/generate_xinyi_yaoyao_phrase_batch.ps1'),
                        '-BatchJson', str(plan_path), '-OutputRoot', str(stage)], stdout=log,
                        stderr=subprocess.STDOUT, timeout=min(60, left))
                assert p.returncode == 0, 'Failed batch preserved; no retry'
                answer = json.loads((stage / ('batches/' + batch + '.result.json')).read_text(encoding='utf8'))
                assert answer['native_rate'] == rate and len(answer['files']) == len(keys)
                for n, row in zip(keys, answer['files']):
                    assert row['path'] == n and row['tokens'] == old['files'][n]['tokens']
                    assert row['text'] == old['files'][n]['text'] and row['spoken_text'] == old['files'][n]['spoken_text']
                    row['native_rate'] = rate
                    path = stage / n
                    validate_row(n, row, path.read_bytes())
                    history.setdefault(n, []).append({**row, 'origin_path': str(path)})
                    if row['samples'] <= CAP or rate == RATES[-1]:
                        pick(n, row, path)
                        del pending[n]
                    else:
                        pending[n] = row
                print('BUDGET900_BATCH', round(rate * 100), batch, 'count', len(keys), flush=True)
        assert not pending and len(selected) == 5103
        for n, row in selected.items():
            validate_row(n, row, (out / n).read_bytes())
        longest = sorted(selected.values(), key=lambda r: r['samples'], reverse=True)
        hist = {str(rate): sum(r['native_rate'] == rate for r in selected.values()) for rate in RATES}
        manifest = dict(schema='xinyi-whole-phrase-budget900-candidate/1', format='s16le', sample_rate=16000,
            channels=1, voice='Microsoft Yaoyao', native_rate='per-file', expected_entries=5103,
            complete=True, files=selected, source_sha256=inputs, source_manifest_sha256=SHA(mb),
            resampled=False, interior_clipped=False, edge_context_samples=240, automatically_played=False,
            hearing_verified=False, installed=False, board_tested=False, physical_1000ms_pass=False,
            proposed_wire_kind=9, max_format_samples=32000, native_rate_histogram=hist,
            maximum_native_rate=1.5, pcm_target_samples=CAP, copied_original_900_clips=reused,
            over900ms=sum(r['samples'] > CAP for r in selected.values()),
            over960ms=sum(r['samples'] > 15360 for r in selected.values()),
            over1000ms=sum(r['samples'] > 16000 for r in selected.values()),
            over2000ms=sum(r['samples'] > 32000 for r in selected.values()),
            maximum_samples=longest[0]['samples'], worst20=longest[:20],
            pcm_bytes=sum(r['bytes'] for r in selected.values()),
            timing_scope='PCM only. Preparation/RT/device/cleanup and result scheduling excluded; no physical1s or hearing acceptance.')
        (out / 'attempts.json').write_text(json.dumps(history, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        preview = {r['path'] for r in old['worst20']}
        preview |= {'whole/22-02-27-05.pcm', 'whole/20-02-25-03.pcm', 'whole/21-09-25-01.pcm',
                    'whole/28-21-25-01.pcm', 'whole/17-05-27-04.pcm'}
        for n in preview:
            key = Path(n).stem
            for label, data in [('old960', (source / n).read_bytes()), ('new900', (out / n).read_bytes())]:
                with wave.open(str(out / 'audition-pairs' / (label + '-' + key + '.wav')), 'wb') as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(16000)
                    w.writeframes(data)
            shutil.copyfile(out / 'audition-pairs' / ('new900-' + key + '.wav'), out / 'preview' / (key + '.wav'))
        assert (source / 'manifest.json').read_bytes() == mb
        result.update(status='YAOYAO_BUDGET900_5103_NATIVE_FINITE_COMPLETE_NOT_PHYSICAL_1S', complete_count=5103,
            pcm_bytes=manifest['pcm_bytes'], over900ms=manifest['over900ms'], maximum_ms=longest[0]['duration_ms'],
            minimum_ms=min(r['duration_ms'] for r in selected.values()),
            median_ms=statistics.median(r['duration_ms'] for r in selected.values()),
            native_rate_histogram=hist, copied_original_900_clips=reused, source_manifest_sha256=SHA(mb),
            manifest_sha256=SHA((out / 'manifest.json').read_bytes()))
    finally:
        result.update(completed=len(selected), elapsed_seconds=time.monotonic() - began)
        (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(result['status'])


if __name__ == '__main__':
    main()
