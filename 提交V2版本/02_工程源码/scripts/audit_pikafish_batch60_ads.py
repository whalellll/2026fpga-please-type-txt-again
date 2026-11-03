"""Compose actual RAS correlation and exported PMA page-fault proofs.

No edits to the unchanged CPU Boolean oracle. Follow actual hierarchy/ports,
prove all producer/consumer truth cases, then bridge only its two declared
instruction contexts. Unknown native leaves still fail.
"""
from pathlib import Path
import hashlib,itertools,json,sys
import audit_cpu_ads as original
import audit_voice_nnue75_ads as ras
PAGE='u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/N92'
RAW='u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/'

def prove_boundary(source):
    c=original.Cone(source,'CoreFrontend');p=original.Cone(source,'PmaMmu')
    ports=original.instance_ports
    assert ports(source,'CoreMemory','PmaMmu','u_pma')['N92']=='u_pma/N92'
    assert ports(source,'Core','CoreMemory','memory')['u_pma/N92']=='memory/u_pma/N92'
    assert ports(source,'Core','CoreFrontend','frontend')[PAGE]=='memory/u_pma/N92'
    producer=p.primitive('N92')
    pins=['_tlb_io_response_bits_pageFault','iTranslate','ownerData','ownerValid','tlb/kill','tlb/state_reg[4]']
    assert producer['type']=='GTP_LUT6' and producer['output']=='Z'
    assert [producer['ports']['I'+str(i)] for i in range(6)]==pins
    capture=c.primitive('fcFaults[7]')
    assert capture['type']=='GTP_DFF_E' and capture['init']==0 and capture['ports']['CLK']=='clock'
    target=capture['ports']['D'];consumer=c.primitive(target)
    assert consumer['type']=='GTP_LUT6D' and consumer['output'] in ('Z','Z5')
    assert consumer['ports']['I5']=="1'b1"
    required={PAGE,'io_ifu_pma_req','io_ifu_pma_vaddr[0]','io_ifu_pma_vaddr[1]'}
    actual={v for k,v in consumer['ports'].items() if k.startswith('I') and v not in ("1'b0","1'b1")}
    assert required<=actual and len(actual-required)==1
    extra=next(iter(actual-required));cases=0
    for values in itertools.product(range(2),repeat=6):
        pg,tr,data,valid,kill,response=values
        mapped=p.evaluate('N92',dict(zip(pins,values)))
        assert mapped==int(bool(pg and tr and not data and valid and not kill and response))
        for req,a0,a1,unrelated in itertools.product(range(2),repeat=4):
            v={PAGE:mapped,'io_ifu_pma_req':req,'io_ifu_pma_vaddr[0]':a0,'io_ifu_pma_vaddr[1]':a1,extra:unrelated}
            assert c.evaluate(target,v)==int(bool(mapped and req and not a0 and not a1))
            cases+=1
    return dict(status='NATIVE_PMA_PAGE_EXPORT_1024_CASES_PASS_NOT_STA',cases=cases,producer=producer,consumer=consumer,capture=capture)

def main():
    source=Path(sys.argv[1]).read_text();proof=prove_boundary(source);pma=original.Cone(source,'PmaMmu')
    def evaluate(self,target,values,cache=None,active=None):
        target=original.signal(target)
        if target==PAGE and target not in values:
            if RAW+'_tlb_io_response_bits_pageFault' in values:
                assert values[RAW+'_tlb_io_response_bits_pageFault']==1
                assert values[RAW+'iResponse']==values[RAW+'iTranslate']==1
                v=dict(zip(['_tlb_io_response_bits_pageFault','iTranslate','ownerData','ownerValid','tlb/kill','tlb/state_reg[4]'],[1,1,0,1,0,1]))
            else:
                assert values.get('io_instructionAccept')==1
                v=dict(zip(['_tlb_io_response_bits_pageFault','iTranslate','ownerData','ownerValid','tlb/kill','tlb/state_reg[4]'],[0,0,0,0,0,0]))
            return ras.BASE_EVALUATE(pma,'N92',v)
        return ras.evaluate(self,target,values,cache,active)
    original.bind_registered_frontend_controls=ras.bind
    original.Cone.evaluate=evaluate;original.Cone.primitive=ras.primitive
    try:original.main()
    finally:
        original.bind_registered_frontend_controls=ras.BASE_BIND
        original.Cone.evaluate=ras.BASE_EVALUATE;original.Cone.primitive=ras.BASE_PRIMITIVE
    output=Path(sys.argv[sys.argv.index('--output')+1]);record=json.loads(output.read_text());assert record['status']=='PASS'
    record['voice_nnue_ras_adapter']=dict(status='ACTUAL_RAS_PRODUCER_CORRELATION_AND_UNCHANGED_CPU_ORACLE_PASS',proofs=ras.PROOFS,adapter_sha256=hashlib.sha256(Path(ras.__file__).read_bytes()).hexdigest())
    record['pma_page_export_contract']=proof
    record['pma_page_adapter_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    record['batch_cpu_adapter_sha256']=record['pma_page_adapter_sha256']
    output.write_text(json.dumps(record,indent=2)+'\n')
    print('BATCH60_NATIVE_CPU_RAS_AND_PMA_EXPORT_PASS cases=1024')
if __name__=='__main__':main()
