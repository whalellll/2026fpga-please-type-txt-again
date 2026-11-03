`timescale 1ns/1ps
module tb_cpu125_pll;
 reg reference=0;
 always #18.518518 reference=~reference;
 reg ref125=0;always #4 ref125=~ref125;
 wire cpu_clk,cpu_lock,sys_clk,pix_clk,video_lock;
 pll_cpu #(.CPU_DIVISOR(16),.CPU_CLOCK_MODE(8)) cpu(.clkin1(ref125),.clkout0(cpu_clk),.clkout1(),.clkout2(),.clkout3(),.lock(cpu_lock));
 pll_video #(.CPU_DIVISOR(27),.PIXEL_DIVISOR(6)) video(.clkin1(reference),.clkout0(pix_clk),.clkout1(sys_clk),.clkout2(),.clkout3(),.lock(video_lock));
 real started,period,high_time;
 reg settled=0;
 real last_edge=0;
 always @(posedge cpu_clk)begin
  if(settled && last_edge>0 && ($realtime-last_edge>8.002 || $realtime-last_edge<7.998))
   $fatal(1,"CPU125 fractional edge period=%f",$realtime-last_edge);
  last_edge=$realtime;
 end
 initial begin #2000000;$fatal(1,"CPU125 fractional PLL timeout");end
 initial begin
  // Allow startup and phase propagation, then check each settled edge.
  wait(cpu_lock && video_lock);repeat(256)@(posedge cpu_clk);
  $display("CPU125_FRAC_MODEL vco_period=%f high=%f low=%f ratio0=%f feedback=%f",cpu.u_gpll.vcoclk_period,cpu.u_gpll.odiv0_frac_hp,cpu.u_gpll.odiv0_frac_lp,cpu.u_gpll.STATIC_RATIO0,cpu.u_gpll.STATIC_RATIOF);
  settled=1;
  started=$realtime;repeat(1024)@(posedge cpu_clk);period=($realtime-started)/1024;
  if(period<7.998 || period>8.002)$fatal(1,"CPU125 expected8ns actual%f",period);
  started=$realtime;@(negedge cpu_clk);high_time=$realtime-started;
  if(high_time<3.998 || high_time>4.002)$fatal(1,"CPU125 expected50percent duty actual_high=%f",high_time);
  @(posedge sys_clk);started=$realtime;repeat(128)@(posedge sys_clk);period=($realtime-started)/128;
  if(period<20.200020 || period>20.204020)$fatal(1,"SYS changed%f",period);
  @(posedge pix_clk);started=$realtime;repeat(128)@(posedge pix_clk);period=($realtime-started)/128;
  if(period<6.732007 || period>6.736007)$fatal(1,"Video changed%f",period);
  $display("CPU125_FRAC_PLL_VENDOR_WAVEFORM_PASS cpu=125 duty=50 sys=49.5 video=148.5 reference=125 vco=1000 odiv0=8");$finish;
 end
endmodule
