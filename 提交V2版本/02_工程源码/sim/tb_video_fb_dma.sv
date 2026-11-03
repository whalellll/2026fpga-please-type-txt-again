`timescale 1ns/1ps

module tb_video_fb_dma;
    localparam [27:0] FB0_NATIVE = 28'h6c80000;
    localparam [27:0] FB1_NATIVE = 28'h6d00000;

    reg sys_enable = 1;
    reg sys_camera_mode = 0;
    reg sys_requested_buffer = 0;
    reg sys_clear_underflow_toggle = 0;
    reg ddr_clk = 0, pix_clk = 0;
    reg ddr_resetn = 0, pix_resetn = 0;
    reg ddr_init_done = 0;
    always #2.5 ddr_clk = ~ddr_clk;
    always #6.734 pix_clk = ~pix_clk;

    wire [27:0] fb_araddr;
    wire [3:0] fb_arid, fb_arlen;
    wire fb_arvalid, fb_urgent;
    wire dma_busy_ddr;
    wire dma_error_ddr;
    reg fb_arready = 0;
    reg [255:0] fb_rdata = 0;
    reg [3:0] fb_rid = 0;
    reg fb_rlast = 0, fb_rvalid = 0;
    wire active_enable_pix, active_buffer_pix, underflow_pix;
    wire [31:0] frame_count_pix, underflow_count_pix;
    wire vs_out, hs_out, de_out;
    wire [7:0] r_out, g_out, b_out;

    video_fb_dma #(.V_ACT(4)) dut(.*);

    integer ar_count = 0;
    integer red_pixels = 0;
    integer response_beat = 0;
    reg response_active = 0;
    reg [3:0] response_id = 0;
    reg [27:0] expected_addr;
    integer expected_line, expected_burst;

    task fail(input string reason);
        begin $display("FAIL: %s", reason); $fatal(1); end
    endtask

    always @(posedge ddr_clk) begin
        if (!ddr_resetn) begin
            fb_arready <= 0;
            fb_rvalid <= 0;
            fb_rlast <= 0;
            response_active <= 0;
            response_beat <= 0;
            ar_count <= 0;
        end else begin
            fb_arready <= !response_active;
            fb_rvalid <= 0;
            fb_rlast <= 0;
            if (!response_active && fb_arvalid && fb_arready) begin
                expected_line = (ar_count / 5) % 4;
                expected_burst = ar_count % 5;
                expected_addr = (ar_count < 20 ? FB0_NATIVE : FB1_NATIVE) +
                                expected_line * 640 + expected_burst * 128;
                if (fb_araddr !== expected_addr)
                    fail("unexpected or out-of-window framebuffer address");
                if (fb_arid != 4'he || fb_arlen != 4'hf || !fb_urgent)
                    fail("invalid native DDR burst attributes");
                response_active <= 1;
                response_beat <= 0;
                response_id <= fb_arid;
                ar_count <= ar_count + 1;
            end else if (response_active) begin
                fb_rvalid <= 1;
                fb_rid <= response_id;
                fb_rdata <= {16{16'hf800}};
                fb_rlast <= response_beat == 15;
                if (response_beat == 15)
                    response_active <= 0;
                else
                    response_beat <= response_beat + 1;
            end
        end
    end

    always @(posedge pix_clk)
        if (pix_resetn && de_out && r_out == 8'hff && !g_out && !b_out)
            red_pixels <= red_pixels + 1;

    initial begin
        repeat (8) @(posedge ddr_clk);
        ddr_resetn <= 1;
        ddr_init_done <= 1;
        repeat (4) @(posedge pix_clk);
        pix_resetn <= 1;

        wait (active_enable_pix);
        // Ask for FB1 well before the next boundary; the current frame must
        // finish on FB0 and the following frame must start at FB1.
        wait (ar_count >= 5);
        sys_requested_buffer <= 1;
        wait (active_buffer_pix);
        wait (ar_count >= 25);
        repeat (200) @(posedge pix_clk);

        if (underflow_pix || underflow_count_pix != 0)
            fail("scanout underflowed with a 200 MHz DDR responder");
        if (dma_error_ddr)
            fail("DMA reported a native DDR protocol error");
        if (red_pixels == 0)
            fail("no RGB565 framebuffer pixels reached the video output");
        $display("VIDEO_FB_DMA_PASS bursts=%0d red_pixels=%0d frames=%0d",
                 ar_count, red_pixels, frame_count_pix);
        $finish;
    end

    initial begin
        #10000000;
        fail("timeout");
    end
endmodule
