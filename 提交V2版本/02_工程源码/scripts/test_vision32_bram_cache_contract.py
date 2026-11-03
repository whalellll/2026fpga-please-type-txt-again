"""Positive whole-SoC mapped cache proof and mutations of actual native pins.

No generated miniature implementation is accepted as the positive fixture.
Run against the fresh PDS whole-SoC VM; each worker is a separate process.
"""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys,traceback
from audit_icache_pad_ads import module,cells,ports
from vision32_bram_cache_contract import bram_cache_contract

def mutate(text,label):
    # cells() strips comments before matching. Normalize the input the same
    # way so replacements bind the real instance, including native comments.
    text=re.sub(r'/\*.*?\*/|//[^\r\n]*','',text,flags=re.S)
    if label=='positive':return text
    pe=label=='apm_weight_bit'
    name='vision32_pe' if pe else 'vision32_layer'
    body=module(text,name)
    kind='GTP_APM_E2' if pe else ('GTP_DFF' if label=='selector_hold' else 'GTP_DRM18K_E1')
    targets=[m for m in cells(body,kind) if pe or m['name']==('weight_tail_selected_q_vname' if label=='selector_hold' else 'weight_tail_hi')]
    assert targets
    m=targets[0];old=m[0];p=ports(m['ports'])
    if label=='tail_read_row_alias':field,value='ADDRB',p['ADDRB'].replace('weight_ra[6]','weight_ra[5]')
    elif label=='tail_write_row_alias':field,value='ADDRA',p['ADDRA'].replace('load_index[7]','load_index[6]')
    elif label=='tail_data_permutation':field,value='DIB',p['DIB'].replace('mem_rsp_rdata[31]','mem_rsp_rdata[30]')
    elif label=='tail_hi_wrong_parity':
        lo=next(x for x in cells(body,kind) if x['name']=='weight_tail_lo')
        field,value='WEA',ports(lo['ports'])['WEA']
    elif label=='read_disabled':field,value='CEB',"1'b0"
    elif label=='wrong_clock':field,value='CLKB',"1'b0"
    elif label=='selector_hold':field,value='D',p['Q']
    elif label=='apm_weight_bit':field,value='Y',p['Y'].replace('weights[0]','weights[1]')
    elif label=='extra_read_stage':field,value='DOB_REG','1'
    elif label=='half_capacity':field,value='DATA_WIDTH_B','16'
    elif label=='write_byte_disabled':field,value='BWEA',"4'b0111"
    elif label=='ram_read_address_hold':field,value='ADDRB_HOLD',"1'b1"
    else:raise ValueError(label)
    pat=r'(\.'+re.escape(field)+r'\s*\()[^()]*(\))'
    new,n=re.subn(pat,lambda x:x[1]+value+x[2],old)
    assert n==1 and old!=new,(label,n)
    assert text.count(old)==1
    return text.replace(old,new,1)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--netlist',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--worker',choices=['positive','tail_read_row_alias','tail_write_row_alias','tail_data_permutation','tail_hi_wrong_parity','read_disabled','wrong_clock','selector_hold','apm_weight_bit','extra_read_stage','half_capacity','write_byte_disabled','ram_read_address_hold'])
    a=p.parse_args();sha=lambda x:hashlib.sha256(x.read_bytes()).hexdigest()
    if a.worker:
        text=mutate(a.netlist.read_text(),a.worker)
        r=dict(case=a.worker,original_netlist_sha256=sha(a.netlist),mutated_netlist_sha256=hashlib.sha256(text.encode()).hexdigest())
        try:
            r['proof']=bram_cache_contract(text);r['accepted']=True
        except (AssertionError,ValueError,KeyError) as e:
            r.update(accepted=False,rejection=repr(e))
        a.output.write_text(json.dumps(r,indent=2)+'\n')
        assert r['accepted']==(a.worker=='positive'),r
        print(a.worker,'PASS' if r['accepted'] else 'REJECTED',flush=True)
        return
    a.output.mkdir(exist_ok=False,parents=True)
    cases=p._actions[-1].choices
    results=[]
    for case in cases:
        output=a.output/(case+'.json');log=a.output/(case+'.log')
        cmd=[sys.executable,'-X','utf8','-B',str(Path(__file__).resolve()),'--netlist',str(a.netlist),'--output',str(output),'--worker',case]
        with log.open('wb') as f:code=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=120).returncode
        results.append(dict(case=case,exit=code,log_sha256=sha(log),receipt_sha256=sha(output) if output.exists() else None))
        print(case,code,flush=True)
        (a.output/'progress.json').write_text(json.dumps(results,indent=2)+'\n')
        assert code==0,case
    r=dict(status='ACTUAL_WHOLE_SOC_BRAM_MAPPING_POSITIVE_AND_12_NATIVE_MUTATIONS_PASS_NOT_STA_NOT_BOARD',netlist_sha256=sha(a.netlist),checker_sha256=sha(Path(__file__).with_name('vision32_bram_cache_contract.py')),test_sha256=sha(Path(__file__)),cases=results)
    (a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(r['status'])

if __name__=='__main__':main()
