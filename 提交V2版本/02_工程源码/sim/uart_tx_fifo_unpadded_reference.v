// Test-only frozen TX reference from 0b771c84c2246367eb459ba9fbcdcc415c4c396f
// Original complete UART source SHA256: 489a83e1c5d12f01d203acfbd8584f54e48c92b31427364ff1705825ec015fbc
// TX body is unchanged except the module name. Do not follow DUT edits.
`timescale 1ns / 1ps

// ============================================================
// uart_tx_fifo 模块（带 FIFO 缓冲的 UART 发送器）
// ------------------------------------------------------------
// - BAUD_DIV=234 时 27 MHz 下波特率 115384（偏差 0.16%，
//   常见 USB 转串口均可容忍）。
// ============================================================
module uart_tx_fifo_unpadded_reference #(
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
                fifo[wr_ptr] <= push_data;
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
