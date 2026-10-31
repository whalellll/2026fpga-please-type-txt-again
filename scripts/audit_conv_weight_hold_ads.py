"""Prove the retained convolution write hold pad and both actual RAM DI pairs."""
from pathlib import Path
import argparse, hashlib, json, re, sys
from audit_icache_pad_ads import cells, module, ports, sha
from audit_cpu_ads import Cone, signal
sys.path.insert(0,str(Path(__file__).with_name('gui1080_mul')))
from native_hier_cone_vector_v2 import VectorHierCone
if sys.flags.optimize:raise RuntimeError('Assertions must remain enabled')

def audit(source):
    body=module(source,'mac_conv_weight_dma')
    pads=[p for p in cells(body,'GTP_LUT6D') if p['name'].endswith('.u_line_write_hold_lut')]
    assert len(pads)==1,'Missing/duplicate native hold pad'
    pad=pads[0];assert (pad['attr'] or '').strip()=='(* PAP_DONT_TOUCH *)'
    init=ports(pad['params'])['INIT'];m=re.fullmatch(r"64'([bh])([0-9a-fA-F_]+)",init)
    assert m and int(m[2].replace('_',''),2 if m[1]=='b' else 16)==0xCCCCCCCCAAAAAAAA
    pins={p:signal(v) for p,v in ports(pad['ports']).items()}
    assert set(pins)=={'I0','I1','I2','I3','I4','I5','Z','Z5'}
    assert [pins[p] for p in ['I0','I1','I2','I3','I4','I5']]==['line_shift[120]','line_shift[121]',"1'b0","1'b0","1'b0","1'b1"]
    cone=Cone(source,'mac_conv_weight_dma')
    for value in range(4):
        inputs={'line_shift[120]':value&1,'line_shift[121]':value>>1}
        assert cone.evaluate(pins['Z5'],inputs)==value&1
        assert cone.evaluate(pins['Z'],inputs)==value>>1
    h=VectorHierCone(re.sub(r'\(\*.*?\*\)','',source,flags=re.S),root='soc_top')
    context=h.find('mac_conv_weight_dma')
    children=[x for x in h.children(context) if h.contexts[x][0]=='mac_weight_double_buffer']
    assert len(children)==1;child=children[0]
    for bit,out in [(120,pins['Z5']),(121,pins['Z'])]:
        assert h.input_binding(child,'load_data['+str(bit)+']')==(context,out),'Native child input bypass/swapped'
    ram=cells(module(source,'mac_weight_double_buffer'),'GTP_RAM32X2DP')
    assert len(ram)==544,'544-bit two-bank RAM capacity changed'
    names=[]
    for cell in ram:
        p=ports(cell['ports']);di=h.vector_bits(child,p['DI'])
        if di==('load_data[120]','load_data[121]'):
            assert cell['name'] in ['bank0_60','bank1_60'];names.append(cell['name'])
            assert p['WCLK']=='clk'
    assert sorted(names)==['bank0_60','bank1_60']
    return dict(status='PASS',scope='Native identity pad and four bank DI pins only; not routed timing/whole-SoC equivalence',
                primitive=pad['name'],truth_cases=4,padded_di_pins=4,ram_cells=544,pins=pins)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ['netlist','input-snapshot','output']:ap.add_argument('--'+name,type=Path,required=True)
    a=ap.parse_args();assert not a.output.exists();raw=a.netlist.read_bytes();snap=json.loads(a.input_snapshot.read_text(encoding='utf-8-sig'))
    assert snap['inputs']['scripts/audit_conv_weight_hold_ads.py']==sha(Path(__file__))
    result=audit(raw.decode());assert raw==a.netlist.read_bytes()
    result.update(run_id=snap['run_id'],netlist_sha256=sha(a.netlist),input_snapshot_sha256=sha(a.input_snapshot),checker_sha256=sha(Path(__file__)))
    a.output.write_text(json.dumps(result,indent=2)+'\n');print('CONV_WEIGHT_WRITE_HOLD_ADS_PASS truth_cases=4 ram_di_pins=4')

if __name__=='__main__':main()
