"""Cycle-compare packed line RAM with the frozen two-bank video implementation."""
from pathlib import Path
import argparse, hashlib, json, os, re, subprocess

ROOT=Path(__file__).resolve().parents[1]
BIN=Path('G:/fpga/workspace/tools/msys64/ucrt64/bin')
os.environ['PATH']=str(BIN)+';G:/fpga/workspace/tools/msys64/usr/bin;'+os.environ['PATH']
BASE='182a0c50827a0634d8e1840e770e47c815551e79'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    old=subprocess.check_output(['git','show',BASE+':rtl/video/video_fb_dma.v'],cwd=ROOT).decode()
    reference=a.output/'before.v';reference.write_text(old.replace('module video_fb_dma #(','module video_fb_dma_before #(',1))
    ports=re.findall(r'^\s*output\s+(?:wire|reg)\s*(\[[^]]+\])?\s*(\w+)\s*,?\s*$',old,re.M)
    assert len(ports)==18,len(ports)
    wires='\n'.join(f'wire {width} ref_{name};' for width,name in ports)
    connections=','.join(f'.{name}(ref_{name})' for _,name in ports)
    actual='{'+','.join(name for _,name in ports)+'}'
    expected='{'+','.join('ref_'+name for _,name in ports)+'}'
    checks=f'''always @(negedge pix_clk) if(pix_resetn && ddr_resetn)
      if({actual} !== {expected}) fail("packed line RAM changed pixel or DDR transaction cycle");
    always @(negedge ddr_clk) if(pix_resetn && ddr_resetn)
      if({actual} !== {expected}) fail("packed line RAM changed DDR-domain outputs");
    '''
    cases=[]
    for width in [640,1280,1920]:
        tb=(ROOT/'sim/tb_video_fb_dma.sv').read_text()
        params=f'.V_ACT(4),.H_ACT({width})'
        tb=tb.replace('video_fb_dma #(.V_ACT(4)) dut(.*);',
          wires+f'\nvideo_fb_dma #({params}) dut(.*);\nvideo_fb_dma_before #({params}) reference_dut({connections},.*);\n'+checks)
        bursts=width//256 if width%256==0 else width//128
        beats=16 if width%256==0 else 8
        tb=tb.replace('(ar_count / 5) % 4',f'(ar_count / {bursts}) % 4').replace('ar_count % 5',f'ar_count % {bursts}')
        tb=tb.replace('ar_count < 20',f'ar_count < {bursts*4}').replace('expected_line * 640',f'expected_line * {width//2}')
        tb=tb.replace('expected_burst * 128',f'expected_burst * {beats*8}')
        tb=tb.replace("fb_arlen != 4'hf",f"fb_arlen != 4'd{beats-1}").replace('response_beat == 15',f'response_beat == {beats-1}')
        tb=tb.replace('wait (ar_count >= 5)',f'wait (ar_count >= {bursts})').replace('wait (ar_count >= 25)',f'wait (ar_count >= {bursts*5})')
        tb=tb.replace("fb_rdata <= {16{16'hf800}};",'''for(integer lane=0;lane<16;lane=lane+1)
          fb_rdata[lane*16+:16] <= lane==0 ? 16'hf800 : (ar_count*211+response_beat*17+lane);''')
        tb=tb.replace('fb_arready <= !response_active;', 'fb_arready <= !response_active && (ar_count+response_beat)%3!=1;')
        # Avoid a deterministic stall before the first accepted transaction.
        tb=tb.replace('(ar_count+response_beat)%3!=1', '($time/5)%3!=1')
        source=a.output/f'tb{width}.sv';source.write_text(tb)
        sim=a.output/f'video{width}.vvp'
        compile=subprocess.run([str(BIN/'iverilog.exe'),'-g2012','-s','tb_video_fb_dma','-o',str(sim),
                  str(ROOT/'rtl/video/video_fb_dma.v'),str(reference),str(source)],capture_output=True,timeout=60)
        (a.output/f'compile{width}.log').write_bytes(compile.stdout+compile.stderr);assert compile.returncode==0,(compile.returncode,compile.stderr.decode(errors='replace'))
        child=subprocess.run([str(BIN/'vvp.exe'),str(sim)],capture_output=True,timeout=180)
        (a.output/f'run{width}.log').write_bytes(child.stdout+child.stderr)
        assert child.returncode==0 and b'VIDEO_FB_DMA_PASS' in child.stdout,child.stdout.decode()
        cases.append(dict(width=width,log_sha256=sha(a.output/f'run{width}.log')))
    result=dict(status='PACKED_VIDEO_LINE_RAM_CYCLE_EQUIVALENCE_PASS_NOT_NATIVE_OR_BOARD',baseline_commit=BASE,
      before_sha256=hashlib.sha256(old.encode()).hexdigest(),sources_sha256={n:sha(ROOT/n) for n in ['rtl/video/video_fb_dma.v','sim/tb_video_fb_dma.sv']},
      compared_outputs=len(ports),cases=cases,pnr=False,board=False)
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])

if __name__=='__main__':main()
