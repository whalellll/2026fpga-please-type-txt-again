`timescale 1ns/1ps

// Fixed-address framebuffer control block.
//
// Software can only select FB0 or FB1; it cannot program an arbitrary DMA
// address.  This makes the 0x1b000000 accelerator aperture unreachable from
// the video DMA even if software writes a malformed control value.
module video_fb_mmio #(
    parameter [31:0] BASE     = 32'h1fe1_1000,
    parameter [31:0] FB0_BASE = 32'h1b20_0000,
    parameter [31:0] FB1_BASE = 32'h1b40_0000
) (
    input  wire        clk,
    input  wire        resetn,
    input  wire [31:0] addr,
    input  wire        wr,
    input  wire [31:0] wdata,
    input  wire [3:0]  wstrb,
    output reg  [31:0] rdata,
    output wire        hit,

    output reg         enable,
    output reg         requested_buffer,
    output reg         clear_underflow_toggle,

    input  wire        active_enable_pix,
    input  wire        active_buffer_pix,
    input  wire        underflow_pix,
    input  wire [31:0] frame_count_pix,
    input  wire [31:0] underflow_count_pix,
    input  wire        dma_busy_ddr,
    input  wire        dma_error_ddr
);
    localparam [31:0] FRAME_BYTES = 32'h001c_2000;
    localparam [31:0] STRIDE      = 32'h0000_0a00;

    reg active_enable_s1, active_enable_s2;
    reg active_buffer_s1, active_buffer_s2;
    reg underflow_s1, underflow_s2;
    reg dma_busy_s1, dma_busy_s2;
    reg dma_error_s1, dma_error_s2;
    reg [31:0] frame_count_s1, frame_count_s2;
    reg [31:0] underflow_count_s1, underflow_count_s2;

    assign hit = (addr >= BASE) && (addr < BASE + 32'h100);

    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            enable                    <= 1'b0;
            requested_buffer          <= 1'b0;
            clear_underflow_toggle    <= 1'b0;
            active_enable_s1          <= 1'b0;
            active_enable_s2          <= 1'b0;
            active_buffer_s1          <= 1'b0;
            active_buffer_s2          <= 1'b0;
            underflow_s1              <= 1'b0;
            underflow_s2              <= 1'b0;
            dma_busy_s1               <= 1'b0;
            dma_busy_s2               <= 1'b0;
            dma_error_s1              <= 1'b0;
            dma_error_s2              <= 1'b0;
            frame_count_s1            <= 32'd0;
            frame_count_s2            <= 32'd0;
            underflow_count_s1        <= 32'd0;
            underflow_count_s2        <= 32'd0;
        end else begin
            active_enable_s1   <= active_enable_pix;
            active_enable_s2   <= active_enable_s1;
            active_buffer_s1   <= active_buffer_pix;
            active_buffer_s2   <= active_buffer_s1;
            underflow_s1       <= underflow_pix;
            underflow_s2       <= underflow_s1;
            dma_busy_s1        <= dma_busy_ddr;
            dma_busy_s2        <= dma_busy_s1;
            dma_error_s1       <= dma_error_ddr;
            dma_error_s2       <= dma_error_s1;
            frame_count_s1     <= frame_count_pix;
            frame_count_s2     <= frame_count_s1;
            underflow_count_s1 <= underflow_count_pix;
            underflow_count_s2 <= underflow_count_s1;

            if (wr && hit && (addr[7:2] == 6'h02) && wstrb[0]) begin
                enable           <= wdata[0];
                requested_buffer <= wdata[1];
                if (wdata[8])
                    clear_underflow_toggle <= ~clear_underflow_toggle;
            end
        end
    end

    always @* begin
        case (addr[7:2])
            6'h00: rdata = 32'h5851_4642; // "XQFB"
            6'h01: rdata = 32'h0001_0000;
            6'h02: rdata = {30'd0, requested_buffer, enable};
            6'h03: rdata = {26'd0, dma_error_s2, dma_busy_s2,
                             underflow_s2, active_buffer_s2,
                             active_enable_s2, enable};
            6'h04: rdata = FB0_BASE;
            6'h05: rdata = FB1_BASE;
            6'h06: rdata = STRIDE;
            6'h07: rdata = {16'd720, 16'd1280};
            6'h08: rdata = FRAME_BYTES;
            6'h09: rdata = frame_count_s2;
            6'h0a: rdata = underflow_count_s2;
            default: rdata = 32'd0;
        endcase
    end
endmodule
