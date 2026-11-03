"""Rejection tests only; synthetic mutations are never hardware acceptance."""
from pathlib import Path
import argparse,copy,json,tempfile,xml.etree.ElementTree as ET
from unittest.mock import patch
from zipfile import ZipFile
import verify_cpu80_delivery as v

ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args()
root=a.root.resolve();xml=(root/'artifacts/final_timing_xml.xml').read_bytes()
v.timing(xml);count=0
for name,table in [('negative_setup','report_timing_slow_setup'),('negative_fast_hold','report_timing_fast_hold')]:
    mutated=ET.fromstring(xml)
    target=next(t for t in mutated.findall('table') if t.get('id')==table)
    row=next(r for r in target.findall('row') if [d.text for d in r.findall('data')][:2]==['cpu_clk','cpu_clk'])
    row.findall('data')[2].text='-0.001';bad=ET.tostring(mutated)
    try:v.timing(bad)
    except ValueError:count+=1
    else:raise AssertionError('Accepted '+name)
original=v.read;board_path=root/v.BASE/'board/result.json';board=original(board_path)
for name,changes in [('missing_hdmi',dict(hdmi_visual='PENDING_USER_CONFIRMATION')),
                     ('wrong_bitstream',dict(bitstream_sha256='0'*64)),
                     ('performance_pending',dict(performance_nonregression_gate='RECHECK_REQUIRED'))]:
    changed=copy.deepcopy(board);changed.update(changes)
    with patch.object(v,'read',side_effect=lambda p:changed if Path(p)==board_path else original(p)):
        try:v.validate(root,'unused-host-gcc',inventory=False)
        except ValueError:count+=1
        else:raise AssertionError('Accepted '+name)
with tempfile.TemporaryDirectory(prefix='cpu80-zip-rejection-') as temp:
    q=Path(temp)/'unsafe.zip'
    with ZipFile(q,'w') as z:z.writestr('SOC/../escape.txt','synthetic only')
    try:v.check_zip(q)
    except ValueError:count+=1
    else:raise AssertionError('Accepted traversal')
assert count==6
print('CPU80_DELIVERY_POLICY_REJECTIONS_PASS cases=6 synthetic_only=true hardware_acceptance=false')
