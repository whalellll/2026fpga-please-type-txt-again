`timescale 1ns/1ps

module tb_camera_frame_writer;
    localparam [27:0] FB0_NATIVE = 28'h6c80000;
    localparam [27:0] FB1_NATIVE = 28'h6d00000;
    localparam [9:0] TEST_FRAME_LINES = 10'd4;

    reg pixel_clk = 1'b0;
    reg pixel_resetn = 1'b0;
    reg pixel_vsync = 1'b0;
    reg pixel_line_active = 1'b0;
    reg pixel_valid = 1'b0;
    reg [15:0] pixel_rgb565 = 16'd0;

    reg ddr_clk = 1'b0;
    reg ddr_resetn = 1'b0;
    reg enable = 1'b0;
    reg frame_accept_enable = 1'b0;
    reg write_buffer = 1'b0;
    reg stop_request = 1'b0;
    reg pixel_clock_enable = 1'b1;
    reg hold_native_aw = 1'b0;
    reg hold_native_write = 1'b0;

    wire [27:0] cam_awaddr;
    wire [3:0] cam_awid;
    wire [3:0] cam_awlen;
    wire cam_awvalid;
    wire cam_awready;
    wire [255:0] cam_wdata;
    wire [31:0] cam_wstrb;
    wire cam_wready;
    wire [3:0] cam_wid;
    wire cam_wlast;
    wire cam_urgent;
    wire frame_started;
    wire frame_complete;
    wire completed_buffer;
    wire busy;
    wire idle;
    wire [31:0] bad_line_count;
    wire [31:0] drop_frame_count;
    wire ddr_error;

    integer line_index;
    integer pixel_index;
    integer aw_count = 0;
    integer beat_count = 0;
    integer frame_started_count = 0;
    integer frame_complete_count = 0;
    integer errors = 0;
    integer lane_index;
    integer expected_line;
    integer expected_burst;
    integer expected_x;
    integer complete_origin;
    reg [15:0] expected_pixel;
    reg [27:0] active_awaddr = 28'd0;
    reg [9:0] active_line = 10'd0;
    reg [2:0] active_burst = 3'd0;
    reg [3:0] native_beat = 4'd0;
    reg native_active = 1'b0;
    reg verify_payload = 1'b0;
    reg [27:0] verify_base = FB0_NATIVE;
    integer verify_aw_origin = 0;
    reg previous_frame_complete = 1'b0;
    reg [7:0] ddr_cycle = 8'd0;
    reg held_req_toggle = 1'b0;
    reg held_req1_toggle = 1'b0;

    always #6.734 begin
        if (pixel_clock_enable)
            pixel_clk = ~pixel_clk;
    end
    always #2.5 ddr_clk = ~ddr_clk;

    assign cam_awready = ddr_resetn && !native_active && !hold_native_aw &&
                         (ddr_cycle[2:0] != 3'b011);
    assign cam_wready = native_active && !hold_native_write &&
                        (ddr_cycle[3:0] != 4'h5) &&
                        (ddr_cycle[3:0] != 4'hb);
    assign cam_wid = native_active ? 4'hc : 4'd0;
    assign cam_wlast = cam_wready && (native_beat == 4'd15);

    camera_frame_writer #(
        .FB0_NATIVE(FB0_NATIVE),
        .FB1_NATIVE(FB1_NATIVE),
        .FRAME_LINES(TEST_FRAME_LINES),
        .STOP_QUIET_CYCLES(16'd64)
    ) dut (
        .pixel_clk(pixel_clk),
        .pixel_resetn(pixel_resetn),
        .pixel_vsync(pixel_vsync),
        .pixel_line_active(pixel_line_active),
        .pixel_valid(pixel_valid),
        .pixel_rgb565(pixel_rgb565),
        .ddr_clk(ddr_clk),
        .ddr_resetn(ddr_resetn),
        .enable(enable),
        .frame_accept_enable(frame_accept_enable),
        .write_buffer(write_buffer),
        .stop_request(stop_request),
        .cam_awaddr(cam_awaddr),
        .cam_awid(cam_awid),
        .cam_awlen(cam_awlen),
        .cam_awvalid(cam_awvalid),
        .cam_awready(cam_awready),
        .cam_wdata(cam_wdata),
        .cam_wstrb(cam_wstrb),
        .cam_wready(cam_wready),
        .cam_wid(cam_wid),
        .cam_wlast(cam_wlast),
        .cam_urgent(cam_urgent),
        .frame_started(frame_started),
        .frame_complete(frame_complete),
        .completed_buffer(completed_buffer),
        .busy(busy),
        .idle(idle),
        .bad_line_count(bad_line_count),
        .drop_frame_count(drop_frame_count),
        .ddr_error(ddr_error)
    );

    task pulse_vsync;
        begin
            @(negedge pixel_clk);
            pixel_vsync = 1'b1;
            repeat (4) @(negedge pixel_clk);
            pixel_vsync = 1'b0;
            repeat (4) @(negedge pixel_clk);
        end
    endtask

    task drive_line;
        input integer line_number;
        input integer pixel_total;
        input integer gap_pixel_valid;
        begin
            @(negedge pixel_clk);
            pixel_line_active = 1'b1;
            pixel_valid = 1'b0;
            @(negedge pixel_clk);
            for (pixel_index = 0; pixel_index < pixel_total;
                 pixel_index = pixel_index + 1) begin
                pixel_rgb565 = ((line_number * 31) + pixel_index) ^ 16'h5a5a;
                pixel_valid = 1'b1;
                @(negedge pixel_clk);
                if (gap_pixel_valid != 0) begin
                    pixel_valid = 1'b0;
                    @(negedge pixel_clk);
                end
            end
            pixel_line_active = 1'b0;
            pixel_valid = 1'b0;
            pixel_rgb565 = 16'd0;
            repeat (20) @(negedge pixel_clk);
        end
    endtask

    task wait_until_idle;
        integer timeout_count;
        begin
            timeout_count = 0;
            while (busy && timeout_count < 2000000) begin
                @(posedge ddr_clk);
                timeout_count = timeout_count + 1;
            end
            if (busy) begin
                $display("ERROR: writer failed to become idle");
                errors = errors + 1;
            end
            repeat (8) @(posedge pixel_clk);
        end
    endtask

    task drive_line_stop_before_fall;
        begin
            @(negedge pixel_clk);
            pixel_line_active = 1'b1;
            pixel_valid = 1'b0;
            @(negedge pixel_clk);
            for (pixel_index = 0; pixel_index < 1280;
                 pixel_index = pixel_index + 1) begin
                pixel_rgb565 = pixel_index ^ 16'h5a5a;
                pixel_valid = 1'b1;
                @(negedge pixel_clk);
            end
            pixel_valid = 1'b0;
            held_req_toggle = dut.req0_toggle_pix;
            stop_request = 1'b1;
            repeat (5) @(negedge pixel_clk);
            pixel_line_active = 1'b0;
            pixel_rgb565 = 16'd0;
            repeat (5) @(negedge pixel_clk);
        end
    endtask

    always @(posedge ddr_clk) begin
        if (!ddr_resetn) begin
            ddr_cycle <= 8'd0;
            native_active <= 1'b0;
            native_beat <= 4'd0;
            aw_count <= 0;
            beat_count <= 0;
            frame_started_count <= 0;
            frame_complete_count <= 0;
            previous_frame_complete <= 1'b0;
        end else begin
            ddr_cycle <= ddr_cycle + 8'd1;

            if (frame_started)
                frame_started_count <= frame_started_count + 1;
            if (frame_complete)
                frame_complete_count <= frame_complete_count + 1;
            if (frame_complete && native_active) begin
                $display("ERROR: frame_complete preceded the final native WLAST");
                errors = errors + 1;
            end
            if (frame_complete && previous_frame_complete) begin
                $display("ERROR: frame_complete was wider than one DDR cycle");
                errors = errors + 1;
            end
            previous_frame_complete <= frame_complete;

            if (cam_awvalid && cam_awready) begin
                if (native_active) begin
                    $display("ERROR: AW accepted while prior burst active");
                    errors = errors + 1;
                end
                native_active <= 1'b1;
                native_beat <= 4'd0;
                active_awaddr <= cam_awaddr;
                if (cam_awid !== 4'hc || cam_awlen !== 4'd15) begin
                    $display("ERROR: AW attributes id=%x len=%0d", cam_awid,
                             cam_awlen);
                    errors = errors + 1;
                end
                if (cam_wstrb !== 32'hffff_ffff) begin
                    $display("ERROR: WSTRB is not all ones");
                    errors = errors + 1;
                end

                if (verify_payload) begin
                    expected_line = (aw_count - verify_aw_origin) / 5;
                    expected_burst = (aw_count - verify_aw_origin) % 5;
                    if (cam_awaddr !== verify_base + expected_line * 640 +
                                         expected_burst * 128) begin
                        $display("ERROR: AW[%0d]=%h expected=%h", aw_count,
                                 cam_awaddr, verify_base + expected_line * 640 +
                                 expected_burst * 128);
                        errors = errors + 1;
                    end
                    active_line <= expected_line;
                    active_burst <= expected_burst;
                end
                aw_count <= aw_count + 1;
            end

            if (native_active && cam_wready) begin
                if (verify_payload) begin
                    for (lane_index = 0; lane_index < 16;
                         lane_index = lane_index + 1) begin
                        expected_x = active_burst * 256 + native_beat * 16 +
                                     lane_index;
                        expected_pixel = ((active_line * 31) + expected_x) ^
                                         16'h5a5a;
                        if (cam_wdata[lane_index * 16 +: 16] !==
                            expected_pixel) begin
                            if (errors < 20)
                                $display("ERROR: PIX line=%0d x=%0d got=%04x expected=%04x",
                                         active_line, expected_x,
                                         cam_wdata[lane_index * 16 +: 16],
                                         expected_pixel);
                            errors = errors + 1;
                        end
                    end
                end
                beat_count <= beat_count + 1;
                if (cam_wlast) begin
                    if (native_beat != 4'd15) begin
                        $display("ERROR: early WLAST at beat %0d", native_beat);
                        errors = errors + 1;
                    end
                    native_active <= 1'b0;
                    native_beat <= 4'd0;
                end else begin
                    native_beat <= native_beat + 4'd1;
                end
            end
        end
    end

    initial begin
        #5000000;
        $fatal(1, "TIMEOUT: tb_camera_frame_writer");
    end

    initial begin
        repeat (12) @(posedge ddr_clk);
        ddr_resetn = 1'b1;
        repeat (8) @(posedge pixel_clk);
        pixel_resetn = 1'b1;
        enable = 1'b1;
        frame_accept_enable = 1'b1;
        write_buffer = 1'b0;
        repeat (8) @(posedge pixel_clk);

        // Use four lines to keep the unit test quick; the production default
        // is exactly 720.  Horizontal packing remains the full 1280 pixels.
        verify_payload = 1'b1;
        verify_base = FB0_NATIVE;
        verify_aw_origin = aw_count;
        pulse_vsync;
        drive_line(0, 1280, 1);
        for (line_index = 1; line_index < TEST_FRAME_LINES;
             line_index = line_index + 1)
            drive_line(line_index, 1280, 0);
        if (frame_complete_count != 0) begin
            $display("ERROR: valid frame published before closing VSYNC");
            errors = errors + 1;
        end
        pulse_vsync;
        wait_until_idle;
        if (aw_count != TEST_FRAME_LINES * 5 ||
            beat_count != TEST_FRAME_LINES * 80) begin
            $display("ERROR: valid frame transactions AW=%0d W=%0d", aw_count,
                     beat_count);
            errors = errors + 1;
        end
        if (frame_complete_count != 1 || completed_buffer != 1'b0) begin
            $display("ERROR: valid FB0 frame was not published");
            errors = errors + 1;
        end

        // Buffer select and permit may change together in the source domain.
        // Permit has an extra pixel-domain settling stage, so the first frame
        // admitted after the update must use the new FB1 selection.
        frame_accept_enable = 1'b0;
        repeat (5) @(posedge pixel_clk);
        @(negedge ddr_clk);
        write_buffer = 1'b1;
        frame_accept_enable = 1'b1;
        repeat (5) @(posedge pixel_clk);
        verify_base = FB1_NATIVE;
        verify_aw_origin = aw_count;
        pulse_vsync;
        drive_line(0, 1280, 1);
        for (line_index = 1; line_index < TEST_FRAME_LINES;
             line_index = line_index + 1)
            drive_line(line_index, 1280, 0);
        pulse_vsync;
        wait_until_idle;
        if (aw_count != verify_aw_origin + TEST_FRAME_LINES * 5) begin
            $display("ERROR: FB1 frame burst count mismatch");
            errors = errors + 1;
        end
        if (frame_complete_count != 2 || completed_buffer != 1'b1) begin
            $display("ERROR: CDC-safe FB1 frame was not published");
            errors = errors + 1;
        end

        // One short line invalidates the whole frame.  It may have dirtied the
        // unpublished back buffer, but it must never issue frame_complete.
        verify_payload = 1'b0;
        write_buffer = 1'b1;
        pulse_vsync;
        drive_line(0, 1279, 1);
        pulse_vsync;
        wait_until_idle;
        if (frame_complete_count != 2 || drop_frame_count != 1) begin
            $display("ERROR: short-line frame was not dropped complete=%0d drop=%0d",
                     frame_complete_count, drop_frame_count);
            errors = errors + 1;
        end

        // A line longer than 1280 pixels is likewise a whole-frame failure.
        pulse_vsync;
        drive_line(0, 1281, 1);
        pulse_vsync;
        wait_until_idle;
        if (frame_complete_count != 2 || drop_frame_count != 2 ||
            bad_line_count < 2) begin
            $display("ERROR: long-line frame/status mismatch complete=%0d drop=%0d bad=%0d",
                     frame_complete_count, drop_frame_count, bad_line_count);
            errors = errors + 1;
        end

        // Stop just before HREF falls must discard even an otherwise complete
        // line.  No request is allowed to escape after the stop acknowledgement.
        stop_request = 1'b0;
        repeat (6) @(posedge pixel_clk);
        pulse_vsync;
        drive_line_stop_before_fall;
        wait_until_idle;
        if (dut.req0_toggle_pix != held_req_toggle) begin
            $display("ERROR: stop-before-HREF-fall emitted a line request");
            errors = errors + 1;
        end
        if (frame_complete_count != 2 || drop_frame_count != 3) begin
            $display("ERROR: stop-before-HREF-fall was not dropped cleanly");
            errors = errors + 1;
        end

        // Once the writer presents AWVALID, stop must not retract the native
        // request even when AWREADY is held low.  Address and AWVALID remain
        // stable until the handshake, then the accepted burst drains through
        // WLAST before the stopped frame becomes idle.
        stop_request = 1'b0;
        hold_native_aw = 1'b1;
        repeat (6) @(posedge pixel_clk);
        verify_aw_origin = aw_count;
        complete_origin = beat_count;
        pulse_vsync;
        drive_line(0, 1280, 0);
        while (!cam_awvalid)
            @(posedge ddr_clk);
        active_awaddr = cam_awaddr;
        stop_request = 1'b1;
        repeat (20) begin
            @(posedge ddr_clk);
            if (!cam_awvalid || (cam_awaddr != active_awaddr)) begin
                $display("ERROR: stop retracted or changed blocked AW");
                errors = errors + 1;
            end
        end
        if (aw_count != verify_aw_origin) begin
            $display("ERROR: blocked AW unexpectedly handshook");
            errors = errors + 1;
        end
        hold_native_aw = 1'b0;
        while (!native_active)
            @(posedge ddr_clk);
        wait_until_idle;
        if ((aw_count != verify_aw_origin + 1) ||
            (beat_count != complete_origin + 16) ||
            (frame_complete_count != 2) || (drop_frame_count != 4)) begin
            $display("ERROR: stopped blocked-AW burst did not drain AW=%0d W=%0d complete=%0d drop=%0d",
                     aw_count - verify_aw_origin,
                     beat_count - complete_origin,
                     frame_complete_count, drop_frame_count);
            errors = errors + 1;
        end

        // A mid-frame stop may discard the frame, but an AW that has already
        // been accepted must retain ownership until its WLAST is consumed.
        stop_request = 1'b0;
        hold_native_write = 1'b1;
        repeat (5) @(posedge pixel_clk);
        pulse_vsync;
        drive_line(0, 1280, 0);
        while (!native_active)
            @(posedge ddr_clk);
        stop_request = 1'b1;
        repeat (5) @(posedge pixel_clk);
        repeat (20) @(posedge ddr_clk);
        if (!native_active || !busy) begin
            $display("ERROR: stop abandoned an accepted native burst");
            errors = errors + 1;
        end
        hold_native_write = 1'b0;
        wait_until_idle;
        if (frame_complete_count != 2 || drop_frame_count != 5) begin
            $display("ERROR: mid-frame stop was not dropped cleanly");
            errors = errors + 1;
        end

        // If HREF is stuck high while PCLK remains alive, stop must be
        // confirmed by the pixel domain instead of waiting for the DDR quiet
        // fallback.  The partial line is discarded immediately.  Lowering
        // HREF later (as sensor reset takes effect) must not emit a stale line
        // request into the following camera session.
        stop_request = 1'b0;
        repeat (6) @(posedge pixel_clk);
        pulse_vsync;
        @(negedge pixel_clk);
        pixel_line_active = 1'b1;
        pixel_valid = 1'b1;
        for (pixel_index = 0; pixel_index < 64;
             pixel_index = pixel_index + 1) begin
            pixel_rgb565 = pixel_index ^ 16'h33cc;
            @(negedge pixel_clk);
        end
        pixel_valid = 1'b0;
        held_req_toggle = dut.req0_toggle_pix;
        held_req1_toggle = dut.req1_toggle_pix;
        stop_request = 1'b1;
        line_index = 0;
        while (busy && line_index < 48) begin
            @(posedge ddr_clk);
            line_index = line_index + 1;
        end
        if (busy) begin
            $display("ERROR: live PCLK stop used quiet fallback with HREF high");
            errors = errors + 1;
            wait_until_idle;
        end
        @(negedge pixel_clk);
        pixel_line_active = 1'b0;
        pixel_rgb565 = 16'd0;
        repeat (20) @(posedge pixel_clk);
        if ((dut.req0_toggle_pix != held_req_toggle) ||
            (dut.req1_toggle_pix != held_req1_toggle) ||
            (dut.req0_d2 != dut.ack0_ddr) ||
            (dut.req1_d2 != dut.ack1_ddr)) begin
            $display("ERROR: delayed HREF fall emitted a stale line request");
            errors = errors + 1;
        end
        if (drop_frame_count != 6) begin
            $display("ERROR: HREF-high stop did not drop exactly one frame");
            errors = errors + 1;
        end

        // Re-enter capture without resetting the writer.  A complete frame in
        // this session proves that no old request/end mailbox state survived.
        stop_request = 1'b0;
        write_buffer = 1'b0;
        repeat (6) @(posedge pixel_clk);
        verify_aw_origin = aw_count;
        complete_origin = frame_complete_count;
        pulse_vsync;
        for (line_index = 0; line_index < TEST_FRAME_LINES;
             line_index = line_index + 1)
            drive_line(line_index, 1280, 0);
        pulse_vsync;
        wait_until_idle;
        if ((aw_count != verify_aw_origin + TEST_FRAME_LINES * 5) ||
            (frame_complete_count != complete_origin + 1) ||
            (completed_buffer != 1'b0)) begin
            $display("ERROR: next session was polluted AW=%0d complete=%0d",
                     aw_count - verify_aw_origin,
                     frame_complete_count - complete_origin);
            errors = errors + 1;
        end

        // DDR-side fallback must release a stopped session even if PCLK and
        // VSYNC disappear before the pixel-domain abort can return.
        stop_request = 1'b0;
        repeat (6) @(posedge pixel_clk);
        pulse_vsync;
        while (!busy)
            @(posedge ddr_clk);
        @(negedge pixel_clk);
        pixel_clock_enable = 1'b0;
        stop_request = 1'b1;
        line_index = 0;
        while (busy && line_index < 1000) begin
            @(posedge ddr_clk);
            line_index = line_index + 1;
        end
        if (busy || drop_frame_count != 7) begin
            $display("ERROR: stopped writer did not recover with PCLK absent");
            errors = errors + 1;
        end
        pixel_clock_enable = 1'b1;
        repeat (8) @(posedge pixel_clk);

        // A start toggle can already be crossing when Esc is pressed.  The
        // DDR domain must reject that late start and return the pixel slot.
        stop_request = 1'b0;
        repeat (5) @(posedge pixel_clk);
        line_index = frame_started_count;
        @(negedge pixel_clk);
        pixel_vsync = 1'b1;
        @(posedge pixel_clk);
        #1 stop_request = 1'b1;
        @(negedge pixel_clk);
        pixel_vsync = 1'b0;
        repeat (100) @(posedge ddr_clk);
        if (busy || frame_started_count != line_index ||
            drop_frame_count != 8) begin
            $display("ERROR: late frame start was not rejected");
            errors = errors + 1;
        end

        // stop_request present before VSYNC rejects capture in the pixel
        // domain and must not open a native DDR transaction.
        stop_request = 1'b1;
        repeat (5) @(posedge pixel_clk);
        line_index = frame_started_count;
        pulse_vsync;
        drive_line(0, 64, 1);
        repeat (20) @(posedge ddr_clk);
        if (busy || frame_started_count != line_index || cam_awvalid) begin
            $display("ERROR: stop_request did not reject the next VSYNC");
            errors = errors + 1;
        end

        // Statistics and the sticky DDR fault belong to one ENABLE session.
        // A fresh idle 0->1 transition must start with clean status.
        if (bad_line_count == 0 || drop_frame_count == 0) begin
            $display("ERROR: re-entry test lacked accumulated status");
            errors = errors + 1;
        end
        enable = 1'b0;
        repeat (4) @(posedge ddr_clk);
        enable = 1'b1;
        @(posedge ddr_clk);
        #1;
        if (bad_line_count != 0 || drop_frame_count != 0 || ddr_error) begin
            $display("ERROR: ENABLE re-entry did not clear session status");
            errors = errors + 1;
        end

        if (!idle || cam_urgent) begin
            $display("ERROR: idle/urgent status mismatch at end of test");
            errors = errors + 1;
        end
        if (ddr_error) begin
            $display("ERROR: DDR protocol error asserted during valid handshakes");
            errors = errors + 1;
        end

        if (errors == 0)
            $display("CAMERA_FRAME_WRITER_PASS");
        else
            $fatal(1, "CAMERA_FRAME_WRITER_FAIL errors=%0d", errors);
        $finish;
    end
endmodule
