import argparse,hashlib,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--expected',type=Path,required=True);p.add_argument('--actual',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
p.add_argument('--partial',action='store_true');a=p.parse_args()
if a.out.exists():raise FileExistsError(a.out)
expected=json.loads(a.expected.read_text());payload=a.actual.read_text();lines=payload.splitlines();assert lines[0]=='XQ_NATIVE_CHECKS_V1'
if a.partial and not payload.endswith('\n'):lines=lines[:-1]
rows={}
for line in lines[1:]:
    s=line.split();assert len(s) in (7,11) and len(s)==len(expected['rows'][0])
    row=[*map(int,s[:3]),*[int(x,16) for x in s[3:7]],*s[7:]];assert row[0] not in rows;rows[row[0]]=row
assert rows and set(rows)<=set(range(80)),len(rows)
if not a.partial:assert set(rows)==set(range(80)),len(rows)
differences=[dict(layer=e[0],expected=e,actual=rows[e[0]]) for e in expected['rows'] if e[0] in rows and rows[e[0]]!=e]
complete=len(rows)==80
result=dict(status=('PASS' if complete else 'PARTIAL') if not differences else 'FAIL',layers=len(rows),complete=complete,
    missing_layers=sorted(set(range(80))-set(rows)),tensors_per_layer=4,differences=differences,
    fields=['layer','input_elements','output_elements','input_S8_CRC','accumulator_I32_CRC','preactivation_S16_CRC','output_as_I16_CRC',
            'input_SHA256','accumulator_SHA256','preactivation_SHA256','output_as_I16_SHA256'][:len(next(iter(rows.values())))],
    actual_sha256=hashlib.sha256(a.actual.read_bytes()).hexdigest(),source_dump_manifest_sha256=expected['source_dump_manifest_sha256'])
a.out.write_text(json.dumps(result,indent=2)+'\n');print('GOLDEN_80_CHECKS',result['status'],'differences',len(differences));assert not differences
