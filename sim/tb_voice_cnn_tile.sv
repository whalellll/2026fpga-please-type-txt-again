`timescale 1ns/1ps
module tb_voice_cnn_tile;
 parameter WRAPPER=0;
 reg clk=0;always #10 clk=~clk;
 reg resetn=0,wr=0;reg [7:0] addr=0;reg [31:0] wdata=0;wire [31:0] rdata;
 generate if(WRAPPER==0)begin:g_unit
 voice_cnn_tile_core dut(.clk(clk),.resetn(resetn),.wr(wr),.addr(addr),.wdata(wdata),.rdata(rdata));
 end else begin:g_mmio
 voice_accel_mmio #(.CNN_ENABLE(1)) dut(.clk(clk),.resetn(resetn),.counter_clear(1'b0),
  .wr(wr),.addr(32'h1fe00800|{24'b0,addr}),.wdata(wdata),.wstrb(4'hf),.hit(),.rdata(rdata),
  .microphone_sample(24'b0),.microphone_count(32'b0));
 end endgenerate
 reg [31:0] vectors[0:400000];integer c,i,j,n,k,co,p,nw,ni,no,cursor=0;
 reg [31:0] value;integer cycles=0;
 task put(input [7:0] a,input [31:0] v);begin @(negedge clk);wr=1;addr=a;wdata=v;@(negedge clk);wr=0;end endtask
 task get(input [7:0] a,output [31:0] v);begin @(negedge clk);addr=a;repeat(2)@(negedge clk);v=rdata;end endtask
 initial begin
  $readmemh("vectors.hex",vectors);repeat(4)@(negedge clk);resetn=1;
  n=vectors[cursor];cursor=cursor+1;
  for(c=0;c<n;c=c+1)begin
   k=vectors[cursor];co=vectors[cursor+1];p=vectors[cursor+2];cursor=cursor+3;
   nw=k/4*co;ni=k/4*p;no=co*p;
   put(8'h88,6);put(8'ha0,{co[15:0],k[15:0]});put(8'ha4,p);
   for(i=0;i<nw;i=i+1)begin put(8'h94,vectors[cursor]);cursor=cursor+1;end
   for(i=0;i<ni;i=i+1)begin put(8'h9c,vectors[cursor]);cursor=cursor+1;end
   put(8'h88,1);cycles=0;
   get(8'h8c,value);
   while(value[0])begin get(8'h8c,value);cycles=cycles+1;if(cycles>100000)$fatal(1,"timeout");end
   if(value!==2)$fatal(1,"completion status %h",value);
   for(i=0;i<no;i=i+1)begin put(8'hac,i);get(8'hb0,value);if(value!==vectors[cursor])$fatal(1,"case%0d result%0d got%h want%h",c,i,value,vectors[cursor]);cursor=cursor+1;end
   // Reuse the resident layer with the identical input, then abort mid-tile.
   put(8'h88,1);repeat(12)@(negedge clk);put(8'h88,2);get(8'h8c,value);if(value!==0)$fatal(1,"cancel status");
   put(8'h88,1);get(8'h8c,value);if(value!==6)$fatal(1,"cancel must invalidate input");
  end
  put(8'h88,6);put(8'ha0,32'h00200000);put(8'ha4,1);put(8'h88,1);get(8'h8c,value);if(value!==6)$fatal(1,"zeroK accepted");
  $display("VOICE_CNN_TILE_DIFFERENTIAL_PASS cases=%0d",n);$finish;
 end
 initial begin #100000000;$fatal(1,"simulation timeout");end
endmodule
