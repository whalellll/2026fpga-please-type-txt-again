`timescale 1ns/1ps
module tb_cpu80_pll;
 reg ref125=0,free27=0;
 always #4 ref125=~ref125;
 always #18.518518 free27=~free27;
 wire cpu_clk,cpu_lock,sys_clk,pix_clk,i2c_clk,video_lock;
 pll_cpu #(.CPU_DIVISOR(10),.CPU_CLOCK_MODE(3)) cpu(.clkin1(ref125),.clkout0(),.clkout1(),.clkout2(),.clkout3(cpu_clk),.lock(cpu_lock));
 pll_video #(.CPU_DIVISOR(10)) video(.clkin1(free27),.clkout0(pix_clk),.clkout1(sys_clk),.clkout2(i2c_clk),.clkout3(),.lock(video_lock));
 real started,period;
 initial begin #2000000;$fatal(1,"CPU80 PLL timeout");end
 initial begin
  wait(cpu_lock && video_lock);repeat(16) @(posedge cpu_clk);
  started=$realtime;repeat(256) @(posedge cpu_clk);period=($realtime-started)/256;
  if(period<12.498 || period>12.502)$fatal(1,"CPU80 expected12.5ns, actual%f",period);
  @(posedge sys_clk);started=$realtime;repeat(128) @(posedge sys_clk);period=($realtime-started)/128;
  if(period<20.200020 || period>20.204020)$fatal(1,"SYS changed%f",period);
  @(posedge pix_clk);started=$realtime;repeat(128) @(posedge pix_clk);period=($realtime-started)/128;
  if(period<13.466013 || period>13.470013)$fatal(1,"Video changed%f",period);
  $display("CPU80_PLL_VENDOR_WAVEFORM_PASS cpu=80 sys=49.5 video=74.25 reference=125 idiv=5 fdiv=32 odiv=10");$finish;
 end
endmodule
