`timescale 1ns/1ps

module tb_axi_1x2;
    reg clk=0, resetn=0;
    always #5 clk=~clk;

    reg [3:0] s_arid=4'h3; reg [31:0] s_araddr=0; reg [7:0] s_arlen=0;
    reg [2:0] s_arsize=3'd2; reg [1:0] s_arburst=2'b01, s_arlock=0;
    reg [3:0] s_arcache=0; reg [2:0] s_arprot=0; reg s_arvalid=0;
    wire s_arready; wire [3:0] s_rid; wire [31:0] s_rdata;
    wire [1:0] s_rresp; wire s_rlast, s_rvalid; reg s_rready=1;
    reg [3:0] s_awid=4'h5; reg [31:0] s_awaddr=0; reg [7:0] s_awlen=0;
    reg [2:0] s_awsize=3'd2; reg [1:0] s_awburst=2'b01, s_awlock=0;
    reg [3:0] s_awcache=0; reg [2:0] s_awprot=0; reg s_awvalid=0;
    wire s_awready; reg [3:0] s_wid=4'h5; reg [31:0] s_wdata=32'h12345678;
    reg [3:0] s_wstrb=4'hf; reg s_wlast=1, s_wvalid=0; wire s_wready;
    wire [3:0] s_bid; wire [1:0] s_bresp; wire s_bvalid; reg s_bready=1;

    wire [3:0] m0_arid,m0_awid,m0_wid,m1_arid,m1_awid,m1_wid;
    wire [31:0] m0_araddr,m0_awaddr,m0_wdata,m1_araddr,m1_awaddr,m1_wdata;
    wire [7:0] m0_arlen,m0_awlen,m1_arlen,m1_awlen;
    wire [2:0] m0_arsize,m0_awsize,m1_arsize,m1_awsize;
    wire [1:0] m0_arburst,m0_awburst,m1_arburst,m1_awburst;
    wire m0_arvalid,m0_rready,m0_awvalid,m0_wlast,m0_wvalid,m0_bready;
    wire m1_arvalid,m1_rready,m1_awvalid,m1_wlast,m1_wvalid,m1_bready;
    reg m0_arready=1,m0_awready=1,m0_wready=1,m0_rvalid=0,m0_rlast=1,m0_bvalid=0;
    reg m1_arready=1,m1_awready=1,m1_wready=1,m1_rvalid=0,m1_rlast=1,m1_bvalid=0;
    reg [3:0] m0_rid=4'h3,m0_bid=4'h5,m1_rid=4'h3,m1_bid=4'h5;
    reg [31:0] m0_rdata=32'hd0d0d0d0,m1_rdata=32'h11111111;
    reg [1:0] m0_rresp=0,m0_bresp=0,m1_rresp=0,m1_bresp=0;
    wire [3:0] m0_wstrb,m1_wstrb;

    axi_1x2 dut(.*);

    task fail; input [255:0] why; begin $fatal(1,"FAIL tb_axi_1x2: %0s",why); end endtask
    task check_read_route; input [31:0] addr; input expect_ddr; begin
        @(negedge clk); s_araddr=addr; s_arvalid=1;
        #1;
        if (!s_arready) fail("read address not ready");
        if (m0_arvalid !== expect_ddr || m1_arvalid !== !expect_ddr) fail("wrong read route");
        if (expect_ddr && m0_araddr !== ((addr[31:30] == 2'b10) ?
            {1'b0,addr[30:0]} : addr)) fail("wrong DDR read alias translation");
        @(posedge clk); #1;
        if (s_arready) fail("read accepted again while transaction active");
        @(negedge clk); s_arvalid=0;
        if (expect_ddr) m0_rvalid=1; else m1_rvalid=1;
        #1;
        if (!s_rvalid || s_rdata !== (expect_ddr ? 32'hd0d0d0d0 : 32'h11111111)) fail("wrong read response");
        @(posedge clk); #1;
        @(negedge clk); if (expect_ddr) m0_rvalid=0; else m1_rvalid=0;
        @(posedge clk); #1;
    end endtask

    task check_write_route; input [31:0] addr; input expect_ddr; begin
        @(negedge clk); s_awaddr=addr; s_awvalid=1;
        #1;
        if (!s_awready) fail("write address not ready");
        if (m0_awvalid !== expect_ddr || m1_awvalid !== !expect_ddr) fail("wrong write route");
        if (expect_ddr && m0_awaddr !== ((addr[31:30] == 2'b10) ?
            {1'b0,addr[30:0]} : addr)) fail("wrong DDR write alias translation");
        @(posedge clk); #1;
        if (s_awready) fail("write accepted again while transaction active");
        @(negedge clk); s_awvalid=0; s_wvalid=1;
        @(posedge clk); #1;
        @(negedge clk); s_wvalid=0; if (expect_ddr) m0_bvalid=1; else m1_bvalid=1;
        #1;
        if (!s_bvalid) fail("write response missing");
        @(posedge clk); #1;
        @(negedge clk); if (expect_ddr) m0_bvalid=0; else m1_bvalid=0;
        @(posedge clk); #1;
    end endtask

    initial begin
        repeat(3) @(posedge clk); resetn=1;
        check_read_route(32'h0100_0000,1'b1);
        check_read_route(32'h1c00_0000,1'b0);
        check_read_route(32'h1c01_ffff,1'b0);
        check_read_route(32'h1c02_0000,1'b1);
        check_read_route(32'h1fe0_01e0,1'b0);
        check_read_route(32'h1fe0_3000,1'b0);
        check_read_route(32'h9b00_0040,1'b1);
        check_write_route(32'h0200_0000,1'b1);
        check_write_route(32'h1c00_0040,1'b0);
        check_write_route(32'h1fe0_0200,1'b0);
        check_write_route(32'h9b00_0080,1'b1);
        $display("PASS tb_axi_1x2"); $finish;
    end
endmodule
