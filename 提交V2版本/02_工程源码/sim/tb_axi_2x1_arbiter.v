`timescale 1ns/1ps

module tb_axi_2x1_arbiter;
    reg clk=0, resetn=0;
    always #5 clk=~clk;

    reg [3:0] s0_arid=4'h3; reg [31:0] s0_araddr=32'h100;
    reg [7:0] s0_arlen=0; reg [2:0] s0_arsize=2;
    reg [1:0] s0_arburst=1; reg s0_arvalid=0; wire s0_arready;
    wire [3:0] s0_rid; wire [31:0] s0_rdata; wire [1:0] s0_rresp;
    wire s0_rlast,s0_rvalid; reg s0_rready=1;
    reg [3:0] s0_awid=4'h4; reg [31:0] s0_awaddr=32'h300;
    reg [7:0] s0_awlen=0; reg [2:0] s0_awsize=2;
    reg [1:0] s0_awburst=1; reg s0_awvalid=0; wire s0_awready;
    reg [3:0] s0_wid=4'h4; reg [31:0] s0_wdata=32'hc001cafe;
    reg [3:0] s0_wstrb=4'hf; reg s0_wlast=1,s0_wvalid=0;
    wire s0_wready; wire [3:0] s0_bid; wire [1:0] s0_bresp;
    wire s0_bvalid; reg s0_bready=1;

    reg [31:0] s1_araddr=32'h200; reg [7:0] s1_arlen=0;
    reg [2:0] s1_arsize=2; reg [1:0] s1_arburst=1;
    reg s1_arvalid=0; wire s1_arready; wire [31:0] s1_rdata;
    wire [1:0] s1_rresp; wire s1_rlast,s1_rvalid; reg s1_rready=1;
    reg [31:0] s1_awaddr=32'h400; reg [7:0] s1_awlen=0;
    reg [2:0] s1_awsize=2; reg [1:0] s1_awburst=1;
    reg s1_awvalid=0; wire s1_awready;
    reg [31:0] s1_wdata=32'h5a5aa5a5; reg [3:0] s1_wstrb=4'hf;
    reg s1_wlast=1,s1_wvalid=0; wire s1_wready;
    wire [1:0] s1_bresp; wire s1_bvalid; reg s1_bready=1;

    wire [3:0] m_arid; wire [31:0] m_araddr; wire [7:0] m_arlen;
    wire [2:0] m_arsize; wire [1:0] m_arburst; wire m_arvalid;
    reg m_arready=1; reg [3:0] m_rid=0; reg [31:0] m_rdata=0;
    reg [1:0] m_rresp=0; reg m_rlast=1,m_rvalid=0; wire m_rready;
    wire [3:0] m_awid; wire [31:0] m_awaddr; wire [7:0] m_awlen;
    wire [2:0] m_awsize; wire [1:0] m_awburst; wire m_awvalid;
    reg m_awready=1; wire [3:0] m_wid; wire [31:0] m_wdata;
    wire [3:0] m_wstrb; wire m_wlast,m_wvalid; reg m_wready=1;
    reg [3:0] m_bid=0; reg [1:0] m_bresp=0; reg m_bvalid=0;
    wire m_bready;

    axi_2x1_arbiter dut(.*);

    task fail; input [255:0] why; begin
        $fatal(1,"FAIL tb_axi_2x1_arbiter: %0s",why);
    end endtask

    initial begin
        repeat(3) @(posedge clk); resetn=1;

        // Both readers request together. CPU wins first, then the waiting DMA.
        @(negedge clk); s0_arvalid=1; s1_arvalid=1; #1;
        if(!s0_arready||s1_arready||m_araddr!=32'h100||m_arid!=4'h3)
            fail("CPU did not receive first read grant");
        @(posedge clk); #1; @(negedge clk); s0_arvalid=0;
        m_rid=4'h3; m_rdata=32'h11112222; m_rvalid=1; #1;
        if(!s0_rvalid||s1_rvalid||s0_rdata!=32'h11112222)
            fail("CPU read response routed incorrectly");
        @(posedge clk); #1; @(negedge clk); m_rvalid=0; #1;
        if(!s1_arready||m_araddr!=32'h200||m_arid!=4'hf)
            fail("DMA did not receive second read grant");
        @(posedge clk); #1; @(negedge clk); s1_arvalid=0;
        m_rid=4'hf; m_rdata=32'h33334444; m_rvalid=1; #1;
        if(!s1_rvalid||s0_rvalid||s1_rdata!=32'h33334444)
            fail("DMA read response routed incorrectly");
        @(posedge clk); #1; @(negedge clk); m_rvalid=0;

        // Write ownership includes W and B, so payloads cannot interleave.
        @(posedge clk); @(negedge clk); s0_awvalid=1; s1_awvalid=1; #1;
        if(!s0_awready||s1_awready||m_awaddr!=32'h300||m_awid!=4'h4)
            fail("CPU did not receive first write grant");
        @(posedge clk); #1; @(negedge clk); s0_awvalid=0;s0_wvalid=1; #1;
        if(!s0_wready||s1_wready||m_wdata!=32'hc001cafe||m_wid!=4'h4)
            fail("CPU write payload routed incorrectly");
        @(posedge clk); #1; @(negedge clk); s0_wvalid=0;m_bid=4'h4;m_bvalid=1; #1;
        if(!s0_bvalid||s1_bvalid) fail("CPU write response routed incorrectly");
        @(posedge clk); #1; @(negedge clk); m_bvalid=0; #1;
        if(!s1_awready||m_awaddr!=32'h400||m_awid!=4'hf)
            fail("DMA did not receive second write grant");
        @(posedge clk); #1; @(negedge clk); s1_awvalid=0;s1_wvalid=1; #1;
        if(!s1_wready||s0_wready||m_wdata!=32'h5a5aa5a5||m_wid!=4'hf)
            fail("DMA write payload routed incorrectly");
        @(posedge clk); #1; @(negedge clk); s1_wvalid=0;m_bid=4'hf;m_bvalid=1; #1;
        if(!s1_bvalid||s0_bvalid) fail("DMA write response routed incorrectly");
        @(posedge clk); #1;

        $display("PASS tb_axi_2x1_arbiter");
        $finish;
    end
endmodule
