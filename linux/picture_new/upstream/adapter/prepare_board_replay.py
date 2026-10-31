"""Prepare temporary RAM replay inputs from an existing training-frame conversion.

Not a camera capture, new test game, or part of the deployment/handoff ZIP.
"""
import argparse,gzip,hashlib,zlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
a.out.mkdir(parents=True,exist_ok=False)
raw=a.source.read_bytes();assert len(raw)==1843200
(a.out/'input.rgb565.gz').write_bytes(gzip.compress(raw,compresslevel=9,mtime=0))
(a.out/'request.txt').write_text(f'XQ_MODEL_REQUEST_V1 1 1 {zlib.crc32(raw):08x} rv32-driver-quantized-mac\n')
print('BOARD_REPLAY_PREPARED',len(raw),(a.out/'input.rgb565.gz').stat().st_size,hashlib.sha256(raw).hexdigest())
