"""Read-only intake: bind preview claims to frozen r14 packs without executing
the preview's recalibration/export code or opening any photographs/dataset."""
import argparse
from collections import Counter
import json
from pathlib import Path
import struct
import check_picture_integer_graph as common


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--delivery',type=Path,default=common.ROOT/'build/training_side_r24a')
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();assert not a.output.exists()
    delivery={p.relative_to(a.delivery).as_posix():common.sha(p) for p in a.delivery.rglob('*') if p.is_file()}
    directory=common.ROOT/'build/picture-merge-20261023/native-models'
    pinned=dict(line.split()[::-1] for line in (common.ROOT/'linux/picture_new/r14-models.sha256').read_text().splitlines())
    labels=json.loads((directory/'native_manifest.json').read_text())['models']
    result={'status':'PREVIEW_NOT_DEPLOYABLE_BINDINGS_PENDING','hardware_used':False,
            'preview_executed':False,'training_delivery_sha256':delivery,'models':{},
            'preview_inventory':json.loads((a.delivery/'node_inventory.json').read_text()),
            'uncovered_operator_types':[],
            'findings':[
                'No XQGRPH2 binary graphs or per-nonconv n[27] metadata delivered; export_v2.py writes exponent JSON templates.',
                'Preview classifier recalibrates on eight random samples and calls quantize_model; this cannot replace frozen r14.',
                'Preview classifier computes predictions before its separate integer GAP demo; gap_real is printed but not fed into the linear head.',
                'Preview classifier capture references outer-loop node instead of a per-layer bound node; exponent capture is not a trusted trace.',
                'Preview V2Node concat copies branches without exponent reconciliation and has no concrete _conv_forward implementation.',
                'Primitive-node mapping/weight hashes are missing from node_inventory; upsample mode conflicts with frozen packs require resolution.',
            ],
            'required':'Node-level graph/weight/quantization binding, actual v2 exporter/reference, formal LUT and trace/selection-set release.'}
    names={1:'conv_or_linear',3:'sigmoid',4:'maxpool',5:'nearest',6:'bilinear',7:'concat',8:'add',9:'gap',10:'identity',11:'relu'}
    for name in ['board','detector','classifier']:
        path=directory/(name+'.xqm');assert common.sha(path)==pinned[path.name]
        raw=path.read_bytes();h=struct.unpack_from('<10I',raw,8);off=48+(16 if h[0]==2 else 0)
        nodes=[struct.unpack_from('<32i',raw,off+i*128) for i in range(h[2])]
        assert len(labels[name]['labels'])==len(nodes) and labels[name]['sha256']==pinned[path.name]
        meta=json.loads((a.delivery/'v2_export'/(name+'_v2_exponents.json')).read_text())
        comparisons=[]
        for i,n in enumerate(nodes):
            if n[0]!=1:
                continue
            label=labels[name]['labels'][i];preview=meta.get(label)
            comparisons.append({'node':i,'label':label,'layer':n[9], 'frozen_input_exponent':n[18],
                'frozen_output_exponent':n[19],'preview':preview,
                'equal_if_treated_as_frozen_conv_parameters':bool(preview and
                    preview['input_exponent']==n[18] and preview['output_exponent']==n[19])})
        result['models'][name]={
            'frozen_pack_sha256':pinned[path.name],'primitive_node_counts':dict(Counter(names[n[0]] for n in nodes)),
            'linear_count':sum(n[0]==1 and n[25] for n in nodes),
            'upsample_nodes':[{'index':i,'mode':names[n[0]],'label':labels[name]['labels'][i]} for i,n in enumerate(nodes) if n[0] in (5,6)],
            'preview_exponents_distribution':dict(Counter(f'{v["input_exponent"]}/{v["output_exponent"]}' for v in meta.values())),
            'conv_parameter_comparison':comparisons,
            'matched_frozen_conv_parameters':sum(v['equal_if_treated_as_frozen_conv_parameters'] for v in comparisons)}
    assert all(common.sha(a.delivery/n)==h for n,h in delivery.items())
    a.output.mkdir(parents=True)
    result['script_sha256']=common.sha(Path(__file__))
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])
    for name,m in result['models'].items():
        print(name,m['primitive_node_counts'],'matching_frozen_exponents=',m['matched_frozen_conv_parameters'])


if __name__=='__main__':
    main()
