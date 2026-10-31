`timescale 1ns/1ps

// One four-byte SCCB write transaction.  This intentionally retains the
// working soc_shexiantou3 electrical behavior: SCL is push-pull, while SDA is
// open-drain (drive low or release to the camera module's pull-up).
module ov5640_sccb_write(
    input  wire        clock_i2c,
    input  wire        camera_resetn,
    input  wire [31:0] write_data,
    input  wire        start,
    output wire        ack_error,
    output reg         transfer_done,
    output wire        i2c_scl,
    inout  wire        i2c_sda
);
    reg [5:0] cycle_count;
    reg sda_release;
    reg scl_idle_high;
    reg ack1;
    reg ack2;
    reg ack3;

    assign ack_error = ack1 | ack2 | ack3;
    assign i2c_scl = scl_idle_high |
        (((cycle_count >= 6'd4) && (cycle_count <= 6'd39)) ?
            ~clock_i2c : 1'b0);
    assign i2c_sda = sda_release ? 1'bz : 1'b0;

    always @(posedge clock_i2c or negedge camera_resetn) begin
        if (!camera_resetn)
            cycle_count <= 6'h3f;
        else if (!start)
            cycle_count <= 6'd0;
        else if (cycle_count < 6'h3f)
            cycle_count <= cycle_count + 1'b1;
    end

    always @(posedge clock_i2c or negedge camera_resetn) begin
        if (!camera_resetn) begin
            transfer_done <= 1'b0;
            ack1 <= 1'b1;
            ack2 <= 1'b1;
            ack3 <= 1'b1;
            scl_idle_high <= 1'b1;
            sda_release <= 1'b1;
        end else begin
            case (cycle_count)
                6'd0: begin
                    ack1 <= 1'b1;
                    ack2 <= 1'b1;
                    ack3 <= 1'b1;
                    transfer_done <= 1'b0;
                    scl_idle_high <= 1'b1;
                    sda_release <= 1'b1;
                end
                6'd1:  sda_release <= 1'b0;
                6'd2:  scl_idle_high <= 1'b0;
                6'd3:  sda_release <= write_data[31];
                6'd4:  sda_release <= write_data[30];
                6'd5:  sda_release <= write_data[29];
                6'd6:  sda_release <= write_data[28];
                6'd7:  sda_release <= write_data[27];
                6'd8:  sda_release <= write_data[26];
                6'd9:  sda_release <= write_data[25];
                6'd10: sda_release <= write_data[24];
                6'd11: sda_release <= 1'b1;
                6'd12: begin
                    sda_release <= write_data[23];
                    ack1 <= i2c_sda;
                end
                6'd13: sda_release <= write_data[22];
                6'd14: sda_release <= write_data[21];
                6'd15: sda_release <= write_data[20];
                6'd16: sda_release <= write_data[19];
                6'd17: sda_release <= write_data[18];
                6'd18: sda_release <= write_data[17];
                6'd19: sda_release <= write_data[16];
                6'd20: sda_release <= 1'b1;
                6'd21: begin
                    sda_release <= write_data[15];
                    ack1 <= i2c_sda;
                end
                6'd22: sda_release <= write_data[14];
                6'd23: sda_release <= write_data[13];
                6'd24: sda_release <= write_data[12];
                6'd25: sda_release <= write_data[11];
                6'd26: sda_release <= write_data[10];
                6'd27: sda_release <= write_data[9];
                6'd28: sda_release <= write_data[8];
                6'd29: sda_release <= 1'b1;
                6'd30: begin
                    sda_release <= write_data[7];
                    ack2 <= i2c_sda;
                end
                6'd31: sda_release <= write_data[6];
                6'd32: sda_release <= write_data[5];
                6'd33: sda_release <= write_data[4];
                6'd34: sda_release <= write_data[3];
                6'd35: sda_release <= write_data[2];
                6'd36: sda_release <= write_data[1];
                6'd37: sda_release <= write_data[0];
                6'd38: sda_release <= 1'b1;
                6'd39: begin
                    ack3 <= i2c_sda;
                    scl_idle_high <= 1'b0;
                    sda_release <= 1'b0;
                end
                6'd40: scl_idle_high <= 1'b1;
                6'd41: begin
                    sda_release <= 1'b1;
                    transfer_done <= 1'b1;
                end
                default: begin
                    transfer_done <= transfer_done;
                end
            endcase
        end
    end
endmodule
