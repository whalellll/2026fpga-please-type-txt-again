"""Validate observed PMA Z/Z5 export forms and semantic faults on real netlists."""
from pathlib import Path
import argparse,hashlib,json,re
from audit_cpu85_half_ads import prove_boundary
from audit_cpu_ads import module_text,Cone
from audit_icache_pad_ads import cells,clean

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--netlist',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();assert not a.output.exists();raw=a.netlist.read_bytes();source=clean(raw.decode())
    positive=prove_boundary(source);body=module_text(source,'PmaMmu');node=Cone(source,'PmaMmu').primitive('iResponse')
    assert node['type']=='GTP_LUT6D'
    cell=next(c for c in cells(body,'GTP_LUT6D') if c['name'].replace('\\','')==node['instance'])
    def once(text,old,new):
        assert text.count(old)==1;return text.replace(old,new,1)
    faults=[]
    # Every output truth bit must retain the same response equation. Invert
    # exactly the half used by the instruction-response output.
    pattern=r"(\.INIT\s*\(\s*64')([bh])([0-9a-fA-F_]+)"
    def flip(m):
        value=int(m[3].replace('_',''),2 if m[2]=='b' else 16)
        mask=(1<<32)-1 if node['output']=='Z5' else ((1<<64)-1)
        return m[1]+'h'+format(value^mask,'016x')
    changed,n=re.subn(pattern,flip,cell.group());assert n==1
    faults.append(('producer_response_inverted',once(source,body,once(body,cell.group(),changed))))
    # A corruption of the otherwise unused I4 cofactor must fail the Boolean
    # proof, even though the pin is unconnected in the native Z5 form.
    if node['output']=='Z5':
        def dependent(m):
            value=int(m[3].replace('_',''),2 if m[2]=='b' else 16)
            return m[1]+'h'+format(value^(1<<16),'016x')
        changed,n=re.subn(pattern,dependent,cell.group());assert n==1
        faults.append(('unconnected_i4_dependency',once(source,body,once(body,cell.group(),changed))))
    # Keep the actual parent wiring contract strict as well.
    ports_pattern=r'(\.iResponse\s*\(\s*)\\?u_pma/iResponse(\s*\))'
    changed,n=re.subn(ports_pattern,lambda m:m[1]+'wrong_pma_response'+m[2],source,count=1);assert n==1
    faults.append(('producer_consumer_binding_swapped',changed))
    rejected=[]
    for label,mutant in faults:
        assert mutant!=source
        try:prove_boundary(mutant)
        except (AssertionError,ValueError,KeyError) as e:
            rejected.append(dict(case=label,status='REJECTED',diagnostic=str(e),mutated_netlist_sha256=hashlib.sha256(mutant.encode()).hexdigest()))
        else:raise AssertionError('PMA fault escaped: '+label)
    assert a.netlist.read_bytes()==raw
    r=dict(status='ACTUAL_PMA_EXPORT_PRODUCER_COFACTOR_AND_BINDING_MUTATIONS_PASS_NOT_NEW_HARDWARE',positive=positive,faults=rejected,
        netlist_sha256=hashlib.sha256(raw).hexdigest(),sources_sha256={n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in ('audit_cpu85_half_ads.py','audit_cpu_ads.py','audit_icache_pad_ads.py','test_pma_direct_export_native_mutations.py')})
    a.output.write_text(json.dumps(r,indent=2)+'\n');print(r['status'],len(rejected))

if __name__=='__main__':main()
