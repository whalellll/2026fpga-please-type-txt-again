"""Bind CPU75 prepared shifter registers in native ADS; not timing/board proof."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from audit_cpu_ads import Cone, signal

def audit(netlist, rtl, snapshot, checker):
    source=rtl.read_bytes();blob=netlist.read_bytes();identity=json.loads(snapshot.read_text())
    assert b'io_shiftSrcPrepared' in source and b'exShiftSrc' in source,'Prepared-shift source profile missing'
    assert identity['inputs']['rtl/cpu/CoreTop.sv']==hashlib.sha256(source).hexdigest(),'RTL snapshot mismatch'
    assert identity['inputs']['scripts/audit_cpu_prepared_shift_ads.py']==hashlib.sha256(checker.read_bytes()).hexdigest(),'Checker snapshot mismatch'
    text=blob.decode()
    instances=re.findall(r'(?m)^\s*(FuAlu(?:_unq\d+)?)\s+(\\[^\s]+|\w+)\s*\(',text)
    assert len(instances)==2 and {signal(n).split('/')[-1] for _,n in instances}=={'u_fu_alu0','u_fu_alu1'},('Expected two FU-ALUs',instances)
    targets=[f'exShiftSrc[{i}]' for i in range(32)]+['exShiftSign']+[f'exShiftAmount[{i}]' for i in range(5)]
    rows=[]
    for module,instance in instances:
        c=Cone(text,module);unique=set()
        for target in targets:
            resolved=target;seen=set()
            while resolved in c.aliases and resolved not in seen:seen.add(resolved);resolved=c.aliases[resolved]
            assert resolved in c.drivers,('Prepared operand register missing',module,target,resolved)
            item=c.primitive(resolved)
            assert item['type'].startswith('GTP_DFF') and item['output']=='Q' and item['ports']['CLK']=='clock',('Prepared operand not a CPU register',module,target,item)
            assert item['instance'] not in unique,('Prepared bits share a register',module,target)
            unique.add(item['instance'])
            rows.append({'fu_instance':signal(instance),'fu_module':module,'target':target,'resolved':resolved,**item})
        body=re.search(r'(?ms)^module '+re.escape(module)+r'\b.*?^endmodule',text).group()
        child=re.findall(r'\bAlu(?:_unq\d+)?\s+(?:\\[^\s]+|\w+)\s*\((.*?)\);',body,re.S)
        assert len(child)==1,('Expected one ALU child per FU',module)
        ports={name:signal(value) for name,value in re.findall(r'\.(\w+)\s*\(([^()]*)\)',child[0])}
        for name,value in [('io_shiftSrcPrepared','exShiftSrc'),('io_shiftSignPrepared','exShiftSign'),('io_shiftAmountPrepared','exShiftAmount')]:
            assert ports.get(name)==value,('ALU prepared operand binding mismatch',module,name,ports.get(name))
    return {'status':'PREPARED_SHIFT_ADS_PASS_NOT_STA_OR_BOARD','run_id':identity['run_id'],'register_bits_per_fu':38,'fu_instances':2,'total_register_bits':76,
      'netlist_sha256':hashlib.sha256(blob).hexdigest(),'rtl_sha256':hashlib.sha256(source).hexdigest(),'input_snapshot_sha256':hashlib.sha256(snapshot.read_bytes()).hexdigest(),'checker_sha256':hashlib.sha256(checker.read_bytes()).hexdigest(),'registers':rows,
      'scope':'Native ADS register retention and child binding only. Source cycle equivalence, routed timing, physical retention and board performance are separate.'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['netlist','rtl','input-snapshot','output']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();record=audit(a.netlist,a.rtl,a.input_snapshot,Path(__file__))
    a.output.write_text(json.dumps(record,indent=2)+'\n');print('PREPARED_SHIFT_NATIVE_ADS_PASS bits=76 NOT_STA_OR_BOARD')
if __name__=='__main__':main()
