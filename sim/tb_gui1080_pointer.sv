`timescale 1ns/1ps
module tb_gui1080_pointer;
    reg pix_clk=0,resetn=0,hs_in=0,vs_in=1,de_in=0;
    always #5 pix_clk=~pix_clk;
    wire de_out;
    wire [7:0] r_out,g_out,b_out;
    integer row,col,black=0,white=0;
    hid_gui_overlay #(.LINUX_PROFILE(1)) dut(
        .pix_clk(pix_clk),.resetn(resetn),.hs_in(hs_in),.vs_in(vs_in),.de_in(de_in),
        .r_in(8'h2a),.g_in(8'h5c),.b_in(8'h7e),
        .mouse_x(11'd1850),.mouse_y(11'd1040),.mouse_buttons(3'd1),.mouse_seen(1'b1),
        .mouse_wheel(8'd0),.last_usage(8'd0),.keyboard_seen(1'b0),
        .keyboard_count(32'd0),.mouse_count(32'd0),.error_count(32'd0),
        .gui_help(1'b0),.gui_stats(1'b0),.gui_speed_2x(1'b0),
        .gui_cursor_alt(1'b0),.gui_term_focus(1'b1),
        .de_out(de_out),.r_out(r_out),.g_out(g_out),.b_out(b_out));
    initial begin
        repeat(4) @(negedge pix_clk);resetn=1;
        repeat(4) @(negedge pix_clk);vs_in=0;
        for(row=0;row<1080;row=row+1) begin
            de_in=1;
            for(col=0;col<1920;col=col+1) begin
                @(negedge pix_clk);
                if(row>=1040 && row<1064 && col>=1850 && col<1872 && de_out) begin
                    if({r_out,g_out,b_out}==24'h000000) black=black+1;
                    if({r_out,g_out,b_out}==24'hf8f8f8) white=white+1;
                end
                if(row>1024 && col<1800 && de_out && {r_out,g_out,b_out}!==24'h2a5c7e)
                    $fatal(1,"unexpected lower-screen overlay y=%0d x=%0d",row,col);
            end
            de_in=0;repeat(8) @(negedge pix_clk);
        end
        if(black<20 || white<20) $fatal(1,"lower-right cursor missing black=%0d white=%0d",black,white);
        $display("GUI1080_POINTER_PASS bottom-right=1850x1040 black=%0d white=%0d",black,white);
        $finish;
    end
    initial begin #30000000;$fatal(1,"pointer timeout");end
endmodule
