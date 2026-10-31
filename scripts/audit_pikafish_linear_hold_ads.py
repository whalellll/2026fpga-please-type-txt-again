"""Bind native retained identity LUTs to both dedicated NNUE linear RAM DI buses."""
from pathlib import Path
import argparse, hashlib, json, re
from audit_icache_pad_ads import cells, module, ports
from audit_cpu_ads import signal

def audit(source):
    body=module(source,'pikafish_mlp_dedicated')
    pads=[p for p in cells(body,'GTP_LUT6D') if p['name'].endswith('.u_linear_hold_lut')]
    assert len(pads)==16,('Expected16 retained dual-output pads',len(pads))
    outputs={};inputs={}
    for pad in pads:
        assert (pad['attr'] or '').strip()=='(* PAP_DONT_TOUCH *)'
        match=re.search(r'g_linear_hold\[(\d+)\]',pad['name']);assert match
        pair=int(match[1]);assert 0<=pair<16
        init=ports(pad['params'])['INIT'];m=re.fullmatch(r"64'([bh])([0-9a-fA-F_]+)",init);assert m
        assert int(m[2].replace('_',''),2 if m[1]=='b' else 16)==0xCCCCCCCCAAAAAAAA
        pins={p:signal(v) for p,v in ports(pad['ports']).items()}
        assert [pins[p] for p in ['I2','I3','I4','I5']]==["1'b0","1'b0","1'b0","1'b1"]
        for bit,inp,out in [(pair*2,'I0','Z5'),(pair*2+1,'I1','Z')]:
            want=f'lin_pack[{bit}]' if bit<24 else f'linear_q[{bit-24}]'
            # Each byte is the exact unsigned seven-bit linear activation.
            assert pins[inp]==want or (bit%8==7 and pins[inp]=="1'b0"),(bit,pins[inp],want)
            outputs[bit]=pins[out];inputs[bit]=pins[inp]
    assert len(outputs)==32
    ram=[p for p in cells(body,'GTP_RAM32X2DP') if re.fullmatch(r'lin[01]_\d+',p['name'])]
    assert len(ram)==32,('Linear RAM capacity changed',len(ram))
    checked=padded=0
    for cell in ram:
        p=ports(cell['ports']);pair=int(cell['name'].split('_')[1]);assert p['WCLK']=='clk'
        di=[signal(s.strip()) for s in p['DI'].strip('{} ').split(',')]
        assert len(di)==2
        for bit,actual in [(pair*2+1,di[0]),(pair*2,di[1])]:
            assert actual==outputs[bit] or (inputs[bit]=="1'b0" and actual=="1'b0"),(cell['name'],bit,actual,outputs[bit])
            checked+=1
            if inputs[bit]!="1'b0":padded+=1
    return dict(status='PASS',pads=16,identity_truth_cases=64,ram_cells=32,padded_di_pins=padded,ram_di_pins_checked=checked,
                scope='Native identity function and actual two linear RAM DI buses; routed hold remains a separate gate')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ['netlist','input-snapshot','output']:ap.add_argument('--'+name,type=Path,required=True)
    a=ap.parse_args();assert not a.output.exists()
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    snap=json.loads(a.input_snapshot.read_text(encoding='utf-8-sig'))
    assert snap['inputs']['scripts/audit_pikafish_linear_hold_ads.py']==sha(Path(__file__))
    result=audit(a.netlist.read_text())
    result.update(run_id=snap['run_id'],netlist_sha256=sha(a.netlist),input_snapshot_sha256=sha(a.input_snapshot),checker_sha256=sha(Path(__file__)))
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(f"PIKAFISH_LINEAR_HOLD_ADS_PASS pads=16 checked_di_pins={result['ram_di_pins_checked']} padded_di_pins={result['padded_di_pins']}")
if __name__=='__main__':main()
