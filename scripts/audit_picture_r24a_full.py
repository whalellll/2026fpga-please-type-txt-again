"""Hash-complete intake and range checks for the adjudicated full package.
No training/export script, photograph, sealed dataset or per-frame attribution
is executed. Frame summaries are reduced to per-module range diagnostics.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import struct

ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--delivery',type=Path,default=ROOT/'build/training_side_r24a_full')
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();assert not a.output.exists()
    manifest=a.delivery/'MANIFEST.sha256';entries={};folded=set()
    for line in manifest.read_text(encoding='utf-8-sig').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):continue
        digest,name=line.split(maxsplit=1);name=name.lstrip('*')
        relative=Path(name)
        assert re.fullmatch('[0-9a-f]{64}',digest) and not relative.is_absolute() and '..' not in relative.parts
        assert name.casefold() not in folded;folded.add(name.casefold())
        assert (a.delivery/relative).resolve().is_relative_to(a.delivery.resolve())
        assert sha(a.delivery/relative)==digest,name
        entries[relative.as_posix()]=digest
    actual={p.relative_to(a.delivery).as_posix() for p in a.delivery.rglob('*') if p.is_file()}
    assert actual==set(entries)|{'MANIFEST.sha256'},'Manifest coverage mismatch'
    summary=json.loads((a.delivery/'perlayer_3frames/detector_perlayer_3frames.json').read_text())
    models=ROOT/'build/picture-merge-20261023/native-models'
    native=json.loads((models/'native_manifest.json').read_text())['models']['detector']
    raw=(models/'detector.xqm').read_bytes();assert sha(models/'detector.xqm')==native['sha256']
    h=struct.unpack_from('<10I',raw,8);offset=48+(16 if h[0]==2 else 0)
    nodes=[struct.unpack_from('<32i',raw,offset+i*128) for i in range(h[2])]
    shapes={native['labels'][i]:list(n[1:4]) for i,n in enumerate(nodes) if n[0]==1}
    rows=[]
    for layer in summary['layers']:
        values=[float(v['absmax']) for v in layer['per_frame'].values()]
        assert values and all(math.isfinite(v) and v>=0 for v in values)
        maximum=max(values)
        exponent=math.ceil(math.log2(maximum/32767)) if maximum else -15
        bound=32767*2.0**exponent
        assert maximum<=bound
        if maximum:assert maximum>32767*2.0**(exponent-1)
        path=layer['module_path']
        label='detector__'+path.removesuffix('.conv').replace('.','_')
        expected_shape=shapes.get(label) if layer['kind']=='conv' else None
        rows.append({'module_path':path,'kind':layer['kind'],'shape':layer['shape'],
            'absmax_over_three_summaries':maximum,'required_s16_exponent':exponent,
            'delivered_common_exponent':layer['s16_exponent_common'],
            'delivered_exponent_matches_range':exponent==layer['s16_exponent_common'],
            'all_minus14_metadata_would_exceed_s16_range':maximum>32767*2.0**-14,
            'frozen_conv_shape':expected_shape,
            'frozen_shape_equal':layer['shape']==[1,*expected_shape] if expected_shape else None})
    assert len(rows)==summary['n_layers'] and sum(r['kind']=='conv' for r in rows)==summary['n_conv']
    rule=ROOT/'docs/PictureNew_全整数图_r24a_full裁定_20261025.md'
    result={'status':'R24A_FULL_MANIFEST_AND_SUMMARY_RANGE_CHECK_PASS_NOT_INTEGER_GRAPH_ACCEPTANCE',
        'manifest_sha256':sha(manifest),'files':entries,'payload_count':len(entries),
        'adjudication_sha256':sha(rule),'hardware_used':False,'preview_scripts_executed':False,
        'photographs_or_dataset_opened':False,'detector_switch_enabled':False,
        'claimed_156_of_178_accepted':False,'classifier_integration_authorized':True,
        'classifier_training_reference_8_of_8':'Accepted as measured by user-supplied adjudication; not extrapolated to178',
        'range_check':{'summary_frames':len(summary['frames']),'rows':rows,
            'exponent_histogram':dict(Counter(row['required_s16_exponent'] for row in rows)),
            'ranges_inconsistent_with_delivered_common':sum(not row['delivered_exponent_matches_range'] for row in rows),
            'minus14_would_overflow_rows':sum(row['all_minus14_metadata_would_exceed_s16_range'] for row in rows),
            'conv_shape_mismatch_rows':sum(row['frozen_shape_equal'] is False for row in rows)},
        'limitations':'shape+absmax summaries are not raw integer tensors or independent per-layer exactness evidence. '
                      'Derived exponents are range diagnostics, never replacements of frozen conv input/output scales. '
                      'Detector mode/selection waits for r24b exact-int64 empirical release.'}
    assert all(sha(a.delivery/name)==digest for name,digest in entries.items())
    a.output.mkdir(parents=True);(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'],'payloads=',len(entries),'rows=',len(rows),
          'minus14_overflow_rows=',result['range_check']['minus14_would_overflow_rows'])


if __name__=='__main__':main()
