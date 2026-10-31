"""Finite offline Yaoyao whole-phrase candidate: 5103 structural move sequences.

No audio playback. No old PCM overwrite, resampling or interior clipping. Each
batch has at most100 phrases/60s; the complete task has a15-minute hard budget.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

from picture_workspace import ROOT, workspace_path

SHA = lambda b: hashlib.sha256(b).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--plan-only', action='store_true')
    ap.add_argument('--max-phrases', type=int, default=5103,
                    help='Finite smoke subset; anything below5103 is explicitly incomplete')
    a = ap.parse_args()
    assert 1 <= a.max_phrases <= 5103
    out = workspace_path(a.output)
    assert out.is_relative_to((ROOT / 'build/picture-e42-20261025').resolve())
    out.mkdir(parents=True, exist_ok=False)
    inputs = {}

    def read(name):
        b = (ROOT / name).read_bytes()
        inputs[name] = SHA(b)
        q = out / 'inputs' / name
        q.parent.mkdir(parents=True, exist_ok=True)
        q.write_bytes(b)
        return b

    # Cross-check the actual producer enum and its token-name table; do not
    # infer phonemes from UI text or include red/black prefixes.
    h = read('linux/voice_speech/xq_speech.h').decode()
    c = read('linux/voice_speech/xq_speech.c').decode()
    enums = [n.strip() for n in re.search(r'typedef enum\s*\{(.*?)\}', h, re.S).group(1).split(',')]
    names = re.findall(r'"([a-z_]+)"', re.search(r'xqs_names\[XQS_COUNT\]=\{(.*?)\};', c, re.S).group(1))
    assert len(enums) == len(names) + 1 and enums[-1] == 'XQS_COUNT'
    assert {enums[i]: i for i in [1, 9, 16, 24, 25, 27, 28, 30]} == dict(
        XQS_ONE=1, XQS_NINE=9, XQS_KING_RED=16, XQS_PAWN_BLACK=24,
        XQS_FORWARD=25, XQS_HORIZONTAL=27, XQS_FRONT=28, XQS_MIDDLE=30)
    old = json.loads(read('linux/boot/v2_1_sd/rootfs_payloads/picture/pcm/manifest.json'))
    tokens = {i: dict(name=names[i], text=old['files'][names[i] + '.pcm']['text'],
                      spoken_text=old['files'][names[i] + '.pcm']['spoken_text'])
              for i in [*range(1, 10), *range(16, 31)]}
    assert all(len(row['text']) == len(row['spoken_text']) == 1 for row in tokens.values())
    preview = {(22, 2, 27, 5), (20, 2, 25, 3), (21, 9, 25, 1),
               (20, 8, 25, 7), (28, 21, 25, 1), (30, 23, 25, 1), (5, 23, 25, 1)}
    sequences = sorted(set(itertools.product(range(16, 25), range(1, 10), range(25, 28), range(1, 10))) |
                       set(itertools.product(range(28, 31), range(16, 25), range(25, 28), range(1, 10))) |
                       set(itertools.product(range(1, 10), range(16, 25), range(25, 28), range(1, 10))))
    assert len(sequences) == 5103
    rows = [dict(tokens=list(s), path='whole/' + '-'.join(f'{i:02d}' for i in s) + '.pcm',
                 text=''.join(tokens[i]['text'] for i in s),
                 spoken_text=''.join(tokens[i]['spoken_text'] for i in s), preview=s in preview)
            for s in sequences]
    assert len({r['path'] for r in rows}) == len(rows) and all(len(r['spoken_text']) == 4 for r in rows)
    # Put ordinary representative phrases into even a smoke run; full runs
    # still cover the same exact set and preserve stable ASCII filenames.
    rows.sort(key=lambda r: (not r['preview'], r['tokens']))
    plan = dict(schema='xinyi-whole-phrase-plan/1', conservative_producer_closure=5103,
        grammar='piece16..24,digit1..9,action25..27,dest1..9 OR prefix28..30,piece,action,dest OR digit,piece,action,dest',
        selected_count=a.max_phrases, complete=a.max_phrases == 5103,
        tokens=tokens, native_rate=1.2, sample_rate=16000, channels=1, format='s16le',
        proposed_wire_kind=9, max_format_samples=32000, timing_target_ms=1000,
        pcm_warning_ms=960, board_tested=False, physical_1000ms_pass=False,
        resampled=False, interior_clipped=False, quiet_edge_context_samples=240,
        source_sha256=inputs.copy(), rows=rows[:a.max_phrases])
    (out / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    if a.plan_only:
        print('WHOLE_PHRASE_PLAN_ONLY_COUNT', a.max_phrases)
        return
    for n in ['whole', 'preview', 'batches', 'source/scripts']:
        (out / n).mkdir(parents=True)
    for n in ['scripts/prepare_xinyi_yaoyao_phrases.py',
              'scripts/generate_xinyi_yaoyao_phrase_batch.ps1', 'scripts/xinyi_yaoyao_common.ps1']:
        read(n)
        shutil.copyfile(ROOT / n, out / 'source' / n)
    result = dict(status='FAILED_OR_INCOMPLETE_PRESERVED', hardware_used=False,
                  installed=False, automatic_playback=False, physical_1000ms_pass=False)
    started = time.monotonic()
    completed = []
    try:
        for start in range(0, a.max_phrases, 100):
            index = f'{start // 100 + 1:03d}'
            batch_path = out / ('batches/' + index + '.input.json')
            batch = dict(batch=index, native_rate=1.2, rows=rows[start:min(start + 100, a.max_phrases)])
            batch_path.write_text(json.dumps(batch, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
            left = 900 - (time.monotonic() - started)
            assert left >= 1, 'Finite15-minute budget exhausted; preserve completed files'
            with (out / ('batches/' + index + '.log')).open('xb') as log:
                q = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                    '-File', str(ROOT / 'scripts/generate_xinyi_yaoyao_phrase_batch.ps1'),
                    '-BatchJson', str(batch_path), '-OutputRoot', str(out)],
                    stdout=log, stderr=subprocess.STDOUT, timeout=min(60, left))
            assert q.returncode == 0, 'Batch failed; no automatic retry: ' + index
            actual = json.loads((out / ('batches/' + index + '.result.json')).read_text(encoding='utf8'))
            assert actual['status'] == 'BATCH_COMPLETE_NO_AUTOPLAY' and len(actual['files']) == len(batch['rows'])
            for expected, row in zip(batch['rows'], actual['files']):
                assert all(row[k] == expected[k] for k in ['tokens', 'path', 'text', 'spoken_text'])
                data = (out / row['path']).read_bytes()
                assert len(data) == row['bytes'] and SHA(data) == row['sha256'] and len(data) % 2 == 0
                assert row['samples'] == len(data) // 2
            completed.extend(actual['files'])
            print('WHOLE_PHRASE_BATCH', index, 'count', len(actual['files']), flush=True)
        longest = sorted(completed, key=lambda r: r['samples'], reverse=True)
        manifest = dict(schema='xinyi-whole-phrase-candidate/1', format='s16le', sample_rate=16000,
            channels=1, voice='Microsoft Yaoyao', native_rate=1.2, expected_entries=5103,
            complete=a.max_phrases == 5103, files={r['path']: r for r in completed},
            source_sha256=inputs, resampled=False, interior_clipped=False, edge_context_samples=240,
            automatically_played=False, hearing_verified=False, installed=False, board_tested=False,
            physical_1000ms_pass=False, proposed_wire_kind=9, max_format_samples=32000,
            over960ms=sum(r['samples'] > 15360 for r in completed),
            over1000ms=sum(r['samples'] > 16000 for r in completed),
            over2000ms=sum(r['samples'] > 32000 for r in completed),
            maximum_samples=longest[0]['samples'], worst20=longest[:20],
            pcm_bytes=sum(r['bytes'] for r in completed),
            timing_scope='PCM only. Result scheduling/startup/device/cleanup excluded; no physical1s pass.')
        (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        # The enum/name/old-asset inputs are frozen at planning time. Other
        # GUI work may add unrelated code to the shared producer file while
        # synthesis runs; never rebind that snapshot to its later bytes.
        assert all(SHA((out / 'inputs' / n).read_bytes()) == h for n, h in inputs.items())
        result.update(status='YAOYAO_COMPLETE_5103_OFFLINE_NOT_PHYSICAL_1S' if a.max_phrases == 5103 else 'YAOYAO_SMOKE_SUBSET_NOT_COMPLETE',
            completed=len(completed), pcm_bytes=manifest['pcm_bytes'], over960ms=manifest['over960ms'],
            over1000ms=manifest['over1000ms'], over2000ms=manifest['over2000ms'],
            maximum_ms=longest[0]['duration_ms'], worst20=longest[:20])
    finally:
        result.update(completed=len(completed), elapsed_seconds=time.monotonic() - started)
        (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(result['status'])


if __name__ == '__main__':
    main()
