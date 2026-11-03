"""Prove the three generated parent changes only remove unused key wiring."""
from pathlib import Path
import argparse,hashlib,json,re

def modules(p):return {m[1]:m[0] for m in re.finditer(r'(?ms)^module\s+(\w+).*?^endmodule',p.read_text())}
def body(text):return text.split(');',1)[1]
def normalized(text):return re.sub(r'\s+','',text)
def ports(text):
    header=text.split('(',1)[1].split(');',1)[0];result={};direction=width=None
    for item in header.split(','):
        m=re.fullmatch(r'\s*(?:(input|output|inout)\s+)?(\[\d+:\d+\]\s*)?(\w+)\s*',item)
        assert m,('Unknown generated port',item)
        if m[1]:direction=m[1];width=m[2] or ''
        elif m[2]:width=m[2]
        assert direction is not None
        result[m[3]]=(direction,normalized(width))
    return result
def audit(before,after):
    a=modules(before);b=modules(after);assert a.keys()==b.keys() and len(a)==64
    changed=[n for n in sorted(a) if a[n]!=b[n]]
    assert changed==['CoreBackend','Dispatch','Rob','RsMem'],changed
    reports=[]
    for name,removed in [('Rob',{'io_rdataNoAlu_0','io_rdataNoAlu_1'}),
        ('Dispatch',{'io_robRdataNoAlu_0','io_robRdataNoAlu_1','io_rsMemPushSrc0KeyVal_0','io_rsMemPushSrc0KeyVal_1','io_rsMemPushSrc0RobWait_0','io_rsMemPushSrc0RobWait_1'})]:
        pa,pb=ports(a[name]),ports(b[name]);assert set(pa)-set(pb)==removed and not set(pb)-set(pa)
        assert all(pa[n]==pb[n] for n in pb)
        old=body(a[name]);new=body(b[name]);assigns=removed-{'io_robRdataNoAlu_0','io_robRdataNoAlu_1'}
        for signal in sorted(assigns):
            old,count=re.subn(r'\bassign\s+'+signal+r'\s*=.*?;', '',old,flags=re.S);assert count==1,(name,signal,count)
        if name=='Dispatch':
            old,count=re.subn(r'\bwire\s+\[31:0\]\s+s0KeyVal_1\s*=.*?;', '',old,flags=re.S);assert count==1
        assert normalized(old)==normalized(new),name+' has a change beyond removed key assignments'
        reports.append(dict(module=name,removed_ports=sorted(removed),remaining_ports_and_body_equal_after_exact_unused_assignment_removal=True))
    assert ports(a['CoreBackend'])==ports(b['CoreBackend'])
    old=body(a['CoreBackend']);new=body(b['CoreBackend'])
    wire_pattern=r'\bwire\s+(?:\[\d+:\d+\]\s+)?(_u_rob_io_rdataNoAlu_[01]|_u_dispatch_io_rsMemPushSrc0(?:KeyVal|RobWait)_[01])\s*;'
    old,count=re.subn(wire_pattern,'',old);assert count==6,count
    connection_pattern=r'(?m)^\s*\.io_(?:rdataNoAlu_[01]|robRdataNoAlu_[01]|rsMemPushSrc0(?:KeyVal|RobWait)_[01]|push(?:1)?Src0(?:KeyVal|RobWait))\s*\([^()]*\),?\s*$'
    old,count=re.subn(connection_pattern,'',old);assert count==12,count
    assert normalized(old)==normalized(new),'CoreBackend has a change beyond removed key port bindings'
    reports.append(dict(module='CoreBackend',removed_wire_declarations=6,removed_child_port_bindings=count,remaining_interface_and_body_equal=True))
    assert a['RobTagRegisterFile']==b['RobTagRegisterFile'],'Original RF must remain byte-identical'
    return dict(status='RESIDENT_KEY_PARENT_PRUNING_EXACT_REMAINDER_PASS_NOT_SEQUENTIAL_PROOF_OR_STA',
        modules=64,changed_generated_modules=changed,byte_identical_modules=60,behavior_changed_module='RsMem',pruning_only=reports,
        scope='Exact port dictionary and normalized body comparison after only the listed deleted unused signals, assignments and child bindings. RsMem behavior and timing are separately tested.')
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
    r=audit(a.before,a.after);r.update(before_sha256=hashlib.sha256(a.before.read_bytes()).hexdigest(),after_sha256=hashlib.sha256(a.after.read_bytes()).hexdigest(),checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    a.output.write_text(json.dumps(r,indent=2)+'\n');print(r['status'])
if __name__=='__main__':main()
