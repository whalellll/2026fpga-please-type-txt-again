`timescale 1ns / 1ps

// TX-only bring-up for the MS7210 HDMI transmitter.
//
// The reference ms72xx_ctl initialises the MS7200 (HDMI receiver, 0x56)
// FIRST and only starts the MS7210 (transmitter, 0xB2) after the receiver
// reports init_over_rx.  The receiver FSM only finishes when it detects an
// incoming HDMI signal (frequency-status reads in STA_RD), so without an
// HDMI input cable the transmitter is never configured and the screen
// stays black.
//
// soc_video generates its own video and never uses the receiver, so this
// module configures ONLY the transmitter: ms7210_ctl drives a dedicated
// iic_dri at device id 0xB2.  The MS7200 simply stays unconfigured on the
// shared bus (I2C is address-multiplexed; it never ACKs 0xB2 traffic).
//
// I2C bit rate 200 kHz - the rate the 2_10_hdmi_loop reference design
// actually runs at (its 5 MHz cfg_clk divided by CLK_DIV 25).  T_WR=2
// gives the 2 us inter-write delay of that demo.
module ms72xx_tx_only #(
    parameter integer CLK_FRE = 74_250_000
)(
    input  wire clk,
    input  wire rst_n,        // already-deglitched reset (self-synchronised inside)
    output wire init_over,    // MS7210 configuration sequence finished
    output wire iic_scl,
    inout  wire iic_sda,
    output wire busy_stat     // high while an I2C transaction is in flight
);

    // Reset synchroniser (two-stage) as in the reference module.
    reg rstn_t1, rstn_t2;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rstn_t1 <= 1'b0;
            rstn_t2 <= 1'b0;
        end else begin
            rstn_t1 <= 1'b1;
            rstn_t2 <= rstn_t1;
        end
    end
    wire rstn = rstn_t2;

    // MS7210 control FSM (reference module, unmodified).
    wire        iic_trig;
    wire        w_r;
    wire [15:0] addr;
    wire [ 7:0] data_in;
    wire        busy;
    wire [ 7:0] data_out;
    wire        byte_over;

    ms7210_ctl u_ms7210_ctl (
        .clk       (clk),
        .rstn      (rstn),
        .init_over (init_over),
        .device_id (),
        .iic_trig  (iic_trig),
        .w_r       (w_r),
        .addr      (addr),
        .data_in   (data_in),
        .busy      (busy),
        .data_out  (data_out),
        .byte_over (byte_over)
    );

    wire        sda_in;
    wire        sda_out;
    wire        sda_out_en;

    iic_dri #(
        .CLK_FRE  (CLK_FRE),
        .IIC_FREQ (20'd200_000),
        .T_WR     (10'd2),
        .ADDR_BYTE(2'd2),
        .LEN_WIDTH(8'd3),
        .DATA_BYTE(2'd1)
    ) u_iic_dri (
        .clk       (clk),
        .rstn      (rstn),
        .device_id (8'hB2),     // MS7210 I2C address (board manual)
        .pluse     (iic_trig),
        .w_r       (w_r),
        .byte_len  (4'd1),
        .addr      (addr),
        .data_in   (data_in),
        .busy      (busy),
        .byte_over (byte_over),
        .data_out  (data_out),
        .scl       (iic_scl),
        .sda_in    (sda_in),
        .sda_out   (sda_out),
        .sda_out_en(sda_out_en)
    );

    assign iic_sda = sda_out_en ? sda_out : 1'bz;
    assign sda_in  = iic_sda;
    assign busy_stat = busy;

endmodule
