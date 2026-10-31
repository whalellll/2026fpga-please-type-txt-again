"""Bounded det416+A+B native replay against the exact PC chain (training only)."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--models', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--receipt', type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    source_hashes = json.loads((a.build / 'sources-before.json').read_text())
    assert all(sha(REPO / k) == v for k, v in source_hashes.items())
    from r09_reference import selected_paths, configure
    release, candidate = selected_paths()
    sys.path[:0] = [str(release), str(HERE.parent / 'vision-model-20261020/golden/quantization')]
    from pc_exact import load_integer_runtime, characterize
    model = configure(load_integer_runtime(release, candidate), True, 'B')
    rows = []
    for i in range(908, 1043):
        stem = f'IMG{i:05d}'
        inputs = REPO / 'build/picture-p21-native/pipeline-135-r02'
        raw = inputs / (stem + '.rgb565')
        request = inputs / (stem + '.request')
        row = dict(frame=stem)
        packets = {}
        for name in (('before', 'after') if i % 2 else ('after', 'before')):
            packet = a.out / (stem + '.' + name + '.packet')
            start = time.monotonic()
            run = subprocess.run([str(a.build / name), '--models', str(a.models), '--cpu-reference',
                                  '--input', str(raw), '--request', str(request), '--output', str(packet)],
                                 text=True, capture_output=True, timeout=120)
            (a.out / (stem + '.' + name + '.log')).write_text(run.stdout + run.stderr)
            assert run.returncode in (0, 1) and packet.is_file(), (stem, name, run.returncode, run.stderr)
            packets[name] = packet.read_bytes()
            fields = dict(re.findall(r'(\w+)=(\d+)', run.stdout))
            row[name] = {k: int(fields[k]) for k in ('classifier_batch', 'classifier_ms', 'board_ms',
                        'detector_ms', 'refine_ms', 'assign_ms', 'total_ms')}
            row[name]['wall_s'] = time.monotonic() - start
        assert packets['before'] == packets['after'], (stem, 'filter changes packet')
        reference = model.predict(raw, pixel_format='rgb565', width=1280, height=720,
                                  byte_order='little', stride_bytes=2560)
        (a.out / (stem + '.reference.json')).write_text(json.dumps(reference, allow_nan=False) + '\n')
        packet_lines = packets['after'].decode().splitlines()
        native_usable = int(packet_lines[0].split()[5]) == 0
        native_fen = packet_lines[1].split()[0] if native_usable else None
        expected_usable = reference['status'] == 'candidate_board' and reference['can_use_as_candidate']
        assert native_usable == expected_usable, (stem, 'strict status', reference['status'], packet_lines[0])
        assert native_fen == reference['board_placement_fen'], (stem, 'strict FEN')
        row.update(packet_byte_identical=True, native_vs_exact_status_and_fen_equal=True,
                   strict_usable=bool(native_usable), classifier_input=model.pipeline.detector._r09_counts)
        rows.append(row)
        (a.out / 'progress.json').write_text(json.dumps(rows, indent=2) + '\n')
        if len(rows) % 15 == 0:
            print('R09_NATIVE_EXACT_REPLAY', len(rows), '/135', flush=True)
    assert all(sha(REPO / k) == v for k, v in source_hashes.items())
    counts = {name: sum(r[name]['classifier_batch'] for r in rows) for name in ('before', 'after')}
    report = dict(status='PASS', frames=135, hardware_used=False, candidate='det416+v2-band+board+A+B',
                  scope='training RGB565 replay; CPU reference; no independent accuracy or board timing',
                  filter_packets_identical=135, native_exact_strict_status_and_fen_equal=135,
                  classifier_batches=counts, batch_reduction=1-counts['after']/counts['before'],
                  platform_probe=characterize(), source_hashes=source_hashes,
                  executables={n: sha(a.build/n) for n in ('before', 'after')},
                  model_hashes={f.name: sha(f) for f in a.models.glob('*.xqm')},
                  source_stable_during_run=True, rows=rows, production_ready=False)
    a.receipt.write_text(json.dumps(report, indent=2) + '\n')
    print('R09_NATIVE_EXACT_135_PASS', counts, flush=True)


if __name__ == '__main__':
    main()
