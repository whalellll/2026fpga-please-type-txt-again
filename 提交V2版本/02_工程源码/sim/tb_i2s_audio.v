`timescale 1ns/1ps
module tb_i2s_audio;
 localparam[23:0]MIC_PATTERN=24'h35a96c;
 localparam[15:0]PLAY_SAMPLE=16'ha55a;
 reg clk,resetn,mic,wr,clear;reg[15:0]data;
 wire bclk,ws,amp,full;wire[4:0]level;wire[23:0]sample;
 wire[31:0]count,underflows;
 i2s_audio_duplex dut(.clk(clk),.resetn(resetn),.counter_clear(clear),
  .mic_sd(mic),.i2s_bclk(bclk),.i2s_ws(ws),.amp_sd(amp),.sample_write(wr),
  .sample_data(data),.fifo_full(full),.fifo_level(level),
  .microphone_sample(sample),.microphone_count(count),
  .playback_underflows(underflows),.microphone_read(1'b0));
 always #5 clk=~clk;
 integer cpu_cycles,rise_index,got_bits,got_right_bits,i;
 integer frame_start,frame_end,frame_span,frame_sum,min_frame,max_frame;
 reg[15:0]captured_play,captured_right;
 always@(posedge clk)cpu_cycles=cpu_cycles+1;
 always@(posedge bclk)if(resetn)begin
  if(rise_index>=1&&rise_index<=16&&ws==0&&got_bits<16)begin
   captured_play={captured_play[14:0],amp};got_bits=got_bits+1;end
  if(rise_index>=33&&rise_index<=48&&ws==1&&got_right_bits<16)begin
   captured_right={captured_right[14:0],amp};got_right_bits=got_right_bits+1;end
  if(rise_index==63)rise_index=0;else rise_index=rise_index+1;
 end
 always@(negedge bclk)begin
  if(!resetn)mic=0;
  else if(rise_index>=1&&rise_index<=24)mic=MIC_PATTERN[24-rise_index];
  else mic=0;
 end
 task check;input condition;input[8*80-1:0]message;begin
  if(!condition)begin $display("TB_I2S_AUDIO_FAIL %0s",message);$fatal(1);end
 end endtask
 task push_sample;input[15:0]value;begin
  @(negedge clk);data=value;wr=1;@(negedge clk);wr=0;
 end endtask
 initial begin
  clk=0;resetn=0;mic=0;wr=0;clear=0;data=0;cpu_cycles=0;rise_index=0;
  got_bits=0;got_right_bits=0;captured_play=0;captured_right=0;
  frame_sum=0;min_frame=32'h7fffffff;max_frame=0;
  repeat(4)@(negedge clk);resetn=1;push_sample(PLAY_SAMPLE);
  wait(got_bits==16&&got_right_bits==16);
  check(captured_play===PLAY_SAMPLE&&captured_right===PLAY_SAMPLE,
   "playback data is not MSB-first in both slots");
  wait(count>=4);check(sample===MIC_PATTERN,"microphone payload alignment mismatch");
  @(posedge ws);frame_start=cpu_cycles;
  for(i=0;i<16;i=i+1)begin
   @(posedge ws);frame_end=cpu_cycles;frame_span=frame_end-frame_start;
   frame_sum=frame_sum+frame_span;if(frame_span<min_frame)min_frame=frame_span;
   if(frame_span>max_frame)max_frame=frame_span;frame_start=frame_end;
  end
  check(min_frame>=3093&&max_frame<=3094,"frame jitter outside 3093..3094");
  check(frame_sum==49500,"16 frames do not average exactly 16 kHz");
  @(negedge clk);clear=1;@(posedge clk);#1;
  check(count==0&&underflows==0,"counter clear failed");
  @(negedge clk);clear=0;wait(level==0);wait(underflows>0);
  $display("TB_I2S_AUDIO_PASS frame_sum=%0d min=%0d max=%0d mic=%h left=%h right=%h",
   frame_sum,min_frame,max_frame,sample,captured_play,captured_right);$finish;
 end
endmodule
