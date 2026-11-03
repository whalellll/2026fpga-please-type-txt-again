`timescale 1ns/1ps
module tb_voice_confidence;
 reg clk=0;always #5 clk=~clk;
 reg resetn=0,start=0,mwe=0,iwe=0;
 reg[10:0] ma=0;reg[31:0] md=0;reg[3:0] ia=0;
 wire busy,done,valid;wire[31:0]cycles;wire[1:0]layer;wire[6:0]index;
 wire[7:0]data,token;wire[9:0]confidence;
 voice_classifier_core dut(.clk(clk),.resetn(resetn),.start(start),
 .model_we(mwe),.model_addr(ma),.model_data(md),.input_we(iwe),.input_addr(ia),.input_data(32'b0),
 .shift1(5'b0),.shift2(5'b0),.shift3(5'b0),.busy(busy),.done(done),.cycles(cycles),
 .result_valid(valid),.result_ready(1'b1),.result_layer(layer),.result_index(index),
 .result_data(data),.token(token),.confidence(confidence));
 task word(input[10:0] a,input[31:0] d);begin ma=a;md=d;mwe=1;@(negedge clk);mwe=0;end endtask
 integer i,margin,ticks=0;
 always @(posedge clk)begin ticks<=ticks+1;if(ticks>2000000)$fatal(1,"timeout");end
 initial begin
  repeat(4)@(negedge clk);resetn=1;
  for(i=0;i<1505;i=i+1)word(i,0);
  for(i=0;i<25;i=i+1)word(1480+i,-128);
  for(i=0;i<10;i=i+1)begin ia=i;iwe=1;@(negedge clk);iwe=0;end
  for(margin=0;margin<256;margin=margin+1)begin
   word(1481,127);word(1482,127-margin);
   start=1;@(negedge clk);start=0;
   while(!done)@(negedge clk);
   if(token!=1 || confidence!=margin*1000/255)
    $fatal(1,"margin%0d token%0d confidence%0d",margin,token,confidence);
  end
  $display("VOICE_CONFIDENCE_ALL256_MARGINS_EXACT_PASS");$finish;
 end
endmodule
