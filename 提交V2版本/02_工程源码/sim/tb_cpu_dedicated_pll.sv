`timescale 1ns/1ps
`ifndef CPU_PLL_DUT
`define CPU_PLL_DUT pll_cpu
`endif
module tb_cpu_dedicated_pll;
 reg reference=0;
 always #18.518518 reference=~reference;
 wire pixel,system_clock,slow_clock,video_lock,cpu_clock,cpu_lock;
 pll_video #(.CPU_DIVISOR(12)) video(
  .clkin1(reference),.lock(video_lock),.clkout0(pixel),
  .clkout1(system_clock),.clkout2(slow_clock),.clkout3());
 `CPU_PLL_DUT #(.CPU_DIVISOR(12)) cpu(
  .clkin1(reference),.lock(cpu_lock),.clkout0(),
  .clkout1(),.clkout2(),.clkout3(cpu_clock));
 real started,observed;
 initial begin
  #2000000;
  $fatal(1,"PLL waveform timeout");
 end
 initial begin
  wait(video_lock && cpu_lock);
  repeat(16) @(posedge cpu_clock);
  started=$realtime;repeat(128) @(posedge cpu_clock);
  observed=($realtime-started)/128.0;
  if(observed<14.107347 || observed>14.111347)
   $fatal(1,"CPU PLL expected 70.875 MHz, actual period %f ns",observed);
  @(posedge pixel);started=$realtime;repeat(128) @(posedge pixel);
  observed=($realtime-started)/128.0;
  if(observed<13.466013 || observed>13.470013) $fatal(1,"Pixel clock changed %f",observed);
  @(posedge system_clock);started=$realtime;repeat(128) @(posedge system_clock);
  observed=($realtime-started)/128.0;
  if(observed<20.200020 || observed>20.204020) $fatal(1,"SYS clock changed %f",observed);
  @(posedge slow_clock);started=$realtime;repeat(128) @(posedge slow_clock);
  observed=($realtime-started)/128.0;
  if(observed<141.408141 || observed>141.420141) $fatal(1,"I2C clock changed %f",observed);
  $display("CPU_DEDICATED_PLL_WAVEFORM_PASS cpu=70.875 sys=49.5 pixel=74.25 source=vendor_GTP_GPLL");
  $finish;
 end
endmodule
