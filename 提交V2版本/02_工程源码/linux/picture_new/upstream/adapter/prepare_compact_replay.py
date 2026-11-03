"""Prepare a clearly labelled, bandwidth-limited engineering replay.

Nearest sampling/replication is applied to the RGB565 training image only;
this is not live-camera evidence, independent data or a model acceptance score.
"""
import argparse, gzip, hashlib, json, subprocess, zlib
from pathlib import Path
import numpy as np

p = argparse.ArgumentParser()
p.add_argument('--source', type=Path, required=True)
p.add_argument('--worker', type=Path, required=True)
p.add_argument('--models', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
a.out.mkdir(parents=True, exist_ok=False)
original = gzip.decompress(a.source.read_bytes())
image = np.frombuffer(original, dtype='<u2').reshape(720, 1280)
rows = []
for factor in (4, 2):
    raw = image[::factor, ::factor].repeat(factor, 0).repeat(factor, 1).tobytes()
    base = a.out / f'sample{factor}'
    base.with_suffix('.rgb565').write_bytes(raw)
    base.with_suffix('.rgb565.gz').write_bytes(gzip.compress(raw, mtime=0))
    crc = zlib.crc32(raw)
    request = f'XQ_MODEL_REQUEST_V1 1 1 {crc:08x} '
    base.with_suffix('.cpu.request').write_text(request + 'CPU_REFERENCE\n')
    base.with_suffix('.board.request').write_text(request + 'rv32-driver-quantized-mac\n')
    run = subprocess.run([str(a.worker), '--models', str(a.models), '--cpu-reference',
        '--request', str(base.with_suffix('.cpu.request')),
        '--input', str(base.with_suffix('.rgb565')),
        '--output', str(base.with_suffix('.packet'))], capture_output=True, text=True, timeout=120)
    base.with_suffix('.log').write_text(run.stdout + run.stderr)
    rows.append(dict(factor=factor, raw_sha256=hashlib.sha256(raw).hexdigest(),
        gzip_bytes=base.with_suffix('.rgb565.gz').stat().st_size,
        cpu_exit=run.returncode, packet=base.with_suffix('.packet').read_text()))
result = dict(scope='IMG00908 training fixture, explicitly transformed offline engineering replay',
    original_sha256=hashlib.sha256(original).hexdigest(), variants=rows)
(a.out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
