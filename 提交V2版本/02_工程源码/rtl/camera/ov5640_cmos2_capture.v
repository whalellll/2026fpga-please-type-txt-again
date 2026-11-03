`timescale 1ns/1ps

// Captures the second OV5640's 8-bit DVP stream and emits one RGB565 pixel
// pulse for every two HREF bytes.  The byte order and RGB565 bit reorder are
// the same as soc_shexiantou3.  Byte phase is deliberately cleared outside
// HREF so an odd/truncated line can never pair with the next line.
module ov5640_cmos2_capture(
    input  wire        pclk,
    input  wire        resetn,
    input  wire        capture_enable,
    input  wire        camera_vsync,
    input  wire        camera_href,
    input  wire [7:0]  camera_data,
    output reg         frame_vsync,
    output reg         line_active,
    output reg         pixel_valid,
    output reg  [15:0] pixel_rgb565
);
    reg [7:0] camera_data_d;
    reg camera_href_d;
    reg camera_vsync_d;
    reg stream_armed;
    reg arm_low_seen;
    reg first_byte_valid;
    reg [7:0] first_byte;

    always @(posedge pclk or negedge resetn) begin
        if (!resetn) begin
            camera_data_d <= 8'd0;
            camera_href_d <= 1'b0;
            camera_vsync_d <= 1'b0;
            stream_armed <= 1'b0;
            arm_low_seen <= 1'b0;
            frame_vsync <= 1'b0;
            line_active <= 1'b0;
            pixel_valid <= 1'b0;
            pixel_rgb565 <= 16'd0;
            first_byte_valid <= 1'b0;
            first_byte <= 8'd0;
        end else begin
            camera_data_d <= camera_data;
            camera_href_d <= camera_href;
            camera_vsync_d <= camera_vsync;
            if (!capture_enable) begin
                stream_armed <= 1'b0;
                arm_low_seen <= 1'b0;
                frame_vsync <= 1'b0;
            end else if (!stream_armed) begin
                // Initialization may finish in the middle of a VSYNC pulse.
                // Arm only after observing two blank VSYNC-low samples, so an
                // old low value in the input register cannot create a false
                // edge when enable rises during VSYNC.  The writer's
                // first rising edge always denotes a complete new frame.
                frame_vsync <= 1'b0;
                if (camera_vsync_d) begin
                    arm_low_seen <= 1'b0;
                end else if (arm_low_seen) begin
                    stream_armed <= 1'b1;
                    arm_low_seen <= 1'b0;
                end else begin
                    arm_low_seen <= 1'b1;
                end
            end else begin
                frame_vsync <= camera_vsync_d;
            end
            line_active <= camera_href_d & capture_enable & stream_armed;
            pixel_valid <= 1'b0;

            if (!capture_enable || !stream_armed || !camera_href_d ||
                camera_vsync_d) begin
                first_byte_valid <= 1'b0;
            end else if (!first_byte_valid) begin
                first_byte <= camera_data_d;
                first_byte_valid <= 1'b1;
            end else begin
                // Raw reference word is {first_byte, camera_data_d}; the
                // official demo then applies {raw[4:0],raw[10:5],raw[15:11]}.
                pixel_rgb565 <= {
                    camera_data_d[4:0],
                    first_byte[2:0],
                    camera_data_d[7:5],
                    first_byte[7:3]
                };
                pixel_valid <= 1'b1;
                first_byte_valid <= 1'b0;
            end
        end
    end
endmodule
