`timescale 1ns/1ps

// Two 32-bit AXI masters to one slave. Master 0 is the CPU and retains its
// AXI IDs; master 1 is the MAC DMA and uses a fixed ID. Read and write
// ownership are independent and stay locked until the matching response.
module axi_2x1_arbiter #(
    parameter [3:0] MASTER1_ID = 4'hf
)(
    input wire clk, input wire resetn,

    input wire [3:0] s0_arid, input wire [31:0] s0_araddr,
    input wire [7:0] s0_arlen, input wire [2:0] s0_arsize,
    input wire [1:0] s0_arburst, input wire s0_arvalid,
    output wire s0_arready, output wire [3:0] s0_rid,
    output wire [31:0] s0_rdata, output wire [1:0] s0_rresp,
    output wire s0_rlast, output wire s0_rvalid, input wire s0_rready,
    input wire [3:0] s0_awid, input wire [31:0] s0_awaddr,
    input wire [7:0] s0_awlen, input wire [2:0] s0_awsize,
    input wire [1:0] s0_awburst, input wire s0_awvalid,
    output wire s0_awready, input wire [3:0] s0_wid,
    input wire [31:0] s0_wdata, input wire [3:0] s0_wstrb,
    input wire s0_wlast, input wire s0_wvalid, output wire s0_wready,
    output wire [3:0] s0_bid, output wire [1:0] s0_bresp,
    output wire s0_bvalid, input wire s0_bready,

    input wire [31:0] s1_araddr, input wire [7:0] s1_arlen,
    input wire [2:0] s1_arsize, input wire [1:0] s1_arburst,
    input wire s1_arvalid, output wire s1_arready,
    output wire [31:0] s1_rdata, output wire [1:0] s1_rresp,
    output wire s1_rlast, output wire s1_rvalid, input wire s1_rready,
    input wire [31:0] s1_awaddr, input wire [7:0] s1_awlen,
    input wire [2:0] s1_awsize, input wire [1:0] s1_awburst,
    input wire s1_awvalid, output wire s1_awready,
    input wire [31:0] s1_wdata, input wire [3:0] s1_wstrb,
    input wire s1_wlast, input wire s1_wvalid, output wire s1_wready,
    output wire [1:0] s1_bresp, output wire s1_bvalid,
    input wire s1_bready,

    output wire [3:0] m_arid, output wire [31:0] m_araddr,
    output wire [7:0] m_arlen, output wire [2:0] m_arsize,
    output wire [1:0] m_arburst, output wire m_arvalid,
    input wire m_arready, input wire [3:0] m_rid,
    input wire [31:0] m_rdata, input wire [1:0] m_rresp,
    input wire m_rlast, input wire m_rvalid, output wire m_rready,
    output wire [3:0] m_awid, output wire [31:0] m_awaddr,
    output wire [7:0] m_awlen, output wire [2:0] m_awsize,
    output wire [1:0] m_awburst, output wire m_awvalid,
    input wire m_awready, output wire [3:0] m_wid,
    output wire [31:0] m_wdata, output wire [3:0] m_wstrb,
    output wire m_wlast, output wire m_wvalid, input wire m_wready,
    input wire [3:0] m_bid, input wire [1:0] m_bresp,
    input wire m_bvalid, output wire m_bready
);
    reg rd_active, rd_owner, rd_last_owner;
    reg wr_active, wr_owner, wr_last_owner;

    wire rd_pick1 = s1_arvalid && (!s0_arvalid || !rd_last_owner);
    wire rd_pick0 = s0_arvalid && !rd_pick1;
    wire wr_pick1 = s1_awvalid && (!s0_awvalid || !wr_last_owner);
    wire wr_pick0 = s0_awvalid && !wr_pick1;

    assign m_arid = rd_pick1 ? MASTER1_ID : s0_arid;
    assign m_araddr = rd_pick1 ? s1_araddr : s0_araddr;
    assign m_arlen = rd_pick1 ? s1_arlen : s0_arlen;
    assign m_arsize = rd_pick1 ? s1_arsize : s0_arsize;
    assign m_arburst = rd_pick1 ? s1_arburst : s0_arburst;
    assign m_arvalid = !rd_active && (rd_pick0 || rd_pick1);
    assign s0_arready = !rd_active && rd_pick0 && m_arready;
    assign s1_arready = !rd_active && rd_pick1 && m_arready;

    assign s0_rid = m_rid;
    assign s0_rdata = m_rdata;
    assign s0_rresp = m_rresp;
    assign s0_rlast = m_rlast;
    assign s0_rvalid = rd_active && !rd_owner && m_rvalid;
    assign s1_rdata = m_rdata;
    assign s1_rresp = m_rresp;
    assign s1_rlast = m_rlast;
    assign s1_rvalid = rd_active && rd_owner && m_rvalid;
    assign m_rready = rd_active && (rd_owner ? s1_rready : s0_rready);

    assign m_awid = wr_pick1 ? MASTER1_ID : s0_awid;
    assign m_awaddr = wr_pick1 ? s1_awaddr : s0_awaddr;
    assign m_awlen = wr_pick1 ? s1_awlen : s0_awlen;
    assign m_awsize = wr_pick1 ? s1_awsize : s0_awsize;
    assign m_awburst = wr_pick1 ? s1_awburst : s0_awburst;
    assign m_awvalid = !wr_active && (wr_pick0 || wr_pick1);
    assign s0_awready = !wr_active && wr_pick0 && m_awready;
    assign s1_awready = !wr_active && wr_pick1 && m_awready;

    assign m_wid = wr_owner ? MASTER1_ID : s0_wid;
    assign m_wdata = wr_owner ? s1_wdata : s0_wdata;
    assign m_wstrb = wr_owner ? s1_wstrb : s0_wstrb;
    assign m_wlast = wr_owner ? s1_wlast : s0_wlast;
    assign m_wvalid = wr_active && (wr_owner ? s1_wvalid : s0_wvalid);
    assign s0_wready = wr_active && !wr_owner && m_wready;
    assign s1_wready = wr_active && wr_owner && m_wready;

    assign s0_bid = m_bid;
    assign s0_bresp = m_bresp;
    assign s0_bvalid = wr_active && !wr_owner && m_bvalid;
    assign s1_bresp = m_bresp;
    assign s1_bvalid = wr_active && wr_owner && m_bvalid;
    assign m_bready = wr_active && (wr_owner ? s1_bready : s0_bready);

    always @(posedge clk) begin
        if (!resetn) begin
            rd_active <= 1'b0;
            rd_owner <= 1'b0;
            rd_last_owner <= 1'b1;
            wr_active <= 1'b0;
            wr_owner <= 1'b0;
            wr_last_owner <= 1'b1;
        end else begin
            if (!rd_active && m_arvalid && m_arready) begin
                rd_active <= 1'b1;
                rd_owner <= rd_pick1;
                rd_last_owner <= rd_pick1;
            end
            if (rd_active && m_rvalid && m_rready && m_rlast)
                rd_active <= 1'b0;

            if (!wr_active && m_awvalid && m_awready) begin
                wr_active <= 1'b1;
                wr_owner <= wr_pick1;
                wr_last_owner <= wr_pick1;
            end
            if (wr_active && m_bvalid && m_bready)
                wr_active <= 1'b0;
        end
    end
endmodule
