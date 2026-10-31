`timescale 1ns/1ps
module tb_voice_accel_mmio;
 reg clk=0;always #10 clk=~clk;
 reg resetn=0,wr=0;reg[31:0]addr=32'h1fe00800,wdata=0,mcount=0;reg[23:0]msample=0;
 wire[31:0]rdata;wire hit;
 voice_accel_mmio dut(.clk(clk),.resetn(resetn),.counter_clear(1'b0),.addr(addr),.wdata(wdata),
  .wr(wr),.wstrb(4'hf),.hit(hit),.rdata(rdata),.microphone_sample(msample),.microphone_count(mcount));
 reg[15:0]pcm[0:1599],levels[0:9];reg[31:0]model[0:1504],features[0:39],pooled[0:9],expected[0:1];
 reg[7:0]layers[0:120];integer i,j,ticks=0,timeout;
 task put(input[7:0]r,input[31:0]v);
  begin @(negedge clk);addr=32'h1fe00800+r;wdata=v;wr=1;@(negedge clk);wr=0;end
 endtask
 task get(input[7:0]r);
  begin addr=32'h1fe00800+r;#1;end
 endtask
 always @(posedge clk)begin ticks<=ticks+1;if(ticks>1500000)$fatal(1,"timeout");end
 initial begin
  $readmemh("pcm.hex",pcm);$readmemh("model.hex",model);$readmemh("features.hex",features);
  $readmemh("pooled.hex",pooled);$readmemh("layers.hex",layers);$readmemh("result.hex",expected);$readmemh("level.hex",levels);
  repeat(4)@(negedge clk);resetn=1;
  get(0);if(!hit||rdata!=32'h56434531)$fatal(1,"voice ID");
  put(8'h10,0);for(i=0;i<1505;i=i+1)put(8'h14,model[i]);
  put(8'h18,32'h00070708);put(8'h1c,1841);put(8'h20,489);
  put(8'h08,2);put(8'h08,1);
  for(i=0;i<400;i=i+1)begin
   get(8'h0c);if(!rdata[6])$fatal(1,"manual ready");put(8'h24,{16'b0,pcm[i]});
  end
  get(8'h0c);timeout=0;
  while(!rdata[1]&&timeout<60000)begin @(negedge clk);get(8'h0c);timeout=timeout+1;end
  if(timeout==60000)$fatal(1,"manual feature timeout");
  for(j=0;j<5;j=j+1)begin put(8'h60,j);get(8'h64);if(rdata!==features[j])$fatal(1,"manual feature word%0d",j);end
  put(8'h08,2);put(8'h5c,1);
  for(i=0;i<1600;i=i+1)begin
   msample={pcm[i],8'b0};mcount=i+1;repeat(256)@(negedge clk);
  end
  repeat(50000)@(negedge clk);
  put(8'h5c,0);
  get(8'h50);if(rdata!=0)$fatal(1,"unexpected live overflow %0d",rdata);
  for(i=0;i<8;i=i+1)begin
   get(8'h0c);if(!rdata[5])$fatal(1,"missing live frame");
   get(8'h68);if(rdata!=400+160*i)$fatal(1,"frame sample timestamp");
   get(8'h6c);if(rdata!=i)$fatal(1,"frame sequence");
   for(j=0;j<5;j=j+1)begin put(8'h60,j);get(8'h64);if(rdata!==features[i*5+j])$fatal(1,"live frame%0d word%0d got%h want%h",i,j,rdata,features[i*5+j]);end
   put(8'h08,8);
  end
  for(i=0;i<10;i=i+1)begin
   get(8'h70);if(rdata!=={16'b0,levels[i]})$fatal(1,"level%0d got%0d want%0d",i,rdata,levels[i]);
   get(8'h74);if(rdata!=160*(i+1))$fatal(1,"level sample timestamp");put(8'h08,16);
  end
  put(8'h30,0);for(i=0;i<10;i=i+1)put(8'h34,pooled[i]);put(8'h08,4);
  get(8'h0c);timeout=0;while(!rdata[4]&&timeout<30000)begin @(negedge clk);get(8'h0c);timeout=timeout+1;end
  if(timeout==30000)$fatal(1,"classifier timeout");
  get(8'h48);if(rdata[7:0]!=expected[0] || rdata[17:8]!=expected[1])$fatal(1,"classification token/confidence");
  for(i=0;i<121;i=i+1)begin put(8'h38,i);get(8'h3c);if(rdata[7:0]!==layers[i])$fatal(1,"classifier output%0d",i);end
  get(8'h0c);if(rdata[2])$fatal(1,"voice error status");
  $display("VOICE_MMIO_LIVE_C_ORACLE_PASS samples=1600 windows=8 levels=10 classifier_outputs=121");$finish;
 end
endmodule
