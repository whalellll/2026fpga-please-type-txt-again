`timescale 1ns/1ps

module tb_audio_mmio;
 reg clk,resetn,wr,fifo_full;
 reg[31:0]addr,wdata,microphone_count,playback_underflows;
 reg[3:0]wstrb;
 reg[4:0]fifo_level;
 reg[23:0]microphone_sample;
 reg[23:0]microphone_fifo_data;
 reg microphone_fifo_empty,microphone_fifo_full;
 reg[9:0]microphone_fifo_level;
 reg[31:0]microphone_overflows;
 wire[31:0]rdata;
 wire hit,sample_write,counter_clear,microphone_read;
 wire[15:0]sample_data;
 audio_mmio dut(.clk(clk),.resetn(resetn),.addr(addr),.wr(wr),.wdata(wdata),
  .wstrb(wstrb),.rdata(rdata),.hit(hit),.sample_write(sample_write),
  .sample_data(sample_data),.fifo_full(fifo_full),.fifo_level(fifo_level),
  .microphone_sample(microphone_sample),.microphone_count(microphone_count),
  .playback_underflows(playback_underflows),.counter_clear(counter_clear),
  .microphone_read(microphone_read),.microphone_fifo_data(microphone_fifo_data),
  .microphone_fifo_empty(microphone_fifo_empty),
  .microphone_fifo_full(microphone_fifo_full),
  .microphone_fifo_level(microphone_fifo_level),.microphone_overflows(microphone_overflows));
 always #5 clk=~clk;
 task check;input condition;input[8*80-1:0]message;begin
  if(!condition)begin $display("TB_AUDIO_MMIO_FAIL %0s",message);$fatal(1);end
 end endtask
 task begin_write;input[31:0]a;input[31:0]d;input[3:0]s;begin
  @(negedge clk);addr=a;wdata=d;wstrb=s;wr=1;@(posedge clk);#1;
 end endtask
 task end_write;begin
  @(negedge clk);wr=0;@(posedge clk);#1;
  check(!sample_write,"sample_write lasted longer than one cycle");
  check(!counter_clear,"counter_clear lasted longer than one cycle");
  check(!microphone_read,"microphone_read lasted longer than one cycle");
 end endtask
 initial begin
  clk=0;resetn=0;addr=0;wr=0;wdata=0;wstrb=0;fifo_full=0;fifo_level=21;
  microphone_sample=24'habc123;microphone_count=32'h12345678;
  playback_underflows=32'h89abcdef;
  microphone_fifo_data=24'hfedcba;microphone_fifo_empty=0;
  microphone_fifo_full=1;microphone_fifo_level=512;microphone_overflows=32'h10203040;
  repeat(3)@(negedge clk);resetn=1;@(posedge clk);#1;
  check(!sample_write&&!counter_clear,"pulse outputs not clear after reset");
  addr=32'h1fe005ff;#1;check(!hit,"address below window hit");
  addr=32'h1fe00600;#1;check(hit&&rdata===32'h41554431,"ID mismatch");
  addr=32'h1fe00604;#1;check(rdata===32'h00020000,"capture v2 version mismatch");
  fifo_full=1;addr=32'h1fe00610;#1;check(rdata===32'h00000115,"status mismatch");
  addr=32'h1fe00614;#1;check(rdata===32'h00abc123,"mic sample mismatch");
  addr=32'h1fe00618;#1;check(rdata===32'h12345678,"mic count mismatch");
  addr=32'h1fe0061c;#1;check(rdata===32'h89abcdef,"underflow mismatch");
  addr=32'h1fe00620;#1;check(rdata===32'h00fedcba,"capture head mismatch");
  addr=32'h1fe00624;#1;check(rdata===32'h02000002,"capture full/level mismatch");
  addr=32'h1fe00628;#1;check(rdata===32'h10203040,"capture overflows mismatch");
  addr=32'h1fe00700;#1;check(!hit,"address above window hit");
  fifo_full=0;begin_write(32'h1fe0060c,32'ha55a,4'b0011);
  check(sample_write&&sample_data===16'ha55a,"sample write mismatch");end_write;
  begin_write(32'h1fe0060c,32'h5aa5,4'b0001);
  check(!sample_write,"partial sample accepted");end_write;
  fifo_full=1;begin_write(32'h1fe0060c,32'h5aa5,4'b0011);
  check(!sample_write,"full FIFO accepted write");end_write;
  begin_write(32'h1fe00608,32'h1,4'b0001);
  check(counter_clear&&!sample_write,"counter clear mismatch");end_write;
  begin_write(32'h1fe00608,32'h1,4'b0010);
  check(!counter_clear,"counter clear ignored strobe");end_write;
  begin_write(32'h1fe00608,32'h2,4'b0001);
  check(microphone_read&&!counter_clear,"capture pop missing");end_write;
  begin_write(32'h1fe00608,32'h2,4'b0010);
  check(!microphone_read,"capture pop ignored strobe");end_write;
  microphone_fifo_empty=1;microphone_fifo_full=0;microphone_fifo_level=0;
  addr=32'h1fe00624;#1;check(rdata===32'h1,"capture empty status mismatch");
  begin_write(32'h1fe00608,32'h2,4'b0001);
  check(!microphone_read,"empty FIFO accepted pop");end_write;
  begin_write(32'h1fe00708,32'h3,4'b0001);
  check(!microphone_read&&!counter_clear,"outside-window control write accepted");end_write;
  $display("TB_AUDIO_MMIO_PASS");$finish;
 end
endmodule
