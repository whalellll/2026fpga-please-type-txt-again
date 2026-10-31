"""Mapped weight-DMA transition proof for the streamed upper-half representation.

Use actual native FF identities, package inputs, and native memory/data boundaries.
Do not pair synthesis-generated module ports or intermediate wire numbers.
"""
from pathlib import Path
import argparse,hashlib,json,re,sys
from functools import lru_cache
from check_sd_argument_native import SdCone,SdGraph,z3
from audit_cpu_ads import signal

sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))

class WeightCone(SdCone):
    @lru_cache(None)
    def cone(self,kind):
        c=super().cone(kind)
        body=re.sub(r'/\*.*?\*/|//[^\n]*','',self.modules[kind],flags=re.S)
        context=next(ctx for ctx,row in self.contexts.items() if row[0]==kind)
        pattern=r'\b(GTP_APM_E2|GTP_DRM(?:18K|36K)_E1)\s*#\s*\((.*?)\)\s+(\\\S+|\w+)\s*\((.*?)\);'
        for m in re.finditer(pattern,body,re.S):
            params={k:v.strip() for k,v in re.findall(r'\.(\w+)\s*\(([^()]*)\)',m[2])}
            ports={k:signal(v) for k,v in re.findall(r'\.(\w+)\s*\(([^()]*)\)',m[4])}
            outputs=['P'] if m[1]=='GTP_APM_E2' else ['DOA','DOB']
            width=48 if m[1]=='GTP_APM_E2' else 36 if '36K' in m[1] else 18
            for port in outputs:
                if not ports.get(port):continue
                bits=self.vector_bits(context,ports[port]);assert len(bits)==width
                for bit,net in enumerate(bits):
                    assert net not in c.drivers
                    c.drivers[net]=({'kind':m[1],'name':signal(m[3]),'ports':ports,
                        'params':params,'init':None,'native_data_bit':bit},port)
        return c

class WeightGraph(SdGraph):
    def __init__(self,source):
        source=re.sub(r'\(\*.*?\*\)','',source,flags=re.S)
        self.h=WeightCone(source,root='soc_top');self.stops=set();self.nodes={};self.active=set();self.ffs={}
        self.ctx=self.h.find('mac_conv_weight_dma')
        self.state={};self.rams={}
        for q,(node,port) in self.h.cone('mac_conv_weight_dma').drivers.items():
            if port=='Q' and node['kind'].startswith('GTP_DFF'):
                assert node['init'] in [0,1] and node['string_params']=={'GRS_EN':'TRUE'}
                assert set(node['ports'])<=set(['Q','D','CE','CLK','R','S'])
                key=(self.ctx,node['name']);assert key not in self.state;self.state[key]=node

