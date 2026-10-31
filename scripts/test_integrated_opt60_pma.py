"""Fault-test actual direct or folded PMA wiring without changing the CPU oracle."""
from pathlib import Path
import argparse, hashlib, json, re
import audit_cpu85_half_ads as adapter
from audit_icache_pad_ads import module

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--netlist',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    o=a.output.resolve();o.mkdir(parents=True,exist_ok=False)
    source=a.netlist.read_text();proof=adapter.prove_boundary(source);faults={}
    def mutate(kind,node,value):
        body=module(source,kind)
        pattern=r"(\.INIT\(64'b)([01]{64})(\)\)\s*\n\s*\\?"+re.escape(node['instance'])+r'\s*\()'
        matches=list(re.finditer(pattern,body));assert len(matches)==1,(kind,node['instance'])
        m=matches[0];bits=value(m[2]);assert len(bits)==64 and bits!=m[2]
        altered=body[:m.start(2)]+bits+body[m.end(2):]
        assert source.count(body)==1
        return source.replace(body,altered,1)
    for name,kind,node,transform in [
        ('producer_zero','PmaMmu',proof['producer'],lambda b:'0'*64),
        ('producer_reachable_flip','PmaMmu',proof['producer'],lambda b:b[:31]+str(1-int(b[31]))+b[32:]),
        ('consumer_zero','CoreFrontend',proof['consumer'],lambda b:'0'*64),
        ('consumer_reachable_flip','CoreFrontend',proof['consumer'],lambda b:b[:31]+str(1-int(b[31]))+b[32:])]:
        mutant=mutate(kind,node,transform)
        try:adapter.prove_boundary(mutant)
        except (AssertionError,ValueError,KeyError) as e:faults[name]=dict(rejected=True,error=type(e).__name__)
        else:raise AssertionError('PMA mutation accepted: '+name)
    body=module(source,'Core');pin=adapter.RAW+'iResponse' if proof.get('variant')=='direct_three_bound_exports' else adapter.PAGE
    marker='.'+'\\'+pin;assert body.count(marker)==1
    mutant=source.replace(body,body.replace(marker,'.\\detached_instruction_response',1),1)
    try:adapter.prove_boundary(mutant)
    except (AssertionError,ValueError,KeyError) as e:faults['disconnected_hierarchy']=dict(rejected=True,error=type(e).__name__)
    else:raise AssertionError('Disconnected PMA export accepted')
    assert source==a.netlist.read_text()
    record=dict(status='INTEGRATED_OPT60_NATIVE_PMA_1024_CASES_AND_FIVE_FAULTS_PASS_NOT_STA',proof=proof,faults=faults,
                netlist_sha256=hashlib.sha256(a.netlist.read_bytes()).hexdigest(),adapter_sha256=hashlib.sha256(Path(adapter.__file__).read_bytes()).hexdigest())
    (o/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(record['status'])
if __name__=='__main__':main()
