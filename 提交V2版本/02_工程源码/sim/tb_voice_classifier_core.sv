`timescale 1ns/1ps
module tb_voice_classifier_core;
 parameter CASES=32;
 reg clk=0;always #10 clk=~clk;
 reg resetn=0,start=0,model_we=0,input_we=0,result_ready=0;
 reg [10:0] model_addr=0;reg [31:0] model_data=0;
 reg [3:0] input_addr=0;reg [31:0] input_data=0;
 wire busy,done,result_valid;wire [1:0] result_layer;wire [6:0] result_index;wire [7:0] result_data;
 wire [7:0] token;wire [9:0] confidence;wire [31:0] cycles;
 voice_classifier_core dut(.clk(clk),.resetn(resetn),.start(start),
  .model_we(model_we),.model_addr(model_addr),.model_data(model_data),
  .input_we(input_we),.input_addr(input_addr),.input_data(input_data),
  .shift1(5'd8),.shift2(5'd7),.shift3(5'd7),.busy(busy),.done(done),.cycles(cycles),
  .result_valid(result_valid),.result_ready(result_ready),.result_layer(result_layer),
  .result_index(result_index),.result_data(result_data),.token(token),.confidence(confidence));
 reg [31:0] weights[0:1504];reg [31:0] inputs[0:CASES*10-1];reg [7:0] golden[0:CASES*121-1];
 integer i,c,n,ticks=0,max_cycles=0,best,second,best_token,value;
 reg holding=0;reg [7:0] held;
 always @(posedge clk)begin ticks<=ticks+1;if(ticks>3000000)$fatal(1,"timeout");end
 initial begin
  $readmemh("model.hex",weights);$readmemh("input.hex",inputs);$readmemh("golden.hex",golden);
  repeat(4)@(negedge clk);resetn=1;
  for(i=0;i<1505;i=i+1)begin model_we=1;model_addr=i;model_data=weights[i];@(negedge clk);end
  model_we=0;
  for(c=0;c<CASES;c=c+1)begin
   for(i=0;i<10;i=i+1)begin input_we=1;input_addr=i;input_data=inputs[c*10+i];@(negedge clk);end
   input_we=0;start=1;@(negedge clk);start=0;n=0;holding=0;
   best=-129;second=-129;best_token=0;
   while(!done)begin
    result_ready=ticks%5!=0;@(posedge clk);
    if(result_valid)begin
     if(holding&&held!==result_data)$fatal(1,"unstable output");
     if(result_ready)begin
      if(result_data!==golden[c*121+n])$fatal(1,"case%0d output%0d got%0d want%0d",c,n,$signed(result_data),$signed(golden[c*121+n]));
      if(n<64)begin if(result_layer!=0||result_index!=n)$fatal(1,"layer0 order");end
      else if(n<96)begin if(result_layer!=1||result_index!=n-64)$fatal(1,"layer1 order");end
      else begin
       if(result_layer!=2||result_index!=n-96)$fatal(1,"layer2 order");
       value=$signed(result_data);
       if(value>best)begin second=best;best=value;best_token=n-96;end
       else if(value>second)second=value;
      end
      n=n+1;holding=0;
     end else begin held=result_data;holding=1;end
    end
    @(negedge clk);
   end
   if(n!=121||token!=best_token||confidence!=(best-second)*1000/255)$fatal(1,"classification final mismatch");
   if(cycles>max_cycles)max_cycles=cycles;
   if(cycles>24750)$fatal(1,"classifier exceeds0.5ms at49.5MHz");
  end
  $display("VOICE_CLASSIFIER_CORE_PASS cases=%0d outputs=%0d max_cycles=%0d",CASES,CASES*121,max_cycles);$finish;
 end
endmodule
