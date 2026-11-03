"""Read-only SD native state transition proof with actual mapped RAM pins.

Foreign native FF states and package inputs are common environment variables.
No RTL control signal or invented memory output is used as a proof boundary.
This is a module transition proof, not STA or complete SoC sequential proof.
"""
from pathlib import Path
from functools import lru_cache
import argparse,hashlib,json,re,sys,traceback
if sys.flags.optimize:
    raise RuntimeError('Native SD proof requires assertions; do not use Python -O')
sys.path.insert(0,str(Path(__file__).with_name('gui1080_mul')))
from native_data_boundary_graph_v2 import NativeDataBoundaryCone,NativeDataGraph
from audit_cpu_ads import signal
from native_sat_bits import z3
from native_hier_cone_vector_v2 import VectorHierCone

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))


class SdCone(NativeDataBoundaryCone):
    @lru_cache(None)
    def ram_cells(self,kind):
        body=re.sub(r'/\*.*?\*/|//[^\n]*','',self.modules[kind],flags=re.S)
        result={}
        for m in re.finditer(r'\b(GTP_RAM64X1DP|GTP_RAM32X1DP)\s*#\s*\((.*?)\)\s*(\\\S+|\w+)\s*\((.*?)\);',body,re.S):
            params={k:v.strip() for k,v in re.findall(r'\.(\w+)\s*\(([^()]*)\)',m[2])}
            ports={k:signal(v) for k,v in re.findall(r'\.(\w+)\s*\(([^()]*)\)',m[4])}
            width=64 if m[1]=='GTP_RAM64X1DP' else 32
            assert set(params)=={'INIT'} and re.fullmatch(str(width)+r"'b[01]{"+str(width)+r"}",params['INIT'])
            assert set(ports)=={'RADDR','WADDR','DO','DI','WCLK','WE'}
            name=signal(m[3]);assert name not in result
            result[name]={'kind':m[1],'name':name,'ports':ports,'params':params,'init':None}
        return result
    @lru_cache(None)
    def cone(self,kind):
        c=VectorHierCone.cone(self,kind)
        body=re.sub(r'/\*.*?\*/|//[^\n]*','',self.modules[kind],flags=re.S)
        context=next(ctx for ctx,row in self.contexts.items() if row[0]==kind)
        for m in re.finditer(r'\bGTP_RAM32X2DP\s*#\s*\((.*?)\)\s*(\\\S+|\w+)\s*\((.*?)\);',body,re.S):
            params={k:v.strip() for k,v in re.findall(r'\.(\w+)\s*\(([^()]*)\)',m[1])}
            ports={k:signal(v) for k,v in re.findall(r'\.(\w+)\s*\(([^()]*)\)',m[3])}
            assert set(params)=={'INIT_0','INIT_1'} and all(re.fullmatch(r"32'b[01]{32}",v) for v in params.values())
            bits=self.vector_bits(context,ports['DO']);assert len(bits)==2
            for bit,net in enumerate(bits):
                assert net not in c.drivers
                c.drivers[net]=({'kind':'GTP_RAM32X2DP','name':signal(m[2]),'ports':ports,'params':params,'init':None,'ram_bit':bit},'DO')
        for m in re.finditer(r'\bGTP_IOBUF\s*#\s*\((.*?)\)\s*(\\\S+|\w+)\s*\((.*?)\);',body,re.S):
            ports={k:signal(v) for k,v in re.findall(r'\.(\w+)\s*\(([^()]*)\)',m[3])}
            assert set(ports)=={'IO','O','I','T'} and context==()
            assert self.directions(kind).get(ports['IO'].split('[')[0])=='inout'
            assert ports['O'] not in c.drivers
            c.drivers[ports['O']]=({'kind':'GTP_IOBUF','name':signal(m[2]),'ports':ports,'params':m[1]},'O')
        for m in re.finditer(r'\bGTP_GPLL\s*#\s*\((.*?)\)\s*(\\\S+|\w+)\s*\((.*?)\);',body,re.S):
            ports={k:signal(v) for k,v in re.findall(r'\.(\w+)\s*\(([^()]*)\)',m[3])}
            for port,net in ports.items():
                if net and (re.fullmatch(r'CLKOUT[0-6F]N?',port) or port=='LOCK'):
                    assert net not in c.drivers
                    c.drivers[net]=({'kind':'GTP_GPLL','name':signal(m[2]),'ports':ports,'params':re.sub(r'\s+','',m[1])},port)
        for m in re.finditer(r'\bGTP_INBUF\s*#\s*\((.*?)\)\s*(\\\S+|\w+)\s*\((.*?)\);',body,re.S):
            ports={k:signal(v) for k,v in re.findall(r'\.(\w+)\s*\(([^()]*)\)',m[3])}
            assert set(ports)=={'I','O'} and context==()
            assert self.directions(kind).get(ports['I'].split('[')[0])=='input'
            assert ports['O'] not in c.drivers
            c.drivers[ports['O']]=({'kind':'GTP_INBUF','name':signal(m[2]),'ports':ports,'params':m[1]},'O')
        for node in self.ram_cells(kind).values():
            net=node['ports']['DO'];assert net not in c.drivers
            c.drivers[net]=(node,'DO')
        return c

