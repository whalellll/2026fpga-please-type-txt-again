"""Resolve the actual exported PMA page-fault term, then run the unchanged CPU audit.

This adapter is for a newly observed ADS shape. It does not edit the locked
CPU Boolean evaluator or assign arbitrary values to unknown native inputs.
"""
from pathlib import Path
import hashlib,itertools,json,sys
import audit_cpu_ads as original

PAGE='u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/N92'
RAW='u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/'

def prove_direct_boundary(source):
    c=original.Cone(source,'CoreFrontend');p=original.Cone(source,'PmaMmu')
    ports=original.instance_ports
    for leaf in ('_tlb_io_response_bits_pageFault','iResponse','iTranslate'):
        assert ports(source,'CoreMemory','PmaMmu','u_pma')[leaf]=='u_pma/'+leaf
        assert ports(source,'Core','CoreMemory','memory')['u_pma/'+leaf]=='memory/u_pma/'+leaf
        assert ports(source,'Core','CoreFrontend','frontend')[RAW+leaf]=='memory/u_pma/'+leaf
    ff=c.primitive('fcFaults[7]');assert ff['type']=='GTP_DFF_E' and ff['init']==0 and ff['ports']['CLK']=='clock'
    target=ff['ports']['D'];consumer=c.primitive(target);producer=p.primitive('iResponse')
    assert consumer['type']=='GTP_LUT6' and consumer['output']=='Z'
    assert [consumer['ports']['I'+str(i)] for i in range(6)]==[
        RAW+'_tlb_io_response_bits_pageFault',RAW+'iResponse',RAW+'iTranslate',
        'io_ifu_pma_req','io_ifu_pma_vaddr[0]','io_ifu_pma_vaddr[1]']
    assert producer['type']=='GTP_LUT6D' and producer['output']=='Z' and producer['ports']['I5']=="1'b1"
    pins=['ownerData','ownerValid','tlb/kill','tlb/state_reg[4]','dTranslate']
    assert [producer['ports']['I'+str(i)] for i in range(5)]==pins
    cases=0
    for values in itertools.product(range(2),repeat=6):
        data,valid,kill,response,extra,tr=values
        mapped=p.evaluate('iResponse',dict(zip(pins,values[:5])))
        assert mapped==int(bool(not data and valid and not kill and response))
        for pg,req,a0,a1 in itertools.product(range(2),repeat=4):
            v={RAW+'_tlb_io_response_bits_pageFault':pg,RAW+'iResponse':mapped,RAW+'iTranslate':tr,
               'io_ifu_pma_req':req,'io_ifu_pma_vaddr[0]':a0,'io_ifu_pma_vaddr[1]':a1}
            assert c.evaluate(target,v)==int(bool(pg and mapped and tr and req and not a0 and not a1));cases+=1
    return dict(status='NATIVE_PMA_PAGE_EXPORT_1024_CASES_PASS_NOT_STA',cases=cases,
                variant='direct_three_bound_exports',producer=producer,consumer=consumer,capture=ff)

