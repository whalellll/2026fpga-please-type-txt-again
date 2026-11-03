"""Freeze NumPy reference RANSAC choices, without replacing its seeded algorithm."""
import argparse,hashlib,json,struct,zlib
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if a.out.exists():raise FileExistsError(a.out)
data=np.zeros((91,240,4),np.uint8)
for n in range(16,91):
    rng=np.random.default_rng(20261020)
    for trial in range(240):data[n,trial]=rng.choice(n,4,replace=False)
raw=data.tobytes();a.out.write_bytes(struct.pack('<8sII',b'XQRNG1\0\0',len(raw),zlib.crc32(raw))+raw)
print('REFINEMENT_RNG_EXPORTED',hashlib.sha256(a.out.read_bytes()).hexdigest())