class SdGraph(NativeDataGraph):
    def __init__(self,source):
        # Attributes contain provenance only; removing them makes the native
        # top declaration visible to the existing strict module parser.
        source=re.sub(r'\(\*.*?\*\)','',source,flags=re.S)
        self.h=SdCone(source,root='soc_top');self.stops=set();self.nodes={};self.active=set();self.ffs={}
        matches=[c for c in self.h.children(()) if self.h.contexts[c][0]=='sd_native_mmio']
        assert matches==[('u_sd',)];self.ctx=matches[0]
        self.rams={}
        for child in self.h.children(self.ctx):
            kind=self.h.contexts[child][0];assert re.fullmatch(r'sd_native_sector_bank(?:_unq\d+)?',kind)
            for name,node in self.h.ram_cells(kind).items():self.rams[(child,name)]=node
        assert len(self.rams)==256
        self.state={}
        for ctx in [self.ctx,*self.h.children(self.ctx)]:
            for q,(node,port) in self.h.cone(self.h.contexts[ctx][0]).drivers.items():
                if port=='Q' and node['kind'].startswith('GTP_DFF'):
                    assert node['init'] in [0,1] and node['string_params']=={'GRS_EN':'TRUE'}
                    assert set(node['ports'])<=set(['Q','D','CE','CLK','R','S'])
                    assert set(['Q','D','CLK'])<=set(node['ports'])
                    key=(ctx,node['name']);assert key not in self.state
                    self.state[key]=node
    def visit(self,key):
        if key not in self.nodes and key[0]!=('UNKNOWN',) and key[1] not in ["1'b0","1'b1"]:
            c=self.h.cone(self.h.contexts[key[0]][0]);entry=c.drivers.get(key[1])
            if entry and entry[0]['kind'] in ['GTP_INV','GTP_BUF']:
                assert entry[1]=='Z' and set(entry[0]['ports'])=={'I','Z'}
                child=self.key(key[0],entry[0]['ports']['I']);self.visit(child)
                self.nodes[key]=('truth',1 if entry[0]['kind']=='GTP_INV' else 2,(child,));return key
            if entry and entry[0]['kind']=='GTP_GPLL':
                self.nodes[key]=('native_clock',entry[0]['name'],entry[1]);return key
            if entry and entry[0]['kind'] in ['GTP_IOBUF','GTP_INBUF'] and entry[1]=='O':
                self.nodes[key]=('package_pad_input',entry[0]['ports']['IO' if entry[0]['kind']=='GTP_IOBUF' else 'I']);return key
            if entry and entry[0]['kind'] in ['GTP_RAM64X1DP','GTP_RAM32X1DP'] and entry[1]=='DO':
                self.nodes[key]=('ram',);return key
        return super().visit(key)

