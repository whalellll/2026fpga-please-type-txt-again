"""Check the real mapped cache and reject capacity, port and decoder mutations."""
from pathlib import Path
import argparse
import hashlib
import json
import re
from vision32_cache_contract import cache_contract


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--native-root', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    p = a.native_root/'pds/synthesize/soc_top_syn.vm'
    source = p.read_text()
    positive = cache_contract(source)
    first = re.search(r'GTP_RAM64X1DP\s*/\*\s*weight_lo_0_0\s*\*/[\s\S]*?;', source)[0]
    next_bank = re.search(r'GTP_RAM64X1DP\s*/\*\s*weight_lo_1_0\s*\*/[\s\S]*?;', source)[0]
    replacement_we = re.search(r'\.WE\s*\(([^)]+)\)', next_bank)[1]
    decoder_mutation = source
    for bit in range(32):
        block = re.search(r'GTP_RAM64X1DP\s*/\*\s*weight_lo_0_'+str(bit)+r'\s*\*/[\s\S]*?;', decoder_mutation)[0]
        mutated = re.sub(r'\.WE\s*\([^)]+\)', '.WE ('+replacement_we+')', block)
        decoder_mutation = decoder_mutation.replace(block, mutated, 1)
    variants = [source.replace(first, '', 1),
                source.replace(first, first.replace('mem_rsp_rdata[0]', 'mem_rsp_rdata[1]'), 1),
                source.replace(first, first.replace('.WCLK (clk)', '.WCLK (resetn)'), 1), decoder_mutation]
    if positive.get('weight_mapping')=='split_1024_128':
        tail=re.search(r'GTP_RAM64X1DP\s*/\*\s*weight_tail_hi_1_31\s*\*/[\s\S]*?;',source)[0]
        variants.append(source.replace(tail,'',1))
        for port,old,new in [('WADDR','load_index[6]','load_index[5]'),
                             ('RADDR','weight_ra[5]','weight_ra[4]')]:
            field=re.search(r'\.'+port+r'\s*\([^)]+\)',tail)[0]
            altered=tail.replace(field,field.replace(old,new))
            assert altered!=tail
            variants.append(source.replace(tail,altered,1))
        core_we=re.search(r'\.WE\s*\(([^)]+)\)',first)[1]
        tail_alias=source
        for bit in range(32):
            block=re.search(r'GTP_RAM64X1DP\s*/\*\s*weight_tail_lo_0_'+str(bit)+r'\s*\*/[\s\S]*?;',tail_alias)[0]
            altered=re.sub(r'\.WE\s*\([^)]+\)','.WE ('+core_we+')',block)
            tail_alias=tail_alias.replace(block,altered,1)
        variants.append(tail_alias)
    # Reject a wrong producer truth table and broken parent/child wiring,
    # including a consistent renaming that used to hide behind numeric names.
    from audit_cpu_ads import Cone
    from audit_icache_pad_ads import module
    if positive['native_read_boundary']['state_width']==6:
        vision_body=module(source,'vision32_layer')
        # A five-bit read decoder incorrectly accepts state41 as state9.
        # Remove the real high-bit qualification while retaining its flop.
        altered,count=re.subn(r'(\.I\d+\s*\()state\[5\](\))',r"\g<1>1'b0\2",vision_body)
        assert count>0 and altered!=vision_body
        variants.append(source.replace(vision_body,altered,1))
    boundary=positive['native_read_boundary']['export']
    producer=positive['native_read_boundary']['producer']
    target='u_mac_accel/g_vision32.u_vision32/'+boundary
    body=module(source,producer)
    node,_=Cone(body[body.index('module '):],producer).drivers[target]
    cell=next(x for x in __import__('audit_icache_pad_ads').cells(body,node['kind']) if x['name'].replace('\\','')==node['name'])
    raw=re.findall(r'\b'+re.escape(node['kind'])+r'\b[^;]*?\b'+re.escape(node['name'])+r'\s*\([^;]*?\);',body,re.S)
    assert len(raw)==1
    original=raw[0]
    altered=re.sub(r"(\.INIT\s*\(\s*\d+')[bh][0-9a-fA-F_]+",r'\g<1>h0',original)
    assert altered!=original
    # Identical primitive blocks can occur in other modules. Mutate the
    # producer's own module, otherwise this would edit an unrelated LUT.
    assert source.count(body)==1 and body.count(original)==1
    variants.append(source.replace(body,body.replace(original,altered,1),1))
    child_port='.'+boundary+' (\\g_vision32.u_vision32/'+boundary+' )'
    assert child_port in source
    variants.append(source.replace(child_port,'.'+boundary+" (1'b1)",1))
    producer_port='.\\'+target+'  (\\'+target+' )'
    assert producer_port in source
    variants.append(source.replace(producer_port,'.\\'+target+"  (1'b0)",1))
    for i, bad in enumerate(variants):
        try:
            cache_contract(bad)
        except AssertionError:
            continue
        raise AssertionError('Native cache mutation accepted: '+str(i))
    result = dict(status='VISION32_NATIVE_CACHE_PORTS_CAPACITY_DECODERS_AND_MUTATIONS_PASS_NOT_STA',
                  native_vm_sha256=hashlib.sha256(p.read_bytes()).hexdigest(), positive=positive,
                  rejected_mutations=len(variants), checker_sha256=hashlib.sha256(Path(__file__).with_name('vision32_cache_contract.py').read_bytes()).hexdigest())
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
