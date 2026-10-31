"""Prove equivalent pin packings and reject faults in the actual LSU load cone."""
from pathlib import Path
import argparse, hashlib, json, re, subprocess, sys
import audit_cpu_ads as a
from test_cpu_ads import change_init
from test_cpu_ads_pma import ADDRESSES, replace_module, expect_rejection


def permute(source, order, reindex):
    cell=a.Cone(source,'Lsu').primitive('N972')
    body=a.module_text(source,'Lsu')
    match=re.search(r'\\?'+re.escape(cell['instance'])+r'\s*\((.*?)\);',body,re.S)
    assert match
    ports=re.sub(r'\.I([0-4])\s*\(',lambda m:'.I'+str(order[int(m[1])])+' (',match[1])
    begin,end=match.span(1)
    result=replace_module(source,body,body[:begin]+ports+body[end:])
    if reindex:
        value=0
        for index in range(64):
            old=(index & 32) | sum(((index>>order[i])&1)<<i for i in range(5))
            value|=((cell['init']>>old)&1)<<index
        result=change_init(result,'Lsu','N972',value)
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--netlist',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();assert not args.output.exists()
    raw=args.netlist.read_bytes();source=raw.decode();proof=a.audit_pma_consumers(source,ADDRESSES)
    cell=a.Cone(source,'Lsu').primitive('N972')
    assert cell['type']=='GTP_LUT6D' and cell['output']=='Z5'
    controls={'io_dcUncached','aGo','uReload',a.PMA_LSU_SHARED}
    extra=set(cell['ports']['I'+str(i)] for i in range(5))-controls
    assert len(extra)==1;extra=extra.pop()
    producer=a.Cone(source,'Lsu').primitive(extra)
    assert producer['type']=='GTP_LUT4' and producer['init']==0xfffe
    base=subprocess.run([sys.executable,str(Path(__file__).with_name('test_cpu_ads_pma.py')),
                         '--netlist',str(args.netlist)],capture_output=True,text=True,timeout=180)
    assert base.returncode==0,(base.stdout,base.stderr)
    assert 'CPU_ADS_PMA_NEGATIVE_FIXTURES_PASS cases=5' in base.stdout
    permutations=[];faults=[]
    for shift in range(1,5):
        order=[(i+shift)%5 for i in range(5)]
        result=a.audit_pma_consumers(permute(source,order,True),ADDRESSES)
        assert result['consumer_cases']==proof['consumer_cases']
        permutations.append(order)
    order=[4,3,2,1,0]
    a.audit_pma_consumers(permute(source,order,True),ADDRESSES);permutations.append(order)
    expect_rejection('load_pin_permutation_without_init',permute(source,[1,2,3,4,0],False),
                     'Supervisor PMA load consumer mismatch')
    faults.append('load_pin_permutation_without_init')
    for bit in [0,3,7,19,31]:
        name='load_Z5_truth_bit_'+str(bit)
        expect_rejection(name,change_init(source,'Lsu','N972',cell['init']^(1<<bit)),
                         'Supervisor PMA load consumer mismatch')
        faults.append(name)
    expect_rejection('exception_OR_truth_corrupt',change_init(source,'Lsu',extra,producer['init']^1),
                     'Supervisor PMA load consumer wiring differs')
    faults.append('exception_OR_truth_corrupt')
    assert args.netlist.read_bytes()==raw
    args.output.parent.mkdir(parents=True,exist_ok=True)
    record=dict(status='NATIVE_LSU_LOAD_PIN_PACKING_AND_12_FAULTS_PASS_NOT_STA',
                netlist_sha256=hashlib.sha256(raw).hexdigest(),
                audit_script_sha256=hashlib.sha256(Path(a.__file__).read_bytes()).hexdigest(),
                test_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                positive=proof,load=cell,exception_OR=producer,
                equivalent_permutations=permutations,base_faults=5,additional_faults=faults,
                rejected_mutations=5+len(faults),base_output=base.stdout,
                architectural_load_oracle='reload OR (aGo AND MAT) OR (dcUncached AND NOT aGo); both extra-input cofactors')
    assert record['rejected_mutations']==12
    args.output.write_text(json.dumps(record,indent=2)+'\n')
    print(record['status'])


if __name__=='__main__':main()
