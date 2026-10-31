`timescale 1ns/1ps
module tb_voice_cnn_quant;
 reg clk=0;always #10 clk=~clk;
 reg resetn=0,wr=0;reg [7:0] addr=0;reg [31:0] wdata=0;wire [31:0] rdata;
 voice_cnn_tile_core dut(.clk(clk),.resetn(resetn),.wr(wr),.addr(addr),.wdata(wdata),.rdata(rdata));
 reg [31:0] vectors[0:200000];integer cursor=0,c,n,i,k,co,p,nw,ni,no,waits,input_start,j;
 reg [31:0] value;
 task put(input [7:0] a,input [31:0] v);begin @(negedge clk);wr=1;addr=a;wdata=v;@(negedge clk);wr=0;end endtask
 task get(input [7:0] a,output [31:0] v);begin @(negedge clk);addr=a;repeat(2)@(negedge clk);v=rdata;end endtask
 initial begin
  $readmemh("quant.hex",vectors);repeat(4)@(negedge clk);resetn=1;
  get(8'hdc,value);if(value!==1)$fatal(1,"quant capability absent");
  n=vectors[cursor];cursor=cursor+1;
  for(c=0;c<n;c=c+1)begin
   k=vectors[cursor];co=vectors[cursor+1];p=vectors[cursor+2];cursor=cursor+3;
   nw=k/4*co;ni=k/4*p;no=co*p;
   put(8'h88,6);put(8'ha0,{co[15:0],k[15:0]});put(8'ha4,p);
   put(8'hd0,vectors[cursor]);put(8'hd4,vectors[cursor+1]);cursor=cursor+2;
   for(i=0;i<co;i=i+1)begin
    put(8'hc0,i);put(8'hc4,vectors[cursor]);put(8'hc8,vectors[cursor+1]);put(8'hcc,vectors[cursor+2]);cursor=cursor+3;
   end
   for(i=0;i<nw;i=i+1)begin put(8'h94,vectors[cursor]);cursor=cursor+1;end
   input_start=cursor;
   for(i=0;i<ni;i=i+1)begin put(8'h9c,vectors[cursor]);cursor=cursor+1;end
   put(8'hbc,1);put(8'h88,1);get(8'h8c,value);waits=0;
   while(value[0])begin get(8'h8c,value);waits=waits+1;if(waits>100000)$fatal(1,"timeout");end
   if(value!==2)$fatal(1,"status %h",value);
   for(i=0;i<no;i=i+1)begin
    put(8'hac,i);get(8'hb0,value);
    if(value!==vectors[cursor])$fatal(1,"case%0d output%0d got%h want%h",c,i,value,vectors[cursor]);cursor=cursor+1;
   end
   // Cancellation at every epilogue stage must suppress partial output.
   for(i=0;i<7;i=i+1)begin
    put(8'h88,2);
    for(j=0;j<ni;j=j+1)put(8'h9c,vectors[input_start+j]);
    put(8'h88,1);repeat(3*k/4+i+1)@(negedge clk);put(8'h88,2);
    get(8'h8c,value);if(value!==0)$fatal(1,"cancel status");
    put(8'hac,0);get(8'hb0,value);if(value!==0)$fatal(1,"cancel publishes output");
   end
  end
  put(8'h88,6);put(8'ha0,32'h00010004);put(8'ha4,1);put(8'h94,0);put(8'h9c,0);
  put(8'hbc,1);put(8'h88,1);get(8'h8c,value);if(value!==6)$fatal(1,"missing quant params accepted");
  $display("VOICE_CNN_QUANT_EXACT_AND_CANCEL_PASS cases=%0d",n);$finish;
 end
 initial begin #100000000;$fatal(1,"simulation timeout");end
endmodule
