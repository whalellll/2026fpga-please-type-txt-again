"""Compare synthetic-vector RV32 outputs with the unchanged host C reference."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct

REPO=Path(__file__).resolve().parents[2]
SOURCE=REPO/'build/picture-p21-native/piece-fit-probe-r01'
DEST=REPO/'docs/validation/picture-p21-runtime-20261020/piece-fit-device-r01'

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def observations(text):
    return [line.split() for line in text.splitlines() if line.startswith('BINARY64 ')]

def number(bits):
    return struct.unpack('>d',bytes.fromhex(bits))[0]

def main():
    assert not DEST.exists(), 'Use a fresh archive'
    host_text=(SOURCE/'host-output.txt').read_text(encoding='utf-8')
    resumed=(SOURCE/'resume-plan.json').exists()
    if resumed:
        plan=json.loads((SOURCE/'resume-plan.json').read_text())
        assert plan['completed_cases']+plan['remaining_cases']==30
        prefix=(SOURCE/'rv32-completed-prefix.txt').read_text(encoding='utf-8')
        assert host_text.startswith(prefix)
        partial=SOURCE/'rv32-partial-output.txt'
        assert sha(partial)==plan['partial_output_sha256']
        assert partial.read_text(encoding='utf-8').startswith(prefix)
        assert sha(SOURCE/'remaining-vectors.tsv')==plan['remaining_vectors_sha256']
        assert len(re.findall(r'^PASS \d{4} ',prefix,re.M))==plan['completed_cases']
        remaining_host=(SOURCE/'host-remaining-output.txt').read_text(encoding='utf-8')
        board_text=(SOURCE/'rv32-remaining-output.txt').read_text(encoding='utf-8')
        assert 'PIECE_FIT_PROBE_RC=0' in (SOURCE/'board-remaining.log').read_text()
        pairs=[('completed_prefix',prefix,prefix),('remaining',remaining_host,board_text)]
        normalized=lambda rows:[row[:2]+row[3:] for row in rows]
        assert normalized(observations(prefix)+observations(remaining_host))==normalized(observations(host_text))
        remaining_ids=re.findall(r'^PASS (\d{4}) ',board_text,re.M)
        assert remaining_ids==plan['remaining_case_ids']
        expected_counts=[30,plan['remaining_cases'],plan['remaining_cases']]
        harness_outputs=[host_text,remaining_host,board_text]
    else:
        board_text=(SOURCE/'rv32-output.txt').read_text(encoding='utf-8')
        pairs=[('full',host_text,board_text)]
        expected_counts=[30,30];harness_outputs=[host_text,board_text]
    tolerance_pass=[]
    for text,expected in zip(harness_outputs,expected_counts):
        match=re.search(r'^(\d+)/(\d+) passed$',text,re.M)
        assert match and int(match[2])==expected
        tolerance_pass.append(match[1]==match[2])
    differences=[];compared=0;exact=0
    assert (SOURCE/'source-before.sha256').read_bytes()==(SOURCE/'source-after.sha256').read_bytes()
    for component,host_part,board_part in pairs:
        a,b=observations(host_part),observations(board_part)
        assert a and len(a)==len(b)
        for x,y in zip(a,b):
            # Keep status, call order and inlier count separate from FP values.
            count=5 if x[1]=='piece_fit' and x[3]=='0' else 4
            assert x[:count]==y[:count] and len(x)==len(y),(x[:count],y[:count])
            for index,(u,v) in enumerate(zip(x[count:],y[count:])):
                assert len(u)==len(v)==16
                compared+=1
                if u==v:exact+=1;continue
                differences.append(dict(component=component,operation=x[1],call=int(x[2]),value_index=index,
                                        host_hex=u,rv32_hex=v,host=number(u),rv32=number(v),
                                        absolute_difference=abs(number(u)-number(v))))
    result=dict(schema_version=1,
                status='BIT_EXACT_PASS' if not differences and all(tolerance_pass)
                       else 'BIT_EXACT_FAIL',
                stock_training_harness_cases=30,stock_host_tolerance_pass=tolerance_pass[0],
                stock_rv32_tolerance_pass=all(tolerance_pass),split_resume=resumed,
                compared_binary64_values=compared,exact_binary64_values=exact,
                mismatched_binary64_values=len(differences),
                maximum_absolute_difference=max((x['absolute_difference'] for x in differences),default=0),
                piece_fit_enabled=False,camera_inputs_used=False,
                note='Original C and tolerance-based training harness unchanged; no FP tolerance applied to bit comparison')
    DEST.mkdir()
    names=['source-before.sha256','source-after.sha256','elf-inspection.txt',
           'host-output.txt','SHA256SUMS.txt','board-run.log','board-run-r02.log']
    names+=['resume-plan.json','rv32-partial-output.txt','rv32-completed-prefix.txt',
            'host-remaining-output.txt','rv32-remaining-output.txt','remaining-vectors.tsv','board-remaining.log'] if resumed else ['rv32-output.txt']
    for name in names:
        shutil.copyfile(SOURCE/name,DEST/name)
    result['evidence_sha256']={p.name:sha(p) for p in DEST.iterdir()}
    (DEST/'differences.json').write_text(json.dumps(differences,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    (DEST/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
