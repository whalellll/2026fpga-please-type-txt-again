"""Reject altered repair identities and proofs without touching native files."""
from pathlib import Path
import argparse,copy,hashlib,json,shutil
from verify_sdboot_native import validate,read,sha

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--root',type=Path,required=True);p.add_argument('--work',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
original=validate(a.root,a.work)
fixture=a.output/'synthetic-rejection-fixture';fixture.mkdir()
names=['flow.json','soc-freeze.json','zero-stage.log','full-soc.log','native-map-audit/result.json','native-map-audit/fold-ads-proof.json']
for n in names:
    dst=fixture/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(a.work/n,dst)
before={n:sha(a.work/n) for n in names}
cases=[('unfinished_flow','flow.json',lambda m:m.update(status='NATIVE_BUILD_RUNNING'),'Native repair flow incomplete'),
       ('wrong_run','flow.json',lambda m:m.update(run_id='0'*32),'Native run mismatch'),
       ('wrong_image','flow.json',lambda m:m.update(bitstream_sha256='0'*64),'Wrong repaired bitstream'),
       ('changed_freeze','soc-freeze.json',lambda m:m['inputs'].update({'sw/bootloader/sd_boot_load.h':'0'*64}),'Implementation freeze differs'),
       ('wrong_mapped_image','native-map-audit/result.json',lambda m:m['candidate'].update(netlist_sha256='0'*64),'Folded audit bound to another VM'),
       ('incomplete_affine_proof','native-map-audit/fold-ads-proof.json',lambda m:m.update(independent_input_bits=511),'Affine proof differs')]
results=[]
for label,name,change,expected in cases:
    path=fixture/name;raw=path.read_bytes();m=read(path);change(m);path.write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
    try:
        try:validate(a.root,fixture)
        except ValueError as e:
            assert str(e)==expected,(label,str(e));results.append(dict(case=label,rejected=str(e)))
        else:raise AssertionError('Altered native evidence accepted: '+label)
    finally:path.write_bytes(raw)
assert before=={n:sha(a.work/n) for n in names},'Native evidence changed'
assert validate(a.root,a.work)==original
record=dict(status='REPAIRED_ROM_NATIVE_GATE_POSITIVE_AND_SIX_REJECTIONS_PASS_NOT_BOARD',native=original,cases=results,
            verifier_sha256=sha(Path(__file__).with_name('verify_sdboot_native.py')),test_sha256=sha(Path(__file__)),
            scope='Only copied JSON fixtures were changed; native sources, bitstream and evidence remained read-only. No device access.')
(a.output/'result.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(record['status'])
