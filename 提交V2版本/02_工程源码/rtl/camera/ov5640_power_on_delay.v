`timescale 1ns/1ps

// Power-on sequencing used by the Double-OV5640 reference design.  The
// external camera_enable input is also the restart control: taking it low
// returns every counter and output to the initial state, so a later assertion
// repeats the complete sensor initialization sequence.
module ov5640_power_on_delay #(
    parameter [18:0] PWDN_DELAY_COUNT = 19'h40000,
    parameter [15:0] RESET_DELAY_COUNT = 16'hffff,
    parameter [19:0] INIT_DELAY_COUNT = 20'hfffff
)(
    input  wire clk_50m,
    input  wire resetn,
    input  wire camera_enable,
    output wire camera1_resetn,
    output wire camera2_resetn,
    output reg  camera_powerdown,
    output reg  initial_enable
);
    reg [18:0] pwdn_count;
    reg [15:0] reset_count;
    reg [19:0] init_count;
    reg camera_resetn;

    assign camera1_resetn = camera_resetn;
    assign camera2_resetn = camera_resetn;

    // The daughter card fixes both PWDN pins low.  Retaining this stage keeps
    // the reference design's delay between enabling the block and RESETB.
    always @(posedge clk_50m or negedge resetn) begin
        if (!resetn) begin
            pwdn_count <= 19'd0;
            camera_powerdown <= 1'b1;
        end else if (!camera_enable) begin
            pwdn_count <= 19'd0;
            camera_powerdown <= 1'b1;
        end else if (pwdn_count < PWDN_DELAY_COUNT) begin
            pwdn_count <= pwdn_count + 1'b1;
            camera_powerdown <= 1'b1;
        end else begin
            camera_powerdown <= 1'b0;
        end
    end

    always @(posedge clk_50m or negedge resetn) begin
        if (!resetn) begin
            reset_count <= 16'd0;
            camera_resetn <= 1'b0;
        end else if (!camera_enable || camera_powerdown) begin
            reset_count <= 16'd0;
            camera_resetn <= 1'b0;
        end else if (reset_count < RESET_DELAY_COUNT) begin
            reset_count <= reset_count + 1'b1;
            camera_resetn <= 1'b0;
        end else begin
            camera_resetn <= 1'b1;
        end
    end

    always @(posedge clk_50m or negedge resetn) begin
        if (!resetn) begin
            init_count <= 20'd0;
            initial_enable <= 1'b0;
        end else if (!camera_enable || !camera_resetn) begin
            init_count <= 20'd0;
            initial_enable <= 1'b0;
        end else if (init_count < INIT_DELAY_COUNT) begin
            init_count <= init_count + 1'b1;
            initial_enable <= 1'b0;
        end else begin
            initial_enable <= 1'b1;
        end
    end
endmodule
