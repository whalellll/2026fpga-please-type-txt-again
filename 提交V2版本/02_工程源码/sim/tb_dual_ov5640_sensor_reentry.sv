`timescale 1ns/1ps

module tb_dual_ov5640_sensor_reentry;
    reg clk_50m = 1'b0;
    reg clk_25m = 1'b0;
    reg resetn = 1'b0;
    reg camera_enable = 1'b0;

    wire camera1_resetn;
    wire camera2_resetn;
    wire camera_powerdown;
    wire camera1_init_done;
    wire camera2_init_done;
    wire sccb_nack_seen;
    wire camera1_scl;
    wire camera2_scl;
    tri camera1_sda;
    tri camera2_sda;

    integer reset_rise_count = 0;
    integer init_done_rise_count = 0;
    integer scl_transition_count = 0;
    reg sda_low_seen = 1'b0;

    always #5 clk_50m = ~clk_50m;
    always #7 clk_25m = ~clk_25m;

    pullup(camera1_sda);
    pullup(camera2_sda);

    dual_ov5640_sensor #(
        .PWDN_DELAY_COUNT(19'd2),
        .RESET_DELAY_COUNT(16'd2),
        .INIT_DELAY_COUNT(20'd2),
        .SCCB_DIVIDER_MAX(16'd0),
        .LAST_REGISTER_INDEX(9'd1)
    ) dut (
        .clk_50m(clk_50m),
        .clk_25m(clk_25m),
        .resetn(resetn),
        .camera_enable(camera_enable),
        .camera1_resetn(camera1_resetn),
        .camera2_resetn(camera2_resetn),
        .camera_powerdown(camera_powerdown),
        .camera1_init_done(camera1_init_done),
        .camera2_init_done(camera2_init_done),
        .sccb_nack_seen(sccb_nack_seen),
        .camera1_scl(camera1_scl),
        .camera1_sda(camera1_sda),
        .camera2_scl(camera2_scl),
        .camera2_sda(camera2_sda)
    );

    always @(posedge camera1_resetn)
        reset_rise_count = reset_rise_count + 1;

    always @(posedge camera1_init_done)
        init_done_rise_count = init_done_rise_count + 1;

    always @(camera1_scl) begin
        if (camera1_resetn)
            scl_transition_count = scl_transition_count + 1;
        if (resetn && (camera1_scl !== 1'b0) && (camera1_scl !== 1'b1))
            $fatal(1, "SCL must remain push-pull, got %b", camera1_scl);
    end

    always @(camera1_sda) begin
        if (camera1_sda === 1'b0)
            sda_low_seen = 1'b1;
        if (resetn && (camera1_sda !== 1'b0) && (camera1_sda !== 1'b1))
            $fatal(1, "pulled-up SDA resolved to %b", camera1_sda);
    end

    initial begin
        repeat (3) @(posedge clk_50m);
        resetn = 1'b1;
        camera_enable = 1'b1;

        wait (camera1_init_done && camera2_init_done);
        #1;
        if ((reset_rise_count != 1) || (init_done_rise_count != 1))
            $fatal(1, "first initialization count mismatch reset=%0d done=%0d",
                reset_rise_count, init_done_rise_count);
        if (!sccb_nack_seen)
            $fatal(1, "unacknowledged test bus did not set sticky NACK status");

        @(negedge clk_50m);
        camera_enable = 1'b0;
        repeat (3) @(posedge clk_50m);
        #1;
        if (camera1_resetn || camera2_resetn)
            $fatal(1, "camera reset outputs did not assert on disable");
        if (camera1_init_done || camera2_init_done || sccb_nack_seen)
            $fatal(1, "initialization state did not clear on disable");
        if (!camera_powerdown)
            $fatal(1, "power sequencing did not return to its initial state");
        if (!camera1_scl || !camera2_scl || !camera1_sda || !camera2_sda)
            $fatal(1, "SCCB buses were not idle-high while reset");

        @(negedge clk_50m);
        camera_enable = 1'b1;
        wait (camera1_init_done && camera2_init_done);
        #1;
        if ((reset_rise_count != 2) || (init_done_rise_count != 2))
            $fatal(1, "re-entry did not rerun initialization reset=%0d done=%0d",
                reset_rise_count, init_done_rise_count);
        if (!sda_low_seen || (scl_transition_count < 20))
            $fatal(1, "SCCB write activity was not observed");

        $display("DUAL_OV5640_REENTRY_PASS reset=%0d done=%0d scl_edges=%0d",
            reset_rise_count, init_done_rise_count, scl_transition_count);
        $finish;
    end

    initial begin
        #100000;
        $fatal(1, "dual sensor re-entry test timeout");
    end
endmodule
