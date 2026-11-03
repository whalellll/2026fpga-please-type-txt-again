"""Read-only proof of IB RF metadata at native RAM write/read boundaries.

The Boolean oracle is scoped to this RV32IMA M/S/U profile. It proves metadata
against each bank's actual instruction DI after rotation, without cutting its
input mux. It does not prove the complete CPU or routed timing.
"""
import argparse,hashlib,json,re,sys
from pathlib import Path
from collections import Counter
from audit_cpu_ads import Cone,signal
from audit_icache_pad_ads import module,cells,ports,clean
from ads_bdd import BDD,cone_leaves,cone_evaluator
from ads_frontend_ib_cone import bind

CSR=(0x100,0x104,0x105,0x106,0x10a,0x140,0x141,0x142,0x143,0x144,0x180,
     0x300,0x301,0x302,0x303,0x304,0x305,0x306,0x30a,0x310,0x31a,0x320,
     0x340,0x341,0x342,0x343,0x344,0xb00,0xb02,0xb80,0xb82,
     0xc00,0xc01,0xc02,0xc80,0xc81,0xc82,0xf11,0xf12,0xf13,0xf14,0xf15,
     *range(0x3a0,0x3a4),*range(0x3b0,0x3c0))

def expand(value,widths):
    value=signal(value)
    if value.startswith('{') and value.endswith('}'):
        return [b for part in value[1:-1].split(',') for b in expand(part,widths)]
    m=re.fullmatch(r"(\d+)'([bh])([0-9a-fA-FxX_]+)",value)
    if m:
        if 'x' in m[3].lower():return ["1'bx"]*int(m[1])
        n=int(m[3].replace('_',''),2 if m[2]=='b' else 16)
        return ["1'b"+str((n>>i)&1) for i in reversed(range(int(m[1])))]
    m=re.fullmatch(r'(.+)\[(\d+):(\d+)\]',value)
    if m:return [f'{m[1]}[{i}]' for i in range(int(m[2]),int(m[3])-1,-1)]
    if '[' in value:return [value]
    return [f'{value}[{i}]' for i in reversed(range(widths[value]))] if value in widths and widths[value]>1 else [value]

def expected(bdd,inst):
    def AND(*args):
        out=1
        for a in args:out=bdd.land(out,a)
        return out
    def OR(*args):
        out=0
        for a in args:out=bdd.lor(out,a)
        return out
    def eq(lo,hi,n):return AND(*(inst[i] if (n>>(i-lo))&1 else bdd.inv(inst[i]) for i in range(lo,hi+1)))
    op=lambda n:eq(0,6,n);f3=lambda n:eq(12,14,n);f7=lambda n:eq(25,31,n)
    nz=bdd.inv(eq(7,11,0))
    arithmetic=OR(AND(op(0x13),OR(*(f3(n) for n in [0,2,3,4,6,7]),AND(f3(1),f7(0)),AND(f3(5),OR(f7(0),f7(32))))),
                  AND(op(0x33),OR(f7(0),f7(1),AND(f7(32),OR(f3(0),f3(5))))))
    atomic=AND(op(0x2f),f3(2),OR(AND(eq(27,31,2),eq(20,24,0)),*(eq(27,31,n) for n in [3,0,1,4,8,12,16,20,24,28])))
    ordinary=AND(nz,OR(op(0x37),op(0x17),op(0x6f),AND(op(0x67),f3(0)),arithmetic,AND(op(3),OR(*(f3(n) for n in [0,1,2,4,5]))),atomic))
    write=OR(eq(12,13,1),bdd.inv(eq(15,19,0)))
    csr=AND(nz,op(0x73),OR(*(f3(n) for n in [1,2,3,5,6,7])),OR(*(eq(20,31,n) for n in CSR)),bdd.inv(AND(write,eq(30,31,3))))
    counter=AND(eq(28,31,12),eq(22,26,0),bdd.inv(eq(20,21,3)))
    return [ordinary,csr,eq(20,31,0x180),counter]

