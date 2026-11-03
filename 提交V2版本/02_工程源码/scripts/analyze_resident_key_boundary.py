"""Inspect mapped key FF inputs for live dispatch/WB data; not arithmetic proof."""
from pathlib import Path
from functools import lru_cache
from collections import Counter
import hashlib,json,re,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'scripts/gui1080_mul')]
from native_hier_cone_vector_v2 import VectorHierCone
from audit_cpu_ads import signal
from audit_icache_pad_ads import cells,ports
from ads_bdd import lut_inputs

def analyze(source):
    class BoundaryCone(VectorHierCone):
        @lru_cache(None)
        def ram_outputs(self,ctx):
            kind=self.contexts[ctx][0];result=set()
            for primitive,outputs in [('GTP_RAM32X2DP',('DO',)),('GTP_DRM18K_E1',('DOA','DOB')),('GTP_APM_E2',('P',))]:
                for cell in cells(self.modules[kind],primitive):
                    pin=ports(cell['ports'])
                    for output in outputs:
                        if pin.get(output):result.update(self.vector_bits(ctx,pin[output]))
            return result
        def canonical(self,ctx,net,active=None):
            net=signal(net)
            if (ctx,net) in cut_classes or net in self.ram_outputs(ctx):return ctx,net
            return super().canonical(ctx,net,active)
    cut_classes={};h=BoundaryCone(source,root='CoreTop');ctx=h.find('RsMem');kind=h.contexts[ctx][0];c=h.cone(kind)
    assert ctx==('core','backend','u_rs_mem'),ctx
    for name,direction in h.directions(kind).items():
        promoted_data=bool(re.search(r'/(?:_u_rename_io_dis(?:Imm|Src[01]Val)_[01]|u_dispatch/s[01]Val_[01])$',name))
        promoted_control=bool(re.search(r'/(?:_u_\w+_io_(?:disFire|disValid|disSrc[01]Ready|rrdy|wbValid)(?:_\d+)?|u_dispatch/(?:s[01]Ready_\d+|memSingleFrom1))$',name))
        if direction!='input' or not (name.startswith('io_') or name in ('clock','reset','s0Wbdat_matches_0') or promoted_data or promoted_control):continue
        raw=bool(promoted_data or re.fullmatch(r'io_push(?:1)?(?:Src[01](?:Key)?Val|Imm)',name) or re.fullmatch(r'io_wb_\d+_bits_data',name))
        for bit in h.vector_bits(ctx,name):cut_classes[ctx,bit]='RAW_DATA_INPUT' if raw else 'DECLARED_CONTROL_INPUT'
    key_ff={q:n for q,(n,p) in c.drivers.items() if p=='Q' and n['name'].startswith('pairKeyA_')}
    assert len(key_ff)==32,('Expected two retained16-bit used key slices',len(key_ff))
    active=set()
    @lru_cache(None)
    def walk(context,net):
        key=h.canonical(context,net);context,net=key
        if net in ("1'b0","1'b1"):return frozenset(),0
        if key in cut_classes:return frozenset([(cut_classes[key],'/'.join(context),net)]),0
        if net in h.ram_outputs(context):return frozenset([('RAM_OR_APM_DATA','/'.join(context),net)]),0
        assert key not in active,('Combinational cycle',key)
        node,port=h.cone(h.contexts[context][0]).drivers[net]
        if port=='Q':return frozenset([('FF_Q','/'.join(context),net)]),0
        active.add(key)
        try:
            _,pins=lut_inputs(node,port);leaves=set();depth=0
            for pin in pins:
                sub,d=walk(context,pin);leaves.update(sub);depth=max(depth,d+1)
            return frozenset(leaves),depth
        finally:active.remove(key)
    results=[]
    for q,node in sorted(key_ff.items()):
        leafset=set();depth=0
        for pin in ('D','CE','R','S'):
            if pin not in node['ports']:continue
            leaves,d=walk(ctx,node['ports'][pin]);leafset.update(leaves);depth=max(depth,d)
        forbidden=sorted(x for x in leafset if x[0] in ('RAW_DATA_INPUT','RAM_OR_APM_DATA'))
        results.append(dict(q=q,instance=node['name'],max_truth_supported_lut_depth=depth,forbidden_same_edge_data_leaves=forbidden,
            registered_data_leaves=sorted(x for x in leafset if x[0]=='FF_Q'),control_input_count=sum(x[0]=='DECLARED_CONTROL_INPUT' for x in leafset)))
    forbidden=[(x['q'],y) for x in results for y in x['forbidden_same_edge_data_leaves']]
    return dict(status='RESIDENT_KEY_NO_SAME_EDGE_RAW_DATA_BOUNDARY_OBSERVED' if not forbidden else 'SAME_EDGE_RAW_DATA_REACHES_KEY_FF',
        key_ff_count=32,results=results,forbidden_count=len(forbidden),max_local_plus_promoted_lut_depth=max(x['max_truth_supported_lut_depth'] for x in results),
        scope='Actual key FF D/CE/R/S truth-supported cones cross promoted aliases/ports until FF Q or explicit RsMem interface cuts. Declared control inputs are free boundaries. Live push values, immediates, WB data and RAM/APM outputs are forbidden. Macro outputs are conservative opaque boundaries; internal macro registers are not inferred. This does not prove the arithmetic, sequential semantics or physical timing.')

if __name__=='__main__':
    p=Path(sys.argv[1]);out=Path(sys.argv[2]);assert not out.exists();raw=p.read_bytes();r=analyze(raw.decode())
    assert p.read_bytes()==raw;r.update(netlist_sha256=hashlib.sha256(raw).hexdigest(),checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    out.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:r[k] for k in ('status','key_ff_count','forbidden_count','max_local_plus_promoted_lut_depth')}))
