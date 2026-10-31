"""Validate the finite whole-phrase closure and durations without playback."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import statistics
import wave

from picture_workspace import ROOT, workspace_path

SHA = lambda b: hashlib.sha256(b).hexdigest()


def validate_row(name, row, data):
    t = row['tokens']
    assert len(t) == 4
    assert ((16 <= t[0] <= 24 and 1 <= t[1] <= 9) or
            (28 <= t[0] <= 30 and 16 <= t[1] <= 24) or
            (1 <= t[0] <= 9 and 16 <= t[1] <= 24))
    assert 25 <= t[2] <= 27 and 1 <= t[3] <= 9
    assert name == 'whole/' + '-'.join(f'{i:02d}' for i in t) + '.pcm'
    assert row['path'] == name and len(row['text']) == len(row['spoken_text']) == 4
    assert len(data) > 0 and len(data) % 2 == 0 and any(data)
    assert len(data) == row['bytes'] and SHA(data) == row['sha256']
    assert row['samples'] == len(data) // 2 and row['duration_ms'] == len(data) / 32
    assert row['samples'] == row['last'] - row['first'] + 1
    assert 0 <= row['first'] <= row['last'] < row['source_samples']
    assert row['over960ms'] == (row['samples'] > 15360)
    assert row['over1000ms'] == (row['samples'] > 16000)
    assert row['over2000ms'] == (row['samples'] > 32000)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--candidate', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    p, out = workspace_path(a.candidate), workspace_path(a.output)
    assert out.is_relative_to((ROOT / 'build/picture-e42-20261025').resolve())
    out.mkdir(parents=True, exist_ok=False)
    mbytes = (p / 'manifest.json').read_bytes()
    m = json.loads(mbytes)
    assert m['complete'] and m['expected_entries'] == 5103
    assert m['format'] == 's16le' and m['sample_rate'] == 16000 and m['channels'] == 1
    assert m['voice'] == 'Microsoft Yaoyao' and m['native_rate'] in [1.2, 'per-file']
    adaptive = m['native_rate'] == 'per-file'
    assert not m['resampled'] and not m['interior_clipped'] and not m['automatically_played']
    actual = {f.relative_to(p).as_posix() for f in (p / 'whole').iterdir()}
    assert actual == set(m['files']) and len(actual) == 5103
    expected = set(itertools.product(range(16, 25), range(1, 10), range(25, 28), range(1, 10)))
    expected |= set(itertools.product(range(28, 31), range(16, 25), range(25, 28), range(1, 10)))
    expected |= set(itertools.product(range(1, 10), range(16, 25), range(25, 28), range(1, 10)))
    assert {tuple(r['tokens']) for r in m['files'].values()} == expected
    durations, pcm_bytes, negatives = [], 0, []
    for name, row in m['files'].items():
        data = (p / name).read_bytes()
        validate_row(name, row, data)
        durations.append(row['duration_ms'])
        pcm_bytes += len(data)
    if adaptive:
        rates = [1.25, 1.30, 1.35, 1.40]
        reference_bytes = (p / 'evidence/reference-manifest.json').read_bytes()
        assert SHA(reference_bytes) == m['source_manifest_sha256']
        reference = json.loads(reference_bytes)
        attempts = json.loads((p / 'attempts.json').read_text(encoding='utf8'))
        copied = 0
        for name, row in m['files'].items():
            original = reference['files'][name]
            assert row['reference_sha256'] == original['sha256']
            assert row['reference_samples'] == original['samples']
            if original['samples'] <= 15360:
                assert row['native_rate'] == 1.2 and row['sha256'] == original['sha256']
                assert name not in attempts
                copied += 1
            else:
                tried = attempts[name]
                assert [r['native_rate'] for r in tried] == rates[:len(tried)]
                assert tried[-1]['sha256'] == row['sha256'] and tried[-1]['native_rate'] == row['native_rate']
                assert all(r['samples'] > 15360 for r in tried[:-1])
                assert tried[-1]['samples'] <= 15360 or row['native_rate'] == 1.4
                for attempt in tried:
                    b = (p / attempt['path']).read_bytes()
                    assert SHA(b) == attempt['sha256'] and len(b) == attempt['samples'] * 2
        assert copied == m['original_short_clips_byte_identical'] == 4033
        assert m['native_rate_histogram'] == {str(rate): sum(r['native_rate'] == rate for r in m['files'].values())
                                             for rate in [1.2, *rates]}
    first = next(iter(m['files']))
    row = m['files'][first]
    data = (p / first).read_bytes()
    bad = bytearray(data)
    bad[len(bad) // 2] ^= 1
    for label, name, metadata, payload in [
        ('corrupt-one-byte', first, row, bad),
        ('wrong-fixed-token-filename', 'whole/00-00-00-00.pcm', row, data),
        ('odd-pcm-length', first, row, data[:-1]),
        ('invalid-token-prefix', first, {**row, 'tokens': [0, 16, 25, 1]}, data)]:
        try:
            validate_row(name, metadata, payload)
        except AssertionError:
            negatives.append(label)
        else:
            raise AssertionError('Negative accepted: ' + label)
    wavs = []
    for q in (p / 'preview').glob('*.wav'):
        with wave.open(str(q)) as w:
            assert w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() == 16000
            b = w.readframes(w.getnframes())
        assert b == (p / 'whole' / (q.stem + '.pcm')).read_bytes()
        wavs.append(q.name)
    longest = sorted(m['files'].values(), key=lambda r: r['samples'], reverse=True)
    for row in longest[:3]:
        q = out / (Path(row['path']).stem + '.wav')
        with wave.open(str(q), 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes((p / row['path']).read_bytes())
    assert pcm_bytes == m['pcm_bytes']
    result = dict(status='WHOLE_YAOYAO_5103_CLOSURE_SHA_FORMAT_NEGATIVES_PASS_NOT_HEARING_OR_BOARD',
        hardware_used=False, automatically_played=False, physical_1000ms_pass=False,
        complete_count=5103, pcm_bytes=pcm_bytes, manifest_sha256=SHA(mbytes),
        adaptive=adaptive, native_rate_histogram=m.get('native_rate_histogram'),
        minimum_ms=min(durations), median_ms=statistics.median(durations), maximum_ms=max(durations),
        over960ms=sum(v > 960 for v in durations), over1000ms=sum(v > 1000 for v in durations),
        over2000ms=sum(v > 2000 for v in durations), negative_controls=negatives,
        representative_wavs_exact=sorted(wavs), worst3=longest[:3])
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({k: v for k, v in result.items() if k not in ['worst3', 'representative_wavs_exact']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
