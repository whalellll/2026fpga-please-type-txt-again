`timescale 1ns/1ps
module period_check #(parameter real PERIOD=12.5,HIGH=6.25)(input wire clk,locked,output reg done=0);
 real a,b,period,high;integer i;
 initial begin
  wait(locked);repeat(8) @(posedge clk);
  for(i=0;i<32;i=i+1) begin
   @(posedge clk);a=$realtime;@(negedge clk);b=$realtime;@(posedge clk);
   period=$realtime-a;high=b-a;
   if(period<PERIOD-0.003 || period>PERIOD+0.003 || high<HIGH-0.003 || high>HIGH+0.003)
    $fatal(1,"%m expected period/high %f/%f actual %f/%f",PERIOD,HIGH,period,high);
  end
  done=1;
 end
endmodule
module tb_cpu_profiles;
 reg ref27=0,ref125=0;always #18.518518 ref27=~ref27;always #4 ref125=~ref125;
 wire [12:0] done;
 wire clk0,locked0; pll_cpu #(.CPU_CLOCK_MODE(1),.CPU_DIVISOR(12)) p0(.clkin1(ref27),.clkout3(clk0),.lock(locked0));
 period_check #(.PERIOD(14.109347442681),.HIGH(7.054673721340)) c0(clk0,locked0,done[0]);
 wire clk1,locked1; pll_cpu #(.CPU_CLOCK_MODE(2),.CPU_DIVISOR(9)) p1(.clkin1(ref27),.clkout3(clk1),.lock(locked1));
 period_check #(.PERIOD(13.333333333333),.HIGH(6.666666666667)) c1(clk1,locked1,done[1]);
 wire clk2,locked2; pll_cpu #(.CPU_CLOCK_MODE(3),.CPU_DIVISOR(10)) p2(.clkin1(ref125),.clkout3(clk2),.lock(locked2));
 period_check #(.PERIOD(12.500000000000),.HIGH(6.250000000000)) c2(clk2,locked2,done[2]);
 wire clk3,locked3; pll_cpu #(.CPU_CLOCK_MODE(4),.CPU_DIVISOR(27)) p3(.clkin1(ref27),.clkout0(clk3),.lock(locked3));
 period_check #(.PERIOD(12.500000000000),.HIGH(6.250000000000)) c3(clk3,locked3,done[3]);
 wire clk4,locked4; pll_cpu #(.CPU_CLOCK_MODE(5),.CPU_DIVISOR(27)) p4(.clkin1(ref27),.clkout0(clk4),.lock(locked4));
 period_check #(.PERIOD(11.764705882353),.HIGH(5.882352941176)) c4(clk4,locked4,done[4]);
 wire clk5,locked5; pll_cpu #(.CPU_CLOCK_MODE(6),.CPU_DIVISOR(27)) p5(.clkin1(ref27),.clkout0(clk5),.lock(locked5));
 period_check #(.PERIOD(14.285714285714),.HIGH(7.142857142857)) c5(clk5,locked5,done[5]);
 wire clk6,locked6; pll_cpu #(.CPU_CLOCK_MODE(4),.CPU_DIVISOR(24)) p6(.clkin1(ref27),.clkout0(clk6),.lock(locked6));
 period_check #(.PERIOD(11.111111111111),.HIGH(5.555555555556)) c6(clk6,locked6,done[6]);
 wire clk7,locked7; pll_cpu #(.CPU_CLOCK_MODE(7),.CPU_DIVISOR(20)) p7(.clkin1(ref125),.clkout0(clk7),.lock(locked7));
 period_check #(.PERIOD(10.526315789474),.HIGH(5.263157894737)) c7(clk7,locked7,done[7]);
 wire clk8,locked8; pll_cpu #(.CPU_CLOCK_MODE(8),.CPU_DIVISOR(20)) p8(.clkin1(ref125),.clkout0(clk8),.lock(locked8));
 period_check #(.PERIOD(10.000000000000),.HIGH(5.000000000000)) c8(clk8,locked8,done[8]);
 wire clk9,locked9; pll_cpu #(.CPU_CLOCK_MODE(9),.CPU_DIVISOR(20)) p9(.clkin1(ref125),.clkout0(clk9),.lock(locked9));
 period_check #(.PERIOD(9.090909090909),.HIGH(4.545454545455)) c9(clk9,locked9,done[9]);
 wire clk10,locked10; pll_cpu #(.CPU_CLOCK_MODE(10),.CPU_DIVISOR(20)) p10(.clkin1(ref125),.clkout0(clk10),.lock(locked10));
 period_check #(.PERIOD(8.333333333333),.HIGH(4.166666666667)) c10(clk10,locked10,done[10]);
 wire clk11,locked11; pll_cpu #(.CPU_CLOCK_MODE(11),.CPU_DIVISOR(15)) p11(.clkin1(ref125),.clkout0(clk11),.lock(locked11));
 period_check #(.PERIOD(7.692307692308),.HIGH(3.846153846154)) c11(clk11,locked11,done[11]);
 wire clk12,locked12; pll_cpu #(.CPU_CLOCK_MODE(8),.CPU_DIVISOR(16)) p12(.clkin1(ref125),.clkout0(clk12),.lock(locked12));
 period_check #(.PERIOD(8.0),.HIGH(4.0)) c12(clk12,locked12,done[12]);
 initial begin wait(&done);$display("CPU_ALL13_ACTIVE_PERIOD_DUTY_PASS");$finish;end
 initial begin #2000000;$fatal(1,"timeout");end
endmodule
