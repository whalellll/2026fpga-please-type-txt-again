"""Bind metadata state reduction to native mapped FFs without removing data boundaries."""
from pathlib import Path
import argparse, hashlib, json, re

def inspect(root):
    vm=root/'pds/synthesize/soc_top_syn.vm'
    text=re.search(r'(?ms)^module mac_weight_double_buffer\b.*?^endmodule',vm.read_text()).group()
    pattern=r'\b(GTP_DFF\w*)\s*/\*.*?\*/\s*#\((.*?)\)\s*(\\\S+|\w+)\s*\((.*?)\);'
    ff={}
    for cell,params,name,body in re.findall(pattern,text,re.S):
        pins={k:v.strip() for k,v in re.findall(r'\.(\w+)\s*\((.*?)\)',body,re.S)}
        q=pins['Q'];assert q not in ff
        assert pins['CLK']=='clk' and 'GRS_EN("TRUE")' in params and ".INIT(1'b0)" in params
        ff[q]=dict(cell=cell,pins=pins)
    return ff,hashlib.sha256(vm.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    assert not a.output.exists()
    before,bh=inspect(a.baseline);after,ch=inspect(a.candidate)
    removed={q for q in before if q.startswith(('pending_model_id[','pending_generation[','pending_tile_id[','pending_lines['))}
    assert len(removed)==110,'Unexpected baseline mapped metadata width'
    assert set(after)==set(before)-removed,'A protected FF disappeared, or duplicate metadata remains'
    for q,ff in after.items():
        assert ff['cell']==before[q]['cell'],q
        if q.startswith(('active_model_id[','active_generation[','active_tile_id[','active_lines[')):
            assert ff['pins']['D']=='target_'+q.removeprefix('active_'),(q,ff)
        if q.startswith(('target_model_id[','target_generation[','target_tile_id[','target_lines[','active_model_id[','active_generation[','active_tile_id[','active_lines[','read_data[')):
            assert ff['pins']['CE'] not in ["1'b0","1'b1"],q
    record=dict(status='NATIVE_WEIGHT_METADATA_110_FF_REMOVED_ALL_OTHER_STORE_FF_RETAINED_NOT_STA',
                baseline_vm_sha256=bh,candidate_vm_sha256=ch,baseline_ff=len(before),candidate_ff=len(after),
                removed=sorted(removed),retained_ff=after,
                scope='Native integrated configuration prunes tile_id to8 bits; source supports32. All other named FF/clock/init/cell boundaries retained. Public control equivalence and final STA remain separate.')
    a.output.write_text(json.dumps(record,indent=2)+'\n');print(record['status'],flush=True)

if __name__=='__main__':main()
