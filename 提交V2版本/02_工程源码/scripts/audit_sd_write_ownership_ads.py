"""Prove mapped SD RAM write guards across optimized module boundaries.

Checks write ownership, strobes and mirrored capacity; not full SD address/data
equivalence, routed timing or board acceptance. Unknown cone drivers reject.
"""
import argparse
from collections import defaultdict
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import pycosat

from ads_bdd import lut_inputs
from audit_cpu_ads import check
from audit_icache_pad_ads import cells, ports
from audit_rob_owner_ads import Hierarchy, expand

# The reconstructed accepted-write expression below is specific to these
# reviewed interfaces. A source change requires review, never a silent guess.
MMIO_CONTRACT_SOURCES = {
    'rtl/cpu_top.v': 'a77e45463ceeaf6864773fda16991409c582d650ff5ad9f55ac735317f1f6881',
    'rtl/soc/axi_1x2.v': '7436987b3cd794c29a7e22e688e047f137ebc9920e4ab87c4ca58153245b0ab6',
    'rtl/soc/axi_boot_periph.v': '6897c8d4902da18f7a6257da1993e9b0d254fa1e139d6a49311ac315de868dc0',
}


class BooleanCNF:
    """Tseitin clauses for exact LUT cones; 0/1 denote Boolean constants."""
    def __init__(self,variables):
        self.variables={v:i+2 for i,v in enumerate(variables)}
        self.next_id=len(variables)+2;self.clauses=[[1]]
    def var(self,name):return self.variables[name]
    def inv(self,x):return 1-x if x in (0,1) else -x
    def clause(self,values):
        if 1 in values:return
        values=set(v for v in values if v!=0)
        if any(-v in values for v in values):return
        self.clauses.append(sorted(values))
    @lru_cache(None)
    def ite(self,c,a,b):
        if c==1:return a
        if c==0:return b
        if a==b:return a
        if a==1 and b==0:return c
        if a==0 and b==1:return self.inv(c)
        check(self.next_id<1000000,'SD SAT variable bound exceeded')
        y=self.next_id;self.next_id+=1
        for row in [[self.inv(c),self.inv(a),y],[self.inv(c),a,-y],
                    [c,self.inv(b),y],[c,b,-y]]:self.clause(row)
        return y
    def land(self,a,b):return self.ite(a,b,0)
    def lor(self,a,b):return self.ite(a,1,b)
    def satisfiable(self,value):
        if value in (0,1):return bool(value)
        result=pycosat.solve(self.clauses+[[value]])
        check(result!='UNKNOWN','SD SAT solver could not decide')
        return result!='UNSAT'


class Symbolic:
    def __init__(self, hierarchy):
        self.h=hierarchy

    @lru_cache(None)
    def memory_outputs(self,kind):
        body=self.h.module(kind)['body'];result=set()
        for primitive,width in [('GTP_RAM32X2DP',2),('GTP_RAM64X1DP',1),('GTP_RAM128X1DP',1)]:
            for c in cells(body,primitive):result.update(expand(ports(c['ports'])['DO'],width))
        return result

    @lru_cache(None)
    def step(self,key):
        path,wire=key
        if wire in ("1'b0","1'b1"): return 'constant',int(wire[-1])
        kind,_,_=self.h.context(path); c=self.h.module(kind)['cone']
        if wire in c.aliases: return 'alias',(path,c.aliases[wire])
        if wire in c.drivers:
            node,port=c.drivers[wire]
            if port=='Q': return 'leaf',key
            table,names=lut_inputs(node,port)
            return 'table',(table,[(path,n) for n in names])
        # Explicit state-bearing RAM outputs are arbitrary data leaves. No
        # combinational ownership/control net is cut by name or assumption.
        if wire in self.memory_outputs(kind):return 'leaf',key
        mapped=self.h.parent_input(path,wire) or self.h.child_output(path,wire)
        if mapped is not None: return 'alias',mapped
        check(not path and wire.split('[')[0] in self.h.module(kind)['ports'],
              'Unresolved SD write-cone leaf '+str(key))
        check(self.h.module(kind)['ports'][wire.split('[')[0]][0]=='input',
              'Undriven SD output '+str(key))
        return 'leaf',key

    def leaves(self,targets):
        active=set()
        @lru_cache(None)
        def walk(key):
            check(key not in active,'SD combinational cycle '+str(key)); active.add(key)
            try:
                kind,value=self.step(key)
                if kind=='constant': return frozenset()
                if kind=='leaf': return frozenset([value])
                if kind=='alias': return walk(value)
                result=set()
                for pin in value[1]:result.update(walk(pin))
                return frozenset(result)
            finally:active.remove(key)
        out=set()
        for t in targets:out.update(walk(t))
        return sorted(out)

    def evaluator(self,bdd):
        active=set()
        @lru_cache(None)
        def walk(key):
            check(key not in active,'SD combinational cycle '+str(key)); active.add(key)
            try:
                kind,value=self.step(key)
                if kind=='constant':return value
                if kind=='leaf':return bdd.var(value)
                if kind=='alias':return walk(value)
                table,names=value; pins=[walk(n) for n in names]
                def apply(v,width):
                    if v==0:return 0
                    if v==(1<<(1<<width))-1:return 1
                    half=1<<(width-1); mask=(1<<half)-1
                    return bdd.ite(pins[width-1],apply(v>>half,width-1),apply(v&mask,width-1))
                return apply(table,len(pins))
            finally:active.remove(key)
        return walk


