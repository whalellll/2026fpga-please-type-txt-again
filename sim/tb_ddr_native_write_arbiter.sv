`timescale 1ns/1ps

module tb_ddr_native_write_arbiter;
    reg clk = 1'b0;
    reg resetn = 1'b0;

    reg [27:0] s0_awaddr = 28'd0;
    reg s0_awuser_ap = 1'b0;
    reg [3:0] s0_awid = 4'd0;
    reg [3:0] s0_awlen = 4'd0;
    reg s0_awvalid = 1'b0;
    wire s0_awready;
    reg [255:0] s0_wdata = 256'd0;
    reg [31:0] s0_wstrb = 32'd0;
    wire s0_wready;
    wire [3:0] s0_wusero_id;
    wire s0_wusero_last;

    reg [27:0] s1_awaddr = 28'd0;
    reg [3:0] s1_awid = 4'd0;
    reg [3:0] s1_awlen = 4'd0;
    reg s1_awvalid = 1'b0;
    reg s1_urgent = 1'b0;
    wire s1_awready;
    reg [255:0] s1_wdata = 256'd0;
    reg [31:0] s1_wstrb = 32'd0;
    wire s1_wready;
    wire [3:0] s1_wusero_id;
    wire s1_wusero_last;

    wire [27:0] m_awaddr;
    wire m_awuser_ap;
    wire [3:0] m_awid;
    wire [3:0] m_awlen;
    wire m_awvalid;
    reg m_awready = 1'b0;
    wire [255:0] m_wdata;
    wire [31:0] m_wstrb;
    reg m_wready = 1'b0;
    reg [3:0] m_wusero_id = 4'd0;
    reg m_wusero_last = 1'b0;
    wire busy;
    wire owner_camera;

    integer beat;

    always #5 clk = ~clk;

    ddr_native_write_arbiter dut (
        .clk(clk), .resetn(resetn),
        .s0_awaddr(s0_awaddr), .s0_awuser_ap(s0_awuser_ap),
        .s0_awid(s0_awid), .s0_awlen(s0_awlen),
        .s0_awvalid(s0_awvalid), .s0_awready(s0_awready),
        .s0_wdata(s0_wdata), .s0_wstrb(s0_wstrb),
        .s0_wready(s0_wready), .s0_wusero_id(s0_wusero_id),
        .s0_wusero_last(s0_wusero_last),
        .s1_awaddr(s1_awaddr), .s1_awid(s1_awid),
        .s1_awlen(s1_awlen), .s1_awvalid(s1_awvalid),
        .s1_urgent(s1_urgent), .s1_awready(s1_awready),
        .s1_wdata(s1_wdata), .s1_wstrb(s1_wstrb),
        .s1_wready(s1_wready), .s1_wusero_id(s1_wusero_id),
        .s1_wusero_last(s1_wusero_last),
        .m_awaddr(m_awaddr), .m_awuser_ap(m_awuser_ap),
        .m_awid(m_awid), .m_awlen(m_awlen),
        .m_awvalid(m_awvalid), .m_awready(m_awready),
        .m_wdata(m_wdata), .m_wstrb(m_wstrb),
        .m_wready(m_wready), .m_wusero_id(m_wusero_id),
        .m_wusero_last(m_wusero_last),
        .busy(busy), .owner_camera(owner_camera)
    );

    initial begin
        repeat (3) @(posedge clk);
        resetn <= 1'b1;
        @(posedge clk);

        // Both request together.  Urgent camera traffic owns the complete
        // transaction even while the CPU request remains asserted.
        s0_awaddr <= 28'h0001234;
        s0_awid <= 4'h2;
        s0_awlen <= 4'd0;
        s0_awvalid <= 1'b1;
        s0_wdata <= {8{32'hc0c0c0c0}};
        s0_wstrb <= 32'h0000000f;
        s1_awaddr <= 28'h6c80000;
        s1_awid <= 4'hc;
        s1_awlen <= 4'd15;
        s1_awvalid <= 1'b1;
        s1_urgent <= 1'b1;
        s1_wdata <= {8{32'h5a5aa5a5}};
        s1_wstrb <= 32'hffffffff;
        @(posedge clk);
        #1;
        if (!m_awvalid || m_awaddr != 28'h6c80000 || m_awlen != 4'd15)
            $fatal(1, "urgent camera AW was not selected");

        // Hold downstream AW stalled and withdraw/change the CPU request.
        // The selected camera address must stay stable.
        s0_awvalid <= 1'b0;
        s0_awaddr <= 28'hfffffff;
        repeat (2) begin
            @(posedge clk);
            #1;
            if (!m_awvalid || m_awaddr != 28'h6c80000 || s0_awready)
                $fatal(1, "AW grant changed while downstream stalled");
        end

        m_awready <= 1'b1;
        @(posedge clk);
        #1;
        m_awready <= 1'b0;
        s1_awvalid <= 1'b0;
        if (!busy || !owner_camera)
            $fatal(1, "camera ownership was not locked after AW acceptance");

        // Every native write beat and completion must be visible only to the
        // owning camera master.
        for (beat = 0; beat < 16; beat = beat + 1) begin
            s1_wdata <= {240'd0, beat[15:0]};
            m_wusero_id <= 4'hc;
            m_wusero_last <= (beat == 15);
            m_wready <= 1'b1;
            #1;
            if (!s1_wready || s0_wready)
                $fatal(1, "write ready routed to wrong owner at beat %0d", beat);
            if (m_wdata[15:0] != beat[15:0] || m_wstrb != 32'hffffffff)
                $fatal(1, "camera write payload mismatch at beat %0d", beat);
            if (!s1_wusero_last && beat == 15)
                $fatal(1, "camera did not receive WLAST");
            @(posedge clk);
        end
        m_wready <= 1'b0;
        m_wusero_last <= 1'b0;
        @(posedge clk);
        #1;
        if (busy)
            $fatal(1, "arbiter did not release after camera WLAST");

        // A waiting CPU write must proceed after the camera burst.
        s0_awvalid <= 1'b1;
        m_awready <= 1'b1;
        #1;
        if (!s0_awready || s1_awready || m_awaddr != 28'hfffffff)
            $fatal(1, "pending CPU write was not granted");
        @(posedge clk);
        m_awready <= 1'b0;
        s0_awvalid <= 1'b0;
        m_wusero_id <= 4'h2;
        m_wusero_last <= 1'b1;
        m_wready <= 1'b1;
        #1;
        if (!s0_wready || s1_wready || s0_wusero_id != 4'h2 ||
            !s0_wusero_last)
            $fatal(1, "CPU completion routed to wrong owner");
        @(posedge clk);
        m_wready <= 1'b0;
        m_wusero_last <= 1'b0;
        @(posedge clk);
        #1;
        if (busy)
            $fatal(1, "arbiter remained busy after CPU write");

        $display("DDR_NATIVE_WRITE_ARBITER_PASS");
        $finish;
    end
endmodule
