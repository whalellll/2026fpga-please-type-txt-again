`timescale 1ns/1ps

module tb_hid_gui_overlay_linux;
    reg pix_clk = 1'b0;
    reg resetn = 1'b0;
    reg hs_in = 1'b0;
    reg vs_in = 1'b1;
    reg de_in = 1'b0;
    reg [2:0] mouse_buttons = 3'b000;
    reg mouse_seen = 1'b0;
    reg [10:0] mouse_x = 11'd640;
    reg [9:0] mouse_y = 10'd360;
    wire hs_out, vs_out, de_out;
    wire [7:0] r_out, g_out, b_out;
    integer pixel_index;
    integer checked_pixels = 0;
    integer changed_pixels = 0;
    integer line_index;
    integer cursor_black = 0;
    integer cursor_white = 0;
    integer cursor_other = 0;

    always #5 pix_clk = ~pix_clk;

    hid_gui_overlay #(.LINUX_PROFILE(1)) dut (
        .pix_clk(pix_clk), .resetn(resetn), .hs_in(hs_in),
        .vs_in(vs_in), .de_in(de_in),
        .r_in(8'h2a), .g_in(8'h5c), .b_in(8'h7e),
        .mouse_x(mouse_x), .mouse_y(mouse_y),
        .mouse_buttons(mouse_buttons), .mouse_wheel(8'h00),
        .last_usage(8'h00), .keyboard_seen(1'b0),
        .mouse_seen(mouse_seen), .keyboard_count(32'd0),
        .mouse_count(32'd0), .error_count(32'd0),
        .gui_help(1'b0), .gui_stats(1'b0), .gui_speed_2x(1'b0),
        .gui_cursor_alt(1'b0), .gui_term_focus(1'b1),
        .hs_out(hs_out), .vs_out(vs_out), .de_out(de_out),
        .r_out(r_out), .g_out(g_out), .b_out(b_out)
    );

    initial begin
        repeat (4) @(posedge pix_clk);
        resetn = 1'b1;
        repeat (2) @(posedge pix_clk);
        vs_in = 1'b0;
        repeat (2) @(posedge pix_clk);

        // The Linux title line must pass through at the former blue toolbar.
        de_in = 1'b1;
        for (pixel_index = 0; pixel_index < 1280;
             pixel_index = pixel_index + 1) begin
            @(negedge pix_clk);
            if ((pixel_index >= 450) && (pixel_index < 1200) && de_out) begin
                checked_pixels = checked_pixels + 1;
                if ((r_out !== 8'h2a) || (g_out !== 8'h5c) ||
                    (b_out !== 8'h7e))
                    changed_pixels = changed_pixels + 1;
            end
        end
        de_in = 1'b0;
        if ((checked_pixels < 700) || (changed_pixels != 0))
            $fatal(1, "LINUX_TOP_RIGHT_BLUE_BOX_PRESENT changed=%0d/%0d",
                   changed_pixels, checked_pixels);

        // Render the cursor at (0,0) while the left button is down.  A
        // Windows-style arrow has a compact black outline, white fill and no
        // green/red/blue click recoloring.
        vs_in = 1'b1;
        mouse_x = 11'd0;
        mouse_y = 10'd0;
        mouse_seen = 1'b1;
        mouse_buttons = 3'b001;
        repeat (4) @(posedge pix_clk);
        vs_in = 1'b0;
        repeat (2) @(posedge pix_clk);
        for (line_index = 0; line_index < 24;
             line_index = line_index + 1) begin
            de_in = 1'b1;
            for (pixel_index = 0; pixel_index < 32;
                 pixel_index = pixel_index + 1) begin
                @(negedge pix_clk);
                if (de_out) begin
                    if ((r_out == 8'h00) && (g_out == 8'h00) &&
                        (b_out == 8'h00))
                        cursor_black = cursor_black + 1;
                    else if ((r_out == 8'hf8) && (g_out == 8'hf8) &&
                             (b_out == 8'hf8))
                        cursor_white = cursor_white + 1;
                    else if ((r_out != 8'h2a) || (g_out != 8'h5c) ||
                             (b_out != 8'h7e))
                        cursor_other = cursor_other + 1;
                end
            end
            de_in = 1'b0;
            repeat (2) @(posedge pix_clk);
        end
        mouse_buttons = 3'b000;
        if ((cursor_black != 60) || (cursor_white != 94) ||
            (cursor_other != 0))
            $fatal(1, "WINDOWS_CURSOR_SHAPE_FAIL black=%0d white=%0d other=%0d",
                   cursor_black, cursor_white, cursor_other);
        $display("PASS tb_hid_gui_overlay_linux black=%0d white=%0d",
                 cursor_black, cursor_white);
        $finish;
    end
endmodule
