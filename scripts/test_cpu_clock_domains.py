"""Exercise the exact SoC clock/reset block with controlled PLL lock events.

Behavioral clocks only isolate reset logic. Vendor-primitive waveform checks
live in tb_cpu_dedicated_pll.sv; this is not an analog PLL or board test.
"""
import argparse
from pathlib import Path
import subprocess


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    source=(root/'rtl/soc/soc_top.v').read_text()
    block=source[source.index(' wire pix_clk,'):source.index(' // Hold the external Gigabit PHY')]
    assert 'cpu_pll_lock' in block and 'CPU_CLOCK_MODE' in block, 'Dedicated PLL reset interlock is missing'
    args.output.mkdir(parents=True,exist_ok=False)
    probe='''`timescale 1ns/1ps
module clock_probe #(parameter CPU_CLOCK_MODE=1, CPU_DIVISOR=12)(input free_clk,rst_board);
 wire ref_clk=free_clk;
'''+block+'''endmodule
module pll_video #(parameter CPU_DIVISOR=15,PIXEL_DIVISOR=12)(input clkin1,output reg lock,
 output reg clkout0,clkout1,clkout2,clkout3);
 initial begin lock=0;clkout0=0;clkout1=0;clkout2=0;clkout3=0;end
 always #(PIXEL_DIVISOR*500.0/891.0) clkout0=~clkout0;
 always #10.101010 clkout1=~clkout1;
 always #70.7070705 clkout2=~clkout2;
 always #(1000000000.0*CPU_DIVISOR/891000000.0/2.0) clkout3=~clkout3;
endmodule
module pll_cpu #(parameter CPU_DIVISOR=12,CPU_CLOCK_MODE=1)(input clkin1,output reg lock,
 output reg clkout0,output clkout1,clkout2,output reg clkout3);
 initial begin lock=0;clkout0=0;clkout3=0;end
 assign {clkout1,clkout2}=0;
 always #6.25 clkout0=~clkout0;
 always #7.0546737 clkout3=~clkout3;
endmodule
module tb;
 reg board=0,free_clk=0;
 always #18.5185 free_clk=~free_clk;
 clock_probe d(free_clk,board);
 clock_probe #(.CPU_CLOCK_MODE(4),.CPU_DIVISOR(27)) frac(free_clk,board);
 clock_probe #(.CPU_CLOCK_MODE(0),.CPU_DIVISOR(15)) legacy(free_clk,board);
 initial begin #20000;$fatal(1,"reset probe timeout");end
 initial begin
  #1;force d.u_video_pll.lock=0;force d.g_dedicated_cpu.u_cpu_pll.lock=0;
  force frac.u_video_pll.lock=0;force frac.g_dedicated_cpu.u_cpu_pll.lock=0;
  force legacy.u_video_pll.lock=0;
  #1;board=1;force d.u_video_pll.lock=1;force legacy.u_video_pll.lock=1;
  force frac.u_video_pll.lock=1;
  #100;
  if(d.sys_resetn!==0 || d.cpu_resetn!==0) $fatal(1,"Released before CPU PLL lock");
  if(frac.sys_resetn!==0 || frac.cpu_resetn!==0)$fatal(1,"Fractional CPU released before lock");
  if(legacy.cpu_resetn!==1 || legacy.sys_resetn!==1) $fatal(1,"Legacy reset changed");
  @(negedge d.cpu_clk);force d.g_dedicated_cpu.u_cpu_pll.lock=1;
  force frac.g_dedicated_cpu.u_cpu_pll.lock=1;
  repeat(2) begin @(posedge d.cpu_clk);#0.001;if(d.cpu_resetn!==0)$fatal(1,"CPU reset released early");end
  @(posedge d.cpu_clk);#0.001;if(d.cpu_resetn!==1)$fatal(1,"CPU reset release is not 3 cycles");
  #100;if(d.sys_resetn!==1)$fatal(1,"SYS reset did not release");
  if(frac.sys_resetn!==1 || frac.cpu_resetn!==1)$fatal(1,"Fractional reset did not release");
  force frac.g_dedicated_cpu.u_cpu_pll.lock=0;#0.001;
  if(frac.sys_resetn!==0 || frac.cpu_resetn!==0)$fatal(1,"Fractional unlock did not assert resets");
  force frac.g_dedicated_cpu.u_cpu_pll.lock=1;#100;
  if(frac.sys_resetn!==1 || frac.cpu_resetn!==1)$fatal(1,"Fractional relock failed");
  force d.g_dedicated_cpu.u_cpu_pll.lock=0;#0.001;
  if(d.sys_resetn!==0 || d.cpu_resetn!==0)$fatal(1,"CPU unlock did not assert resets");
  force d.g_dedicated_cpu.u_cpu_pll.lock=1;#100;
  if(d.sys_resetn!==1 || d.cpu_resetn!==1)$fatal(1,"CPU relock recovery failed");
  force d.u_video_pll.lock=0;#0.001;
  if(d.sys_resetn!==0 || d.cpu_resetn!==0)$fatal(1,"Video unlock did not assert resets");
  force d.u_video_pll.lock=1;#100;
  board=0;#0.001;
  if(d.sys_resetn!==0 || d.cpu_resetn!==0)$fatal(1,"Board reset failed");
  board=1;#100;
  if(d.sys_resetn!==1 || d.cpu_resetn!==1)$fatal(1,"Board reset recovery failed");
  $display("SOC_ACTUAL_CLOCK_RESET_BLOCK_PASS legacy_and_dedicated_and_fractional lock_order_loss_recovery_three_cycles");
  $finish;
 end
endmodule
'''
    (args.output/'probe.sv').write_text(probe)
    subprocess.run(['iverilog','-g2012','-s','tb','-o',args.output/'probe.vvp',args.output/'probe.sv'],check=True)
    result=subprocess.run(['vvp',args.output/'probe.vvp'],capture_output=True,text=True,timeout=30)
    (args.output/'result.txt').write_text(result.stdout+result.stderr)
    print(result.stdout,end='')
    assert result.returncode==0 and 'SOC_ACTUAL_CLOCK_RESET_BLOCK_PASS' in result.stdout


if __name__=='__main__':main()
