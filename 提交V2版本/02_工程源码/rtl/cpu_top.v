`timescale 1ns/1ps
// SoC adapter: CPU CoreTop uses cpu_clk; the CLINT route uses fixed sys_clk.
// CoreTop.sv is copied verbatim from src by scripts/sync_cpu.ps1.
module cpu_core_top #(parameter [31:0] RESET_VECTOR = 32'h1c00_0000)(
    input wire        cpu_clk,
    input wire        cpu_resetn,
    input wire        sys_clk,
    input wire        sys_resetn,
    input wire [31:0] external_interrupts,
    output wire [3:0]  arid,
    output wire [31:0] araddr,
    output wire [7:0]  arlen,
    output wire [2:0]  arsize,
    output wire [1:0]  arburst,
    output wire [1:0]  arlock,
    output wire [3:0]  arcache,
    output wire [2:0]  arprot,
    output wire        arvalid,
    input wire        arready,
    input wire [3:0]  rid,
    input wire [31:0] rdata,
    input wire [1:0]  rresp,
    input wire        rlast,
    input wire        rvalid,
    output wire        rready,
    output wire [3:0]  awid,
    output wire [31:0] awaddr,
    output wire [7:0]  awlen,
    output wire [2:0]  awsize,
    output wire [1:0]  awburst,
    output wire [1:0]  awlock,
    output wire [3:0]  awcache,
    output wire [2:0]  awprot,
    output wire        awvalid,
    input wire        awready,
    output wire [3:0]  wid,
    output wire [31:0] wdata,
    output wire [3:0]  wstrb,
    output wire        wlast,
    output wire        wvalid,
    input wire        wready,
    input wire [3:0]  bid,
    input wire [1:0]  bresp,
    input wire        bvalid,
    output wire        bready
);
    wire [3:0]  c_arid;
    wire [31:0] c_araddr;
    wire [7:0]  c_arlen;
    wire [2:0]  c_arsize;
    wire [1:0]  c_arburst;
    wire [1:0]  c_arlock;
    wire [3:0]  c_arcache;
    wire [2:0]  c_arprot;
    wire        c_arvalid;
    wire        c_arready;
    wire [3:0]  c_rid;
    wire [31:0] c_rdata;
    wire [1:0]  c_rresp;
    wire        c_rlast;
    wire        c_rvalid;
    wire        c_rready;
    wire [3:0]  c_awid;
    wire [31:0] c_awaddr;
    wire [7:0]  c_awlen;
    wire [2:0]  c_awsize;
    wire [1:0]  c_awburst;
    wire [1:0]  c_awlock;
    wire [3:0]  c_awcache;
    wire [2:0]  c_awprot;
    wire        c_awvalid;
    wire        c_awready;
    wire [3:0]  c_wid;
    wire [31:0] c_wdata;
    wire [3:0]  c_wstrb;
    wire        c_wlast;
    wire        c_wvalid;
    wire        c_wready;
    wire [3:0]  c_bid;
    wire [1:0]  c_bresp;
    wire        c_bvalid;
    wire        c_bready;
    wire [3:0] s_arid, s_rid, s_awid, s_wid, s_bid;
    wire [31:0] s_araddr, s_rdata, s_awaddr, s_wdata;
    wire [7:0] s_arlen, s_awlen;
    wire [2:0] s_arsize, s_arprot, s_awsize, s_awprot;
    wire [1:0] s_arburst, s_arlock, s_rresp, s_awburst, s_awlock, s_bresp;
    wire [3:0] s_arcache, s_awcache, s_wstrb;
    wire s_arvalid, s_arready, s_rlast, s_rvalid, s_rready;
    wire s_awvalid, s_awready, s_wlast, s_wvalid, s_wready, s_bvalid, s_bready;

    // Payload bit order is explicit at both ends.  AW and W use separate
    // queues, allowing either channel to arrive first without losing ID or
    // byte strobes.  R and B have independent return capacity.
    axi_cpu_sys_cdc u_axi_cdc(
        .cpu_clk(cpu_clk), .cpu_resetn(cpu_resetn),
        .sys_clk(sys_clk), .sys_resetn(sys_resetn),
        .s_ar_payload({c_arid,c_araddr,c_arlen,c_arsize,c_arburst,c_arlock,c_arcache,c_arprot}),
        .s_arvalid(c_arvalid), .s_arready(c_arready),
        .m_ar_payload({s_arid,s_araddr,s_arlen,s_arsize,s_arburst,s_arlock,s_arcache,s_arprot}),
        .m_arvalid(s_arvalid), .m_arready(s_arready),
        .s_aw_payload({c_awid,c_awaddr,c_awlen,c_awsize,c_awburst,c_awlock,c_awcache,c_awprot}),
        .s_awvalid(c_awvalid), .s_awready(c_awready),
        .m_aw_payload({s_awid,s_awaddr,s_awlen,s_awsize,s_awburst,s_awlock,s_awcache,s_awprot}),
        .m_awvalid(s_awvalid), .m_awready(s_awready),
        .s_w_payload({c_wid,c_wdata,c_wstrb,c_wlast}),
        .s_wvalid(c_wvalid), .s_wready(c_wready),
        .m_w_payload({s_wid,s_wdata,s_wstrb,s_wlast}),
        .m_wvalid(s_wvalid), .m_wready(s_wready),
        .m_r_payload({s_rid,s_rdata,s_rresp,s_rlast}),
        .m_rvalid(s_rvalid), .m_rready(s_rready),
        .s_r_payload({c_rid,c_rdata,c_rresp,c_rlast}),
        .s_rvalid(c_rvalid), .s_rready(c_rready),
        .m_b_payload({s_bid,s_bresp}),
        .m_bvalid(s_bvalid), .m_bready(s_bready),
        .s_b_payload({c_bid,c_bresp}),
        .s_bvalid(c_bvalid), .s_bready(c_bready));

    wire timer_irq, software_irq, clint_ack, clint_error;
    wire [31:0] clint_rdata;
    wire fatal_memory_error;
    wire timer_irq_cpu, software_irq_cpu, external_irq_cpu;
    cpu_irq_sync u_irq_sync(
        .cpu_clk(cpu_clk), .cpu_resetn(cpu_resetn),
        .timer_irq_sys(timer_irq), .software_irq_sys(software_irq),
        .external_irq_sys(|external_interrupts),
        .timer_irq_cpu(timer_irq_cpu),
        .software_irq_cpu(software_irq_cpu),
        .external_irq_cpu(external_irq_cpu));
    wire [7:0] interrupts =
        {timer_irq_cpu, 5'b0, software_irq_cpu, external_irq_cpu};

    // Keep one read and write independently routed until their RLAST/B.
    // The downstream crossbar has the same outstanding-transaction limit.
    reg rd_busy, rd_local, wr_busy, wr_local;
    reg [3:0] local_rid, local_bid;
    reg [31:0] local_rdata, local_wr_addr;
    reg [7:0] local_rd_left, local_wr_left;
    reg [1:0] local_rresp, local_bresp;
    reg local_bvalid, local_wr_bad;
    wire ar_local = s_araddr[31:16] == 16'h0200;
    wire aw_local = s_awaddr[31:16] == 16'h0200;
    wire local_write_fire = wr_busy && wr_local && s_wvalid && s_wready;
    wire local_write_good = local_write_fire && !local_wr_bad &&
                            (local_wr_left == 0) && s_wlast &&
                            (s_wid == local_bid);
    // Reads take a snapshot when AR is accepted; writes take priority for
    // this one register port. CLINT ACK prevents duplicate write acceptance.
    wire [31:0] clint_addr = local_write_fire ?
        {local_wr_addr[31:2], 2'b0} : {s_araddr[31:2], 2'b0};
    clint u_clint(
        .clk(sys_clk), .resetn(sys_resetn), .cyc(local_write_good),
        .stb(local_write_good), .we(1'b1), .addr(clint_addr),
        .wdata(s_wdata), .sel(s_wstrb), .rdata(clint_rdata),
        .ack(clint_ack), .err(clint_error),
        .timer_irq(timer_irq), .software_irq(software_irq)
    );
    assign arvalid = !rd_busy && !ar_local && s_arvalid;
    assign s_arready = !rd_busy && (ar_local ? !local_write_fire : arready);
    assign s_rid = rd_local ? local_rid : rid;
    assign s_rdata = rd_local ? local_rdata : rdata;
    assign s_rresp = rd_local ? local_rresp : rresp;
    assign s_rlast = rd_local ? (local_rd_left == 0) : rlast;
    assign s_rvalid = rd_busy && (rd_local || rvalid);
    assign rready = rd_busy && !rd_local && s_rready;
    assign awvalid = !wr_busy && !aw_local && s_awvalid;
    assign s_awready = !wr_busy && (aw_local || awready);
    assign wvalid = wr_busy && !wr_local && s_wvalid;
    assign s_wready = wr_busy && (wr_local ?
        (!local_bvalid && !clint_ack) : wready);
    assign s_bid = wr_local ? local_bid : bid;
    assign s_bresp = wr_local ? local_bresp : bresp;
    assign s_bvalid = wr_busy && (wr_local ? local_bvalid : bvalid);
    assign bready = wr_busy && !wr_local && s_bready;
    always @(posedge sys_clk) begin
        if (!sys_resetn) begin
            rd_busy <= 0; rd_local <= 0; wr_busy <= 0; wr_local <= 0;
            local_rid <= 0; local_bid <= 0; local_rdata <= 0;
            local_wr_addr <= 0; local_rd_left <= 0; local_wr_left <= 0;
            local_rresp <= 0; local_bresp <= 0;
            local_bvalid <= 0; local_wr_bad <= 0;
        end else begin
            if (s_arvalid && s_arready) begin
                rd_busy <= 1; rd_local <= ar_local;
                if (ar_local) begin
                    local_rid <= s_arid; local_rd_left <= s_arlen;
                    local_rdata <= clint_rdata;
                    local_rresp <= (s_arlen != 0 || s_arsize > 2) ? 2'b10 : 2'b00;
                end
            end
            if (s_rvalid && s_rready) begin
                if (s_rlast) rd_busy <= 0;
                else if (rd_local) local_rd_left <= local_rd_left - 1'b1;
            end
            if (s_awvalid && s_awready) begin
                wr_busy <= 1; wr_local <= aw_local;
                if (aw_local) begin
                    local_bid <= s_awid; local_wr_addr <= s_awaddr;
                    local_wr_left <= s_awlen;
                    local_wr_bad <= (s_awlen != 0 || s_awsize > 2);
                end
            end
            if (local_write_fire) begin
                if (s_wlast || local_wr_left == 0) begin
                    local_bvalid <= 1;
                    local_bresp <= local_write_good ? 2'b00 : 2'b10;
                end else local_wr_left <= local_wr_left - 1'b1;
            end
            if (s_bvalid && s_bready) begin
                wr_busy <= 0;
                if (wr_local) local_bvalid <= 0;
            end
        end
    end
    assign arid = s_arid;
    assign araddr = s_araddr;
    assign arlen = s_arlen;
    assign arsize = s_arsize;
    assign arburst = s_arburst;
    assign arlock = s_arlock;
    assign arcache = s_arcache;
    assign arprot = s_arprot;
    assign awid = s_awid;
    assign awaddr = s_awaddr;
    assign awlen = s_awlen;
    assign awsize = s_awsize;
    assign awburst = s_awburst;
    assign awlock = s_awlock;
    assign awcache = s_awcache;
    assign awprot = s_awprot;
    assign wid = s_wid;
    assign wdata = s_wdata;
    assign wstrb = s_wstrb;
    assign wlast = s_wlast;
    CoreTop u_cpu(
        .io_aclk(cpu_clk), .io_aresetn(cpu_resetn),
        .io_resetVector(RESET_VECTOR), .io_intrpt(interrupts),
        .io_arid(c_arid),
        .io_araddr(c_araddr),
        .io_arlen(c_arlen),
        .io_arsize(c_arsize),
        .io_arburst(c_arburst),
        .io_arlock(c_arlock),
        .io_arcache(c_arcache),
        .io_arprot(c_arprot),
        .io_arvalid(c_arvalid),
        .io_arready(c_arready),
        .io_rid(c_rid),
        .io_rdata(c_rdata),
        .io_rresp(c_rresp),
        .io_rlast(c_rlast),
        .io_rvalid(c_rvalid),
        .io_rready(c_rready),
        .io_awid(c_awid),
        .io_awaddr(c_awaddr),
        .io_awlen(c_awlen),
        .io_awsize(c_awsize),
        .io_awburst(c_awburst),
        .io_awlock(c_awlock),
        .io_awcache(c_awcache),
        .io_awprot(c_awprot),
        .io_awvalid(c_awvalid),
        .io_awready(c_awready),
        .io_wid(c_wid),
        .io_wdata(c_wdata),
        .io_wstrb(c_wstrb),
        .io_wlast(c_wlast),
        .io_wvalid(c_wvalid),
        .io_wready(c_wready),
        .io_bid(c_bid),
        .io_bresp(c_bresp),
        .io_bvalid(c_bvalid),
        .io_bready(c_bready),
        .io_fatalMemoryError(fatal_memory_error),
        .io_break_point(1'b0), .io_infor_flag(1'b0), .io_reg_num(5'b0),
        .io_ws_valid(), .io_rf_rdata(), .io_debug0_wb_pc(),
        .io_debug0_wb_rf_wen(), .io_debug0_wb_rf_wnum(),
        .io_debug0_wb_rf_wdata(), .io_debug0_wb_inst()
    );
endmodule

// SYS interrupt levels remain asserted until software changes their source.
// The CPU samples only synchronized second stages; pulses are not used.
module cpu_irq_sync(
    input wire cpu_clk,
    input wire cpu_resetn,
    input wire timer_irq_sys,
    input wire software_irq_sys,
    input wire external_irq_sys,
    output wire timer_irq_cpu,
    output wire software_irq_cpu,
    output wire external_irq_cpu
);
    (* ASYNC_REG = "TRUE" *) reg timer_c1 /* synthesis syn_preserve=1 */;
    (* ASYNC_REG = "TRUE" *) reg timer_c2 /* synthesis syn_preserve=1 */;
    (* ASYNC_REG = "TRUE" *) reg software_c1 /* synthesis syn_preserve=1 */;
    (* ASYNC_REG = "TRUE" *) reg software_c2 /* synthesis syn_preserve=1 */;
    (* ASYNC_REG = "TRUE" *) reg external_c1 /* synthesis syn_preserve=1 */;
    (* ASYNC_REG = "TRUE" *) reg external_c2 /* synthesis syn_preserve=1 */;
    always @(posedge cpu_clk or negedge cpu_resetn) begin
        if (!cpu_resetn) begin
            timer_c1 <= 1'b0; timer_c2 <= 1'b0;
            software_c1 <= 1'b0; software_c2 <= 1'b0;
            external_c1 <= 1'b0; external_c2 <= 1'b0;
        end else begin
            timer_c1 <= timer_irq_sys; timer_c2 <= timer_c1;
            software_c1 <= software_irq_sys; software_c2 <= software_c1;
            external_c1 <= external_irq_sys; external_c2 <= external_c1;
        end
    end
    assign timer_irq_cpu = timer_c2;
    assign software_irq_cpu = software_c2;
    assign external_irq_cpu = external_c2;
endmodule

// Stable SoC interface; external interrupts are unused by the polling console.
module core_top #(parameter [31:0] RESET_VECTOR = 32'h1c00_0000)(
    input wire        cpu_clk,
    input wire        cpu_resetn,
    input wire        sys_clk,
    input wire        sys_resetn,
    output wire [3:0]  arid,
    output wire [31:0] araddr,
    output wire [7:0]  arlen,
    output wire [2:0]  arsize,
    output wire [1:0]  arburst,
    output wire [1:0]  arlock,
    output wire [3:0]  arcache,
    output wire [2:0]  arprot,
    output wire        arvalid,
    input wire        arready,
    input wire [3:0]  rid,
    input wire [31:0] rdata,
    input wire [1:0]  rresp,
    input wire        rlast,
    input wire        rvalid,
    output wire        rready,
    output wire [3:0]  awid,
    output wire [31:0] awaddr,
    output wire [7:0]  awlen,
    output wire [2:0]  awsize,
    output wire [1:0]  awburst,
    output wire [1:0]  awlock,
    output wire [3:0]  awcache,
    output wire [2:0]  awprot,
    output wire        awvalid,
    input wire        awready,
    output wire [3:0]  wid,
    output wire [31:0] wdata,
    output wire [3:0]  wstrb,
    output wire        wlast,
    output wire        wvalid,
    input wire        wready,
    input wire [3:0]  bid,
    input wire [1:0]  bresp,
    input wire        bvalid,
    output wire        bready
);
    cpu_core_top #(.RESET_VECTOR(RESET_VECTOR)) u_cpu_wrapper(
        .external_interrupts(32'b0),
        .cpu_clk(cpu_clk),
        .cpu_resetn(cpu_resetn),
        .sys_clk(sys_clk),
        .sys_resetn(sys_resetn),
        .arid(arid),
        .araddr(araddr),
        .arlen(arlen),
        .arsize(arsize),
        .arburst(arburst),
        .arlock(arlock),
        .arcache(arcache),
        .arprot(arprot),
        .arvalid(arvalid),
        .arready(arready),
        .rid(rid),
        .rdata(rdata),
        .rresp(rresp),
        .rlast(rlast),
        .rvalid(rvalid),
        .rready(rready),
        .awid(awid),
        .awaddr(awaddr),
        .awlen(awlen),
        .awsize(awsize),
        .awburst(awburst),
        .awlock(awlock),
        .awcache(awcache),
        .awprot(awprot),
        .awvalid(awvalid),
        .awready(awready),
        .wid(wid),
        .wdata(wdata),
        .wstrb(wstrb),
        .wlast(wlast),
        .wvalid(wvalid),
        .wready(wready),
        .bid(bid),
        .bresp(bresp),
        .bvalid(bvalid),
        .bready(bready)
    );
endmodule
