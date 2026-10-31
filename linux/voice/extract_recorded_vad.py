#!/usr/bin/env python3
"""Run the existing offline original-C VAD extractor on a frozen dataset.

The extractor is the original daemon with file audio/IPC stubs and the
sim/xqvoice_segment_capture.c feature hook. Build/identify it separately.
This preprocessing tool needs no torch and runs in Linux/WSL.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--extractor', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--expected-extractor-sha256', required=True)
    args = parser.parse_args()
    if sha(args.extractor) != args.expected_extractor_sha256:
        raise ValueError('Offline extractor hash mismatch')
    args.output.mkdir(parents=True, exist_ok=False)
    snapshot = json.loads(args.snapshot.read_text(encoding='utf8'))
    root = args.snapshot.resolve().parent
    entries = []
    for record in snapshot['records']:
        source = (root / record['path']).with_suffix('.pcm')
        if not source.resolve().is_relative_to(root):
            raise ValueError('PCM path escapes snapshot')
        directory = args.output / ('sample_%03d' % record['index'])
        directory.mkdir()
        stream = directory / 'stream.pcm'
        # Offline EOF flush only; not measured real acoustic silence or latency.
        stream.write_bytes(source.read_bytes() + b'\0' * 32000)
        env = dict(os.environ, XQVOICE_SEGMENT_PREFIX=str(directory.resolve() / 'utterance'))
        result = subprocess.run([str(args.extractor.resolve()), str(stream.resolve()),
                                 str(args.model.resolve()), '200', '160', '500'],
                                env=env, capture_output=True, text=True, timeout=15)
        if result.returncode != 7:
            raise RuntimeError('Unexpected extractor exit: ' + str(result.returncode) + result.stderr)
        files = sorted(directory.glob('utterance-*.pcm'))
        entries.append({'source_index': record['index'], 'token': record['token'], 'label': record['label'],
                        'source_sha256': record['sha256'],
                        'segments': [{'path': f.relative_to(args.output).as_posix(), 'samples': f.stat().st_size // 2,
                                      'sha256': sha(f)} for f in files]})
    report = {'schema': 1, 'snapshot_sha256': sha(args.snapshot), 'entries': entries,
              'extractor_sha256': sha(args.extractor), 'extractor_model_sha256': sha(args.model),
              'scope': 'Original C VAD start200/stop160,100ms pre-roll,300ms end quiet; 1s zero EOF flush; no timing/accuracy acceptance',
              'single_segment_recordings': sum(len(r['segments']) == 1 for r in entries)}
    (args.output / 'segments.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'recordings': len(entries), 'single_segment': report['single_segment_recordings'],
                      'ambiguous': [{'source_index': r['source_index'], 'token': r['token'], 'segments': len(r['segments'])}
                                    for r in entries if len(r['segments']) != 1]}), flush=True)


if __name__ == '__main__':
    main()
