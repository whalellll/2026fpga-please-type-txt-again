"""Full signed33 x unsigned31 RTL product, plus stop/reset during serial step."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from workspace_paths import workspace_path,wsl_path
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);a=p.parse_args();o=workspace_path(a.output);o.mkdir(parents=True,exist_ok=False)
values=[-2**32,-2**32+1,-2**31-1,-2**31,-1,0,1,2**31-1,2**31,2**32-2,2**32-1]
scales=[0,1,2,255,2**15,2**30,2**31-1]
cases=[(b,s) for b in values for s in scales];rng=random.Random(20261025)
cases += [(rng.randrange(-2**32,2**32),rng.randrange(2**31)) for _ in range(2048)]
for name,bits,items in [('bases',33,[b for b,s in cases]),('scales',32,[s for b,s in cases]),('gold',64,[b*s for b,s in cases])]:
 (o/(name+'.hex')).write_text(''.join(f'{v&((1<<bits)-1):0{(bits+3)//4}x}\n' for v in items))
tb='''`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=!clk;reg resetn=0,wr=0;reg [7:0] wa=0;reg [31:0] wd=0;wire busy;wire [31:0] rd;
reg signed [32:0] bases[0:__CASE_COUNT__-1];reg [31:0] scales[0:__CASE_COUNT__-1];reg [63:0] gold[0:__CASE_COUNT__-1];integer i,n;
vision32_layer dut(.clk(clk),.resetn(resetn),.reg_wr_en(wr),.reg_wr_addr(wa),.reg_wr_data(wd),.reg_wr_strb(4'hf),.reg_rd_addr(8'h0),.reg_rd_data(rd),
 .mem_req_ready(1'b0),.mem_w_ready(1'b0),.mem_rsp_valid(1'b0),.mem_rsp_rdata(32'b0),.mem_rsp_last(1'b0),.mem_rsp_error(1'b0),.busy_out(busy));
task inject(input signed [32:0] b,input [31:0] s);
begin @(negedge clk);dut.state=20;dut.biased=b;dut.scales[0]=s;dut.q_channel=0;dut.stop_pending=0;dut.cycles=0;dut.c_timeout=32'h7fffffff;dut.c_flags=0;end
endtask
initial begin
 $readmemh("bases.hex",bases);$readmemh("scales.hex",scales);$readmemh("gold.hex",gold);
 repeat(3)@(negedge clk);resetn=1;
 for(i=0;i<__CASE_COUNT__;i=i+1)begin
  inject(bases[i],scales[i]);n=0;
  while(dut.state!=21 && n<40)begin @(negedge clk);n=n+1;end
  if(n!=32 || dut.product!==gold[i])$fatal(1,"PRODUCT case=%0d cycles=%0d got=%h expected=%h",i,n,dut.product,gold[i]);
 end
 inject(-33'sd4294967296,32'h7fffffff);repeat(5)@(negedge clk);
 wa=8'h08;wd=2;wr=1;@(negedge clk);wr=0;repeat(5)@(negedge clk);
 if(busy || !dut.error || dut.error_code!=4)$fatal(1,"ABORT");
 inject(33'sd4294967295,32'h7fffffff);repeat(5)@(negedge clk);resetn=0;@(negedge clk);resetn=1;@(negedge clk);
 if(busy)$fatal(1,"RESET");
 inject(33'sd4294967295,32'h7fffffff);repeat(32)@(negedge clk);
 if(dut.product!==64'h7ffffffe80000001)$fatal(1,"RESTART %h",dut.product);
 $display("SERIAL_LEGACY_PRODUCTS_ABORT_RESET_PASS cases=__CASE_COUNT__");$finish;
end
endmodule
'''.replace('__CASE_COUNT__',str(len(cases)))
(o/'tb.sv').write_text(tb)
sources=[R/'rtl/mac_accel/vision32_pe.v',R/'rtl/mac_accel/vision32_layer.v',o/'tb.sv']
temporary=o/'tmp';temporary.mkdir()
cmd='set -eu; export TMPDIR='+wsl_path(temporary)+'; cd '+wsl_path(o)+'; iverilog -g2012 -s tb -o run.vvp '+' '.join(wsl_path(s) for s in sources)+'; vvp run.vvp'
q=subprocess.run(['wsl.exe','-d','pikafish-verify','--','sh','-c',cmd],capture_output=True,timeout=180)
(o/'simulation.log').write_bytes(q.stdout+q.stderr);assert q.returncode==0,(q.stdout+q.stderr)[-2000:]
result=dict(status='SERIAL_LEGACY_SIGNED33_UNSIGNED31_PRODUCT_ABORT_RESET_PASS_NOT_BOARD',cases=len(cases),inputs_sha256={str(s.relative_to(R)):hashlib.sha256(s.read_bytes()).hexdigest() for s in sources})
(o/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
