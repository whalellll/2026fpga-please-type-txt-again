"""Native RAS producer/consumer faults must reject before the CPU oracle runs."""
from pathlib import Path
import argparse,copy,hashlib,json
import audit_voice_nnue75_ads as adapter
import audit_cpu_ads as original
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--native',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
source=a.native.read_text();cone=original.Cone(source,'CoreFrontend');proof=adapter.bind(cone,source)
assert proof['truth_cases']==96
ret=proof['return_selector'];call=proof['native_call_target'];push=proof['push_target'];faults=[]
def clone():
    c=copy.deepcopy(cone)
    for node,_ in c.drivers.values():node['support']={}
    return c
for bit in [0,2,4,6]:
    c=clone();c.drivers[call][0]['init']^=1<<bit;faults.append(('producer-found-bypass-'+str(bit),c,source))
for bit in [22,30]:
    c=clone();c.drivers[push][0]['init']^=1<<bit;faults.append(('consumer-reachable-bit-'+str(bit),c,source))
c=clone();node=c.drivers[call][0]
for pin,value in node['ports'].items():
    if value=='found':node['ports'][pin]='trainValid'
faults.append(('producer-found-disconnected',c,source))
for name,c,s in faults:
    try:adapter.bind(c,s)
    except (AssertionError,ValueError):continue
    raise AssertionError('Native RAS fault accepted: '+name)
result=dict(status='VOICE_NNUE75_NATIVE_RAS_ADAPTER_FAULTS_PASS_NOT_STA_OR_BOARD',native_sha256=hashlib.sha256(a.native.read_bytes()).hexdigest(),
            adapter_sha256=hashlib.sha256(Path(adapter.__file__).read_bytes()).hexdigest(),positive_cases=96,rejected=[f[0] for f in faults])
a.output.write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