def validate(baseline,candidate,self_test=False):
    baseline=Path(baseline);candidate=Path(candidate)
    for root in [baseline,candidate]:
        snap=read(root/'pds/build_snapshot.json')
        for n,h in snap['inputs'].items():assert sha(root/n)==h,n
    old_vm=baseline/'pds/synthesize/soc_top_syn.vm';new_vm=candidate/'pds/synthesize/soc_top_syn.vm'
    hashes=[sha(old_vm),sha(new_vm)]
    graphs=[SdGraph(p.read_text()) for p in [old_vm,new_vm]];old,new=graphs
    removed={(old.ctx,'cmd_arg_latched['+str(i)+']') for i in range(32)}
    if self_test:removed=set()
    assert set(old.state)-set(new.state)==removed
    added=set(new.state)-set(old.state)
    assert added==(set() if self_test else {(new.ctx,'cmd_tx_shift[0]')})
    assert len(old.state)==867 and len(new.state)==(867 if self_test else 836)
    assert set(old.rams)==set(new.rams)
    symbols={};memo=[{},{}];actual_ram={};native_clocks={};native_pads={};solver=z3.Solver();solver.set(timeout=60000)
    def leaf(kind,key):
        semantic=(kind,key)
        if semantic not in symbols:symbols[semantic]=z3.Bool('environment_'+str(len(symbols)))
        return symbols[semantic]
    def value(index,ctx,net):
        g=graphs[index];return expr(index,g.build(ctx,net))
    def expr(index,key):
        if key in memo[index]:return memo[index][key]
        g=graphs[index];node=g.nodes[key];kind=node[0]
        if kind=='const':result=z3.BoolVal(bool(node[1]))
        elif kind=='ff':
            native=g.h.cone(g.h.contexts[key[0]][0]).drivers[key[1]][0]
            state_key=(key[0],native['name'])
            distinct=(index,state_key) if not self_test and state_key[0]==g.ctx and state_key[1].startswith('cmd_tx_shift[') and int(state_key[1].split('[')[1][:-1])>=8 else state_key
            if not self_test and state_key in added and index==1:result=z3.BoolVal(True)
            else:result=leaf('actual_ff',distinct)
        elif kind=='external':result=leaf('package_input',key)
        elif kind=='package_pad_input':
            native_pads[(key[0],g.h.cone(g.h.contexts[key[0]][0]).drivers[key[1]][0]['name'])]=g.h.cone(g.h.contexts[key[0]][0]).drivers[key[1]][0]
            result=leaf('package_pad_input',node[1])
        elif kind=='native_clock':
            native_clocks[(key[0],node[1],node[2])]=g.h.cone(g.h.contexts[key[0]][0]).drivers[key[1]][0]
            result=leaf('native_clock',(key[0],node[1],node[2]))
        elif kind=='ram':
            entry=g.h.cone(g.h.contexts[key[0]][0]).drivers[key[1]]
            assert entry[0]['kind'] in ['GTP_RAM64X1DP','GTP_RAM32X1DP','GTP_RAM32X2DP'],'Unexpected memory environment boundary'
            node=entry[0];bit=node.get('ram_bit',0)
            actual_ram[(key[0],node['name'])]=node
            result=leaf('actual_ram_do',(key[0],node['name'],bit))
        else:
            assert kind=='truth',('Unreviewed native leaf',key,node)
            pins=[expr(index,k) for k in node[2]]
            def truth(table,width):
                if not width:return z3.BoolVal(bool(table&1))
                half=1<<(width-1);mask=(1<<half)-1
                return z3.If(pins[width-1],truth(table>>half,width-1),truth(table&mask,width-1))
            result=truth(node[1],len(pins))
        memo[index][key]=result;return result
    rows=[]
    def check(label,a,b):
        solver.push();solver.add(a!=b);answer=solver.check()
        witness={str(k):str(solver.model().eval(v,model_completion=True)) for k,v in symbols.items()} if answer==z3.sat else None
        if answer==z3.sat and label.startswith('next_state:'):
            witness['_NATIVE_TARGET']=[dict(kind=g.state[key]['kind'],ports=g.state[key]['ports'],values={p:str(solver.model().eval(value(i,key[0],n),model_completion=True)) for p,n in g.state[key]['ports'].items()}) for i,g in enumerate(graphs)]
            witness['_MODE']={name:str(solver.model().eval(v,model_completion=True)) for name,v in [('current_crc',current_crc),('next_crc',next_crc),('a',a),('b',b)]}

        solver.pop();assert answer==z3.unsat,(label,str(answer),solver.reason_unknown(),witness)
        rows.append(label)
    assert solver.check()==z3.sat
    def next_state(i,key):
        node=graphs[i].state[key];ctx=key[0];p=node['ports'];q=value(i,ctx,p['Q'])
        result=value(i,ctx,p['D'])
        if 'CE' in p:result=z3.If(value(i,ctx,p['CE']),result,q)
        if 'S' in p:result=z3.If(value(i,ctx,p['S']),z3.BoolVal(True),result)
        if 'R' in p:result=z3.If(value(i,ctx,p['R']),z3.BoolVal(False),result)
        return result
    crc_key=(old.ctx,'state_reg[1]');assert crc_key in old.state and crc_key in new.state
    current_crc=value(0,old.ctx,old.state[crc_key]['ports']['Q']);next_crc=next_state(0,crc_key)
    fsms=[]
    for prefix,count in [('state_reg',19),('data_state_reg',7)]:
        keys=[(old.ctx,prefix+'['+str(i)+']') for i in range(count)]
        assert all(k in old.state and k in new.state for k in keys)
        assert sum(old.state[k]['init'] for k in keys)==sum(new.state[k]['init'] for k in keys)==1
        bits=[value(0,k[0],old.state[k]['ports']['Q']) for k in keys]
        solver.add(z3.PbEq([(v,1) for v in bits],1));fsms.append((prefix,keys))

    tx_key=(old.ctx,'state_reg[2]');current_tx=value(0,old.ctx,old.state[tx_key]['ports']['Q']);next_tx=next_state(0,tx_key)
    busy_key=(old.ctx,'busy_vname');idle_key=(old.ctx,'state_reg[0]')
    solver.add(value(0,old.ctx,old.state[busy_key]['ports']['Q'])==z3.Not(value(0,old.ctx,old.state[idle_key]['ports']['Q'])))
    check('native_busy_idle_induction',next_state(0,busy_key),z3.Not(next_state(0,idle_key)))
    def arg_relation(next_edge):
        left=lambda bit: next_state(1,(new.ctx,'cmd_tx_shift['+str(bit)+']')) if next_edge else value(1,new.ctx,'cmd_tx_shift['+str(bit)+']')
        right=lambda name: next_state(0,(old.ctx,name)) if next_edge else value(0,old.ctx,name)
        relations=[left(i+8)==right('cmd_arg_latched['+str(i)+']') for i in range(32)]
        relations += [left(i+40)==right('cmd_index_latched['+str(i)+']') for i in range(6)]
        relations += [left(46)==z3.BoolVal(True)]
        return z3.And(*relations)
    if not self_test:
        solver.add(z3.Implies(current_crc,arg_relation(False)))
        for key in new.state:
            if key not in added and key[0]==new.ctx and key[1].startswith('cmd_tx_shift['):
                solver.add(z3.Implies(current_tx,value(0,*key)==value(1,*key)))
        assert solver.check()==z3.sat
    for prefix,keys in fsms:
        check('native_fsm_onehot_induction:'+prefix,z3.PbEq([(next_state(0,k),1) for k in keys],1),z3.BoolVal(True))
    for key,node in old.state.items():
        if key in removed:continue
        other=new.state[key];assert node['init']==other['init'] and node['kind']==other['kind'],key
        check('clock:'+str(key),value(0,key[0],node['ports']['CLK']),value(1,key[0],other['ports']['CLK']))
        a=next_state(0,key);b=next_state(1,key)
        if not self_test and key[0]==old.ctx and key[1].startswith('cmd_tx_shift['):
            a=z3.And(next_tx,a);b=z3.And(next_tx,b)
        check('next_state:'+str(key),a,b)
    if not self_test:check('next_crc_header_relation',z3.Implies(next_crc,arg_relation(True)),z3.BoolVal(True))
    for key,node in old.rams.items():
        other=new.rams[key];assert node['params']==other['params']
        for port in ['RADDR','WADDR','DI','WE','WCLK']:
            bits=[g.h.vector_bits(key[0],c['ports'][port]) for g,c in zip(graphs,[node,other])]
            assert len(bits[0])==len(bits[1])
            for bit,(a,b) in enumerate(zip(*bits)):
                check('memory:'+str(key)+':'+port+':'+str(bit),value(0,key[0],a),value(1,key[0],b))
    # Stable physical SD protocol outputs. Synthesized anonymous shared
    # output ports change with optimization; they are not paired by guessed
    # names. MMIO read equivalence is covered by the complete RTL interface
    # miters plus unchanged source read mux and retained state/memory proof.
    outputs=['hit','sd_clk','sd_cmd_out','sd_cmd_oe_inv','sd_dat_out','sd_dat_oe_inv']
    output_count=0
    for port in outputs:
        bits=[g.h.vector_bits(g.ctx,port) for g in graphs];assert len(bits[0])==len(bits[1])
        for bit,(a,b) in enumerate(zip(*bits)):
            check('physical_output:'+port+':'+str(bit),value(0,old.ctx,a),value(1,new.ctx,b));output_count+=1
    for key in added:check('new_constant_one_invariant:'+str(key),next_state(1,key),z3.BoolVal(True))
    checked=set(old.rams)
    while set(actual_ram)-checked:
        key=next(iter(set(actual_ram)-checked));node=actual_ram[key];ctx=key[0]
        alternatives=[]
        for g in graphs:
            c=g.h.cone(g.h.contexts[ctx][0]);found={n['name']:n for n,p in c.drivers.values() if p=='DO' and n['kind']==node['kind']}
            assert key[1] in found;alternatives.append(found[key[1]])
        assert alternatives[0]['params']==alternatives[1]['params']
        for port in ['RADDR','WADDR','DI','WE','WCLK']:
            bits=[g.h.vector_bits(ctx,n['ports'][port]) for g,n in zip(graphs,alternatives)];assert len(bits[0])==len(bits[1])
            for bit,(a,b) in enumerate(zip(*bits)):check('foreign_native_ram:'+str(key)+':'+port+':'+str(bit),value(0,ctx,a),value(1,ctx,b))
        checked.add(key)
    for key,node in native_clocks.items():
        for g in graphs:
            c=g.h.cone(g.h.contexts[key[0]][0]);matches=[n for n,p in c.drivers.values() if n['kind']=='GTP_GPLL' and n['name']==key[1] and p==key[2]]
            assert len(matches)==1 and matches[0]['params']==node['params'] and matches[0]['ports']==node['ports']
    for key,node in native_pads.items():
        paired=[]
        for g in graphs:
            matches=[n for n,p in g.h.cone(g.h.contexts[key[0]][0]).drivers.values() if n['kind']==node['kind'] and n['name']==key[1] and p=='O']
            assert len(matches)==1 and matches[0]['params']==node['params'];paired.append(matches[0])
        pin='IO' if node['kind']=='GTP_IOBUF' else 'I'
        assert paired[0]['ports'][pin]==paired[1]['ports'][pin]
        if node['kind']=='GTP_IOBUF':
            for port in ['I','T']:check('native_pad_drive:'+str(key)+':'+port,value(0,key[0],paired[0]['ports'][port]),value(1,key[0],paired[1]['ports'][port]))
    assert [sha(old_vm),sha(new_vm)]==hashes
    return dict(status='NATIVE_SD_ARGUMENT_SELF_TEST_PASS_NOT_RESOURCE_OR_STA' if self_test else 'NATIVE_SD_ARGUMENT_SHADOW_REMOVED_STATE_MEMORY_PROTOCOL_PIN_EQ_PASS_NOT_STA_OR_BOARD',
        baseline_vm_sha256=hashes[0],candidate_vm_sha256=hashes[1],baseline_ff=len(old.state),candidate_ff=len(new.state),
        removed_ff=[list(k) for k in sorted(removed)],added_ff=[list(k) for k in sorted(added)],ram64_cells=len(old.rams),ram64_storage_bits=len(old.rams)*64,
        output_bits=output_count,proven_obligations=len(rows),proof_labels=rows,native_nodes=[len(m) for m in memo],
        scope='Actual mapped SD FF next states, command-header state relation, RAM64X1DP initialization/control/address/data pins and physical SD protocol outputs; MMIO via full-interface cycle miters and unchanged source mux; common foreign FF/package-input environment; not whole SoC sequential equivalence',
        solver_version=z3.get_version_string(),checker_sha256=sha(Path(__file__)),
        baseline_snapshot_sha256=sha(baseline/'pds/build_snapshot.json'),candidate_snapshot_sha256=sha(candidate/'pds/build_snapshot.json'))

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ['baseline','candidate','output']:ap.add_argument('--'+n,type=Path,required=True)
    ap.add_argument('--self-test',action='store_true');a=ap.parse_args();assert not a.output.exists()
    result={'status':'RUNNING'}
    try:result=validate(a.baseline,a.candidate,a.self_test)
    except Exception:result.update(status='FAILED_SD_ARGUMENT_NATIVE_PROOF_PRESERVED',error=traceback.format_exc());raise
    finally:a.output.write_text(json.dumps(result,indent=2)+'\n');print(result['status'],flush=True)
