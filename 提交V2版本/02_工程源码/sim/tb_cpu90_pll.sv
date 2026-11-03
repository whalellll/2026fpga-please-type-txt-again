`timescale 1ns/1ps
module tb_cpu90_pll;
 reg reference=0;
 always #18.518518 reference=~reference;
 wire cpu_clk,cpu_lock,sys_clk,pix_clk,video_lock;
 pll_cpu #(.CPU_DIVISOR(24),.CPU_CLOCK_MODE(4)) cpu(.clkin1(reference),.clkout0(cpu_clk),.clkout1(),.clkout2(),.clkout3(),.lock(cpu_lock));
 pll_video #(.CPU_DIVISOR(27),.PIXEL_DIVISOR(6)) video(.clkin1(reference),.clkout0(pix_clk),.clkout1(sys_clk),.clkout2(),.clkout3(),.lock(video_lock));
 real started,period,high_time;
 reg settled=0;
 real last_edge=0;
 always @(posedge cpu_clk)begin
  if(settled && last_edge>0 && ($realtime-last_edge>11.113111 || $realtime-last_edge<11.109111))
   $fatal(1,"CPU90 fractional edge period=%f",$realtime-last_edge);
  last_edge=$realtime;
 end
 initial begin #2000000;$fatal(1,"CPU90 fractional PLL timeout");end
 initial begin
  // Allow startup and phase propagation, then check each settled edge.
  wait(cpu_lock && video_lock);repeat(256)@(posedge cpu_clk);
  $display("CPU90_FRAC_MODEL vco_period=%f high=%f low=%f ratio0=%f feedback=%f",cpu.u_gpll.vcoclk_period,cpu.u_gpll.odiv0_frac_hp,cpu.u_gpll.odiv0_frac_lp,cpu.u_gpll.STATIC_RATIO0,cpu.u_gpll.STATIC_RATIOF);
  settled=1;
  started=$realtime;repeat(1024)@(posedge cpu_clk);period=($realtime-started)/1024;
  if(period<11.109111 || period>11.113111)$fatal(1,"CPU90 expected100/9ns actual%f",period);
  started=$realtime;@(negedge cpu_clk);high_time=$realtime-started;
  if(high_time<5.553556 || high_time>5.557556)$fatal(1,"CPU90 expected50percent duty actual_high=%f",high_time);
  @(posedge sys_clk);started=$realtime;repeat(128)@(posedge sys_clk);period=($realtime-started)/128;
  if(period<20.200020 || period>20.204020)$fatal(1,"SYS changed%f",period);
  @(posedge pix_clk);started=$realtime;repeat(128)@(posedge pix_clk);period=($realtime-started)/128;
  if(period<6.732007 || period>6.736007)$fatal(1,"Video changed%f",period);
  $display("CPU90_FRAC_PLL_VENDOR_WAVEFORM_PASS cpu=90 duty=50 sys=49.5 video=148.5 reference=27 vco=1080 odiv0=12");$finish;
 end
endmodule
