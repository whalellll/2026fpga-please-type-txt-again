`timescale 1ns/1ps

// Depth-16 dual-clock FIFO.  Only Gray-coded pointers cross domains.  The
// payload RAM entry is written before its pointer can become visible through
// the two destination synchronizer stages, and remains unchanged until read.
// Both pointer domains are reset together by the SoC's board/PLL reset.
module axi_async_fifo #(
    parameter integer WIDTH = 1
)(
    input wire wr_clk,
    input wire wr_resetn,
    input wire [WIDTH-1:0] wr_data,
    input wire wr_valid,
    output wire wr_ready,
    input wire rd_clk,
    input wire rd_resetn,
    output wire [WIDTH-1:0] rd_data,
    output wire rd_valid,
    input wire rd_ready
);
    reg [WIDTH-1:0] storage [0:15];
    reg [4:0] wr_bin, wr_gray, rd_bin, rd_gray;
    (* ASYNC_REG = "TRUE" *) reg [4:0] rd_gray_wr1 /* synthesis syn_preserve=1 */;
    (* ASYNC_REG = "TRUE" *) reg [4:0] rd_gray_wr2 /* synthesis syn_preserve=1 */;
    (* ASYNC_REG = "TRUE" *) reg [4:0] wr_gray_rd1 /* synthesis syn_preserve=1 */;
    (* ASYNC_REG = "TRUE" *) reg [4:0] wr_gray_rd2 /* synthesis syn_preserve=1 */;

    wire full = wr_gray == {~rd_gray_wr2[4:3], rd_gray_wr2[2:0]};
    wire empty = rd_gray == wr_gray_rd2;
    assign wr_ready = wr_resetn && !full;
    assign rd_valid = rd_resetn && !empty;
    assign rd_data = storage[rd_bin[3:0]];
    wire wr_fire = wr_valid && wr_ready;
    wire rd_fire = rd_valid && rd_ready;
    wire [4:0] wr_bin_next = wr_bin + {4'b0, wr_fire};
    wire [4:0] rd_bin_next = rd_bin + {4'b0, rd_fire};

    always @(posedge wr_clk or negedge wr_resetn) begin
        if (!wr_resetn) begin
            wr_bin <= 5'b0;
            wr_gray <= 5'b0;
            rd_gray_wr1 <= 5'b0;
            rd_gray_wr2 <= 5'b0;
        end else begin
            rd_gray_wr1 <= rd_gray;
            rd_gray_wr2 <= rd_gray_wr1;
            if (wr_fire) begin
                storage[wr_bin[3:0]] <= wr_data;
                wr_bin <= wr_bin_next;
                wr_gray <= (wr_bin_next >> 1) ^ wr_bin_next;
            end
        end
    end

    always @(posedge rd_clk or negedge rd_resetn) begin
        if (!rd_resetn) begin
            rd_bin <= 5'b0;
            rd_gray <= 5'b0;
            wr_gray_rd1 <= 5'b0;
            wr_gray_rd2 <= 5'b0;
        end else begin
            wr_gray_rd1 <= wr_gray;
            wr_gray_rd2 <= wr_gray_rd1;
            if (rd_fire) begin
                rd_bin <= rd_bin_next;
                rd_gray <= (rd_bin_next >> 1) ^ rd_bin_next;
            end
        end
    end
endmodule

// The five AXI channels are independent.  Each 16-entry FIFO can hold a full
// eight-beat cache-line burst while the other channels make progress.  The
// system-side CLINT router and crossbar retain their one-read/one-write
// outstanding limit, so no reordering beyond the existing contract is added.
module axi_cpu_sys_cdc(
    input wire cpu_clk,
    input wire cpu_resetn,
    input wire sys_clk,
    input wire sys_resetn,
    input wire [57:0] s_ar_payload,
    input wire s_arvalid,
    output wire s_arready,
    output wire [57:0] m_ar_payload,
    output wire m_arvalid,
    input wire m_arready,
    input wire [57:0] s_aw_payload,
    input wire s_awvalid,
    output wire s_awready,
    output wire [57:0] m_aw_payload,
    output wire m_awvalid,
    input wire m_awready,
    input wire [40:0] s_w_payload,
    input wire s_wvalid,
    output wire s_wready,
    output wire [40:0] m_w_payload,
    output wire m_wvalid,
    input wire m_wready,
    input wire [38:0] m_r_payload,
    input wire m_rvalid,
    output wire m_rready,
    output wire [38:0] s_r_payload,
    output wire s_rvalid,
    input wire s_rready,
    input wire [5:0] m_b_payload,
    input wire m_bvalid,
    output wire m_bready,
    output wire [5:0] s_b_payload,
    output wire s_bvalid,
    input wire s_bready
);
    // Both resets assert asynchronously from the same board/PLL condition.
    // Peer-ready is synchronized before either AXI side is allowed to run.
    (* ASYNC_REG = "TRUE" *) reg [1:0] sys_ready_cpu /* synthesis syn_preserve=1 */;
    (* ASYNC_REG = "TRUE" *) reg [1:0] cpu_ready_sys /* synthesis syn_preserve=1 */;
    always @(posedge cpu_clk or negedge cpu_resetn) begin
        if (!cpu_resetn) sys_ready_cpu <= 2'b0;
        else sys_ready_cpu <= {sys_ready_cpu[0], sys_resetn};
    end
    always @(posedge sys_clk or negedge sys_resetn) begin
        if (!sys_resetn) cpu_ready_sys <= 2'b0;
        else cpu_ready_sys <= {cpu_ready_sys[0], cpu_resetn};
    end
    wire cpu_active = cpu_resetn && sys_ready_cpu[1];
    wire sys_active = sys_resetn && cpu_ready_sys[1];
    wire ar_wr_ready, aw_wr_ready, w_wr_ready, r_wr_ready, b_wr_ready;
    wire ar_rd_valid, aw_rd_valid, w_rd_valid, r_rd_valid, b_rd_valid;

    assign s_arready = cpu_active && ar_wr_ready;
    assign m_arvalid = sys_active && ar_rd_valid;
    axi_async_fifo #(.WIDTH(58)) u_ar_fifo(
        .wr_clk(cpu_clk), .wr_resetn(cpu_resetn), .wr_data(s_ar_payload),
        .wr_valid(s_arvalid && cpu_active), .wr_ready(ar_wr_ready),
        .rd_clk(sys_clk), .rd_resetn(sys_resetn), .rd_data(m_ar_payload),
        .rd_valid(ar_rd_valid), .rd_ready(m_arready && sys_active));

    assign s_awready = cpu_active && aw_wr_ready;
    assign m_awvalid = sys_active && aw_rd_valid;
    axi_async_fifo #(.WIDTH(58)) u_aw_fifo(
        .wr_clk(cpu_clk), .wr_resetn(cpu_resetn), .wr_data(s_aw_payload),
        .wr_valid(s_awvalid && cpu_active), .wr_ready(aw_wr_ready),
        .rd_clk(sys_clk), .rd_resetn(sys_resetn), .rd_data(m_aw_payload),
        .rd_valid(aw_rd_valid), .rd_ready(m_awready && sys_active));

    assign s_wready = cpu_active && w_wr_ready;
    assign m_wvalid = sys_active && w_rd_valid;
    axi_async_fifo #(.WIDTH(41)) u_w_fifo(
        .wr_clk(cpu_clk), .wr_resetn(cpu_resetn), .wr_data(s_w_payload),
        .wr_valid(s_wvalid && cpu_active), .wr_ready(w_wr_ready),
        .rd_clk(sys_clk), .rd_resetn(sys_resetn), .rd_data(m_w_payload),
        .rd_valid(w_rd_valid), .rd_ready(m_wready && sys_active));

    assign m_rready = sys_active && r_wr_ready;
    assign s_rvalid = cpu_active && r_rd_valid;
    axi_async_fifo #(.WIDTH(39)) u_r_fifo(
        .wr_clk(sys_clk), .wr_resetn(sys_resetn), .wr_data(m_r_payload),
        .wr_valid(m_rvalid && sys_active), .wr_ready(r_wr_ready),
        .rd_clk(cpu_clk), .rd_resetn(cpu_resetn), .rd_data(s_r_payload),
        .rd_valid(r_rd_valid), .rd_ready(s_rready && cpu_active));

    assign m_bready = sys_active && b_wr_ready;
    assign s_bvalid = cpu_active && b_rd_valid;
    axi_async_fifo #(.WIDTH(6)) u_b_fifo(
        .wr_clk(sys_clk), .wr_resetn(sys_resetn), .wr_data(m_b_payload),
        .wr_valid(m_bvalid && sys_active), .wr_ready(b_wr_ready),
        .rd_clk(cpu_clk), .rd_resetn(cpu_resetn), .rd_data(s_b_payload),
        .rd_valid(b_rd_valid), .rd_ready(s_bready && cpu_active));
endmodule
