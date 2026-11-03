`timescale 1ns/1ps
module tb_audio_fifo_order;
    reg clk=0, resetn=0, clear=0, pop=0;
    always #5 clk=~clk;
    wire [23:0] head;
    wire empty,full;
    wire [2:0] level;
    wire [31:0] overflows;
    reg [23:0] captured;
    i2s_audio_duplex #(.ADD_STEP(0),.MIC_FIFO_ADDR_BITS(2)) dut (
        .clk(clk),.resetn(resetn),.counter_clear(clear),.mic_sd(captured[0]),
        .sample_write(1'b0),.sample_data(16'b0),.microphone_read(pop),
        .microphone_fifo_data(head),.microphone_fifo_empty(empty),
        .microphone_fifo_full(full),.microphone_fifo_level(level),
        .microphone_overflows(overflows));
    task step;
        input write_sample,read_sample;
        input [23:0] value;
        begin
            @(negedge clk); captured=value;pop=read_sample;
            if(write_sample)force dut.bclk_rise=1'b1;
            else force dut.bclk_rise=1'b0;
            force dut.bit_index=7'd24;
            force dut.mic_shift=captured>>1;
            @(posedge clk); #1;
            @(negedge clk); pop=0;
            force dut.bclk_rise=1'b0;
            release dut.bit_index;release dut.mic_shift;
        end
    endtask
    task expect_head;
        input integer count;
        input [23:0] value;
        begin
            if(level!==count || head!==value || empty!==(count==0) || full!==(count==4))
                $fatal(1,"FIFO count/head expected %0d/%h got %0d/%h",count,value,level,head);
        end
    endtask
    initial begin
        repeat(3)@(negedge clk);resetn=1;
        step(1,0,24'h123456);expect_head(1,24'h123456);
        step(1,0,24'h234567);expect_head(2,24'h123456);
        step(1,0,24'h345678);step(1,0,24'h456789);expect_head(4,24'h123456);
        step(1,0,24'hdead00);expect_head(4,24'h123456);
        if(overflows!=1)$fatal(1,"overflow counter");
        step(1,1,24'h56789a);expect_head(4,24'h234567);
        step(0,1,0);expect_head(3,24'h345678);
        step(0,1,0);expect_head(2,24'h456789);
        step(0,1,0);expect_head(1,24'h56789a);
        step(1,1,24'hfedcba);expect_head(1,24'hfedcba);
        step(0,1,0);expect_head(0,0);
        step(1,1,24'hab0123);expect_head(1,24'hab0123);
        @(negedge clk);clear=1;@(posedge clk);#1;expect_head(0,0);
        @(negedge clk);clear=0;
        step(1,0,24'hff0080);expect_head(1,24'hff0080);
        $display("AUDIO_FIFO_ORDER_PASS");$finish;
    end
endmodule
