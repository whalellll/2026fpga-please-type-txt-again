`timescale 1ns/1ps
module tb_voice_feature_core;
 parameter CASES=72;
 reg clk=0;always #10 clk=~clk;
 reg resetn=0,start=0,valid=0,ready=0;
 reg signed [15:0] data=0;
 reg signed [31:0] offset=0,scale=0;
 wire input_ready,busy,done,out_valid;
 wire [4:0] out_index;
 wire [7:0] out_data;
 wire [31:0] cycles;
 voice_feature_core dut(.clk(clk),.resetn(resetn),.start(start),
  .sample_valid(valid),.sample_ready(input_ready),.sample_data(data),
  .feature_offset(offset),.feature_scale(scale),.busy(busy),.done(done),.cycles(cycles),
  .feature_valid(out_valid),.feature_ready(ready),.feature_index(out_index),.feature_data(out_data));
 reg [15:0] pcm[0:CASES*400-1];reg [31:0] params[0:CASES*2-1];reg [7:0] golden[0:CASES*20-1];
 integer c,i,n,ticks=0,max_cycles=0;
 reg [7:0] held;reg holding;
 always @(posedge clk)begin
  ticks<=ticks+1;
  if(ticks>5000000)$fatal(1,"bounded timeout");
 end
 initial begin
  $readmemh("pcm.hex",pcm);$readmemh("params.hex",params);$readmemh("golden.hex",golden);
  repeat(4)@(negedge clk);resetn=1;
  for(c=0;c<CASES;c=c+1)begin
   offset=params[2*c];scale=params[2*c+1];start=1;@(negedge clk);start=0;
   for(i=0;i<400;i=i+1)begin
    valid=1;data=pcm[c*400+i];
    while(!input_ready)@(negedge clk);
    @(negedge clk);
    valid=0;if(i%13==0)@(negedge clk);
   end
   n=0;holding=0;
   while(!done)begin
    ready=(ticks%7)!=0;
    @(posedge clk);
    if(out_valid)begin
     if(holding && held!==out_data)$fatal(1,"output changed under backpressure");
     if(ready)begin
      if(out_index!==n || out_data!==golden[c*20+n])
       $fatal(1,"case%0d bin%0d got%0d want%0d",c,n,$signed(out_data),$signed(golden[c*20+n]));
      n=n+1;holding=0;
     end else begin held=out_data;holding=1;end
    end
    @(negedge clk);
   end
   if(n!=20)$fatal(1,"missing feature");
   if(cycles>max_cycles)max_cycles=cycles;
   if(cycles>49500)$fatal(1,"frame budget >1ms at49.5MHz");
  end
  // Reset cancels incomplete input. No output may be committed afterward.
  start=1;@(negedge clk);start=0;valid=1;
  repeat(10)@(negedge clk);resetn=0;valid=0;
  repeat(3)@(negedge clk);resetn=1;
  repeat(15)begin @(negedge clk);if(out_valid||busy)$fatal(1,"reset did not cancel");end
  $display("VOICE_FEATURE_CORE_PASS cases=%0d outputs=%0d max_cycles=%0d",CASES,CASES*20,max_cycles);$finish;
 end
endmodule
