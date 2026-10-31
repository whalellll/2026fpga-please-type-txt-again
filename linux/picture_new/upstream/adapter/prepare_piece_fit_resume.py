"""Retain completed original cases; derive an unchanged-case suffix for RV32."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

REPO=Path(__file__).resolve().parents[2]
OUT=REPO/'build/picture-p21-native/piece-fit-probe-r01'
VECTORS=REPO/'artifacts/vision-model-20261020-adapter/geometry_fallback/test_vectors/vectors.tsv'
host=(OUT/'host-output.txt').read_text(encoding='utf-8').splitlines()
board=(OUT/'rv32-partial-output.txt').read_text(encoding='utf-8').splitlines()
passed=[i for i,line in enumerate(board) if re.match(r'^PASS \d{4} ',line)]
assert passed
last=passed[-1];last_host=host.index(board[last])
host_prefix=host[:last_host+1];board_prefix=board[:last+1]
assert host_prefix==board_prefix,'Completed prefix has a numerical/control mismatch; do not resume as a pass'
blocks=re.split(r'(?=^CASE )',VECTORS.read_text(encoding='utf-8'),flags=re.M)
preamble=blocks.pop(0)
assert len(blocks)==30
done_ids=[re.match(r'^PASS (\d{4}) ',board[i])[1] for i in passed]
all_ids=[re.match(r'^CASE (\d+) ',block)[1].zfill(4) for block in blocks]
assert done_ids==all_ids[:len(done_ids)]
assert not (OUT/'resume-plan.json').exists()
suffix=OUT/'remaining-vectors.tsv'
assert not suffix.exists()
suffix.write_text(preamble+''.join(blocks[len(done_ids):]),encoding='utf-8')
prefix='\n'.join(board_prefix)+'\n'
(OUT/'rv32-completed-prefix.txt').write_text(prefix,encoding='utf-8')
with (OUT/'host-remaining-output.txt').open('x') as output:
    subprocess.run([str(OUT/'host-probe'),str(suffix)],stdout=output,check=True,timeout=30)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
plan=dict(original_vectors_sha256=sha(VECTORS),partial_output_sha256=sha(OUT/'rv32-partial-output.txt'),
          completed_cases=len(done_ids),completed_case_ids=done_ids,
          completed_prefix_bit_exact=True,remaining_cases=len(blocks)-len(done_ids),
          remaining_case_ids=all_ids[len(done_ids):],remaining_vectors_sha256=sha(suffix),
          note='No case content changed; completed cases are not rerun. Original timeout is retained.')
(OUT/'resume-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
print(json.dumps(plan,indent=2))
