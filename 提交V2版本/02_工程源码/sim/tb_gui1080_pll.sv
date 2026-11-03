`timescale 1ns/1ps
module tb_gui1080_pll #(parameter integer PIXEL_DIVISOR=12);
    reg clkin1=0;
    always #18.518518519 clkin1=~clkin1;
    wire pixel,sys,cfg,cpu_unused,lock;
    pll_video #(.CPU_DIVISOR(27),.PIXEL_DIVISOR(PIXEL_DIVISOR)) pll(
        .clkin1(clkin1),.clkout0(pixel),.clkout1(sys),.clkout2(cfg),
        .clkout3(cpu_unused),.lock(lock));
    real start_time,pixel_period,sys_period,cfg_period;
    initial begin
        wait(lock);#1000;
        @(posedge pixel);start_time=$realtime;repeat(20) @(posedge pixel);
        pixel_period=($realtime-start_time)/20;
        @(posedge sys);start_time=$realtime;repeat(20) @(posedge sys);
        sys_period=($realtime-start_time)/20;
        @(posedge cfg);start_time=$realtime;repeat(20) @(posedge cfg);
        cfg_period=($realtime-start_time)/20;
        if(PIXEL_DIVISOR!=6 && PIXEL_DIVISOR!=12) $fatal(1,"unsupported pixel divisor");
        if(pixel_period<(PIXEL_DIVISOR*1000.0/891.0-0.002) ||
           pixel_period>(PIXEL_DIVISOR*1000.0/891.0+0.002)) $fatal(1,"pixel period %f",pixel_period);
        if(sys_period<20.200 || sys_period>20.204) $fatal(1,"SYS period %f",sys_period);
        if(cfg_period<141.39 || cfg_period>141.44) $fatal(1,"I2C period %f",cfg_period);
        $display("GUI1080_VENDOR_PLL_PASS pixel_ns=%f sys_ns=%f cfg_ns=%f",pixel_period,sys_period,cfg_period);
        $finish;
    end
    initial begin #1000000;$fatal(1,"vendor PLL lock timeout");end
endmodule
