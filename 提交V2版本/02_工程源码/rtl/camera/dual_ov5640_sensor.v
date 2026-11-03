`timescale 1ns/1ps

// Sensor-side control for the two OV5640 devices on the official FMC card.
// Each camera has its own SCCB bus; the reset sequence is shared as in the
// official dual-camera demo.
module dual_ov5640_sensor #(
    parameter [18:0] PWDN_DELAY_COUNT = 19'h40000,
    parameter [15:0] RESET_DELAY_COUNT = 16'hffff,
    parameter [19:0] INIT_DELAY_COUNT = 20'hfffff,
    parameter [15:0] SCCB_DIVIDER_MAX = 16'd1249,
    parameter [8:0]  LAST_REGISTER_INDEX = 9'd356
)(
    input  wire       clk_50m,
    input  wire       clk_25m,
    input  wire       resetn,
    input  wire       camera_enable,
    output wire       camera1_resetn,
    output wire       camera2_resetn,
    output wire       camera_powerdown,
    output wire       camera1_init_done,
    output wire       camera2_init_done,
    output wire       sccb_nack_seen,
    output wire       camera1_scl,
    inout  wire       camera1_sda,
    output wire       camera2_scl,
    inout  wire       camera2_sda
);
    wire initial_enable;
    wire camera1_nack_seen;
    wire camera2_nack_seen;

    assign sccb_nack_seen = camera1_nack_seen | camera2_nack_seen;

    ov5640_power_on_delay #(
        .PWDN_DELAY_COUNT(PWDN_DELAY_COUNT),
        .RESET_DELAY_COUNT(RESET_DELAY_COUNT),
        .INIT_DELAY_COUNT(INIT_DELAY_COUNT)
    ) power_on_delay_inst (
        .clk_50m(clk_50m),
        .resetn(resetn),
        .camera_enable(camera_enable),
        .camera1_resetn(camera1_resetn),
        .camera2_resetn(camera2_resetn),
        .camera_powerdown(camera_powerdown),
        .initial_enable(initial_enable)
    );

    ov5640_register_init #(
        .SCCB_DIVIDER_MAX(SCCB_DIVIDER_MAX),
        .LAST_REGISTER_INDEX(LAST_REGISTER_INDEX)
    ) camera1_register_init_inst (
        .clk_25m(clk_25m),
        .camera_resetn(camera1_resetn),
        .initial_enable(initial_enable),
        .init_done(camera1_init_done),
        .nack_seen(camera1_nack_seen),
        .sccb_scl(camera1_scl),
        .sccb_sda(camera1_sda),
        .register_index()
    );

    ov5640_register_init #(
        .SCCB_DIVIDER_MAX(SCCB_DIVIDER_MAX),
        .LAST_REGISTER_INDEX(LAST_REGISTER_INDEX)
    ) camera2_register_init_inst (
        .clk_25m(clk_25m),
        .camera_resetn(camera2_resetn),
        .initial_enable(initial_enable),
        .init_done(camera2_init_done),
        .nack_seen(camera2_nack_seen),
        .sccb_scl(camera2_scl),
        .sccb_sda(camera2_sda),
        .register_index()
    );
endmodule