def audit(source):
    h=Hierarchy(source); sd=('u_sd',); kind,_,_=h.context(sd)
    check(kind=='sd_native_mmio','Actual SD controller binding')
    banks=[];targets=[]
    for bank in range(2):
        path=sd+('u_buffer'+str(bank),);kind,_,_=h.context(path)
        check(re.fullmatch(r'sd_native_sector_bank(?:_unq\d+)?',kind),'SD bank type')
        body=h.module(kind)['body']; ram=[(depth,c) for depth in [64,128] for c in cells(body,'GTP_RAM'+str(depth)+'X1DP')]
        check(len(ram)==len(re.findall(r'\bGTP_RAM\d+X\d+DP\b',body)), 'Unsupported SD RAM primitive')
        bits=defaultdict(int);enables=defaultdict(set)
        for depth,cell in ram:
            view=re.search(r'(cpu|tx)_mem',cell['name']);check(view is not None,'SD RAM read view')
            pin=ports(cell['ports']);bit=re.fullmatch(r'write_data\[(\d+)\]',pin.get('DI',''))
            check(bit is not None and int(bit[1])<32,'SD RAM actual write-data bit')
            bit=int(bit[1]); view=view[1]
            bits[(view,bit)]+=depth;enables[(view,bit)].add(pin['WE'])
            check(pin.get('WCLK')=='clk','SD RAM write clock')
        check(dict(bits)=={(v,b):128 for v in ['cpu','tx'] for b in range(32)},'SD capacity/read-view coverage')
        groups=[]
        for byte in range(4):
            reference=enables[('cpu',8*byte)]
            check(reference,'SD byte write enables absent')
            for v in ['cpu','tx']:
                for b in range(8*byte,8*byte+8):
                    check(enables[(v,b)]==reference,'SD byte/mirror write-enable mismatch')
            keys=[(path,n) for n in sorted(reference)];groups.append(keys);targets+=keys
        banks.append(dict(bank=bank,path=path,groups=groups,ram_cells=len(ram)))
        targets += [(sd,'rx_write'+str(bank)),(sd,'tx'+str(bank)+'_full')]
    sd_module=h.module('sd_native_mmio')
    named_wr='wr' in sd_module['ports'] or 'wr' in sd_module['cone'].drivers or 'wr' in sd_module['cone'].aliases
    control=[(sd,n) for n in ['normal_path','busy','write_multi_active']]
    if named_wr:
        write_inputs=[(sd,'wr')];uart_address=[]
    else:
        # ADS may eliminate mmio_wr and the SD wr port completely. Rebuild
        # the reviewed accepted-write reference from actual routed AXI valid,
        # crossbar owner and peripheral controls. These are all traced through
        # their native cones to FF/RAM/top inputs, with no source-name cuts.
        check(h.context(('u_cpu',))[0]=='core_top' and
              h.context(('u_xbar',))[0]=='axi_1x2' and
              h.context(('u_local',))[0]=='axi_boot_periph','SD write reference interfaces differ')
        write_inputs=[(('u_cpu',),'wvalid'),(('u_xbar',),'wr_busy'),(('u_xbar',),'wr_ddr')]
        write_inputs += [(('u_local',),n) for n in ['wr_active','wr_is_mmio','wr_good']]
        uart_address=[(('u_local',),'wr_addr[%d]'%bit) for bit in range(2,32)]
    strobes=[(sd,'l_wstrb['+str(b)+']') for b in range(4)]
    symbolic=Symbolic(h);variables=symbolic.leaves(targets+control+strobes+write_inputs+uart_address)
    bdd=BooleanCNF(variables);walk=symbolic.evaluator(bdd)
    inv=bdd.inv;land=bdd.land;lor=bdd.lor
    def allof(values):
        result=1
        for v in values:result=land(result,v)
        return result
    def anyof(values):
        result=0
        for v in values:result=lor(result,v)
        return result
    normal,busy,multi=map(walk,control);strobe=list(map(walk,strobes))
    if named_wr:
        wr=walk(write_inputs[0])
    else:
        valid,xbar_busy,xbar_ddr,active,mmio,good=map(walk,write_inputs)
        # axi_boot_periph.wready = active && (!uart_data || !utx_full).
        # Prove, over the mapped address cones, that MMIO never selects the
        # UART data register, so ready reduces to active in this reference.
        uart=allof([walk(key) if (0x1fe001e0>>(i+2))&1 else inv(walk(key))
                    for i,key in enumerate(uart_address)])
        check(not bdd.satisfiable(land(mmio,uart)),'SD MMIO reference overlaps UART data readiness')
        wr=allof([valid,xbar_busy,inv(xbar_ddr),active,mmio,good])
    cpu_activity=[];rx_activity=[];results=[]
    for item in banks:
        bank=item['bank'];rx=walk((sd,'rx_write'+str(bank)));full=walk((sd,'tx'+str(bank)+'_full'))
        guard=allof([wr,normal,inv(full),lor(inv(busy),multi)])
        we=[anyof(map(walk,group)) for group in item['groups']]
        check(bdd.satisfiable(rx),'SD RX ownership is constant zero')
        rx_activity.append(rx)
        for byte,e in enumerate(we):
            cpu=land(e,inv(rx))
            check(bdd.satisfiable(cpu),'SD CPU write path absent')
            check(not bdd.satisfiable(land(cpu,inv(guard))),'SD CPU WE bypasses write/normal/TX-full/busy ownership')
            check(not bdd.satisfiable(land(cpu,inv(strobe[byte]))),'SD CPU WE bypasses its byte strobe')
            check(not bdd.satisfiable(land(rx,inv(e))),'SD RX WE does not cover every address/byte')
            for other in range(byte):
                different=lor(land(e,inv(we[other])),land(inv(e),we[other]))
                check(not bdd.satisfiable(allof([inv(rx),strobe[byte],strobe[other],different])),
                      'SD CPU byte ownership differs with equal active strobes')
        cpu_activity.append(land(anyof(we),inv(rx)))
        results.append(dict(bank=bank,ram_cells=item['ram_cells'],capacity_bits_per_view=4096,
                            byte_groups=4,read_views=2,write_guard_proven=True,rx_coverage_proven=True,
                            strobes_proven=True,nonvacuous_cpu_and_rx=True))
    check(not bdd.satisfiable(land(*cpu_activity)),'SD CPU write ownership overlaps across banks')
    check(not bdd.satisfiable(land(*rx_activity)),'SD RX write ownership overlaps across banks')
    return dict(schema=1,status='SD_WRITE_OWNERSHIP_ADS_PASS_NOT_STA_OR_BOARD',banks=results,
                arbitrary_boolean_leaves=len(variables),cnf_variables=bdd.next_id-1,cnf_clauses=len(bdd.clauses),
                solver='pycosat '+pycosat.__version__,
                write_event_binding='named_native_wr' if named_wr else 'reconstructed_axi_mmio_contract',
                reference_source_sha256={} if named_wr else MMIO_CONTRACT_SOURCES,
                source_boundary_cuts=False,leaf_types=['FF_Q','recognized_RAM_DO','top_input'],bank_cpu_ownership_exclusive=True,bank_rx_ownership_exclusive=True,
                scope='Exact mapped RAM WE guard/strobe/RX coverage invariants over all raw leaves; mirrored capacity and data-bit coverage. SD address decode/data equivalence and protocol cycles are separate RTL tests; not STA/board.')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--netlist',type=Path,required=True)
    ap.add_argument('--input-snapshot',type=Path)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();check(not a.output.exists(),'Refuse SD evidence overwrite')
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    raw=a.netlist.read_bytes()
    try:
        result=audit(raw.decode())
        result.update(netlist_sha256=hashlib.sha256(raw).hexdigest(),checker_sha256=sha(Path(__file__)),
                      native_input_binding_verified=False)
        if a.input_snapshot:
            snap=json.loads(a.input_snapshot.read_text(encoding='utf-8-sig'))
            for n in ['audit_sd_write_ownership_ads.py','audit_rob_owner_ads.py','audit_cpu_ads.py','ads_bdd.py','audit_icache_pad_ads.py']:
                check(snap['inputs']['scripts/'+n]==sha(Path(__file__).with_name(n)),'SD checker input binding '+n)
            for n,h in result['reference_source_sha256'].items():
                check(snap['inputs'][n]==h,'SD MMIO reference source binding '+n)
            result.update(run_id=snap['run_id'],input_snapshot_sha256=sha(a.input_snapshot),native_input_binding_verified=True)
        check(a.netlist.read_bytes()==raw,'SD netlist changed during audit')
    except (ValueError,AssertionError,KeyError) as e:
        result=dict(status='FAIL',error=str(e))
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
    if result['status']=='FAIL':print(result['error']);raise SystemExit(1)


if __name__=='__main__':main()
