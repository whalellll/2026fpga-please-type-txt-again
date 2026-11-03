"""Prove actual promoted dispatch read consumers under explicit WB-off cofactors."""
from pathlib import Path
import hashlib,itertools
from functools import lru_cache
from audit_rob_owner_ads import Hierarchy,RF_PATH,bits,signal,check
from ads_bdd import lut_inputs

class CofactorHierarchy(Hierarchy):
    @lru_cache(None)
    def canonical(self,path,wire):
        key=(path,signal(wire));visited=set()
        while True:
            check(key not in visited,'Port/alias cycle');visited.add(key)
            if key[1] in ("1'b0","1'b1"):return key
            kind,data=self.driver(*key)
            if kind!='alias':return key
            key=data
    @lru_cache(None)
    def driver(self,path,wire):
        wire=signal(wire);kind,_,_=self.context(path);c=self.module(kind)['cone']
        if wire in c.aliases:return 'alias',(path,c.aliases[wire])
        if wire in c.drivers:
            node,port=c.drivers[wire]
            if port=='Q':return 'free',None
            table,pins=lut_inputs(node,port)
            return 'lut',(table,tuple((path,pin) for pin in pins))
        mapped=self.parent_input(path,wire) or self.child_output(path,wire)
        return ('alias',mapped) if mapped else ('free',None)
    def evaluate(self,path,wire,values,cache=None,active=None):
        cache={} if cache is None else cache;active=set() if active is None else active
        key=self.canonical(path,wire);path,wire=key
        if key in values:return values[key]
        if key in cache:return cache[key]
        if wire in ("1'b0","1'b1"):return int(wire[-1])
        check(key not in active,'Combinational cycle');active.add(key)
        try:
            try:kind,data=self.driver(*key)
            except ValueError as e:
                if 'Unsupported combinational cell' not in str(e):raise
                kind,data='free',None
            if kind=='alias':answer=self.evaluate(*data,values,cache,active)
            elif kind=='free':answer=None
            else:
                table,pins=data;known=mask=0
                for i,pin in enumerate(pins):
                    value=self.evaluate(*pin,values,cache,active)
                    if value is not None:mask|=1<<i;known|=value<<i
                possible={(table>>index)&1 for index in range(1<<len(pins)) if index&mask==known}
                answer=possible.pop() if len(possible)==1 else None
            cache[key]=answer;return answer
        finally:active.remove(key)


def prove(source):
    h=CofactorHierarchy(source);rob=RF_PATH[:-1];backend=rob[:-1];rf=h.module('RobTagRegisterFile')['cone'];base={}
    for name in ('io_mduWb_valid','io_memFwd_valid'):
        check(h.module('Rob')['ports'].get(name)==('input',1),'Actual WB-valid input missing');base[rob,name]=0
    for inst in ('u_fu_alu0','u_fu_alu1'):
        path=backend+(inst,);kind,_,_=h.context(path);c=h.module(kind)['cone']
        matches=[wire for wire,(node,pin) in c.drivers.items() if pin=='Q' and node['name']=='exValid']
        check(len(matches)==1,'Actual ALU WB-valid FF missing');base[path,matches[0]]=0
    for wire,(node,port) in rf.drivers.items():
        if port=='Q' and wire.startswith(('resultOwner_','resultValid_')):base[RF_PATH,wire]=0
    rows=[];connections=[]
    dispatch=backend+('u_dispatch',)
    check(h.context(dispatch)[0]=='Dispatch','Actual dispatch consumer missing')
    for port in (0,2):
        name='io_robRdata_'+str(port)
        check(h.module('Dispatch')['ports'].get(name)==('input',32),'Actual dispatch read input missing')
        for bit in range(32):
            check(h.canonical(dispatch,name+'[%d]'%bit)==h.canonical(rob,'io_rdata_%d[%d]'%(port,bit)),'Actual dispatch/Rob read binding differs')
        connections.append(dict(consumer_path='/'.join(dispatch),consumer_port=name,producer_path='/'.join(rob),producer_port='io_rdata_'+str(port),bits=32))
    for lane,read,port in ((2,4,0),(4,2,2)):
        check(h.module('Rob')['ports'].get('io_rdata_'+str(port))==('output',32),'Actual Rob read output missing')
        count=0
        for tag,bank,valid,data in itertools.product(range(32),range(4),range(2),range(2)):
            values=dict(base);values.update({(rob,k):v for k,v in bits('io_raddr_'+str(port),tag,5).items()})
            values.update({(RF_PATH,k):v for k,v in bits('io_tagRead_'+str(lane),tag,5).items()})
            values[RF_PATH,'resultValid_'+str(tag)]=valid
            if bank:values[RF_PATH,'resultOwner_%d_reg[%d]'%(tag,bank)]=1
            for bank2 in range(4):values.update({(RF_PATH,k):v for k,v in bits('_resultBanks_%d_ext_R%d_data'%(bank2,read),0xffffffff if bank2==bank and data else 0,32).items()})
            canonical_values={}
            for key,value in values.items():
                k=h.canonical(*key);check(k not in canonical_values or canonical_values[k]==value,'Aliased conflicting stops');canonical_values[k]=value
            values=canonical_values;cache={}
            for bit in range(32):
                actual=h.evaluate(dispatch,'io_robRdata_%d[%d]'%(port,bit),values,cache)
                check(actual==int(valid and data),'Effective RF read mismatch '+repr((lane,port,tag,bank,valid,data,bit,actual)))
            count+=1
        rows.append(dict(tag_lane=lane,bank_read_port=read,consumer='Dispatch.io_robRdata_'+str(port),producer='Rob.io_rdata_'+str(port),checked_vectors=count,checked_data_bits=32,nonconstant_bits=32))
    return dict(status='PROMOTED_EFFECTIVE_ROB_READS_COFACTORED_WB_OFF_PASS_NOT_SEQ_OR_STA',reads=rows,consumer_connections=connections,consumer_connections_proved=True,unbound_values_are_free=True,all_output_cofactors_resolved=True,writeback_disabled=['Rob.io_mduWb_valid','Rob.io_memFwd_valid','FuAlu0.exValid_Q','FuAlu1.exValid_Q'],checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),scope='Two actual dispatch consumer inputs,64 data bits.512 vectors per read select one tag and one legal bank owner with all other valid/owner bits zero; selected bank data is all-zero/all-one. Current-cycle ALU/MDU/memory forwarding valid boundaries are forced off; other unbound signals are conservative free values. Every output resolves to valid AND selected data, proving all32 bits nonconstant within these cofactors. This is limited native mapping proof, not all tagLive/owner states, writeback priority, sequential equivalence, physical timing or board validation.')
