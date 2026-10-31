"""Static work inventory from the delivered 80 dumps, not a latency prediction."""
import collections
import hashlib
import json
import math
from pathlib import Path

here=Path(__file__).resolve().parent
repo=here.parents[1]
root=here.parent/'vision-model-20261020/golden/quantization/candidate_v1'
graph=json.loads((root/'integer_graph.json').read_text())
dumps=json.loads((root/'golden_dump_manifest.json').read_text())
by_id={r['path'].split('/')[-1].removesuffix('_call0.npz'):r for r in dumps}
rows=[]
totals=collections.defaultdict(lambda:collections.Counter())
for layer in graph['layers']:
    ident=layer['layer_id'];dump=by_id[ident]
    dims=layer['weight_shape'];oshape=dump['tensors']['accumulator_with_bias']['shape']
    ishape=dump['tensors']['input_q']['shape'];n=dims[0];k=math.prod(dims[1:])
    if len(dims)==4:
        assert len(oshape)==4 and oshape[1]==n and ishape[1]==dims[1]
        m=oshape[0]*oshape[2]*oshape[3]
    else:
        assert len(dims)==2 and oshape[-1]==n and ishape[-1]==k
        m=math.prod(oshape[:-1])
    co_step=min(256,32*(64//math.ceil(min(k,256)/4)))
    jobs=math.ceil(m/16)*math.ceil(n/co_step)*math.ceil(k/256)
    staging=0
    for row in range(0,m,16):
        mt=min(16,m-row)
        for co in range(0,n,co_step):
            nt=min(co_step,n-co)
            for ci in range(0,k,256):
                kt=min(256,k-ci);tiles=math.ceil(kt/4)
                staging+=mt*tiles*8+math.ceil(nt/32)*tiles*128+mt*nt*4
    record=dict(layer=ident,input_shape=ishape,output_shape=oshape,m=m,k=k,n=n,
                output_channel_tile=co_step,dense_jobs=jobs,MACs=m*k*n,packed_input_weight_output_bytes=staging,
                im2col_bytes=m*k,int32_output_bytes=m*n*4)
    rows.append(record)
    total=totals[ident.split('__')[0]]
    for name in ('dense_jobs','MACs','packed_input_weight_output_bytes'):total[name]+=record[name]
out=repo/'docs/validation/picture-p20-combined-20261020/dense-plan-bank64.json'
with out.open('x',encoding='utf-8') as f:
    json.dump(dict(scope='Static MAC workload for the shapes in the delivered dump example; NOT latency/board/full-graph acceptance',
        graph_sha256=hashlib.sha256((root/'integer_graph.json').read_bytes()).hexdigest(),
        dump_manifest_sha256=hashlib.sha256((root/'golden_dump_manifest.json').read_bytes()).hexdigest(),
        source_client_sha256=hashlib.sha256((repo/'linux/vision/xq_mac.c').read_bytes()).hexdigest(),
        tiling=dict(m=16,k=256,n='adaptive <=256; ceil(k/4)*ceil(n/32)<=64'),
        classifier_scope='Uses actual dump batch 211 candidate crops, not 32 pieces; candidate count changes per frame',
        totals=dict(totals),layers=rows),f,indent=2);f.write('\n')
print('P21_STATIC_DENSE_PLAN',json.dumps(dict(totals)))
