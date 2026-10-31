"""Release gate faults reject altered consent, identity, arithmetic and limits."""
from copy import deepcopy
from pathlib import Path
import json
from verify_cpu80_approved import approved_contract

root=Path(__file__).resolve().parents[1]
a=json.loads((root/'docs/validation/cpu80-audio-service-20261022/board-repair/release-approval-20261022.json').read_text(encoding='utf-8-sig'))
c=a['coremark_per_mhz']['candidate'];p=a['coremark_per_mhz']['control']
approved_contract(a,c,p)
cases=[]
for key,value in [('exact_user_text','unapproved'),('run_id','wrong'),('bitstream_sha256','0'*64),
                  ('kernel_sha256','0'*64),('loader_sha256','0'*64),('coremark_total_required',True)]:
    r=deepcopy(a);r[key]=value;cases.append((key,r,c,p))
for key,value in [('limit',.1),('passed',False),('candidate',c+.01),('control',p+.01),('absolute_decrease',0)]:
    r=deepcopy(a);r['coremark_per_mhz'][key]=value;cases.append((key,r,c,p))
for name,cv,pv in [('over-budget',p-.051,p),('nan',float('nan'),p),('infinite',float('inf'),p),('negative',-1,p)]:
    cases.append((name,deepcopy(a),cv,pv))
for name,r,cv,pv in cases:
    try:approved_contract(r,cv,pv)
    except (ValueError,KeyError):continue
    raise AssertionError('Altered release contract accepted: '+name)
print('CPU80_APPROVED_CONTRACT_PASS valid=1 rejected='+str(len(cases)))
