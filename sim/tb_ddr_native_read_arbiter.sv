`timescale 1ns/1ps

module tb_ddr_native_read_arbiter;
    reg clk = 0;
    reg resetn = 0;
    always #5 clk = ~clk;

    reg [27:0] s0_araddr = 0;
    reg s0_aruser_ap = 0;
    reg [3:0] s0_arid = 0, s0_arlen = 0;
    reg s0_arvalid = 0;
    wire s0_arready;
    wire [255:0] s0_rdata;
    wire [3:0] s0_rid;
    wire s0_rlast, s0_rvalid;
    reg [27:0] s1_araddr = 0;
    reg [3:0] s1_arid = 0, s1_arlen = 0;
    reg s1_arvalid = 0, s1_urgent = 0;
    wire s1_arready;
    wire [255:0] s1_rdata;
    wire [3:0] s1_rid;
    wire s1_rlast, s1_rvalid;
    wire [27:0] m_araddr;
    wire m_aruser_ap;
    wire [3:0] m_arid, m_arlen;
    wire m_arvalid;
    reg m_arready = 0;
    reg [255:0] m_rdata = 0;
    reg [3:0] m_rid = 0;
    reg m_rlast = 0, m_rvalid = 0;

    ddr_native_read_arbiter dut(.*);

    task fail(input string reason);
        begin $display("FAIL: %s", reason); $fatal(1); end
    endtask

    initial begin
        repeat (3) @(posedge clk);
        resetn <= 1;
        @(posedge clk);

        // A stalled bridge request must not be displaced when urgent video
        // arrives one cycle later.
        s0_araddr <= 28'h0123450;
        s0_arid <= 4'h2;
        s0_arlen <= 4'h0;
        s0_arvalid <= 1;
        @(posedge clk); #1;
        if (!m_arvalid || m_araddr != 28'h0123450)
            fail("bridge request was not selected");
        s1_araddr <= 28'h06c8000;
        s1_arid <= 4'he;
        s1_arlen <= 4'hf;
        s1_arvalid <= 1;
        s1_urgent <= 1;
        @(posedge clk); #1;
        if (m_araddr != 28'h0123450 || m_arid != 4'h2)
            fail("stalled grant changed owner");

        m_arready <= 1;
        #1;
        if (!s0_arready || s1_arready)
            fail("bridge handshake routed incorrectly");
        @(posedge clk); #1;
        s0_arvalid <= 0;
        m_arready <= 0;
        m_rdata <= 256'h55;
        m_rid <= 4'h2;
        m_rlast <= 1;
        m_rvalid <= 1;
        #1;
        if (!s0_rvalid || s1_rvalid || s0_rid != 4'h2)
            fail("bridge response routed incorrectly");
        @(posedge clk); #1;
        m_rvalid <= 0;
        m_rlast <= 0;

        // The already-waiting urgent framebuffer request wins next.
        m_arready <= 1;
        #1;
        if (!s1_arready || m_araddr != 28'h06c8000 || m_arlen != 4'hf)
            fail("urgent framebuffer request did not win");
        @(posedge clk); #1;
        s1_arvalid <= 0;
        m_arready <= 0;
        m_rid <= 4'he;
        m_rlast <= 1;
        m_rvalid <= 1;
        #1;
        if (!s1_rvalid || s0_rvalid)
            fail("framebuffer response routed incorrectly");
        @(posedge clk); #1;

        $display("DDR_NATIVE_READ_ARBITER_PASS");
        $finish;
    end
endmodule
