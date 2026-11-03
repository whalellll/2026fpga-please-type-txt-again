`timescale 1ns / 1ps

// ============================================================
// uart_tx_fifo 模块（带 FIFO 缓冲的 UART 发送器）
// ------------------------------------------------------------
// - BAUD_DIV=234 时 27 MHz 下波特率 115384（偏差 0.16%，
//   常见 USB 转串口均可容忍）。
// ============================================================
module uart_tx_fifo #(
    parameter integer BAUD_DIV = 234,
    parameter integer FIFO_DEPTH = 16,
    parameter integer PTR_W = 4
)(
    input  wire       clk,
    input  wire       resetn,
    input  wire       push,
    input  wire [7:0] push_data,
    output wire       full,
    output wire       empty,
    output wire       idle,
    output reg        tx
);

    reg [7:0] fifo [0:FIFO_DEPTH-1];
    reg [PTR_W-1:0] wr_ptr;
    reg [PTR_W-1:0] rd_ptr;
    reg [PTR_W:0] count;

    wire [PTR_W-1:0] fifo_write_address;
`ifdef SYNTHESIS
    // Retain one combinational identity LUT per two write-address bits.
    // The div15 control run exposed a zero-logic FF-to-LUTRAM WADDR hold
    // path.  This is the same preserved dual-output LUT used by the SoC's
    // ICache/MAC hold pads; it adds no register, cycle or address transform.
    localparam integer PAD_ADDR_W = 2 * ((PTR_W + 1) / 2);
    wire [PAD_ADDR_W-1:0] pad_address_in;
    wire [PAD_ADDR_W-1:0] pad_address_out;
    assign pad_address_in = {{(PAD_ADDR_W-PTR_W){1'b0}}, wr_ptr};
    genvar address_pair;
    generate
        for (address_pair = 0; address_pair < (PTR_W + 1) / 2;
             address_pair = address_pair + 1) begin : write_address_pad
            (* PAP_DONT_TOUCH *) GTP_LUT6D #(.INIT(64'hCCCCCCCC_AAAAAAAA)) u_hold_dual_lut (
                .I0(pad_address_in[2*address_pair]),
                .I1(pad_address_in[2*address_pair+1]),
                .I2(1'b0), .I3(1'b0), .I4(1'b0), .I5(1'b1),
                .Z5(pad_address_out[2*address_pair]),
                .Z(pad_address_out[2*address_pair+1])
            );
        end
    endgenerate
    assign fifo_write_address = pad_address_out[PTR_W-1:0];
`else
    assign fifo_write_address = wr_ptr;
`endif

    reg [9:0] tx_shift;
    reg [3:0] tx_bit;
    reg [15:0] baud_count;
    reg tx_busy;

    wire pop = !tx_busy && (count != 0);

    assign full  = (count == FIFO_DEPTH);
    assign empty = (count == 0);
    assign idle  = !tx_busy && empty;

    always @(posedge clk) begin
        if (!resetn) begin
            wr_ptr     <= {PTR_W{1'b0}};
            rd_ptr     <= {PTR_W{1'b0}};
            count      <= {(PTR_W+1){1'b0}};
            tx_shift   <= 10'h3ff;
            tx_bit     <= 4'd0;
            baud_count <= 16'd0;
            tx_busy    <= 1'b0;
            tx         <= 1'b1;
        end else begin
            if (push && !full) begin
                fifo[fifo_write_address] <= push_data;
                wr_ptr <= wr_ptr + {{(PTR_W-1){1'b0}}, 1'b1};
            end

            if (pop) begin
                tx_shift   <= {1'b1, fifo[rd_ptr], 1'b0};
                rd_ptr     <= rd_ptr + {{(PTR_W-1){1'b0}}, 1'b1};
                tx_bit     <= 4'd0;
                baud_count <= BAUD_DIV - 1;
                tx_busy    <= 1'b1;
                tx         <= 1'b0;
            end else if (tx_busy) begin
                if (baud_count == 0) begin
                    baud_count <= BAUD_DIV - 1;
                    if (tx_bit == 4'd9) begin
                        tx_busy <= 1'b0;
                        tx      <= 1'b1;
                    end else begin
                        tx_bit <= tx_bit + 4'd1;
                        tx     <= tx_shift[tx_bit + 4'd1];
                    end
                end else begin
                    baud_count <= baud_count - 16'd1;
                end
            end

            case ({push && !full, pop})
                2'b10: count <= count + {{PTR_W{1'b0}}, 1'b1};
                2'b01: count <= count - {{PTR_W{1'b0}}, 1'b1};
                default: count <= count;
            endcase
        end
    end

endmodule

// 8-N-1 UART receiver with a small byte FIFO.  The asynchronous RX input is
// synchronized before it is sampled.  A start bit is checked at half a bit,
// then the eight data bits and stop bit are sampled one BAUD_DIV apart.
//
// "data" is a non-destructive view of the oldest byte.  The AXI wrapper only
// asserts pop after the corresponding RBR read response is accepted, so AXI
// backpressure cannot consume a byte early.
module uart_rx_fifo #(
    parameter integer BAUD_DIV = 234,
    parameter integer FIFO_DEPTH = 16,
    parameter integer PTR_W = 4
)(
    input  wire       clk,
    input  wire       resetn,
    input  wire       rx,
    input  wire       pop,
    output wire [7:0] data,
    output wire       full,
    output wire       empty
);

    localparam integer HALF_BAUD_DIV = BAUD_DIV / 2;

    reg [7:0] fifo [0:FIFO_DEPTH-1];
    reg [PTR_W-1:0] wr_ptr;
    reg [PTR_W-1:0] rd_ptr;
    reg [PTR_W:0] count;

    reg rx_meta;
    reg rx_sync;
    reg rx_busy;
    reg [3:0] rx_bit;
    reg [15:0] baud_count;
    reg [7:0] rx_shift;

    wire stop_sample = rx_busy && (baud_count == 0) && (rx_bit == 4'd9);
    wire do_pop = pop && (count != 0);
    // If the FIFO is full, a simultaneous pop makes room for the new byte.
    wire do_push = stop_sample && rx_sync && ((count != FIFO_DEPTH) || do_pop);

    assign data  = (count != 0) ? fifo[rd_ptr] : 8'h00;
    assign full  = (count == FIFO_DEPTH);
    assign empty = (count == 0);

    always @(posedge clk) begin
        if (!resetn) begin
            wr_ptr     <= {PTR_W{1'b0}};
            rd_ptr     <= {PTR_W{1'b0}};
            count      <= {(PTR_W+1){1'b0}};
            rx_meta    <= 1'b1;
            rx_sync    <= 1'b1;
            rx_busy    <= 1'b0;
            rx_bit     <= 4'd0;
            baud_count <= 16'd0;
            rx_shift   <= 8'h00;
        end else begin
            rx_meta <= rx;
            rx_sync <= rx_meta;

            if (!rx_busy) begin
                if (!rx_sync) begin
                    rx_busy    <= 1'b1;
                    rx_bit     <= 4'd0;
                    baud_count <= HALF_BAUD_DIV - 1;
                end
            end else if (baud_count != 0) begin
                baud_count <= baud_count - 16'd1;
            end else if (rx_bit == 4'd0) begin
                // Reject a short low-going glitch instead of treating it as
                // the start of a character.
                if (!rx_sync) begin
                    rx_bit     <= 4'd1;
                    baud_count <= BAUD_DIV - 1;
                end else begin
                    rx_busy <= 1'b0;
                end
            end else if (rx_bit <= 4'd8) begin
                rx_shift[rx_bit - 1'b1] <= rx_sync;
                rx_bit                  <= rx_bit + 4'd1;
                baud_count              <= BAUD_DIV - 1;
            end else begin
                // rx_bit==9: do_push below accepts only a valid high stop bit.
                rx_busy <= 1'b0;
            end

            if (do_push) begin
                fifo[wr_ptr] <= rx_shift;
                wr_ptr       <= wr_ptr + {{(PTR_W-1){1'b0}}, 1'b1};
            end
            if (do_pop)
                rd_ptr <= rd_ptr + {{(PTR_W-1){1'b0}}, 1'b1};

            case ({do_push, do_pop})
                2'b10: count <= count + {{PTR_W{1'b0}}, 1'b1};
                2'b01: count <= count - {{PTR_W{1'b0}}, 1'b1};
                default: count <= count;
            endcase
        end
    end

endmodule
