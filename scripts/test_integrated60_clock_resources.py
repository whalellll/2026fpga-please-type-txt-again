"""Reject damaged packed-video resources without relaxing the mapped PLL check."""
from pathlib import Path
import argparse, hashlib, json, re, subprocess, sys, tempfile

ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--native-root',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();assert not a.output.exists();n=a.native_root.resolve()
    paths={'vm':n/'pds/synthesize/soc_top_syn.vm','snr':n/'pds/synthesize/soc_top.snr','clocks':n/'config/clocks.json','fdc':n/'pds/soc.fdc','top':n/'rtl/soc/soc_top.v'}
    original={key:path.read_text() for key,path in paths.items()};before={k:sha(p) for k,p in paths.items()}
    body=re.search(r'(?ms)^module video_fb_dma\b.*?^endmodule',original['vm']).group()
    cells=list(re.finditer(r'(?s)\bGTP_DRM36K_E1\s*(?:/\*.*?\*/\s*)?#\s*\((.*?)\)\s*(\\?\S+)\s*\((.*?)\);',body))
    cell=next(m.group() for m in cells if m[2]=='line_mem_0')
    assert cell.count('.DATA_WIDTH_A(64)')==1 and cell.count('.CLKA (pix_clk)')==1
    def damaged_cell(old,new):
        assert cell.count(old)==1,(old,cell.count(old))
        return original['vm'].replace(body,body.replace(cell,cell.replace(old,new,1),1),1)
    cases=[('positive',{},True),
           ('line_cell_missing',{'vm':original['vm'].replace(body,body.replace(cell,'',1),1)},False),
           ('line_width_halved',{'vm':damaged_cell('.DATA_WIDTH_A(64)','.DATA_WIDTH_A(32)')},False),
           ('line_wrong_clock',{'vm':damaged_cell('.CLKA (pix_clk)','.CLKA (ddr_clk)')},False),
           ('line_bank_cut',{'vm':damaged_cell("1'b0, data_bank_ddr,","1'b0, 1'b0,")},False),
           ('video_subtree_wrong_count',{'snr':re.sub(r'(?m)^(\|\s*\+ u_fb_dma\s*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|)\s*8\s*\|',r'\g<1> 7 |',original['snr'])},False),
           ('whole_chip_old_count',{'snr':original['snr'].replace('Total DRM = 133.5','Total DRM = 137.5')},False),
           ('wrong_declared_cpu_frequency',{'clocks':json.dumps(dict(json.loads(original['clocks']),cpu_hz=61000000))},False)]
    rows=[]
    with tempfile.TemporaryDirectory(prefix='opt60-clock-resource-') as d:
        work=Path(d)
        for name,changes,accepted in cases:
            assert accepted or any(changes[k]!=original[k] for k in changes),name
            for key,value in dict(original,**changes).items():(work/key).write_text(value)
            out=work/(name+'.json')
            command=[sys.executable,str(ROOT/'scripts/audit_cpu_dedicated_pll_ads.py'),'--netlist',str(work/'vm'),'--resources',str(work/'snr'),'--clocks',str(work/'clocks'),'--fdc',str(work/'fdc'),'--soc-top',str(work/'top'),'--output',str(out)]
            result=subprocess.run(command,capture_output=True,text=True,timeout=120)
            assert (result.returncode==0)==accepted,(name,result.stdout,result.stderr[-2000:])
            assert out.exists()==accepted,name
            row=dict(name=name,expected_accepted=accepted,exit=result.returncode)
            if accepted:
                positive=json.loads(out.read_text());assert positive['video_resources']['drm']==8 and positive['resources']['drm']==133.5
            else:row['failure']=result.stderr.splitlines()[-1]
            rows.append(row);print('CLOCK_RESOURCE_FIXTURE',name,'PASS',flush=True)
    assert {k:sha(p) for k,p in paths.items()}==before
    record=dict(status='PACKED_VIDEO_CLOCK_RESOURCE_NATIVE_AND_SEVEN_FAULTS_PASS_NOT_STA',
                native_root=n.as_posix(),native_vm_sha256=before['vm'],native_inputs_sha256=before,
                audit_script_sha256=sha(ROOT/'scripts/audit_cpu_dedicated_pll_ads.py'),test_script_sha256=sha(Path(__file__)),
                positive=positive,cases=rows,rejected_mutations=7)
    a.output.write_text(json.dumps(record,indent=2)+'\n');print(record['status'])

if __name__=='__main__':main()
