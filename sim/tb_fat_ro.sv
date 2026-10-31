`timescale 1ns/1ps

module tb_fat_ro;
    reg clk = 1'b0;
    reg resetn = 1'b0;
    always #5 clk = ~clk;

    wire [3:0] arid, awid, wid;
    wire [31:0] araddr, awaddr, wdata;
    wire [7:0] arlen, awlen;
    wire [2:0] arsize, arprot, awsize, awprot;
    wire [1:0] arburst, arlock, awburst, awlock;
    wire [3:0] arcache, awcache, wstrb;
    wire arvalid, arready, rlast, rready;
    wire awvalid, awready, wlast, wvalid, wready, bready;
    reg [3:0] rid, bid;
    reg [31:0] rdata;
    reg [1:0] rresp, bresp;
    reg rvalid, bvalid;

    cpu_core_top #(.RESET_VECTOR(32'h0000_0000)) dut (
        .cpu_clk(clk), .cpu_resetn(resetn),
        .sys_clk(clk), .sys_resetn(resetn), .external_interrupts(32'b0),
        .arid(arid), .araddr(araddr), .arlen(arlen), .arsize(arsize),
        .arburst(arburst), .arlock(arlock), .arcache(arcache), .arprot(arprot),
        .arvalid(arvalid), .arready(arready), .rid(rid), .rdata(rdata),
        .rresp(rresp), .rlast(rlast), .rvalid(rvalid), .rready(rready),
        .awid(awid), .awaddr(awaddr), .awlen(awlen), .awsize(awsize),
        .awburst(awburst), .awlock(awlock), .awcache(awcache), .awprot(awprot),
        .awvalid(awvalid), .awready(awready), .wid(wid), .wdata(wdata),
        .wstrb(wstrb), .wlast(wlast), .wvalid(wvalid), .wready(wready),
        .bid(bid), .bresp(bresp), .bvalid(bvalid), .bready(bready)
    );

    reg [31:0] memory [0:32767];
    integer k;
    initial begin
        for (k = 0; k < 32768; k = k + 1)
            memory[k] = 32'b0;
        $readmemh("artifacts/selftest/fat_ro_test.hex", memory);
    end

    // current CPU cache-line AXI responses stay stable until accepted.
    reg read_pending = 1'b0;
    reg [31:0] saved_araddr;
    reg [7:0] saved_arleft;
    reg [2:0] saved_arsize;
    assign arready = !read_pending && !rvalid;
    assign rlast = saved_arleft == 0;
    always @(posedge clk) begin
        if (!resetn) begin
            read_pending <= 0; rid <= 0; rdata <= 0; rresp <= 0; rvalid <= 0;
            saved_araddr <= 0; saved_arleft <= 0; saved_arsize <= 0;
        end else begin
            if (arvalid && arready) begin
                read_pending <= 1; rid <= arid;
                saved_araddr <= araddr; saved_arleft <= arlen; saved_arsize <= arsize;
                if (arlen > 7 || arsize > 2 || arburst != 1)
                    $fatal(1, "unsupported current CPU AXI read");
            end
            if (read_pending && !rvalid) begin
                rvalid <= 1;
                if (saved_araddr < 32'h00020000) begin
                    rdata <= memory[saved_araddr[16:2]]; rresp <= 0;
                end

                else begin rdata <= 0; rresp <= 2'b11; end
            end
            if (rvalid && rready) begin
                rvalid <= 0;
                if (saved_arleft == 0) read_pending <= 0;
                else begin
                    saved_arleft <= saved_arleft - 1'b1;
                    saved_araddr <= saved_araddr + (32'd1 << saved_arsize);
                end
            end
        end
    end

    reg write_pending = 1'b0;
    reg [31:0] saved_awaddr;
    reg [3:0] saved_awid;
    reg [7:0] saved_awleft;
    reg [2:0] saved_awsize;
    assign awready = !write_pending && !bvalid;
    assign wready = write_pending && !bvalid;
    always @(posedge clk) begin
        if (!resetn) begin
            write_pending <= 1'b0;
            saved_awaddr <= 32'b0;
            saved_awid <= 4'b0; saved_awleft <= 0; saved_awsize <= 0;
            bid <= 4'b0;
            bresp <= 2'b0;
            bvalid <= 1'b0;
        end else begin
            if (awvalid && awready) begin
                write_pending <= 1'b1;
                saved_awaddr <= awaddr;
                saved_awid <= awid; saved_awleft <= awlen; saved_awsize <= awsize;
                if (awlen > 7 || awsize > 2 || awburst != 1)
                    $fatal(1, "unsupported current CPU AXI write");
            end
            if (wvalid && wready) begin
                if (wlast != (saved_awleft == 0) || wid != saved_awid)
                    $fatal(1, "current CPU write burst WLAST/ID mismatch");
                if (wlast) begin
                    write_pending <= 0; bid <= saved_awid; bresp <= 0; bvalid <= 1;
                end else begin
                    saved_awleft <= saved_awleft - 1'b1;
                    saved_awaddr <= saved_awaddr + (32'd1 << saved_awsize);
                end
                if (saved_awaddr < 32'h00020000) begin
                    if (wstrb[0]) memory[saved_awaddr[16:2]][7:0] <= wdata[7:0];
                    if (wstrb[1]) memory[saved_awaddr[16:2]][15:8] <= wdata[15:8];
                    if (wstrb[2]) memory[saved_awaddr[16:2]][23:16] <= wdata[23:16];
                    if (wstrb[3]) memory[saved_awaddr[16:2]][31:24] <= wdata[31:24];
                end
                if (saved_awaddr == 32'h80000000) begin
                    if ((wdata == 32'hf470600d) && (wstrb == 4'hf)) begin
                        $display("FAT_RO_PASS");
                        $finish;
                    end else begin
                        $display("FAT_RO_FAIL result=%08x strb=%x", wdata, wstrb);
                        $fatal(1);
                    end
                end
                if (saved_awaddr == 32'h80000004) begin
                    $display("FAT_RO_FAIL code=%08x", wdata);
                    $fatal(1);
                end
            end
            if (bvalid && bready)
                bvalid <= 1'b0;
        end
    end

    integer max_cycles;
    initial begin
        if (!$value$plusargs("max_cycles=%d", max_cycles))
            max_cycles = 10000000;
        repeat (20) @(posedge clk);
        resetn <= 1'b1;
        repeat (max_cycles) @(posedge clk);
        $display("FAT_RO_TIMEOUT");
        $fatal(1);
    end

    wire unused = &{1'b0, arburst, arlock, arcache, arprot,
                    awlen, awsize, awburst, awlock, awcache, awprot,
                    wid, wlast};
endmodule
