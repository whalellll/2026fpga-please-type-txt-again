`timescale 1ns/1ps
module tb_gui1080_controls;
    reg clk=0,resetn=0,ch9350_uart_rx=1;
    always #5 clk=~clk;
    wire [10:0] mouse_x,mouse_y;
    wire [31:0] mouse_frame_count,parse_error_count;
    ch9350_hid_core #(.UART_BAUD_DIV(16),.GUI_PROFILE(1),
        .SCREEN_WIDTH(1920),.SCREEN_HEIGHT(1080)) hid(
        .clk(clk),.resetn(resetn),.ch9350_uart_rx(ch9350_uart_rx),
        .key_ready(1'b1),.mouse_x(mouse_x),.mouse_y(mouse_y),
        .mouse_frame_count(mouse_frame_count),.parse_error_count(parse_error_count));
    reg [31:0] addr=32'h1fe11000,wdata=0;
    reg wr=0;
    wire [31:0] rdata;
    wire hit;
    video_fb_mmio #(.FB0_BASE(32'h1b800000),.FB1_BASE(32'h1bc00000),
        .WIDTH(1920),.HEIGHT(1080)) mmio(
        .clk(clk),.resetn(resetn),.addr(addr),.wr(wr),.wdata(wdata),
        .wstrb(4'hf),.rdata(rdata),.hit(hit),
        .active_enable_pix(1'b0),.active_buffer_pix(1'b0),.underflow_pix(1'b0),
        .frame_count_pix(32'd0),.underflow_count_pix(32'd0),
        .dma_busy_ddr(1'b0),.dma_error_ddr(1'b0));
    task send_byte(input [7:0] value);
        integer bit_index;
        begin
            @(negedge clk);ch9350_uart_rx=0;
            repeat(16) @(negedge clk);
            for(bit_index=0;bit_index<8;bit_index=bit_index+1) begin
                ch9350_uart_rx=value[bit_index];repeat(16) @(negedge clk);
            end
            ch9350_uart_rx=1;repeat(16) @(negedge clk);
        end
    endtask
    task report(input [7:0] dx,input [7:0] dy);
        begin
            send_byte(8'h57);send_byte(8'hab);send_byte(8'h02);send_byte(0);
            send_byte(dx);send_byte(dy);send_byte(0);repeat(20) @(negedge clk);
        end
    endtask
    task read_check(input [7:0] offset,input [31:0] expected);
        begin
            addr=32'h1fe11000+offset;#1;
            if(!hit || rdata!==expected) $fatal(1,"MMIO %h=%h expected=%h",offset,rdata,expected);
        end
    endtask
    integer i;
    initial begin
        repeat(4) @(negedge clk);resetn=1;repeat(4) @(negedge clk);
        if(mouse_x!=960 || mouse_y!=540) $fatal(1,"initial pointer");
        read_check(8'h10,32'h1b800000);read_check(8'h14,32'h1bc00000);
        read_check(8'h18,3840);read_check(8'h1c,{16'd1080,16'd1920});read_check(8'h20,4147200);
        for(i=0;i<12;i=i+1) report(8'd127,8'd127);
        if(mouse_x!=1919 || mouse_y!=1079) $fatal(1,"positive saturation x=%0d y=%0d",mouse_x,mouse_y);
        for(i=0;i<18;i=i+1) report(8'h80,8'h80);
        if(mouse_x!=0 || mouse_y!=0) $fatal(1,"negative saturation x=%0d y=%0d",mouse_x,mouse_y);
        if(mouse_frame_count!=30 || parse_error_count) $fatal(1,"HID reports lost");
        $display("GUI1080_CONTROLS_PASS mmio=5 uart-reports=30 limits=1919x1079 negative=0x0");
        $finish;
    end
    initial begin #1000000; $fatal(1,"controls timeout"); end
endmodule