def prove(root,baseline):
    roots=[Path(baseline),Path(root)]
    for r in roots:
        snap=read(r/'pds/build_snapshot.json')
        for n,h in snap['inputs'].items():assert sha(r/n)==h,n
    vms=[r/'pds/synthesize/soc_top_syn.vm' for r in roots]
    graphs=[WeightGraph(p.read_text()) for p in vms];old,new=graphs
    assert old.ctx==new.ctx
    def names(g,prefix):return {k[1] for k in g.state if k[1].startswith(prefix+'[')}
    assert names(old,'line_shift')=={f'line_shift[{i}]' for i in range(1024)}
    assert names(new,'line_shift')=={f'line_shift[{i}]' for i in range(512)}
    assert not names(old,'upper_fold') and names(new,'upper_fold')=={f'upper_fold[{i}]' for i in range(32)}
    old_control={k for k in old.state if not k[1].startswith('line_shift[')}
    new_control={k for k in new.state if not k[1].startswith(('line_shift[','upper_fold['))}
    assert old_control==new_control and len(old.state)==1270 and len(new.state)==790
    symbols={};memo=[{},{}];solver=z3.Solver();solver.set(timeout=30000);labels=[]
    foreign_native={};clocks={};pads={}
    def leaf(kind,key):
        semantic=(kind,key)
        if semantic not in symbols:symbols[semantic]=z3.Bool('native_environment_'+str(len(symbols)))
        return symbols[semantic]
    def value(i,ctx,net):return expr(i,graphs[i].build(ctx,net))
    def expr(i,key):
        if key in memo[i]:return memo[i][key]
        g=graphs[i];node=g.nodes[key];kind=node[0]
        if kind=='const':v=z3.BoolVal(bool(node[1]))
        elif kind=='ff':
            ff=g.h.cone(g.h.contexts[key[0]][0]).drivers[key[1]][0]
            identity=(key[0],ff['name'])
            if key[0]==g.ctx and ff['name'].startswith(('line_shift[','upper_fold[')):
                identity=(i,*identity)
            v=leaf('native_ff',identity)
        elif kind=='external':v=leaf('package_input',key)
        elif kind=='package_pad_input':
            pads[(key[0],node[1])]=True;v=leaf('package_pad_input',node[1])
        elif kind=='native_clock':
            ff=g.h.cone(g.h.contexts[key[0]][0]).drivers[key[1]][0]
            identity=(key[0],node[1],node[2]);clocks.setdefault(identity,[]).append(ff)
            v=leaf('native_clock',identity)
        elif kind in ['ram','opaque_native_data']:
            ff,port=g.h.cone(g.h.contexts[key[0]][0]).drivers[key[1]]
            assert ff['kind'].startswith(('GTP_RAM','GTP_DRM','GTP_APM'))
            identity=(key[0],ff['name'],port,ff.get('ram_bit',ff.get('native_data_bit',0)))
            foreign_native.setdefault(identity,[]).append((i,ff))
            v=leaf('native_memory_data',identity)
        else:
            assert kind=='truth',('Unsupported native proof boundary',key,node)
            pins=[expr(i,k) for k in node[2]]
            def truth(table,width):
                if not width:return z3.BoolVal(bool(table&1))
                half=1<<(width-1);mask=(1<<half)-1
                return z3.If(pins[width-1],truth(table>>half,width-1),truth(table&mask,width-1))
            v=truth(node[1],len(pins))
        memo[i][key]=v;return v
    def check(label,a,b):
        solver.push();solver.add(a!=b);answer=solver.check()
        witness=str(solver.model())[:1800] if answer==z3.sat else None
        solver.pop();assert answer==z3.unsat,(label,str(answer),witness)
        labels.append(label)
    def q(i,name):
        g=graphs[i];return value(i,g.ctx,g.state[(g.ctx,name)]['ports']['Q'])
    def pin(i,name,p):
        g=graphs[i];return value(i,g.ctx,g.state[(g.ctx,name)]['ports'][p])
    def nxt(i,name):
        g=graphs[i];ff=g.state[(g.ctx,name)];p=ff['ports'];v=pin(i,name,'D')
        if 'CE' in p:v=z3.If(pin(i,name,'CE'),v,q(i,name))
        if 'S' in p:v=z3.If(pin(i,name,'S'),z3.BoolVal(True),v)
        if 'R' in p:v=z3.If(pin(i,name,'R'),z3.BoolVal(False),v)
        return v
    # All unchanged protocol state has identical transitions in the common
    # native-state environment. The new data representation is deliberately
    # independent; a hidden data dependency in protocol control fails here.
    for key in sorted(old_control):
        name=key[1];a=old.state[key];b=new.state[key]
        assert a['init']==b['init'] and a['kind']==b['kind'],name
        check('control_clock:'+name,pin(0,name,'CLK'),pin(1,name,'CLK'))
        check('control_next:'+name,nxt(0,name),nxt(1,name))
    # Actual old capture CE/reset and actual DDR pins anchor the new datapath.
    accepted=pin(0,'line_shift[0]','CE');reset=pin(0,'line_shift[0]','R')
    incoming=[pin(0,f'line_shift[{992+i}]','D') for i in range(32)]
    for bit in range(1024):
        name=f'line_shift[{bit}]';assert old.state[(old.ctx,name)]['init']==0
        check('baseline_capture_clock:'+str(bit),pin(0,name,'CLK'),pin(0,'line_shift[0]','CLK'))
        check('baseline_capture_enable:'+str(bit),pin(0,name,'CE'),accepted)
        check('baseline_capture_reset:'+str(bit),pin(0,name,'R'),reset)
        if bit<992:check('baseline_shift_bit:'+str(bit),pin(0,name,'D'),q(0,f'line_shift[{bit+32}]'))
    high=q(0,'word_index[4]')
    index_bits=[q(0,f'word_index[{i}]') for i in range(6)]
    first=z3.And(*[b if ((16>>i)&1) else z3.Not(b) for i,b in enumerate(index_bits)])
    for bit in range(512):
        name=f'line_shift[{bit}]';ff=new.state[(new.ctx,name)];assert ff['init']==0
        check('capture_clock:'+name,pin(0,'line_shift[0]','CLK'),pin(1,name,'CLK'))
        data=incoming[bit-480] if bit>=480 else q(1,f'line_shift[{bit+32}]')
        expected=z3.If(reset,z3.BoolVal(False),z3.If(z3.And(accepted,z3.Not(high)),data,q(1,name)))
        check('low_capture_transition:'+str(bit),nxt(1,name),expected)
    for bit in range(32):
        name=f'upper_fold[{bit}]';assert new.state[(new.ctx,name)]['init']==0
        check('capture_clock:'+name,pin(0,'line_shift[0]','CLK'),pin(1,name,'CLK'))
        data=z3.If(first,incoming[bit],z3.Xor(q(1,f'upper_fold[{(bit-5)%32}]'),incoming[bit]))
        expected=z3.If(reset,z3.BoolVal(False),z3.If(z3.And(accepted,high),data,q(1,name)))
        check('upper_capture_transition:'+str(bit),nxt(1,name),expected)
    buffers=new.h.children(new.ctx)
    assert buffers==(new.ctx+('u_buffer',),)
    binding=new.h.contexts[buffers[0]][2]
    assert 'load_data' in binding
    publish_bits=new.h.vector_bits(new.ctx,binding['load_data']);assert len(publish_bits)==544
    for bit in range(544):
        expected=q(1,f'line_shift[{bit}]') if bit<512 else q(1,f'upper_fold[{bit-512}]')
        check('encoded_publish_bit:'+str(bit),value(1,new.ctx,publish_bits[bit]),expected)
    # Compose the proven recurrence over all sixteen upper DDR words. Masks
    # encode 512 independent input bits, not selected test vectors.
    state=[0]*32
    for word in range(16):
        state=[(1<<(word*32+bit)) ^ (0 if word==0 else state[(bit-5)%32]) for bit in range(32)]
    for output,mask in enumerate(state):
        expected=sum(1<<(word*32+(output-5*(15-word))%32) for word in range(16))
        assert mask==expected
    # Common foreign native-data boundaries are paired by actual primitive
    # identity, parameters, and every input pin. This also covers a descriptor
    # guard's combinational APM: it is not assumed to be a register.
    checked=set();unused_apm_x_high=[]
    while set(foreign_native)-checked:
        identity=next(iter(set(foreign_native)-checked));ctx,name,output,bit=identity
        pair=[]
        for g in graphs:
            entries={n['name']:n for n,p in g.h.cone(g.h.contexts[ctx][0]).drivers.values()
                     if p==output and n['name']==name}
            assert len(entries)==1;pair.append(entries[name])
        assert pair[0]['kind']==pair[1]['kind'] and pair[0]['params']==pair[1]['params']
        is_drm=pair[0]['kind'].startswith('GTP_DRM')
        is_apm=pair[0]['kind']=='GTP_APM_E2'
        assert set(pair[0]['ports'])==set(pair[1]['ports'])
        excluded={'DOA','DOB'} if is_drm else {'P','CPO','COUT','CXO','CXBO'} if is_apm else {'DO'}
        for port in set(pair[0]['ports'])-excluded:
            if not pair[0]['ports'][port] or not pair[1]['ports'][port]:
                assert pair[0]['ports'][port]==pair[1]['ports'][port]
                continue # Identically omitted native primitive connection.
            nets=[g.h.vector_bits(ctx,n['ports'][port]) for g,n in zip(graphs,pair)]
            assert len(nets[0])==len(nets[1])
            for b,(left,right) in enumerate(zip(*nets)):
                if left==right=="1'bx":
                    # Installed GTP_APM_E2 model: the multiplier consumes
                    # only X[24:0]. X[29:25] can otherwise reach P through
                    # post-adder MODEY=3; require that path disabled by the
                    # actual immutable parameters and constant mode pins.
                    assert is_apm and port=='X' and b>=25
                    params=pair[0]['params'];assert params['USE_PREADD']=='0' and params['X_SEL']=='0'
                    if params['USE_POSTADD']=='1':
                        assert params['MODEY_REG']=='0'
                        mode=graphs[0].h.vector_bits(ctx,pair[0]['ports']['MODEY'])
                        assert mode[0] in ["1'b0","1'b1"] and mode[1] in ["1'b0","1'b1"]
                        assert mode[:2]!=("1'b1","1'b1")
                    unused_apm_x_high.append((ctx,name,port,b));continue
                check('foreign_native_input:'+str((ctx,name,port,b)),value(0,ctx,left),value(1,ctx,right))
        checked.update(k for k in foreign_native if k[:3]==identity[:3])
    # Package clocks are checked by immutable actual PLL primitive parameters;
    # other native memory/data boundaries remain an explicit module assumption.
    for identity in clocks:
        compared=[]
        for g in graphs:
            matches=[n for n,p in g.h.cone(g.h.contexts[identity[0]][0]).drivers.values()
                     if n['kind']=='GTP_GPLL' and n['name']==identity[1] and p==identity[2]]
            assert len(matches)==1;compared.append(matches[0])
        assert compared[0]['params']==compared[1]['params'] and compared[0]['ports']==compared[1]['ports']
    result=dict(status='NATIVE_UPPER_FOLD_AFFINE_EXACT_PROOF_PASS_NOT_STA',
        representation='STREAMED_UPPER_FOLD_544_CAPTURE_BITS',
        baseline_vm_sha256=sha(vms[0]),netlist_sha256=sha(vms[1]),
        baseline_ff=len(old.state),candidate_ff=len(new.state),removed_redundant_bits=480,
        independent_input_bits=512,output_bits=32,proven_obligations=len(labels),proof_labels=labels,
        module_control_ff=len(old_control),native_graph_nodes=[len(m) for m in memo],
        foreign_native_data_bits_checked=len(checked),
        unused_apm_x_high_bits=unused_apm_x_high,
        vendor_model_sha256=sha(Path('G:/fpga/PDS_2022.2-SP6.4/arch/vendor/pango/verilog/simulation/GTP_APM_E2.v')),
        solver_version=z3.get_version_string(),checker_sha256=sha(Path(__file__)),
        scope='Actual mapped control transitions, low512capture and upper32recurrence/reset/enable/clock,544publish bits; affine composition of16upperDDR words. Common foreign native FF/package/memory data environment. Full DDR protocol and publication order via complete cycle miters; not whole-SoC sequential equivalence or final STA.',
        final_sta_required=True)
    return result

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--baseline',type=Path,default=Path('G:/fpga/c80f1080p6'))
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();assert not a.output.exists()
    result=prove(a.root,a.baseline)
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(result['status'],result['proven_obligations'])
