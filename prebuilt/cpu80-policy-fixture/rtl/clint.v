`timescale 1ns/1ps

// Single-hart Core Local Interruptor.
// Address map follows the conventional RISC-V CLINT layout:
//   BASE + 0x0000 : msip[0]
//   BASE + 0x4000 : mtimecmp[31:0]
//   BASE + 0x4004 : mtimecmp[63:32]
//   BASE + 0xbff8 : mtime[31:0]
//   BASE + 0xbffc : mtime[63:32]
module clint #(
    parameter [31:0] BASE = 32'h0200_0000
)(
    input  wire        clk,
    input  wire        resetn,
    input  wire        cyc,
    input  wire        stb,
    input  wire        we,
    input  wire [31:0] addr,
    input  wire [31:0] wdata,
    input  wire [3:0]  sel,
    output reg  [31:0] rdata,
    output reg         ack,
    output wire        err,
    output wire        timer_irq,
    output wire        software_irq
);
    reg        msip;
    reg [63:0] mtime;
    reg [63:0] mtimecmp;

    wire request = cyc && stb;
    wire accept  = request && !ack;
    wire [31:0] offset = addr - BASE;

    wire [31:0] byte_write_mask = {
        {8{sel[3]}}, {8{sel[2]}}, {8{sel[1]}}, {8{sel[0]}}
    };
    wire [31:0] merged_mtimecmp_lo =
        (mtimecmp[31:0] & ~byte_write_mask) | (wdata & byte_write_mask);
    wire [31:0] merged_mtimecmp_hi =
        (mtimecmp[63:32] & ~byte_write_mask) | (wdata & byte_write_mask);
    wire [31:0] merged_mtime_lo =
        (mtime[31:0] & ~byte_write_mask) | (wdata & byte_write_mask);
    wire [31:0] merged_mtime_hi =
        (mtime[63:32] & ~byte_write_mask) | (wdata & byte_write_mask);

    always @(*) begin
        case (offset)
            32'h0000_0000: rdata = {31'b0, msip};
            32'h0000_4000: rdata = mtimecmp[31:0];
            32'h0000_4004: rdata = mtimecmp[63:32];
            32'h0000_bff8: rdata = mtime[31:0];
            32'h0000_bffc: rdata = mtime[63:32];
            default:       rdata = 32'b0;
        endcase
    end

    always @(posedge clk) begin
        if (!resetn) begin
            ack      <= 1'b0;
            msip     <= 1'b0;
            mtime    <= 64'b0;
            mtimecmp <= 64'hffff_ffff_ffff_ffff;
        end else begin
            ack <= accept;

            if (accept && we && (offset == 32'h0000_0000) && sel[0])
                msip <= wdata[0];

            if (accept && we && (offset == 32'h0000_4000))
                mtimecmp[31:0] <= merged_mtimecmp_lo;
            if (accept && we && (offset == 32'h0000_4004))
                mtimecmp[63:32] <= merged_mtimecmp_hi;

            if (accept && we && (|sel) && (offset == 32'h0000_bff8))
                mtime <= {mtime[63:32], merged_mtime_lo};
            else if (accept && we && (|sel) && (offset == 32'h0000_bffc))
                mtime <= {merged_mtime_hi, mtime[31:0]};
            else
                mtime <= mtime + 64'd1;
        end
    end

    assign timer_irq    = (mtime >= mtimecmp);
    assign software_irq = msip;
    assign err          = 1'b0;
endmodule
