`timescale 1ns/1ps

// Programs one OV5640 with the register sequence from soc_shexiantou3.
// Dropping camera_resetn aborts a transaction and clears all state, allowing
// camera_enable in the parent block to restart initialization cleanly.
module ov5640_register_init #(
    parameter [15:0] SCCB_DIVIDER_MAX = 16'd1249,
    parameter [8:0]  LAST_REGISTER_INDEX = 9'd356
)(
    input  wire       clk_25m,
    input  wire       camera_resetn,
    input  wire       initial_enable,
    output wire       init_done,
    output reg        nack_seen,
    output wire       sccb_scl,
    inout  wire       sccb_sda,
    output wire [8:0] register_index
);
    reg [15:0] divider_count;
    reg sccb_clock;
    reg [1:0] config_step;
    reg [8:0] index_reg;
    reg [31:0] write_data;
    reg start;
    reg init_done_reg;

    wire [23:0] register_data;
    wire transfer_done;
    wire transaction_ack_error;

    assign init_done = init_done_reg;
    assign register_index = index_reg;

    ov5640_register_table register_table_inst (
        .register_index(index_reg),
        .register_data(register_data)
    );

    ov5640_sccb_write sccb_write_inst (
        .clock_i2c(sccb_clock),
        .camera_resetn(camera_resetn),
        .write_data(write_data),
        .start(start),
        .ack_error(transaction_ack_error),
        .transfer_done(transfer_done),
        .i2c_scl(sccb_scl),
        .i2c_sda(sccb_sda)
    );

    // The reference divides 25 MHz by 1250 per half-cycle.  Keeping the
    // divider parameterized makes the exact state sequence practical to test.
    always @(posedge clk_25m or negedge camera_resetn) begin
        if (!camera_resetn) begin
            divider_count <= 16'd0;
            sccb_clock <= 1'b0;
        end else if (divider_count < SCCB_DIVIDER_MAX) begin
            divider_count <= divider_count + 1'b1;
        end else begin
            divider_count <= 16'd0;
            sccb_clock <= ~sccb_clock;
        end
    end

    always @(posedge sccb_clock or negedge camera_resetn) begin
        if (!camera_resetn) begin
            config_step <= 2'd0;
            index_reg <= 9'd0;
            write_data <= 32'd0;
            start <= 1'b0;
            init_done_reg <= 1'b0;
            nack_seen <= 1'b0;
        end else if (!initial_enable) begin
            config_step <= 2'd0;
            index_reg <= 9'd0;
            write_data <= 32'd0;
            start <= 1'b0;
            init_done_reg <= 1'b0;
            nack_seen <= 1'b0;
        end else if (!init_done_reg) begin
            if (index_reg <= LAST_REGISTER_INDEX) begin
                case (config_step)
                    2'd0: begin
                        write_data <= {8'h78, register_data};
                        start <= 1'b1;
                        config_step <= 2'd1;
                    end
                    2'd1: begin
                        if (transfer_done) begin
                            start <= 1'b0;
                            config_step <= 2'd2;
                            if (transaction_ack_error)
                                nack_seen <= 1'b1;
                        end
                    end
                    2'd2: begin
                        index_reg <= index_reg + 1'b1;
                        config_step <= 2'd0;
                    end
                    default: begin
                        config_step <= 2'd0;
                        start <= 1'b0;
                    end
                endcase
            end else begin
                start <= 1'b0;
                init_done_reg <= 1'b1;
            end
        end
    end
endmodule
