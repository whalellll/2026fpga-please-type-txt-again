`timescale 1ns/1ps

module tb_camera_buffer_control;
    reg clk = 1'b0;
    reg resetn = 1'b0;
    reg control_enable = 1'b0;
    reg stop_request = 1'b0;
    reg snapshot_hold = 1'b0;
    reg writer_started = 1'b0;
    reg writer_complete = 1'b0;
    reg writer_completed_buffer = 1'b0;
    reg writer_idle = 1'b1;
    reg display_enable = 1'b0;
    reg display_buffer = 1'b0;

    wire sensor_enable;
    wire frame_accept_enable;
    wire write_buffer;
    wire frame_valid;
    wire published_buffer;
    wire idle;
    wire stopping;
    wire snapshot_ready;
    wire snapshot_buffer;
    wire [31:0] snapshot_frame_count;
    wire [31:0] frame_count;

    always #5 clk = ~clk;

    camera_buffer_control dut (
        .clk(clk), .resetn(resetn),
        .control_enable(control_enable), .stop_request(stop_request),
        .snapshot_hold(snapshot_hold), .snapshot_ready(snapshot_ready),
        .snapshot_buffer(snapshot_buffer),
        .snapshot_frame_count(snapshot_frame_count),
        .writer_started(writer_started), .writer_complete(writer_complete),
        .writer_completed_buffer(writer_completed_buffer),
        .writer_idle(writer_idle), .display_enable(display_enable),
        .display_buffer(display_buffer), .sensor_enable(sensor_enable),
        .frame_accept_enable(frame_accept_enable),
        .write_buffer(write_buffer), .frame_valid(frame_valid),
        .published_buffer(published_buffer), .idle(idle),
        .stopping(stopping), .frame_count(frame_count)
    );

    initial begin
        repeat (3) @(posedge clk);
        resetn <= 1'b1;
        @(posedge clk);
        #1;
        if (!idle || sensor_enable || frame_valid)
            $fatal(1, "reset state is not idle");

        // Start with buffer 0 remembered by the display.  The first camera
        // frame must target the opposite buffer even while scanout is off.
        display_buffer <= 1'b0;
        control_enable <= 1'b1;
        @(posedge clk);
        #1;
        if (!sensor_enable || !frame_accept_enable || write_buffer != 1'b1 || idle)
            $fatal(1, "camera session did not grant a safe first buffer");

        writer_idle <= 1'b0;
        writer_started <= 1'b1;
        @(posedge clk);
        #1;
        writer_started <= 1'b0;
        if (frame_accept_enable || idle)
            $fatal(1, "frame grant was not consumed");

        // Publication is forbidden until the writer reports the final native
        // write completion.
        repeat (3) begin
            @(posedge clk);
            #1;
            if (frame_valid)
                $fatal(1, "partial frame was published");
        end
        writer_completed_buffer <= 1'b1;
        writer_complete <= 1'b1;
        writer_idle <= 1'b1;
        @(posedge clk);
        #1;
        writer_complete <= 1'b0;
        if (!frame_valid || published_buffer != 1'b1 || frame_count != 32'd1)
            $fatal(1, "complete frame was not published");
        if (frame_accept_enable)
            $fatal(1, "old display buffer reused before HDMI page flip");

        // Merely enabling display is insufficient; it must acknowledge the
        // exact completed bank at a video frame boundary.
        display_enable <= 1'b1;
        display_buffer <= 1'b0;
        @(posedge clk);
        #1;
        if (frame_accept_enable)
            $fatal(1, "writer ran while HDMI still scanned the old bank");
        display_buffer <= 1'b1;
        @(posedge clk);
        #1;
        if (!frame_accept_enable || write_buffer != 1'b0)
            $fatal(1, "writer did not receive bank 0 after HDMI flip");

        // Holding during an active write waits for final DDR completion and
        // exposes only the fully published bank.  No new grant may appear.
        snapshot_hold <= 1'b1;
        writer_idle <= 1'b0;
        writer_started <= 1'b1;
        @(posedge clk);
        #1;
        writer_started <= 1'b0;
        repeat (3) begin
            @(posedge clk); #1;
            if (snapshot_ready || frame_count != 32'd1)
                $fatal(1, "snapshot was exposed during an active write");
        end
        writer_completed_buffer <= 1'b0;
        writer_complete <= 1'b1;
        writer_idle <= 1'b1;
        @(posedge clk); #1;
        writer_complete <= 1'b0;
        @(posedge clk); #1;
        if (!snapshot_ready || frame_accept_enable ||
            frame_count != 32'd2 || published_buffer != 1'b0 ||
            snapshot_buffer != 1'b1 || snapshot_frame_count != 32'd1)
            $fatal(1, "keypress frame was not frozen before the newer frame completed");
        repeat (5) begin
            @(posedge clk); #1;
            if (!snapshot_ready || snapshot_frame_count != 32'd1 ||
                snapshot_buffer != 1'b1)
                $fatal(1, "frozen snapshot changed during copy");
        end
        display_buffer <= 1'b0;
        snapshot_hold <= 1'b0;
        repeat (2) @(posedge clk);
        #1;
        if (!frame_accept_enable || write_buffer != 1'b1 || snapshot_ready)
            $fatal(1, "preview capture did not resume after snapshot");

        // With no frame active, revoke the asynchronous pixel grant and wait
        // for the CDC drain guard before declaring the bank stable.
        snapshot_hold <= 1'b1;
        @(posedge clk); #1;
        if (snapshot_ready || frame_accept_enable)
            $fatal(1, "idle hold was exposed before its drain guard");
        repeat (1025) @(posedge clk);
        #1;
        if (!snapshot_ready || frame_count != 32'd2 ||
            snapshot_buffer != 1'b0 || snapshot_frame_count != 32'd2)
            $fatal(1, "idle hold failed to lock the published frame");
        snapshot_hold <= 1'b0;
        repeat (2) @(posedge clk);
        #1;
        if (!frame_accept_enable || snapshot_ready)
            $fatal(1, "second snapshot did not resume preview");

        // A newer complete bank may be waiting for the next HDMI boundary.
        // Space must still capture the bank visible at the keypress and the
        // frame number associated with that older displayed bank.
        writer_idle <= 1'b0;
        writer_started <= 1'b1;
        @(posedge clk);
        writer_started <= 1'b0;
        writer_completed_buffer <= 1'b1;
        writer_complete <= 1'b1;
        writer_idle <= 1'b1;
        @(posedge clk);
        #1;
        writer_complete <= 1'b0;
        snapshot_hold <= 1'b1;
        @(posedge clk);
        #1;
        if (!snapshot_ready || published_buffer != 1'b1 ||
            frame_count != 32'd3 || snapshot_buffer != 1'b0 ||
            snapshot_frame_count != 32'd2)
            $fatal(1, "keypress during pending HDMI flip selected the wrong frame");
        snapshot_hold <= 1'b0;
        display_buffer <= 1'b1;
        repeat (2) @(posedge clk);
        #1;
        if (!frame_accept_enable || snapshot_ready)
            $fatal(1, "pending-flip snapshot did not resume preview");

        // A pixel-domain start may arrive several cycles after the grant was
        // revoked.  The pause guard must drain it before READY is asserted.
        snapshot_hold <= 1'b1;
        @(posedge clk); #1;
        repeat (4) @(posedge clk);
        writer_started <= 1'b1;
        writer_idle <= 1'b0;
        @(posedge clk); #1;
        writer_started <= 1'b0;
        if (snapshot_ready)
            $fatal(1, "late CDC writer was ignored during snapshot hold");
        writer_completed_buffer <= 1'b0;
        writer_complete <= 1'b1;
        writer_idle <= 1'b1;
        @(posedge clk); #1;
        writer_complete <= 1'b0;
        @(posedge clk); #1;
        if (!snapshot_ready || frame_count != 32'd4 ||
            snapshot_buffer != 1'b1 || snapshot_frame_count != 32'd3)
            $fatal(1, "late writer changed the keypress snapshot");
        snapshot_hold <= 1'b0;
        display_buffer <= 1'b0;
        repeat (2) @(posedge clk);

        // Stop while no frame is active.  IDLE may assert only after the stop
        // request has been observed; sensor_enable then drops and stays low.
        stop_request <= 1'b1;
        @(posedge clk);
        #1;
        if (frame_accept_enable || idle)
            $fatal(1, "stop did not revoke the next-frame grant");
        @(posedge clk);
        #1;
        if (!idle || sensor_enable || !stopping)
            $fatal(1, "clean stop did not reach stable idle");

        control_enable <= 1'b0;
        stop_request <= 1'b0;
        @(posedge clk);
        #1;
        if (!idle || stopping || frame_valid)
            $fatal(1, "CONTROL clear did not reset session status");

        // Restart and request stop during a live frame.  The sensor must stay
        // enabled until the writer drains and reports idle.
        control_enable <= 1'b1;
        display_buffer <= 1'b1;
        @(posedge clk);
        #1;
        if (published_buffer)
            $fatal(1, "new session retained the previous completed buffer");
        writer_started <= 1'b1;
        writer_idle <= 1'b0;
        @(posedge clk);
        writer_started <= 1'b0;
        stop_request <= 1'b1;
        @(posedge clk);
        #1;
        if (idle || !sensor_enable || !stopping)
            $fatal(1, "mid-frame stop disabled hardware before drain");
        repeat (2) @(posedge clk);
        writer_idle <= 1'b1;
        @(posedge clk);
        @(posedge clk);
        #1;
        if (!idle || sensor_enable)
            $fatal(1, "drained stop did not become idle");

        $display("CAMERA_BUFFER_CONTROL_PASS");
        $finish;
    end
endmodule
