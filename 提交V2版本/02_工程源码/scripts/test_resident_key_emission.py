"""Require the real emission-difference checker to reject unrelated changes."""
from pathlib import Path
import argparse,hashlib,json,re
from verify_resident_key_emission import audit,modules

class TextFixture:
    def __init__(self,text):self.text=text
    def read_text(self):return self.text

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
    old=a.before.read_bytes();new=a.after.read_bytes();old_text=a.before.read_text();text=a.after.read_text();parts=modules(a.after)
    positive=audit(a.before,a.after);faults=[]
    def replace_module(name,changed):
        assert changed!=parts[name] and text.count(parts[name])==1
        return text.replace(parts[name],changed,1)
    for name,target in [('Dispatch','io_rsMemPushSrc0Val_1'),('Rob','io_rdata_0'),('Rename','io_disValid_0')]:
        changed,count=re.subn(r'\bassign\s+'+target+r'\s*=.*?;',lambda _:f'assign {target} = 32\'h0;',parts[name],flags=re.S);assert count==1,(name,target,count)
        faults.append((name+'_effective_output_zeroed',replace_module(name,changed)))
    inst=re.search(r'\bRsMem\s+u_rs_mem\s*\(.*?\);',parts['CoreBackend'],re.S);assert inst
    changed,count=re.subn(r'(\.io_pushSrc0Val\s*\()[^()]+(\))',lambda m:m[1]+"32'h0"+m[2],inst[0]);assert count==1
    faults.append(('CoreBackend_operand_binding_zeroed',replace_module('CoreBackend',parts['CoreBackend'].replace(inst[0],changed,1))))
    rows=[]
    for label,mutant in faults:
        try:audit(TextFixture(old_text),TextFixture(mutant))
        except (AssertionError,ValueError,KeyError) as e:
            rows.append(dict(case=label,status='REJECTED',diagnostic=str(e),mutated_rtl_sha256=hashlib.sha256(mutant.encode()).hexdigest()))
        else:raise AssertionError('Emission scope fault escaped: '+label)
    assert a.before.read_bytes()==old and a.after.read_bytes()==new
    r=dict(status='EXACT_EMISSION_PRUNING_POSITIVE_AND4_UNRELATED_FUNCTIONAL_MUTATIONS_PASS',positive=positive,faults=rows,
        before_sha256=hashlib.sha256(old).hexdigest(),after_sha256=hashlib.sha256(new).hexdigest(),
        sources_sha256={n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in ('verify_resident_key_emission.py','test_resident_key_emission.py')},scope='In-memory fixtures only; emitted RTL never modified. Not sequential equivalence, native synthesis or STA.')
    a.output.write_text(json.dumps(r,indent=2)+'\n');print(r['status'])
if __name__=='__main__':main()
