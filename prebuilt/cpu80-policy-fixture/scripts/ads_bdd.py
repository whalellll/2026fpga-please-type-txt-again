"""Small exact ROBDD engine for native LUT-cone equivalence, with a node bound."""
from functools import lru_cache
import re

class BDD:
    def __init__(self,variables,limit=200000):
        self.order={v:i for i,v in enumerate(variables)}
        self.nodes=[None,None];self.unique={};self.limit=limit
    def node(self,var,low,high):
        if low==high:return low
        key=(var,low,high)
        if key not in self.unique:
            if len(self.nodes)>=self.limit:raise ValueError('BDD node bound exceeded')
            self.unique[key]=len(self.nodes);self.nodes.append(key)
        return self.unique[key]
    def var(self,name):
        if name not in self.order:raise ValueError('Unknown cone leaf '+name)
        return self.node(self.order[name],0,1)
    @lru_cache(None)
    def ite(self,cond,yes,no):
        if cond==1:return yes
        if cond==0:return no
        if yes==no:return yes
        if yes==1 and no==0:return cond
        top=min(self.nodes[n][0] for n in [cond,yes,no] if n>1)
        def split(n,side):return self.nodes[n][side] if n>1 and self.nodes[n][0]==top else n
        return self.node(top,self.ite(split(cond,1),split(yes,1),split(no,1)),
                         self.ite(split(cond,2),split(yes,2),split(no,2)))
    def inv(self,value):return self.ite(value,0,1)
    def land(self,a,b):return self.ite(a,b,0)
    def lor(self,a,b):return self.ite(a,1,b)

def lut_inputs(node,port):
    if node['kind'] in ['GTP_MUX2LUT7','GTP_MUX2LUT8'] and port=='Z':
        return 0xca,[node['ports'][p] for p in ['I0','I1','S']]
    lut=re.fullmatch(r'GTP_LUT([1-6])(D)?',node['kind'])
    if not lut:raise ValueError('Unsupported combinational cell '+node['kind']+'/'+port)
    width=5 if port=='Z5' else int(lut[1]);init=node['init']
    fixed_mask=fixed_value=0
    for i in range(width):
        name=node['ports']['I'+str(i)]
        if name in ["1'b0","1'b1"]:
            fixed_mask|=1<<i;fixed_value|=int(name[-1])<<i
    allowed=[n for n in range(1<<width) if n&fixed_mask==fixed_value]
    support=[i for i in range(width) if not fixed_mask&(1<<i) and
        any(((init>>n)^(init>>(n^(1<<i))))&1 for n in allowed)]
    table=0
    for choice in range(1<<len(support)):
        original=fixed_value|sum(((choice>>n)&1)<<i for n,i in enumerate(support))
        table|=((init>>original)&1)<<choice
    return table,[node['ports']['I'+str(i)] for i in support]

def cone_leaves(c,targets):
    active=set()
    @lru_cache(None)
    def walk(net):
        if net in ["1'b0","1'b1"]:return frozenset()
        if net in active:raise ValueError('Combinational cycle '+net)
        active.add(net)
        try:
            if net in c.aliases:return walk(c.aliases[net])
            if net not in c.drivers or c.drivers[net][1]=='Q':return frozenset([net])
            node,port=c.drivers[net];_,pins=lut_inputs(node,port)
            result=set()
            for name in pins:result.update(walk(name))
            return frozenset(result)
        finally:active.remove(net)
    result=set()
    for target in targets:result.update(walk(target))
    return result

def cone_evaluator(c,bdd):
    active=set()
    @lru_cache(None)
    def walk(net):
        if net=="1'b0":return 0
        if net=="1'b1":return 1
        if net in active:raise ValueError('Combinational cycle '+net)
        active.add(net)
        try:
            if net in c.aliases:return walk(c.aliases[net])
            if net not in c.drivers or c.drivers[net][1]=='Q':return bdd.var(net)
            node,port=c.drivers[net];table,names=lut_inputs(node,port)
            pins=[walk(n) for n in names]
            def apply(value,width):
                if value==0:return 0
                if value==(1<<(1<<width))-1:return 1
                half=1<<(width-1);mask=(1<<half)-1
                return bdd.ite(pins[width-1],apply(value>>half,width-1),apply(value&mask,width-1))
            return apply(table,len(pins))
        finally:active.remove(net)
    return walk

def metadata_expected(bdd,bits):
    def eq(indices,value):
        result=1
        for n,i in enumerate(indices):result=bdd.land(result,bits[i] if (value>>n)&1 else bdd.inv(bits[i]))
        return result
    jal=eq(range(7),0x6f)
    jalr=bdd.land(eq(range(7),0x67),eq(range(12,15),0))
    ret=bdd.land(bdd.land(jalr,eq(range(7,12),0)),bdd.lor(eq(range(15,20),1),eq(range(15,20),5)))
    call=bdd.land(bdd.lor(jal,jalr),bdd.lor(eq(range(7,12),1),eq(range(7,12),5)))
    return {'Returns':ret,'Calls':call}
