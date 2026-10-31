"""Static exact-equality analysis only; does not change the runtime/candidate."""
import argparse, hashlib, json
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
assert not a.out.exists()
root=Path(__file__).resolve().parent.parent/'vision-model-20261020/golden/quantization/candidate_v1'
manifest=json.loads((root/'golden_dump_manifest.json').read_text())
item=next(v for v in manifest if v['path'].endswith('/classifier__features_0_call0.npz'))
path=root/item['path']
with np.load(path,allow_pickle=False) as f:q=f['input_q'].copy()
assert q.dtype==np.int8 and q.shape[1:]==(3,32,32)
unique=len(np.unique(q.reshape(q.shape[0],-1),axis=0))
result=dict(scope='Static delivered classifier input, exact equality; no runtime cache enabled',
    source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),batch=int(q.shape[0]),
    exact_unique_quantized_crops=unique,duplicates=int(q.shape[0])-unique)
a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
