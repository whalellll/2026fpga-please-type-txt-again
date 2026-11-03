`timescale 1ns/1ps

module tb_hdmi_console;
    reg sys_clk = 1'b0;
    reg pix_clk = 1'b0;
    always #10.101 sys_clk = ~sys_clk; // 49.5 MHz V3 system clock
    always #6.734 pix_clk = ~pix_clk;  // 74.25 MHz

    reg sys_resetn = 1'b0;
    reg pix_resetn = 1'b0;
    reg char_valid = 1'b0;
    reg [7:0] char_data = 8'd0;
    wire [4:0] rd_row;
    wire [6:0] rd_col;
    wire [7:0] rd_data;
    wire [11:0] cursor_cell;
    wire overflow;
    wire vs, hs, de;
    wire [7:0] r, g, b;

    uart_console_text dut_text (
        .sys_clk(sys_clk), .sys_resetn(sys_resetn),
        .char_valid(char_valid), .char_data(char_data),
        .pix_clk(pix_clk), .pix_resetn(pix_resetn),
        .rd_row(rd_row), .rd_col(rd_col), .rd_data(rd_data),
        .cursor_cell(cursor_cell), .fifo_overflow(overflow)
    );

    video_linux_console dut_video (
        .pix_clk(pix_clk), .rstn(pix_resetn),
        .text_rd_row(rd_row), .text_rd_col(rd_col),
        .text_rd_data(rd_data), .cursor_cell(cursor_cell),
        .vs_out(vs), .hs_out(hs), .de_out(de),
        .r_out(r), .g_out(g), .b_out(b)
    );

    task send_char(input [7:0] value);
        begin
            @(posedge sys_clk);
            char_data <= value;
            char_valid <= 1'b1;
            @(posedge sys_clk);
            char_valid <= 1'b0;
        end
    endtask

    integer i;
    integer clear_cycles;
    integer clear_seen = 0;
    integer icon_pixels = 0;
    integer console_bits = 0;
    integer chinese_bits = 0;
    integer header_pixels = 0;
    initial begin
        #100;
        sys_resetn = 1'b1;
        pix_resetn = 1'b1;

        // Allow deterministic RAM clear to complete.
        repeat (4300) @(posedge pix_clk);
        send_char("A");
        send_char("B");
        send_char(8'h1b); send_char("["); send_char("3");
        send_char("1"); send_char("m");
        send_char("C");
        send_char(8'h0a);
        send_char("D");
        repeat (100) @(posedge pix_clk);

        if (dut_text.text_ram[0] !== "A" ||
            dut_text.text_ram[1] !== "B" ||
            dut_text.text_ram[2] !== "C")
            $fatal(1, "HDMI_UART_MIRROR_ROW0_FAIL %02x %02x %02x",
                   dut_text.text_ram[0], dut_text.text_ram[1],
                   dut_text.text_ram[2]);
        if (dut_text.text_ram[128] !== "D")
            $fatal(1, "HDMI_UART_MIRROR_ROW1_FAIL %02x",
                   dut_text.text_ram[128]);
        if (cursor_cell !== {5'd1, 7'd1})
            $fatal(1, "HDMI_CURSOR_FAIL %03x", cursor_cell);
        if (overflow)
            $fatal(1, "HDMI_CONSOLE_FIFO_OVERFLOW");

        // Linux line editors emit BS to move the displayed cursor left, then
        // redraw the character when moving right.  A terminal must not erase
        // the cell merely because the cursor moved onto it.
        send_char("X");
        send_char(8'h08);
        repeat (40) @(posedge pix_clk);
        if ((cursor_cell !== {5'd1, 7'd1}) ||
            (dut_text.text_ram[129] !== "X"))
            $fatal(1, "HDMI_CONSOLE_LEFT_HIDES_CHARACTER cell=%02x cursor=%03x",
                   dut_text.text_ram[129], cursor_cell);

        // The common relative cursor controls must move within the 80x20
        // terminal without modifying either row.  Ignoring up/down makes the
        // next shell redraw overlap the wrong line.
        send_char("X");
        send_char(8'h1b); send_char("["); send_char("D");
        repeat (40) @(posedge pix_clk);
        if ((cursor_cell !== {5'd1, 7'd1}) ||
            (dut_text.text_ram[129] !== "X"))
            $fatal(1, "HDMI_CONSOLE_CSI_LEFT_FAIL cell=%02x cursor=%03x",
                   dut_text.text_ram[129], cursor_cell);
        send_char(8'h1b); send_char("["); send_char("C");
        send_char(8'h1b); send_char("["); send_char("A");
        repeat (40) @(posedge pix_clk);
        if (cursor_cell !== {5'd0, 7'd2})
            $fatal(1, "HDMI_CONSOLE_CSI_RIGHT_UP_FAIL cursor=%03x", cursor_cell);
        send_char(8'h1b); send_char("["); send_char("B");
        repeat (40) @(posedge pix_clk);
        if ((cursor_cell !== {5'd1, 7'd2}) ||
            (dut_text.text_ram[0] !== "A") ||
            (dut_text.text_ram[1] !== "B") ||
            (dut_text.text_ram[2] !== "C") ||
            (dut_text.text_ram[128] !== "D") ||
            (dut_text.text_ram[129] !== "X"))
            $fatal(1, "HDMI_CONSOLE_ARROW_OVERLAP_FAIL cursor=%03x", cursor_cell);
        $display("LINUX_CONSOLE_ARROW_EDITING_PASS");

        // A shorter history entry is normally followed by CSI K.  Default K
        // clears only cursor-to-EOL, retaining the prefix and other rows.
        send_char("Y"); send_char("Z");
        send_char(8'h1b); send_char("["); send_char("2"); send_char("D");
        send_char(8'h1b); send_char("["); send_char("K");
        repeat (120) @(posedge pix_clk);
        if ((cursor_cell !== {5'd1, 7'd2}) ||
            (dut_text.text_ram[128] !== "D") ||
            (dut_text.text_ram[129] !== "X") ||
            (dut_text.text_ram[130] !== 8'h20) ||
            (dut_text.text_ram[131] !== 8'h20) ||
            (dut_text.text_ram[2] !== "C"))
            $fatal(1, "HDMI_CONSOLE_CSI_K_RANGE_FAIL cursor=%03x", cursor_cell);
        $display("LINUX_CONSOLE_HISTORY_REDRAW_PASS");

        // BusyBox clear emits ESC[H followed by the parameterless ESC[J.
        // Verify home independently so a J-parser failure is unambiguous.
        send_char(8'h1b); send_char("["); send_char("H");
        repeat (40) @(posedge pix_clk);
        if (cursor_cell !== 12'd0)
            $fatal(1, "HDMI_CONSOLE_HOME_FAIL cursor=%03x", cursor_cell);

        send_char(8'h1b); send_char("["); send_char("J");
        for (clear_cycles = 0; clear_cycles < 4300;
             clear_cycles = clear_cycles + 1) begin
            @(posedge pix_clk);
            if (dut_text.clear_all_active)
                clear_seen = 1;
        end
        if (!clear_seen)
            $fatal(1, "HDMI_CONSOLE_ESC_J_NOT_HANDLED");
        if ((dut_text.top_row !== 5'd0) || (cursor_cell !== 12'd0))
            $fatal(1, "HDMI_CONSOLE_CLEAR_CURSOR_FAIL top=%0d cursor=%03x",
                   dut_text.top_row, cursor_cell);
        for (i = 0; i < 2560; i = i + 1) begin
            if ((i % 128 < 80) && (dut_text.text_ram[i] !== 8'h20))
                $fatal(1,
                       "HDMI_CONSOLE_CLEAR_CHARACTER_REMAINS addr=%0d data=%02x",
                       i, dut_text.text_ram[i]);
        end
        $display("LINUX_CONSOLE_EDITING_PASS");

        // Asset-level check: terminal icon, CONSOLE label and Chinese title
        // must all contain visible pixels.
        for (i = 0; i < 5120; i = i + 1) begin
            if (dut_video.u_logo.rom[i] != 8'h00)
                icon_pixels = icon_pixels + 1;
        end
        for (i = 0; i < 3072; i = i + 1) begin
            if (((i % 48) >= 10) && ((i % 48) < 24))
                console_bits = console_bits + $countones(dut_video.u_header.rom[i]);
            if ((i % 48) >= 24)
                chinese_bits = chinese_bits + $countones(dut_video.u_header.rom[i]);
        end
        if (icon_pixels < 500)
            $fatal(1, "HDMI_CONSOLE_ICON_BITMAP_FAIL pixels=%0d", icon_pixels);
        if (console_bits < 200)
            $fatal(1, "HDMI_CONSOLE_TITLE_BITMAP_FAIL bits=%0d", console_bits);
        if (chinese_bits < 300)
            $fatal(1, "HDMI_CHINESE_TITLE_BITMAP_FAIL bits=%0d", chinese_bits);

        // Wait until the raster has rendered the fixed header and make sure
        // foreground pixels are observed on the actual video output.
        wait (dut_video.v_count == 10'd90 && dut_video.h_count == 11'd0);
        if (header_pixels < 300)
            $fatal(1, "HDMI_HEADER_RENDER_FAIL pixels=%0d", header_pixels);

        $display("TB_HDMI_CONSOLE_PASS icon_pixels=%0d console_bits=%0d chinese_bits=%0d header_pixels=%0d",
                 icon_pixels, console_bits, chinese_bits, header_pixels);
        $finish;
    end

    always @(posedge pix_clk) begin
        if (pix_resetn && de && (g > 8'h60) && (r > 8'h60))
            header_pixels = header_pixels + 1;
    end
endmodule
