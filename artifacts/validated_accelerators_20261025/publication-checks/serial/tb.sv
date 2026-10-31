`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=!clk;reg resetn=0,wr=0;reg [7:0] wa=0;reg [31:0] wd=0;wire busy;wire [31:0] rd;
reg signed [32:0] bases[0:2125-1];reg [31:0] scales[0:2125-1];reg [63:0] gold[0:2125-1];integer i,n;
vision32_layer dut(.clk(clk),.resetn(resetn),.reg_wr_en(wr),.reg_wr_addr(wa),.reg_wr_data(wd),.reg_wr_strb(4'hf),.reg_rd_addr(8'h0),.reg_rd_data(rd),
 .mem_req_ready(1'b0),.mem_w_ready(1'b0),.mem_rsp_valid(1'b0),.mem_rsp_rdata(32'b0),.mem_rsp_last(1'b0),.mem_rsp_error(1'b0),.busy_out(busy));
task inject(input signed [32:0] b,input [31:0] s);
begin @(negedge clk);dut.state=20;dut.biased=b;dut.scales[0]=s;dut.q_channel=0;dut.stop_pending=0;dut.cycles=0;dut.c_timeout=32'h7fffffff;dut.c_flags=0;end
endtask
initial begin
 $readmemh("bases.hex",bases);$readmemh("scales.hex",scales);$readmemh("gold.hex",gold);
 repeat(3)@(negedge clk);resetn=1;
 for(i=0;i<2125;i=i+1)begin
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
 $display("SERIAL_LEGACY_PRODUCTS_ABORT_RESET_PASS cases=2125");$finish;
end
endmodule