def prove_boundary(source):
    if PAGE not in original.instance_ports(source,'Core','CoreFrontend','frontend'):
        return prove_direct_boundary(source)
    c=original.Cone(source,'CoreFrontend');p=original.Cone(source,'PmaMmu')
    ports=original.instance_ports
    # These are actual connected parent wires, not inferred from instance names.
    assert ports(source,'CoreMemory','PmaMmu','u_pma')['N92']=='u_pma/N92'
    assert ports(source,'Core','CoreMemory','memory')['u_pma/N92']=='memory/u_pma/N92'
    assert ports(source,'Core','CoreFrontend','frontend')[PAGE]=='memory/u_pma/N92'
    node=p.primitive('N92');pins=['_tlb_io_response_bits_pageFault','iTranslate','ownerData','ownerValid','tlb/kill','tlb/state_reg[4]']
    assert node['type']=='GTP_LUT6' and node['output']=='Z'
    assert [node['ports']['I'+str(i)] for i in range(6)]==pins
    ff=c.primitive('fcFaults[7]');assert ff['type']=='GTP_DFF_E' and ff['init']==0 and ff['ports']['CLK']=='clock'
    target=ff['ports']['D'];consumer=c.primitive(target)
    assert consumer['type']=='GTP_LUT6D' and consumer['ports']['I5']=="1'b1"
    if consumer['output']=='Z5':
        assert consumer['ports']['I1']==PAGE and consumer['ports']['I2']=='io_ifu_pma_req'
        assert consumer['ports']['I3']=='io_ifu_pma_vaddr[0]' and consumer['ports']['I4']=='io_ifu_pma_vaddr[1]'
        unrelated=consumer['ports']['I0'];variant='page_on_I1_Z5'
    else:
        # Combined vision/voice mapping places the same term on LUT6 Z.
        # Require the exact observed wiring and prove the complete truth table.
        assert consumer['output']=='Z' and consumer['ports']['I0']==PAGE
        assert consumer['ports']['I1']=='io_ifu_pma_req'
        assert consumer['ports']['I2']=='io_ifu_pma_vaddr[0]' and consumer['ports']['I3']=='io_ifu_pma_vaddr[1]'
        unrelated=consumer['ports']['I4'];variant='page_on_I0_Z'
    cases=0
    for values in itertools.product(range(2),repeat=6):
        pg,tr,data,valid,kill,response=values
        mapped=p.evaluate('N92',dict(zip(pins,values)))
        assert mapped==int(bool(pg and tr and not data and valid and not kill and response))
        for req,a0,a1,extra in itertools.product(range(2),repeat=4):
            v={PAGE:mapped,'io_ifu_pma_req':req,'io_ifu_pma_vaddr[0]':a0,'io_ifu_pma_vaddr[1]':a1,unrelated:extra}
            assert c.evaluate(target,v)==int(bool(mapped and req and not a0 and not a1))
            cases+=1
    return dict(status='NATIVE_PMA_PAGE_EXPORT_1024_CASES_PASS_NOT_STA',cases=cases,variant=variant,producer=node,consumer=consumer,capture=ff)

def scoped_evaluator(source,evaluate):
    if PAGE not in original.instance_ports(source,'Core','CoreFrontend','frontend'):
        prove_direct_boundary(source)
        return evaluate
    pma=original.Cone(source,'PmaMmu')
    def scoped(self,target,values,cache=None,active=None):
        target=original.signal(target)
        if target==PAGE and target not in values:
            # The old audit fixes translation-disabled instruction accesses,
            # and separately checks an accepted instruction page-fault response.
            # Here both contexts are evaluated through the proven actual LUT.
            if RAW+'_tlb_io_response_bits_pageFault' in values:
                assert values[RAW+'_tlb_io_response_bits_pageFault']==1
                assert values[RAW+'iResponse']==values[RAW+'iTranslate']==1
                v={'_tlb_io_response_bits_pageFault':1,'iTranslate':1,'ownerData':0,'ownerValid':1,'tlb/kill':0,'tlb/state_reg[4]':1}
            else:
                assert values.get('io_instructionAccept')==1
                v={'_tlb_io_response_bits_pageFault':0,'iTranslate':0,'ownerData':0,'ownerValid':0,'tlb/kill':0,'tlb/state_reg[4]':0}
            return evaluate(pma,'N92',v)
        return evaluate(self,target,values,cache,active)
    return scoped

def main():
    netlist=Path(sys.argv[1]);source=netlist.read_text();proof=prove_boundary(source)
    evaluate=original.Cone.evaluate
    original.Cone.evaluate=scoped_evaluator(source,evaluate)
    try:original.main()
    finally:original.Cone.evaluate=evaluate
    output=Path(sys.argv[sys.argv.index('--output')+1]);record=json.loads(output.read_text())
    assert record['status']=='PASS'
    record['pma_page_export_contract']=proof
    record['pma_page_adapter_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    output.write_text(json.dumps(record,indent=2)+'\n')
    print('CPU85_PMA_PAGE_EXPORT_ACTUAL_PRODUCER_AND_CONSUMER_PASS cases='+str(proof['cases']))

if __name__=='__main__':main()