def audit(source):
    for parent,kind,instance in [('soc_top','core_top','u_cpu'),('core_top','cpu_core_top','u_cpu_wrapper'),('cpu_core_top','CoreTop','u_cpu'),('CoreTop','Core','core'),('Core','CoreFrontend','frontend'),('CoreFrontend','InstBuffer','buffer')]:
        found=cells(module(source,parent),kind)
        assert len(found)==1 and found[0]['name']==instance,'Unknown actual hierarchy '+parent
    body=module(source,'InstBuffer');c,translate,hierarchy=bind(source)
    widths={name:int(high)+1 for high,name in re.findall(r'\b(?:wire|input|output)\s+\[(\d+):0\]\s+([A-Za-z_][\w$]*)',body)}
    links=re.findall(r'(?m)^\s*(\w+)\s+(bank_[0-3]_ext)\s*\(',clean(body))
    assert len(links)==4 and {n for _,n in links}=={f'bank_{i}_ext' for i in range(4)},'Four IB banks required'
    results=[]
    for kind,name in links:
        matched=[m for m in cells(body,kind) if m['name']==name];assert len(matched)==1
        pin=ports(matched[0]['ports']);data=expand(pin['W0_data'],widths)
        assert len(data)==84 and pin['R0_clk']=='clock','IB geometry/clock'
        ram=module(source,kind)
        assert re.search(r'\binput\s+\[1:0\]\s+R0_addr',ram) and re.search(r'\binput\s+\[1:0\]\s+W0_addr',ram),'IB four rows'
        seen=[]
        for m in cells(ram,'GTP_RAM32X2DP'):
            q=ports(m['ports']);di=expand(q['DI'],{})
            if not any(re.fullmatch(r'W0_data\[8[0-3]\]',b) for b in di):continue
            bits=[int(re.fullmatch(r'W0_data\[(\d+)\]',b)[1]) for b in di]
            assert expand(q['DO'],{})==[f'R0_data[{b}]' for b in bits],'Metadata read/write bit pairing'
            assert q['WCLK']=='R0_clk' and q['WE']=='W0_en','Metadata write control'
            assert expand(q['WADDR'],{})==["1'b0"]*3+['W0_addr[1]','W0_addr[0]'],'Metadata write address'
            assert expand(q['RADDR'],{})==["1'b0"]*3+['R0_addr[1]','R0_addr[0]'],'Metadata read address'
            seen.extend(bits)
        assert Counter(seen)==Counter({i:1 for i in range(80,84)}),'All four metadata bits must retain RAM read/write storage'
        targets=[translate(n) for n in list(reversed(data))[32:64]+list(reversed(data))[80:84]]
        leaves=cone_leaves(c,targets)
        assert 0<len(leaves)<=300,'Unexpected capture cone size '+repr(sorted(leaves))
        def order(n):
            m=re.search(r'(?:Insts|Inst)_(\d)\[(\d+)\]',n)
            return (int(m[2]),int(m[1]),n) if m else (-1,0,n)
        bdd=BDD(sorted(leaves,key=order));walk=cone_evaluator(c,bdd)
        inst=[walk(n) for n in targets[:32]];want=expected(bdd,inst)
        assert [walk(n) for n in targets[32:]]==want,'Native RF metadata differs from selected instruction at '+name
        results.append(dict(bank=name,module=kind,rows=4,payload_bits=80,metadata_bits=4,arbitrary_source_leaves=len(leaves),bdd_nodes=len(bdd.nodes),all_leaf_assignments_equivalent=True))
    return dict(status='IB_RF_METADATA_CAPTURE_ADS_PASS_NOT_STA_OR_BOARD',banks=results,metadata_storage_bits=64,hierarchy_binding=hierarchy,scope='Actual four bank metadata RAM DI/DO/addresses/control and complete post-rotation write-cone equality; dynamic CSR and whole CPU separately tested')

def main():
    if sys.flags.optimize:raise RuntimeError('Assertions must remain enabled')
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--netlist',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    assert not a.output.exists();raw=a.netlist.read_bytes();r=audit(raw.decode())
    assert a.netlist.read_bytes()==raw
    r.update(netlist_sha256=hashlib.sha256(raw).hexdigest(),checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),dependencies_sha256={n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in ['audit_cpu_ads.py','audit_icache_pad_ads.py','ads_bdd.py','ads_frontend_ib_cone.py']})
    a.output.write_text(json.dumps(r,indent=2)+'\n');print(r['status'])

if __name__=='__main__':main()
