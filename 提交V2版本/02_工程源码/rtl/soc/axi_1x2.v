`timescale 1ns/1ps

// One AXI master to two AXI slaves. DDR occupies 0x0000_0000..0x3fff_ffff.
// 0x8000_0000..0xbfff_ffff is an uncached CPU alias of the same DDR space;
// bit 31 is removed before forwarding. The alias lets software exchange small
// buffers with non-coherent DMA without depending on cache maintenance CSRs.
// Boot BRAM and MMIO apertures take priority over DDR.
// Read and write channels are independently locked until their response ends.
module axi_1x2(
    input wire clk, input wire resetn,
    input wire [3:0] s_arid, input wire [31:0] s_araddr,
    input wire [7:0] s_arlen, input wire [2:0] s_arsize,
    input wire [1:0] s_arburst, input wire [1:0] s_arlock,
    input wire [3:0] s_arcache, input wire [2:0] s_arprot,
    input wire s_arvalid, output wire s_arready,
    output wire [3:0] s_rid, output wire [31:0] s_rdata,
    output wire [1:0] s_rresp, output wire s_rlast,
    output wire s_rvalid, input wire s_rready,
    input wire [3:0] s_awid, input wire [31:0] s_awaddr,
    input wire [7:0] s_awlen, input wire [2:0] s_awsize,
    input wire [1:0] s_awburst, input wire [1:0] s_awlock,
    input wire [3:0] s_awcache, input wire [2:0] s_awprot,
    input wire s_awvalid, output wire s_awready,
    input wire [3:0] s_wid, input wire [31:0] s_wdata,
    input wire [3:0] s_wstrb, input wire s_wlast,
    input wire s_wvalid, output wire s_wready,
    output wire [3:0] s_bid, output wire [1:0] s_bresp,
    output wire s_bvalid, input wire s_bready,

    output wire [3:0] m0_arid, output wire [31:0] m0_araddr,
    output wire [7:0] m0_arlen, output wire [2:0] m0_arsize,
    output wire [1:0] m0_arburst, output wire m0_arvalid,
    input wire m0_arready, input wire [3:0] m0_rid,
    input wire [31:0] m0_rdata, input wire [1:0] m0_rresp,
    input wire m0_rlast, input wire m0_rvalid, output wire m0_rready,
    output wire [3:0] m0_awid, output wire [31:0] m0_awaddr,
    output wire [7:0] m0_awlen, output wire [2:0] m0_awsize,
    output wire [1:0] m0_awburst, output wire m0_awvalid,
    input wire m0_awready, output wire [3:0] m0_wid,
    output wire [31:0] m0_wdata, output wire [3:0] m0_wstrb,
    output wire m0_wlast, output wire m0_wvalid, input wire m0_wready,
    input wire [3:0] m0_bid, input wire [1:0] m0_bresp,
    input wire m0_bvalid, output wire m0_bready,

    output wire [3:0] m1_arid, output wire [31:0] m1_araddr,
    output wire [7:0] m1_arlen, output wire [2:0] m1_arsize,
    output wire [1:0] m1_arburst, output wire m1_arvalid,
    input wire m1_arready, input wire [3:0] m1_rid,
    input wire [31:0] m1_rdata, input wire [1:0] m1_rresp,
    input wire m1_rlast, input wire m1_rvalid, output wire m1_rready,
    output wire [3:0] m1_awid, output wire [31:0] m1_awaddr,
    output wire [7:0] m1_awlen, output wire [2:0] m1_awsize,
    output wire [1:0] m1_awburst, output wire m1_awvalid,
    input wire m1_awready, output wire [3:0] m1_wid,
    output wire [31:0] m1_wdata, output wire [3:0] m1_wstrb,
    output wire m1_wlast, output wire m1_wvalid, input wire m1_wready,
    input wire [3:0] m1_bid, input wire [1:0] m1_bresp,
    input wire m1_bvalid, output wire m1_bready
);
    wire ar_boot = (s_araddr >= 32'h1c00_0000) && (s_araddr < 32'h1c02_0000);
    wire aw_boot = (s_awaddr >= 32'h1c00_0000) && (s_awaddr < 32'h1c02_0000);
    wire ar_mmio = (s_araddr >= 32'h1fe0_0000) && (s_araddr < 32'h1ff0_0000);
    wire aw_mmio = (s_awaddr >= 32'h1fe0_0000) && (s_awaddr < 32'h1ff0_0000);
    wire ar_ddr_alias = s_araddr[31:30] == 2'b10;
    wire aw_ddr_alias = s_awaddr[31:30] == 2'b10;
    wire ar_ddr_now = (((s_araddr[31:30] == 2'b00) && !ar_boot && !ar_mmio) ||
                       ar_ddr_alias);
    wire aw_ddr_now = (((s_awaddr[31:30] == 2'b00) && !aw_boot && !aw_mmio) ||
                       aw_ddr_alias);
    reg rd_busy, rd_ddr, wr_busy, wr_ddr;

    always @(posedge clk) begin
        if (!resetn) begin rd_busy<=0; rd_ddr<=0; wr_busy<=0; wr_ddr<=0; end
        else begin
            if (!rd_busy && s_arvalid && s_arready) begin rd_busy<=1; rd_ddr<=ar_ddr_now; end
            if (rd_busy && s_rvalid && s_rready && s_rlast) rd_busy<=0;
            if (!wr_busy && s_awvalid && s_awready) begin wr_busy<=1; wr_ddr<=aw_ddr_now; end
            if (wr_busy && s_bvalid && s_bready) wr_busy<=0;
        end
    end

    wire rsel = rd_busy ? rd_ddr : ar_ddr_now;
    wire wsel = wr_busy ? wr_ddr : aw_ddr_now;
    assign s_arready = !rd_busy && (rsel ? m0_arready : m1_arready);
    assign s_rid    = rd_ddr ? m0_rid    : m1_rid;
    assign s_rdata  = rd_ddr ? m0_rdata  : m1_rdata;
    assign s_rresp  = rd_ddr ? m0_rresp  : m1_rresp;
    assign s_rlast  = rd_ddr ? m0_rlast  : m1_rlast;
    assign s_rvalid = rd_busy && (rd_ddr ? m0_rvalid : m1_rvalid);
    assign m0_rready = rd_busy && rd_ddr && s_rready;
    assign m1_rready = rd_busy && !rd_ddr && s_rready;
    assign m0_arvalid = !rd_busy && ar_ddr_now && s_arvalid;
    assign m1_arvalid = !rd_busy && !ar_ddr_now && s_arvalid;

    assign s_awready = !wr_busy && (wsel ? m0_awready : m1_awready);
    assign m0_awvalid = !wr_busy && aw_ddr_now && s_awvalid;
    assign m1_awvalid = !wr_busy && !aw_ddr_now && s_awvalid;
    assign m0_wvalid = wr_busy && wr_ddr && s_wvalid;
    assign m1_wvalid = wr_busy && !wr_ddr && s_wvalid;
    assign s_wready = wr_busy && (wr_ddr ? m0_wready : m1_wready);
    assign s_bid    = wr_ddr ? m0_bid    : m1_bid;
    assign s_bresp  = wr_ddr ? m0_bresp  : m1_bresp;
    assign s_bvalid = wr_busy && (wr_ddr ? m0_bvalid : m1_bvalid);
    assign m0_bready = wr_busy && wr_ddr && s_bready;
    assign m1_bready = wr_busy && !wr_ddr && s_bready;

    assign m0_arid=s_arid; assign m1_arid=s_arid;
    assign m0_araddr=ar_ddr_alias?{1'b0,s_araddr[30:0]}:s_araddr;
    assign m1_araddr=s_araddr;
    assign m0_arlen=s_arlen; assign m1_arlen=s_arlen;
    assign m0_arsize=s_arsize; assign m1_arsize=s_arsize;
    assign m0_arburst=s_arburst; assign m1_arburst=s_arburst;
    assign m0_awid=s_awid; assign m1_awid=s_awid;
    assign m0_awaddr=aw_ddr_alias?{1'b0,s_awaddr[30:0]}:s_awaddr;
    assign m1_awaddr=s_awaddr;
    assign m0_awlen=s_awlen; assign m1_awlen=s_awlen;
    assign m0_awsize=s_awsize; assign m1_awsize=s_awsize;
    assign m0_awburst=s_awburst; assign m1_awburst=s_awburst;
    assign m0_wid=s_wid; assign m1_wid=s_wid;
    assign m0_wdata=s_wdata; assign m1_wdata=s_wdata;
    assign m0_wstrb=s_wstrb; assign m1_wstrb=s_wstrb;
    assign m0_wlast=s_wlast; assign m1_wlast=s_wlast;
endmodule
