"""Actual effective consumer LUT depth after exact WB-off cofactoring, not STA."""
from pathlib import Path
import sys,json,hashlib
from functools import lru_cache
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from audit_rob_promoted_reads_ads import CofactorHierarchy,RF_PATH,check

def analyze(source):
    h=CofactorHierarchy(source);rob=RF_PATH[:-1];backend=rob[:-1];dispatch=backend+('u_dispatch',);values={};anchors={}
    for name in ('io_mduWb_valid','io_memFwd_valid'):values[h.canonical(rob,name)]=0
    for inst in ('u_fu_alu0','u_fu_alu1'):
        path=backend+(inst,);kind,_,_=h.context(path);matches=[q for q,(n,p) in h.module(kind)['cone'].drivers.items() if p=='Q' and n['name']=='exValid'];check(len(matches)==1,'Actual WB FF missing');values[h.canonical(path,matches[0])]=0
    rf=h.module('RobTagRegisterFile')['cone']
    for q,(node,port) in rf.drivers.items():
        if port=='Q' and q.startswith(('resultValid_','resultOwner_')):anchors[h.canonical(RF_PATH,q)]='valid_q' if q.startswith('resultValid_') else 'owner_q'
    for lane,read in ((2,4),(4,2)):
        for bit in range(5):anchors[h.canonical(RF_PATH,'io_tagRead_%d[%d]'%(lane,bit))]='read_address'
        for bank in range(4):
            for bit in range(32):anchors[h.canonical(RF_PATH,'_resultBanks_%d_ext_R%d_data[%d]'%(bank,read,bit))]='ram_data'
    cache={};active=set()
    @lru_cache(None)
    def depth(context,wire):
        key=h.canonical(context,wire);context,wire=key
        if key in anchors:return {anchors[key]:0}
        if key in values or wire in ("1'b0","1'b1"):return {}
        known=h.evaluate(context,wire,values,cache)
        if known is not None:return {}
        check(key not in active,'Combinational cycle');active.add(key)
        try:
            kind,data=h.driver(*key)
            if kind=='free':return {'other_boundary':0}
            check(kind=='lut','Unexpected alias after canonicalization')
            table,pins=data;fixed={i:h.evaluate(*pin,values,cache) for i,pin in enumerate(pins)};fixed={i:v for i,v in fixed.items() if v is not None}
            allowed=[i for i in range(1<<len(pins)) if all((i>>b)&1==v for b,v in fixed.items())]
            support=[i for i in range(len(pins)) if i not in fixed and any(((table>>n)^(table>>(n^(1<<i))))&1 for n in allowed)]
            result={}
            for i in support:
                for name,d in depth(*pins[i]).items():result[name]=max(result.get(name,0),d+1)
            return result
        finally:active.remove(key)
    rows=[]
    for port in (0,2):
        check(h.module('Dispatch')['ports'].get('io_robRdata_'+str(port))==('input',32),'Actual consumer missing')
        for bit in range(32):rows.append(dict(port=port,bit=bit,depth_by_leaf_class=depth(dispatch,'io_robRdata_%d[%d]'%(port,bit))))
    protected={}
    for kind,prefixes in {'Rename':('disS0RobidR','disS1RobidR'),'RsMem':('pairKeyA','s0ValA','s0KeyRefreshA'),'Rob':('memShadowRobid',)}.items():
        c=h.module(kind)['cone'];protected[kind]=sorted((n['name'],q) for q,(n,p) in c.drivers.items() if p=='Q' and n['name'].startswith(prefixes));check(protected[kind],'Missing protected pipeline FFs')
    return dict(status='ACTUAL_PROMOTED_CONSUMER_COFACTOR_LUT_DEPTH_NOT_ROUTED_TIMING',rows=rows,max_depth={k:max(x['depth_by_leaf_class'].get(k,0) for x in rows) for k in ('owner_q','valid_q','read_address','ram_data','other_boundary')},protected_named_ff_outputs=protected,scope='Actual Dispatch.io_robRdata_0/2 consumer inputs,64 bits; exact current-WB-off cofactors. RF address, legal state FFs and actual bank RAM outputs are boundaries. Local+promoted truth-supported LUT depth excludes routing/placement, fanout delay and non-dispatch paths.')
if __name__=='__main__':
    p=Path(sys.argv[1]);out=Path(sys.argv[2]);assert not out.exists();raw=p.read_bytes();q=analyze(raw.decode());assert p.read_bytes()==raw
    q.update(netlist_sha256=hashlib.sha256(raw).hexdigest(),checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest());out.write_text(json.dumps(q,indent=2)+'\n');print(json.dumps(dict(status=q['status'],max_depth=q['max_depth'],protected_counts={k:len(v) for k,v in q['protected_named_ff_outputs'].items()})))
