`timescale 1ns/1ps
module tb_cpu75_pll;
 reg reference=0;
 always #18.518518 reference=~reference;
 wire cpu_clock,cpu_lock,pixel,system_clock,slow_clock,video_lock;
 pll_cpu #(.CPU_DIVISOR(9),.CPU_CLOCK_MODE(2)) cpu(
  .clkin1(reference),.lock(cpu_lock),.clkout0(),.clkout1(),.clkout2(),.clkout3(cpu_clock));
 pll_video video(.clkin1(reference),.lock(video_lock),.clkout0(pixel),
  .clkout1(system_clock),.clkout2(slow_clock),.clkout3());
 real began,period,high_time;
 integer n;
 initial begin #2000000; $fatal(1,"CPU75 PLL timeout"); end
 initial begin
  wait(cpu_lock && video_lock);
  repeat(16) @(posedge cpu_clock);
  for(n=0;n<128;n=n+1) begin
   began=$realtime; @(negedge cpu_clock); high_time=$realtime-began;
   @(posedge cpu_clock);period=$realtime-began;
   if(period<13.331333 || period>13.335333 || high_time<6.664667 || high_time>6.668667)
    $fatal(1,"CPU75 PLL waveform period=%f high=%f",period,high_time);
  end
  @(posedge system_clock);began=$realtime;repeat(128) @(posedge system_clock);
  period=($realtime-began)/128.0;
  if(period<20.200020 || period>20.204020) $fatal(1,"SYS changed %f",period);
  @(posedge pixel);began=$realtime;repeat(128) @(posedge pixel);
  period=($realtime-began)/128.0;
  if(period<13.466013 || period>13.470013) $fatal(1,"Pixel changed %f",period);
  @(posedge slow_clock);began=$realtime;repeat(128) @(posedge slow_clock);
  period=($realtime-began)/128.0;
  if(period<141.408141 || period>141.420141) $fatal(1,"I2C changed %f",period);
  $display("CPU75_PLL_VENDOR_PASS cpu=75 sys=49.5 pixel=74.25 duty=50");$finish;
 end
endmodule
