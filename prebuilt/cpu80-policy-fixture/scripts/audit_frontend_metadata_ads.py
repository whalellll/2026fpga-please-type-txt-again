#!/usr/bin/env python3
"""Audit eight existing-edge frontend metadata FF and exact 20-bit LUT truth tables.

Standalone native logic proof; it does not establish final STA or board performance.
Unknown leaves, cross-lane dependencies or non-LUT combinational cells reject.
"""
import argparse,hashlib,json
from pathlib import Path
from functools import lru_cache
import re

def patterns(width):
    count=1<<width; mask=(1<<count)-1
    return mask,[mask//((1<<(1<<i))+1)<<(1<<i) for i in range(width)]

def evaluate(c,target,values,mask):
    active=set()
    @lru_cache(None)
    def walk(net):
        if net in values:return values[net]
        if net=="1'b0":return 0
        if net=="1'b1":return mask
        if net in active:raise ValueError('Combinational cycle '+net)
        active.add(net)
        try:
            if net in c.aliases:return walk(c.aliases[net])
            if net not in c.drivers:raise ValueError('Unknown input '+net)
            node,port=c.drivers[net]
            lut=re.fullmatch(r'GTP_LUT([1-6])(D)?',node['kind'])
            if not lut:raise ValueError('Unsupported '+node['kind']+'/'+port+' at '+net)
            width=5 if port=='Z5' else int(lut[1]);init=node['init']
            fixed_mask=fixed_value=0
            for i in range(width):
                name=node['ports']['I'+str(i)]
                if name in ["1'b0","1'b1"]:
                    fixed_mask|=1<<i;fixed_value|=int(name[-1])<<i
            allowed=[n for n in range(1<<width) if n&fixed_mask==fixed_value]
            support=[i for i in range(width) if not fixed_mask&(1<<i) and
                any(((init>>n)^(init>>(n^(1<<i))))&1 for n in allowed)]
            pins=[walk(node['ports']['I'+str(i)]) for i in support]
            result=0
            for choice in range(1<<len(support)):
                original=fixed_value|sum(((choice>>n)&1)<<i for n,i in enumerate(support))
                if not (init>>original)&1:continue
                term=mask
                for n,value in enumerate(pins):term&=value if (choice>>n)&1 else mask^value
                result|=term
            return result
        finally:active.remove(net)
    return walk(target)

def expected(mask,bits):
    def eq(indices,value):
        out=mask
        for n,i in enumerate(indices):out&=bits[i] if (value>>n)&1 else mask^bits[i]
        return out
    jal=eq(range(7),0x6f)
    jalr=eq(range(7),0x67)&eq(range(12,15),0)
    ret=jalr&eq(range(7,12),0)&(eq(range(15,20),1)|eq(range(15,20),5))
    call=(jal|jalr)&(eq(range(7,12),1)|eq(range(7,12),5))
    return {'Returns':ret,'Calls':call}

def audit_metadata(c):
    from ads_bdd import BDD,cone_leaves,cone_evaluator,metadata_expected
    nodes={node['name']:node for node,port in c.drivers.values()}
    ffs={node['ports']['Q']:node for node in nodes.values() if node['kind'].startswith('GTP_DFF')}
    flags=[n for n in ffs if re.fullmatch(r'pd(Returns|Calls)_\d',n)]
    assert len(flags)==8,'Expected eight metadata FF, got '+str(flags)
    results=[]
    for lane in range(4):
        ds=[]
        for bit in range(20):
            ff=ffs['pdInsts_%d[%d]'%(lane,bit)]
            assert ff['ports']['CLK']=='clock' and ff['ports']['CE']=='fcToPd','Instruction capture clock/enable mismatch'
            ds.append(ff['ports']['D'])
        leaves=cone_leaves(c,ds)
        def order(name):
            data='line' in name.lower() or bool(re.fullmatch(r'D\d+_\d+',name))
            indices=re.findall(r'\d+',name)
            return (int(data),int(indices[-1])%32 if indices else -1,name)
        variables=sorted(leaves,key=order)
        bdd=BDD(variables);walk=cone_evaluator(c,bdd)
        want=metadata_expected(bdd,[walk(d) for d in ds])
        for flag in ['Returns','Calls']:
            ff=ffs['pd%s_%d'%(flag,lane)]
            assert ff['ports']['CLK']=='clock','Metadata capture clock mismatch'
            assert ff['ports']['CE']=='fcToPd','Metadata capture enable mismatch'
            actual=walk(ff['ports']['D'])
            assert actual==want[flag],(lane,flag,'Native D function differs from instruction-D decode')
            results.append({'lane':lane,'flag':flag,'ff':ff['name'],'Q':ff['ports']['Q'],'D':ff['ports']['D'],
                'CLK':ff['ports']['CLK'],'CE':ff['ports']['CE'],'instruction_classes':1<<20,
                'arbitrary_boolean_leaves':len(variables),'bdd_nodes':len(bdd.nodes),
                'variable_order_sha256':hashlib.sha256('\n'.join(variables).encode()).hexdigest(),
                'equivalent_for_all_leaf_assignments':True})
    return {'status':'PASS','proof':'ROBDD equality of complete native D cones over all source leaves; no input-MUX cut assumption',
            'instruction_classes_per_lane':1<<20,'results':results}

def main():
    from audit_cpu_ads import Cone
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('netlist',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();raw=args.netlist.read_bytes()
    result=audit_metadata(Cone(raw.decode(),'CoreFrontend'))
    assert args.netlist.read_bytes()==raw,'Netlist changed during audit'
    result.update(netlist_sha256=hashlib.sha256(raw).hexdigest(),
        checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='Eight metadata FF same clock/enable as instruction FF; complete native D cone equivalence over all raw Boolean source leaves, not routed timing or board performance.')
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print('FRONTEND_METADATA_ADS_PASS flags=8 cases_per_lane=1048576')
if __name__=='__main__':main()
