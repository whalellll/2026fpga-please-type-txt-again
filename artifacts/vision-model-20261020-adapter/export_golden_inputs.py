"""Use each model's actual first delivered S8 input to replay all 80 layers."""
import argparse,gzip,hashlib,io,json,struct,tarfile,zlib
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent/'vision-model-20261020/golden/quantization/candidate_v1'
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
graph=json.loads((ROOT/'integer_graph.json').read_text());dumps=json.loads((ROOT/'golden_dump_manifest.json').read_text())
paths={x['path'].split('/')[-1].removesuffix('_call0.npz'):ROOT/x['path'] for x in dumps}
expected=[];inputs=[]
for index,name in enumerate(('board','detector','classifier')):
    layer=next(m for m in graph['layers'] if m['layer_id'].startswith(name+'__'))
    with np.load(paths[layer['layer_id']],allow_pickle=False) as z:q=z['input_q'].copy()
    assert q.dtype==np.int8 and q.ndim==4
    raw=q.tobytes();header=struct.pack('<8s8Ii',b'XQINP1\0\0',1,index,*q.shape,len(raw),zlib.crc32(raw),layer['input_exponent'])
    dest=a.out/(name+'.input');dest.write_bytes(header+raw)
    inputs.append(dict(model=name,shape=list(q.shape),bytes=len(raw),source=layer['layer_id'],sha256=hashlib.sha256(dest.read_bytes()).hexdigest()))
for index,meta in enumerate(graph['layers']):
    with np.load(paths[meta['layer_id']],allow_pickle=False) as z:
        q=z['input_q'];acc=z['accumulator_with_bias'].astype('<i4');pre=z['preactivation_s16'].astype('<i2');out=z['output_q'].astype('<i2')
    arrays=[q,acc,pre,out]
    expected.append([index,q.size,out.size,*[zlib.crc32(x.tobytes()) for x in arrays],*[hashlib.sha256(x.tobytes()).hexdigest() for x in arrays]])
(a.out/'expected.json').write_text(json.dumps(dict(scope='Original delivered 80 layer dumps, canonical output stored as I16 for S8/S16 heads',
    inputs=inputs,rows=expected,source_dump_manifest_sha256=hashlib.sha256((ROOT/'golden_dump_manifest.json').read_bytes()).hexdigest()),indent=2)+'\n')
stream=io.BytesIO()
with tarfile.open(fileobj=stream,mode='w',format=tarfile.USTAR_FORMAT) as tf:
    for path in sorted(a.out.glob('*.input')):
        data=path.read_bytes();entry=tarfile.TarInfo('xq-golden/'+path.name);entry.size=len(data);entry.mode=0o644;entry.mtime=0;tf.addfile(entry,io.BytesIO(data))
(a.out/'inputs.tar.gz').write_bytes(gzip.compress(stream.getvalue(),mtime=0))
print('GOLDEN_INPUTS_EXPORTED',inputs,'gzip_bytes',(a.out/'inputs.tar.gz').stat().st_size,flush=True)
