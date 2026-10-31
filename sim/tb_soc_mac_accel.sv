`timescale 1ns/1ps

// System-level MAC path: a software-like CPU master stages data in shared
// DDR, programs the MMIO register port, and reads back DMA results through
// the same fair AXI arbiter used by soc_top.
module tb_soc_mac_accel #(parameter H128_ENABLED=1,parameter CONV_ENABLED=0,parameter HALF_DENSE=0,parameter NNUE_ENABLED=0,parameter PIKAFISH_ONLY=0,parameter BATCH_ENABLED=0);
    reg clk=0,resetn=0;
    always #5 clk=~clk;

    reg reg_wr_en=0;reg[8:0]reg_wr_addr=0;reg[31:0]reg_wr_data=0;
    reg[3:0]reg_wr_strb=4'hf;reg[8:0]reg_rd_addr=0;
    wire[31:0]reg_rd_data;wire irq;

    reg[3:0]s0_arid=4'h1;reg[31:0]s0_araddr=0;reg[7:0]s0_arlen=0;
    reg[2:0]s0_arsize=3'd2;reg[1:0]s0_arburst=2'b01;
    reg s0_arvalid=0;wire s0_arready;wire[3:0]s0_rid;
    wire[31:0]s0_rdata;wire[1:0]s0_rresp;wire s0_rlast,s0_rvalid;
    reg s0_rready=0;
    reg[3:0]s0_awid=4'h2;reg[31:0]s0_awaddr=0;reg[7:0]s0_awlen=0;
    reg[2:0]s0_awsize=3'd2;reg[1:0]s0_awburst=2'b01;
    reg s0_awvalid=0;wire s0_awready;reg[3:0]s0_wid=4'h2;
    reg[31:0]s0_wdata=0;reg[3:0]s0_wstrb=4'hf;reg s0_wlast=0;
    reg s0_wvalid=0;wire s0_wready;wire[3:0]s0_bid;
    wire[1:0]s0_bresp;wire s0_bvalid;reg s0_bready=0;

    wire[31:0]s1_araddr,s1_rdata,s1_awaddr,s1_wdata;
    wire[7:0]s1_arlen,s1_awlen;wire[2:0]s1_arsize,s1_awsize;
    wire[1:0]s1_arburst,s1_rresp,s1_awburst,s1_bresp;
    wire[3:0]s1_wstrb;wire s1_arvalid,s1_arready,s1_rlast,s1_rvalid;
    wire s1_rready,s1_awvalid,s1_awready,s1_wlast,s1_wvalid,s1_wready;
    wire s1_bvalid,s1_bready;

    wire[3:0]m_arid,m_rid,m_awid,m_wid,m_bid;wire[31:0]m_araddr,m_rdata,m_awaddr,m_wdata;
    wire[7:0]m_arlen,m_awlen;wire[2:0]m_arsize,m_awsize;
    wire[1:0]m_arburst,m_rresp,m_awburst,m_bresp;wire[3:0]m_wstrb;
    wire m_arvalid,m_arready,m_rlast,m_rvalid,m_rready,m_awvalid,m_awready;
    wire m_wlast,m_wvalid,m_wready,m_bvalid,m_bready;

    mac_accel_ddr_kernel_top #(
        .DDR_BASE(32'h1b00_0000),.DDR_BYTES(BATCH_ENABLED?1024*1024:64*1024),.ENABLE_NNUE_BATCH(BATCH_ENABLED),
        .PIKAFISH_ONLY(PIKAFISH_ONLY),.HALF_OUTPUT(HALF_DENSE),.SPARSE_MODEL_ROWS(16),.ENABLE_CONV(CONV_ENABLED),.ENABLE_PFF1_GATHER(1),.ENABLE_NNUE_PIPELINE(NNUE_ENABLED),.ENABLE_H128_SPARSE(H128_ENABLED),
`ifdef PIKAFISH_BOOT_MIN_DRM
        .WEIGHT_BANK_LINES(64),.ENABLE_FP8(0)
`else
        .WEIGHT_BANK_LINES(1024),.ENABLE_FP8(1)
`endif
    ) u_mac(
        .clk(clk),.resetn(resetn),.reg_wr_en(reg_wr_en),
        .reg_wr_addr(reg_wr_addr),.reg_wr_data(reg_wr_data),
        .reg_wr_strb(reg_wr_strb),.reg_rd_addr(reg_rd_addr),
        .reg_rd_data(reg_rd_data),.irq(irq),
        .m_axi_awaddr(s1_awaddr),.m_axi_awlen(s1_awlen),
        .m_axi_awsize(s1_awsize),.m_axi_awburst(s1_awburst),
        .m_axi_awvalid(s1_awvalid),.m_axi_awready(s1_awready),
        .m_axi_wdata(s1_wdata),.m_axi_wstrb(s1_wstrb),
        .m_axi_wlast(s1_wlast),.m_axi_wvalid(s1_wvalid),
        .m_axi_wready(s1_wready),.m_axi_bresp(s1_bresp),
        .m_axi_bvalid(s1_bvalid),.m_axi_bready(s1_bready),
        .m_axi_araddr(s1_araddr),.m_axi_arlen(s1_arlen),
        .m_axi_arsize(s1_arsize),.m_axi_arburst(s1_arburst),
        .m_axi_arvalid(s1_arvalid),.m_axi_arready(s1_arready),
        .m_axi_rdata(s1_rdata),.m_axi_rresp(s1_rresp),
        .m_axi_rlast(s1_rlast),.m_axi_rvalid(s1_rvalid),
        .m_axi_rready(s1_rready));

    axi_2x1_arbiter u_arbiter(.*);

    axi_shared_ram #(.BASE(32'h1b00_0000),.BYTES(BATCH_ENABLED?1024*1024:64*1024),.PFF1_SYNTHETIC(1)) u_ram(
        .clk(clk),.resetn(resetn),.arid(m_arid),.araddr(m_araddr),
        .arlen(m_arlen),.arsize(m_arsize),.arburst(m_arburst),
        .arvalid(m_arvalid),.arready(m_arready),.rid(m_rid),
        .rdata(m_rdata),.rresp(m_rresp),.rlast(m_rlast),
        .rvalid(m_rvalid),.rready(m_rready),.awid(m_awid),
        .awaddr(m_awaddr),.awlen(m_awlen),.awsize(m_awsize),
        .awburst(m_awburst),.awvalid(m_awvalid),.awready(m_awready),
        .wid(m_wid),.wdata(m_wdata),.wstrb(m_wstrb),.wlast(m_wlast),
        .wvalid(m_wvalid),.wready(m_wready),.bid(m_bid),.bresp(m_bresp),
        .bvalid(m_bvalid),.bready(m_bready));

    task fail;input[255:0]why;begin
        $fatal(1,"FAIL tb_soc_mac_accel: %0s",why);
    end endtask

    task cpu_write_repeat;
        input[31:0]address;input integer beats;input[31:0]value;
        integer n;
        begin
            @(negedge clk);s0_awaddr=address;s0_awlen=beats-1;
            s0_awvalid=1;
            #1;
            while(!s0_awready)@(negedge clk);
            @(posedge clk);#1;@(negedge clk);s0_awvalid=0;
            for(n=0;n<beats;n=n+1)begin
                s0_wdata=value;s0_wlast=(n==beats-1);s0_wvalid=1;
                while(!s0_wready)@(negedge clk);
                @(posedge clk);#1;@(negedge clk);
            end
            s0_wvalid=0;s0_wlast=0;
            while(!s0_bvalid)@(negedge clk);
            if(s0_bresp!=0)fail("CPU DDR write response error");
            s0_bready=1;@(posedge clk);#1;@(negedge clk);s0_bready=0;
        end
    endtask

    task batch_job;
      input integer slot;input [31:0] parent;input integer terms;input [31:0] dest;
      integer j;
      begin
       cpu_write_repeat(32'h1b024000+slot*32,1,parent);
       cpu_write_repeat(32'h1b024004+slot*32,1,32'h1b021000);
       cpu_write_repeat(32'h1b024008+slot*32,1,terms);
       cpu_write_repeat(32'h1b02400c+slot*32,1,dest);
       for(j=4;j<8;j=j+1)cpu_write_repeat(32'h1b024000+slot*32+j*4,1,0);
      end
    endtask
    task batch_wait;
      input integer expected_error;
      integer ticks;
      begin
       reg_rd_addr=9'h08c;#1;ticks=0;
       while((reg_rd_data[0] || !reg_rd_data[1]) && ticks<300000)begin
        @(posedge clk);#1;ticks=ticks+1;
       end
       if(ticks==300000)begin
        $display("BATCH_TIMEOUT status=%h gather=%h owner=%d",reg_rd_data,u_mac.gather_reg_rd_data,u_mac.memory_owner);
        fail("batch timeout");
       end
       if(reg_rd_data[2]!==expected_error[0])begin
        $display("BATCH_STATUS=%h expected_error=%0d",reg_rd_data,expected_error);fail("batch status");
       end
      end
    endtask

    task cpu_read_word;
        input[31:0]address;output[31:0]value;
        begin
            @(negedge clk);s0_araddr=address;s0_arlen=0;s0_arvalid=1;
            #1;
            while(!s0_arready)@(negedge clk);
            @(posedge clk);#1;@(negedge clk);s0_arvalid=0;
            while(!s0_rvalid)@(negedge clk);
            if(s0_rresp!=0||!s0_rlast)fail("CPU DDR read response error");
            value=s0_rdata;s0_rready=1;
            @(posedge clk);#1;@(negedge clk);s0_rready=0;
        end
    endtask

    task reg_write;
        input[8:0]address;input[31:0]value;
        begin
            @(negedge clk);reg_wr_addr=address;reg_wr_data=value;
            reg_wr_en=1;@(posedge clk);#1;@(negedge clk);reg_wr_en=0;
        end
    endtask

    // Same-shape 1x1/4-input/16-output legacy baseline. Count only the MAC
    // AXI master, excluding CPU staging and result readback transactions.
    reg measure_legacy=0;
    integer legacy_input_bytes=0, legacy_weight_bytes=0;
    integer legacy_bias_bytes=0, legacy_output_bytes=0;
    integer legacy_read_bursts=0, legacy_write_bursts=0;
    always @(posedge clk) if (measure_legacy) begin
        if (s1_arvalid && s1_arready) begin
            legacy_read_bursts = legacy_read_bursts + 1;
            if (s1_arlen >= 8 ||
                (s1_araddr[11:0] + ((s1_arlen + 1) << 2)) > 4096)
                fail("legacy MAC read burst crosses 4 KiB or exceeds 8 beats");
            if (s1_araddr >= 32'h1b00_0000 && s1_araddr < 32'h1b00_1000)
                legacy_input_bytes = legacy_input_bytes + ((s1_arlen + 1) << 2);
            else if (s1_araddr >= 32'h1b00_1000 && s1_araddr < 32'h1b00_2000)
                legacy_weight_bytes = legacy_weight_bytes + ((s1_arlen + 1) << 2);
            else if (s1_araddr >= 32'h1b00_2000 && s1_araddr < 32'h1b00_3000)
                legacy_bias_bytes = legacy_bias_bytes + ((s1_arlen + 1) << 2);
            else fail("legacy MAC unexpected read address");
        end
        if (s1_awvalid && s1_awready) begin
            legacy_write_bursts = legacy_write_bursts + 1;
            if (s1_awlen >= 8 ||
                (s1_awaddr[11:0] + ((s1_awlen + 1) << 2)) > 4096 ||
                s1_awaddr < 32'h1b00_3000 || s1_awaddr >= 32'h1b00_4000)
                fail("legacy MAC invalid output burst");
            legacy_output_bytes = legacy_output_bytes + ((s1_awlen + 1) << 2);
        end
    end

    integer i,timeout;reg[31:0]value;
    integer nv,nr,nnue_stream_words=0,nnue_stream_commits=0,nnue_write_bursts=0;
    reg measure_nnue=0;
    reg[31:0]nnue_model[0:16383],nnue_golden[0:0];
    always @(posedge clk)if(resetn && NNUE_ENABLED)begin
        if(u_mac.gather_stream_valid)begin
            if(u_mac.gather_stream_data!==(u_mac.gather_stream_index[0]?32'h7ffe7ffe:32'h7ffc7ffc))
                fail("StageA local forwarding data");
            nnue_stream_words=nnue_stream_words+1;
        end
        if(u_mac.gather_stream_commit)nnue_stream_commits=nnue_stream_commits+1;
        if(measure_nnue && s1_awvalid && s1_awready)nnue_write_bursts=nnue_write_bursts+1;
        if(BATCH_ENABLED && s1_awvalid && s1_awready && s1_awaddr>=32'h1b0f0000 && s1_awaddr<32'h1b0f4000)
            fail("local batch context leaked to DDR");
    end
    initial begin
        repeat(500000)@(posedge clk);
        $fatal(1,"FAIL tb_soc_mac_accel: global timeout");
    end
    initial begin
        repeat(4)@(posedge clk);resetn=1;

        if(!PIKAFISH_ONLY)begin
        reg_rd_addr=8'h00;#1;if(reg_rd_data!=32'h4d41434b)
            fail("MAC ID mismatch");
        reg_rd_addr=8'h04;#1;if(reg_rd_data!=32'h00020100)
            fail("MAC version mismatch");

        // Maximum accepted dimensions exercise the narrowed count products.
        reg_write(8'h10,32'h01000010);
        reg_write(8'h14,32'h53000100);
        reg_rd_addr=8'h38;#1;if(reg_rd_data!=32'h02000400)
            fail("packed maximum input/weight line count mismatch");
        reg_rd_addr=8'h3c;#1;if(reg_rd_data!=32'h10000008)
            fail("packed maximum bias/output count mismatch");
        reg_write(8'h14,32'h43000100);
        reg_rd_addr=8'h38;#1;if(reg_rd_data!=32'h04000400)
            fail("legacy maximum input/weight line count mismatch");
        reg_rd_addr=8'h3c;#1;if(reg_rd_data!=32'h10000010)
            fail("legacy maximum bias/output count mismatch");

        $display("INFO tb_soc_mac_accel: staging shared DDR");
        cpu_write_repeat(32'h1b00_0000,2,32'h00010001);
        for(i=0;i<4;i=i+1)
            cpu_write_repeat(32'h1b00_1000+i*32,8,
                             {2{16'(i+1)}});
        cpu_write_repeat(32'h1b00_3000,8,32'hdeadbeef);
        cpu_write_repeat(32'h1b00_3020,8,32'hdeadbeef);

        $display("INFO tb_soc_mac_accel: programming MAC registers");
        reg_write(8'h08,32'h00000002);
        reg_write(8'h10,32'h00040001);
        reg_write(8'h14,32'h43000010);
        reg_write(8'h18,32'h1b000000);
        reg_write(8'h1c,32'h1b001000);
        reg_write(8'h20,32'h1b002000);
        reg_write(8'h24,32'h1b003000);
        measure_legacy=1;
        reg_write(8'h08,32'h00000001);

        $display("INFO tb_soc_mac_accel: waiting for DMA");
        reg_rd_addr=8'h0c;#1;timeout=0;
        while(!reg_rd_data[1]&&!reg_rd_data[2]&&timeout<200000)begin
            @(posedge clk);timeout=timeout+1;
        end
        if(timeout==200000)fail("MAC DMA timeout");
        if(reg_rd_data[2])fail("MAC DMA reported an error");
        measure_legacy=0;
        if (legacy_input_bytes != 8 || legacy_weight_bytes != 128 ||
            legacy_bias_bytes != 0 || legacy_output_bytes != 64 ||
            legacy_read_bursts == 0 || legacy_write_bursts == 0)
            fail("legacy MAC DDR byte baseline mismatch");
        $display("LEGACY_MAC_TRAFFIC_PASS input=%0d weight=%0d bias=%0d output=%0d read_bursts=%0d write_bursts=%0d",
                 legacy_input_bytes,legacy_weight_bytes,legacy_bias_bytes,
                 legacy_output_bytes,legacy_read_bursts,legacy_write_bursts);
        $display("INFO tb_soc_mac_accel: DMA status=%08x",reg_rd_data);

        for(i=0;i<16;i=i+1)begin
            cpu_read_word(32'h1b00_3000+i*4,value);
`ifdef MAC_CORE_STUB
            if(value!=(32'ha5000000|i))begin
`else
            if(value!=32'(4 * (i / 4 + 1)))begin
`endif
                $display("lane=%0d value=%08x",i,value);
                fail("MAC result mismatch");
            end
        end
        reg_rd_addr=8'h28;#1;
`ifdef MAC_CORE_STUB
        if(reg_rd_data>32'd161)begin
`else
        // Two half-output tiles add one11-cycle RAM/PE/bias pipeline fill.
        // The full-width baseline bound remains132; this is not the NNUE gate.
        if(reg_rd_data>(HALF_DENSE==2 ? 32'd160 : HALF_DENSE ? 32'd143 : 32'd132))begin
`endif
            $display("cycles=%0d",reg_rd_data);
            fail("MAC performance regression");
        end
        $display("INFO tb_soc_mac_accel: legacy MAC cycles=%0d",reg_rd_data);

        // Exercise real DDR bias assembly after the zero-bias path. The
        // first 48-bit lane has a distinct nonzero bias; all other lanes
        // remain zero, so word order and zero/DDR mode switching matter.
        cpu_write_repeat(32'h1b00_2000,48,32'b0);
        cpu_write_repeat(32'h1b00_2000,1,32'd7);
        reg_write(8'h08,32'h00000002);
        reg_write(8'h14,32'h03000010);
        reg_write(8'h08,32'h00000001);
        reg_rd_addr=8'h0c;#1;timeout=0;
        while(!reg_rd_data[1]&&!reg_rd_data[2]&&timeout<200000)begin
            @(posedge clk);timeout=timeout+1;
        end
        if(timeout==200000)fail("DDR-bias MAC timeout");
        if(reg_rd_data[2])fail("DDR-bias MAC reported an error");
        for(i=0;i<16;i=i+1)begin
            cpu_read_word(32'h1b00_3000+i*4,value);
            if(value!=32'(4 * (i / 4 + 1) + (i == 0 ? 7 : 0)))begin
                $display("bias lane=%0d value=%08x",i,value);
                fail("DDR-bias MAC result mismatch");
            end
        end
        reg_rd_addr=8'h28;#1;
        $display("DDR_BIAS_MAC_PASS cycles=%0d",reg_rd_data);

        // Cross both four-input and 32-output boundaries in packed mode.
        // [1,-1,1,-1,1] times all-one weights gives 1 for every valid lane.
        cpu_write_repeat(32'h1b00_0000,2,32'h00ff0001);
        cpu_write_repeat(32'h1b00_0008,1,32'h00000001);
        cpu_write_repeat(32'h1b00_000c,1,32'h00000000);
        cpu_write_repeat(32'h1b00_1000,128,32'h01010101);
        reg_write(8'h08,32'h00000002);
        reg_write(8'h10,32'h00050001);
        reg_write(8'h14,32'h53000021);
        reg_write(8'h08,32'h00000001);
        reg_rd_addr=8'h0c;#1;timeout=0;
        while(!reg_rd_data[1]&&!reg_rd_data[2]&&timeout<200000)begin
            @(posedge clk);timeout=timeout+1;
        end
        if(timeout==200000||reg_rd_data[2])fail("partial packed MAC failed");
        for(i=0;i<33;i=i+1)begin
            cpu_read_word(32'h1b00_3000+i*4,value);
            if(value!=32'd1)begin
                $display("partial lane=%0d value=%0d",i,value);
                fail("partial packed MAC result mismatch");
            end
        end
        reg_rd_addr=8'h28;#1;
        $display("PARTIAL_PACKED_MAC_PASS cycles=%0d",reg_rd_data);

        // Maximum accepted Cin reaches the 64th input tile in the MAC core.
        cpu_write_repeat(32'h1b00_0000,128,32'h00010001);
        for(i=0;i<8;i=i+1)
            cpu_write_repeat(32'h1b00_1000+i*1024,256,32'h01010101);
        reg_write(8'h08,32'h00000002);
        reg_write(8'h10,32'h01000001);
        reg_write(8'h14,32'h53000020);
        reg_write(8'h08,32'h00000001);
        reg_rd_addr=8'h0c;#1;timeout=0;
        while(!reg_rd_data[1]&&!reg_rd_data[2]&&timeout<200000)begin
            @(posedge clk);timeout=timeout+1;
        end
        if(timeout==200000||reg_rd_data[2])fail("maximum Cin MAC failed");
        for(i=0;i<32;i=i+1)begin
            cpu_read_word(32'h1b00_3000+i*4,value);
            if(value!=32'd256)begin
                $display("maximum Cin lane=%0d value=%0d",i,value);
                fail("maximum Cin MAC result mismatch");
            end
        end
        reg_rd_addr=8'h28;#1;
        $display("MAX_CIN_MAC_PASS cycles=%0d",reg_rd_data);

        // Maximum Cout crosses all eight packed output tiles.
        cpu_write_repeat(32'h1b00_0000,2,32'h00010001);
        cpu_write_repeat(32'h1b00_1000,256,32'h01010101);
        reg_write(8'h08,32'h00000002);
        reg_write(8'h10,32'h00040001);
        reg_write(8'h14,32'h53000100);
        reg_write(8'h08,32'h00000001);
        reg_rd_addr=8'h0c;#1;timeout=0;
        while(!reg_rd_data[1]&&!reg_rd_data[2]&&timeout<200000)begin
            @(posedge clk);timeout=timeout+1;
        end
        if(timeout==200000||reg_rd_data[2])fail("maximum Cout MAC failed");
        for(i=0;i<256;i=i+1)begin
            cpu_read_word(32'h1b00_3000+i*4,value);
            if(value!=32'd4)begin
                $display("maximum Cout lane=%0d value=%0d",i,value);
                fail("maximum Cout MAC result mismatch");
            end
        end
        reg_rd_addr=8'h28;#1;
        $display("MAX_COUT_MAC_PASS cycles=%0d",reg_rd_data);

        // Legacy mode reaches 16 output tiles with the same 256-lane bound.
        cpu_write_repeat(32'h1b00_1000,256,32'h00010001);
        cpu_write_repeat(32'h1b00_1400,256,32'h00010001);
        reg_write(8'h08,32'h00000002);
        reg_write(8'h14,32'h43000100);
        reg_write(8'h08,32'h00000001);
        reg_rd_addr=8'h0c;#1;timeout=0;
        while(!reg_rd_data[1]&&!reg_rd_data[2]&&timeout<200000)begin
            @(posedge clk);timeout=timeout+1;
        end
        if(timeout==200000||reg_rd_data[2])fail("legacy maximum Cout MAC failed");
        for(i=0;i<256;i=i+1)begin
            cpu_read_word(32'h1b00_3000+i*4,value);
            if(value!=32'd4)fail("legacy maximum Cout result mismatch");
        end
        reg_rd_addr=8'h28;#1;
        $display("LEGACY_MAX_COUT_MAC_PASS cycles=%0d",reg_rd_data);

        // Maximum Pixels exercises the 5-bit pixel index rollover.
        cpu_write_repeat(32'h1b00_0000,32,32'h00010001);
        reg_write(8'h08,32'h00000002);
        reg_write(8'h10,32'h00040010);
        reg_write(8'h14,32'h43000010);
        reg_write(8'h08,32'h00000001);
        reg_rd_addr=8'h0c;#1;timeout=0;
        while(!reg_rd_data[1]&&!reg_rd_data[2]&&timeout<200000)begin
            @(posedge clk);timeout=timeout+1;
        end
        if(timeout==200000||reg_rd_data[2])fail("maximum Pixels MAC failed");
        for(i=0;i<256;i=i+1)begin
            cpu_read_word(32'h1b00_3000+i*4,value);
            if(value!=32'd4)fail("maximum Pixels result mismatch");
        end
        reg_rd_addr=8'h28;#1;
        $display("MAX_PIXELS_MAC_PASS cycles=%0d",reg_rd_data);
        reg_write(8'h14,32'h03000010);
        end else begin
            reg_rd_addr=9'h000;#1;if(reg_rd_data!=32'h50464e31)fail("dedicated ID");
            reg_rd_addr=9'h184;#1;if(reg_rd_data!=32'h00020000)fail("dedicated version");
            reg_rd_addr=9'h1c0;#1;if(reg_rd_data!=1)fail("dedicated capability");
            reg_write(9'h008,1);reg_rd_addr=9'h00c;#1;
            if(reg_rd_data!=6)fail("dedicated generic dense rejection");
            repeat(32)begin @(posedge clk);#1;
                if(s1_arvalid || s1_awvalid)fail("rejected dense emitted DMA");
            end
            $display("PIKAFISH_GENERIC_DENSE_REJECT_PASS");
        end

        if(H128_ENABLED) begin
        // Exercise the sparse evaluator through the same DDR arbiter and AXI
        // RAM. Parent red/black are 1000, row0 is +1, row1 is +2 and both
        // output-weight banks are +1. A -row0/+row1 child therefore scores 5.
        reg_rd_addr=8'h80;#1;if(reg_rd_data!=32'h58515345)
            fail("sparse evaluator ID mismatch");
        cpu_write_repeat(32'h1b004000,32,32'h01010101);
        cpu_write_repeat(32'h1b004080,32,32'h02020202);
        cpu_write_repeat(32'h1b005000,256,32'd1000);
        cpu_write_repeat(32'h1b005400,64,32'h01010101);
        cpu_write_repeat(32'h1b005600,1,32'd0);
        cpu_write_repeat(32'h1b005604,1,32'd0);
        cpu_write_repeat(32'h1b005608,1,32'd1);
        cpu_write_repeat(32'h1b00560c,1,32'hffffffff);
        cpu_write_repeat(32'h1b005610,1,32'hffffffff);
        cpu_write_repeat(32'h1b005614,1,32'hffffffff);
        cpu_write_repeat(32'h1b005618,1,32'hffffffff);
        cpu_write_repeat(32'h1b00561c,1,32'd0);

        reg_write(8'h90,32'd1);
        reg_write(8'h94,32'h1b004000);
        reg_write(8'h98,32'h1b005000);
        reg_write(8'h9c,32'h1b005400);
        reg_write(8'ha0,32'h1b005600);
        reg_write(8'ha4,32'd0);
        reg_write(8'ha8,32'd0);
        reg_write(8'h88,32'd1);
        reg_rd_addr=8'h8c;#1;timeout=0;
        while(!reg_rd_data[1]&&timeout<200000)begin
            @(posedge clk);#1;timeout=timeout+1;
        end
        if(timeout==200000)fail("sparse evaluator timeout");
        if(reg_rd_data[2])begin
            $display("sparse status=%08x",reg_rd_data);
            fail("sparse evaluator reported an error");
        end
        reg_rd_addr=8'hc0;#1;
        if($signed(reg_rd_data)!=5)begin
            $display("sparse result=%0d",$signed(reg_rd_data));
            fail("sparse evaluator result mismatch");
        end
        reg_rd_addr=8'hac;#1;
        if(reg_rd_data==0||reg_rd_data>2000)
            fail("sparse evaluator cycle budget regression");
        $display("PASS tb_soc_mac_accel legacy=161 sparse=%0d",
                 reg_rd_data);
        end else begin
            if(!BATCH_ENABLED)for(i=128;i<256;i=i+4)begin
                reg_write(i,32'hffffffff);reg_rd_addr=i;#1;
                if(reg_rd_data!==0)fail("disabled H128 MMIO must read zero");
            end
            repeat(64)begin @(posedge clk);#1;
                if(u_mac.sparse_req_valid!==0 || u_mac.sparse_irq!==0 || s1_arvalid!==0 || s1_awvalid!==0)
                    fail("disabled H128 generated an IRQ or DDR request");
            end
            $display("H128_DISABLED_MMIO_IRQ_DDR_PASS registers=32 idle_cycles=64");
        end
        // All three DMA clients and a CPU share the actual AXI adapter/arbiter.
        // threat - PSQ - threat leaves base - PSQ, including signed wrap.
        reg_rd_addr=9'h100;#1;if(reg_rd_data!=32'h50464741)fail("gather decode ID");
        reg_rd_addr=9'h104;#1;if(reg_rd_data!=32'h00020000)fail("gather decode version");
        cpu_write_repeat(32'h1b008000,256,32'h7fff8000);
        cpu_write_repeat(32'h1b008400,256,32'h7fff8000);
        cpu_write_repeat(32'h1b009000,1,0);
        cpu_write_repeat(32'h1b009004,1,32'hc0000000);
        cpu_write_repeat(32'h1b009008,1,32'h80000000);
        cpu_write_repeat(32'h1b00a000-4,1,32'hdeadbeef);
        cpu_write_repeat(32'h1b00a800,1,32'hdeadbeef);
        reg_write(9'h110,32'h1b008000);reg_write(9'h114,32'h1b009000);
        reg_write(9'h118,32'h1b00a000);reg_write(9'h11c,3);
        cpu_write_repeat(32'h1b000000,2,32'h00010001);
        cpu_write_repeat(32'h1b001000,32,32'h01010101);
        reg_write(9'h010,32'h00040001);reg_write(9'h014,32'h53000010);
        reg_write(9'h018,32'h1b000000);reg_write(9'h01c,32'h1b001000);
        reg_write(9'h024,32'h1b003000);
        if(NNUE_ENABLED)begin reg_write(9'h128,1);reg_write(9'h12c,32'h75000010);end
        reg_write(9'h108,1);reg_write(9'h008,1);
        cpu_read_word(32'h1b00a800,value);if(value!=32'hdeadbeef)fail("CPU concurrent read");
        reg_rd_addr=9'h10c;#1;timeout=0;
        while(!reg_rd_data[1] && timeout<20000)begin @(posedge clk);#1;timeout=timeout+1;end
        if(timeout==20000 || reg_rd_data[2])fail("gather shared AXI completion");
        for(i=0;i<512;i=i+1)begin
            cpu_read_word(32'h1b00a000+i*4,value);
            if(value!==(i[0]?32'h7ffe7ffe:32'h7ffc7ffc))fail("gather shared AXI output");
        end
        cpu_read_word(32'h1b009ffc,value);if(value!=32'hdeadbeef)fail("gather leading canary");
        cpu_read_word(32'h1b00a800,value);if(value!=32'hdeadbeef)fail("gather trailing canary");
        if(!PIKAFISH_ONLY)begin
            reg_rd_addr=9'h00c;#1;if(!reg_rd_data[1]||reg_rd_data[2])fail("dense concurrent completion");
            cpu_read_word(32'h1b003000,value);if(value!=4)fail("dense concurrent output");
        end
        reg_rd_addr=9'h0c0;#1;if(!BATCH_ENABLED && reg_rd_data!=(H128_ENABLED?5:0))fail("gather corrupted sparse score register");
        reg_rd_addr=9'h120;#1;
        $display("SOC_STAGEA_GATHER_PASS terms=3 cycles=%0d concurrent=dense,cpu h128_enabled=%0d",reg_rd_data,H128_ENABLED);
        if(!PIKAFISH_ONLY)begin
        // Narrow offset arithmetic must keep exact-end and overflow behavior.
        cpu_write_repeat(32'h1b00fff8,2,32'h00010001);
        reg_write(9'h018,32'h1b00fff8);reg_write(9'h024,32'h1b00ffc0);
        reg_write(9'h008,1);reg_rd_addr=9'h00c;#1;timeout=0;
        while(!reg_rd_data[1] && timeout<20000)begin @(posedge clk);#1;timeout=timeout+1;end
        if(timeout==20000 || reg_rd_data[2])fail("dense exact scratch end");
        cpu_read_word(32'h1b00fffc,value);if(value!=4)fail("dense exact end output");
        reg_write(9'h018,32'h1b00fffc);reg_write(9'h008,1);
        reg_rd_addr=9'h00c;#1;if(!reg_rd_data[2] || reg_rd_data[15:12]!=2)fail("dense end overflow accepted");
        reg_write(9'h018,32'hfffffffC);reg_write(9'h008,1);
        reg_rd_addr=9'h00c;#1;if(!reg_rd_data[2] || reg_rd_data[15:12]!=2)fail("dense high address accepted");
        $display("DENSE_SCRATCH_BOUNDARY_PASS exact_end=65536 overflow=reject");
`ifdef PIKAFISH_BOOT_MIN_DRM
        // Pikafish FC0 uses exactly 64 weight lines. A larger dense job must
        // fail before DMA, otherwise the compact bank would wrap silently.
        reg_write(9'h008,2);
        reg_write(9'h010,32'h01000001);
        reg_write(9'h014,32'h53000040);
        reg_write(9'h018,32'h1b000000);
        reg_write(9'h01c,32'h1b001000);
        reg_write(9'h020,32'h1b002000);
        reg_write(9'h024,32'h1b003000);
        reg_write(9'h008,1);
        reg_rd_addr=9'h00c;#1;
        if(!reg_rd_data[2] || reg_rd_data[15:12]!=1)
            fail("compact bank accepted 128 weight lines");
        // This boot-only profile omits FP8 decode logic. Reject that mode
        // explicitly while retaining the generic profile's FP8 engine.
        reg_write(9'h008,2);
        reg_write(9'h014,32'h73000020);
        reg_write(9'h008,1);
        reg_rd_addr=9'h00c;#1;
        if(!reg_rd_data[2] || reg_rd_data[15:12]!=1)
            fail("Pikafish boot profile accepted unsupported FP8 job");
        $display("PIKAFISH_BOOT_MIN_DRM_PASS lines=64 overflow=reject");
`endif
        // The maximum S16 descriptor uses 4096 compact physical bank words.
        // Distinct
        // pixels and channels detect address wrap, duplicated and skipped data.
        for(i=0;i<16;i=i+1)
            cpu_write_repeat(32'h1b000000+i*8,2,((i+1)<<16)|(i+1));
        for(i=0;i<512;i=i+1)
            cpu_write_repeat(32'h1b001000+i*4,1,((i/2+1)<<16)|(i/2+1));
        cpu_write_repeat(32'h1b005ffc,1,32'hdeadbeef);
        cpu_write_repeat(32'h1b00a000,1,32'hdeadbeef);
        reg_write(9'h008,2);
        reg_write(9'h010,32'h00040010);reg_write(9'h014,32'h43000100);
        reg_write(9'h018,32'h1b000000);reg_write(9'h01c,32'h1b001000);
        reg_write(9'h020,32'h1b002000);reg_write(9'h024,32'h1b006000);
        reg_write(9'h008,1);reg_rd_addr=9'h00c;#1;timeout=0;
        while(!reg_rd_data[1] && timeout<200000)begin @(posedge clk);#1;timeout=timeout+1;end
        if(timeout==200000 || reg_rd_data[2])fail("S16 maximum output descriptor");
        reg_rd_addr=9'h028;#1;
        // 16pixels*16old tiles*11extra fill cycles, fixed DDR traffic.
        // Q32 adds 11 fixed cycles for each additional output tile.
        // Full13800 + (1024 quarter tiles -256 full tiles)*11 =22248.
        if(reg_rd_data>(HALF_DENSE==2 ? 32'd22248 : HALF_DENSE ? 32'd16616 : 32'd13800))fail("S16 maximum output performance regression");
        $display("S16_MAX_OUTPUT_CYCLES cycles=%0d",reg_rd_data);
        for(i=0;i<4096;i=i+1)begin
            cpu_read_word(32'h1b006000+i*4,value);
            if(value!==32'(4*(i/256+1)*(i%256+1)))begin
                $display("S16 maximum output element=%0d got=%0d expected=%0d",i,value,4*(i/256+1)*(i%256+1));
                fail("S16 maximum output mismatch");
            end
        end
        cpu_read_word(32'h1b005ffc,value);if(value!=32'hdeadbeef)fail("S16 leading guard");
        cpu_read_word(32'h1b00a000,value);if(value!=32'hdeadbeef)fail("S16 trailing guard");
        $display("S16_MAX_OUTPUT_PASS pixels=16 cout=256 words=4096 bank_last=4095");
        end
        if(NNUE_ENABLED)begin
            if(nnue_stream_words!=512 || nnue_stream_commits!=1)fail("StageA local commit accounting");
            $readmemh("nnue-model.hex",nnue_model);$readmemh("nnue-golden.hex",nnue_golden);
            for(i=0;i<16384;i=i+1)cpu_write_repeat(32'h1b000000+i*4,1,nnue_model[i]);
            reg_rd_addr=9'h180;#1;if(reg_rd_data!=32'h4e4e5031)fail("NNUE pipeline capability ID");
            // View0 is consumed directly from the preceding real StageA job.
            // Only view1 requires an initial cache upload. Both clip to255.
            reg_write(9'h19c,256);reg_write(9'h1a0,32'h75000011);reg_write(9'h188,8);
            for(i=0;i<512;i=i+1)reg_write(9'h1a8,32'h00ff00ff);
            reg_write(9'h188,16);
            reg_write(9'h190,32'h1b000000);reg_write(9'h194,32'h75000010);reg_write(9'h198,32'h75000011);
            for(nr=0;nr<2;nr=nr+1)begin
                measure_nnue=1;nnue_write_bursts=0;
                reg_write(9'h188,1);reg_rd_addr=9'h18c;#1;timeout=0;
                while((!reg_rd_data[1] || reg_rd_data[0]) && timeout<100000)begin @(posedge clk);#1;timeout=timeout+1;end
                if(timeout==100000 || reg_rd_data[2])fail("NNUE pipeline shared AXI completion");
                reg_rd_addr=9'h1ac;#1;if(reg_rd_data!==nnue_golden[0])fail("NNUE full C score");
                reg_rd_addr=9'h1b4;#1;if(reg_rd_data!=6)fail("NNUE full job count");
                if(nnue_write_bursts!=0)fail("NNUE intermediate result written to DDR");
                measure_nnue=0;
                if(PIKAFISH_ONLY)begin
                    reg_rd_addr=9'h1c8;#1;if(reg_rd_data!=8801)fail("dedicated cold model reads");
                    reg_write(9'h188,1);reg_rd_addr=9'h18c;#1;timeout=0;
                    while((!reg_rd_data[1] || reg_rd_data[0]) && timeout<10000)begin @(posedge clk);#1;timeout=timeout+1;end
                    if(timeout==10000 || reg_rd_data[2])fail("dedicated warm completion");
                    reg_rd_addr=9'h1ac;#1;if(reg_rd_data!==nnue_golden[0])fail("dedicated warm score");
                    reg_rd_addr=9'h1c8;#1;if(reg_rd_data!=0)fail("dedicated warm DDR reads");
                    reg_rd_addr=9'h1c4;#1;if(reg_rd_data!=3)fail("dedicated cache status");
                    reg_write(9'h188,64);
                    @(posedge clk);#1;
                    reg_rd_addr=9'h1c4;#1;if(reg_rd_data[0])fail("dedicated invalidate");
                    $display("PIKAFISH_SOC_CACHE_PASS cold_reads=8801 warm_reads=0 explicit_invalidate=pass");
                end
                if(nr==0)begin
                    // An incorrect tag is rejected, then a complete re-upload recovers.
                    reg_write(9'h198,32'hdeadbeef);reg_write(9'h188,1);reg_rd_addr=9'h18c;#1;timeout=0;
                    while((!reg_rd_data[1] || reg_rd_data[0]) && timeout<10000)begin @(posedge clk);#1;timeout=timeout+1;end
                    if(timeout==10000 || !reg_rd_data[2])fail("NNUE stale context accepted");
                    for(nv=0;nv<2;nv=nv+1)begin
                        reg_write(9'h19c,nv*256);reg_write(9'h1a0,32'h75000010+nv);reg_write(9'h188,8);
                        for(i=0;i<512;i=i+1)reg_write(9'h1a8,32'h00ff00ff);
                        reg_write(9'h188,16);
                    end
                    reg_write(9'h198,32'h75000011);
                end
            end
            $display("NNUE_SOC_DIRECT_PIPELINE_PASS stagea_words=512 mlp_jobs=6 intermediate_DDR_writes=0 stale_recovery=pass");
        end
        if(BATCH_ENABLED)begin
         reg [31:0] resident_cycle_count,external_cycle_count;
         reg_rd_addr=9'h080;#1;if(reg_rd_data!=32'h50464231)fail("batch ID");
         cpu_write_repeat(32'h1b020000,256,32'h02000200);
         cpu_write_repeat(32'h1b020400,256,32'h02000200);
         cpu_write_repeat(32'h1b021000,1,0);
         cpu_write_repeat(32'h1b021004,1,32'hc0000000);
         cpu_write_repeat(32'h1b021008,1,32'h80000000);
         batch_job(0,32'h1b020000,3,32'h1b022000);
         batch_job(1,32'h1b0f0000,3,32'h1b022800);
         batch_job(2,32'h1b0f0800,0,32'h1b023000);
         batch_job(3,32'h1b020000,1,32'h1b023800);
         reg_write(9'h090,32'h1b024000);reg_write(9'h094,4);
         reg_write(9'h098,32'h1b000000);reg_write(9'h09c,32'h232);
         reg_write(9'h088,1);batch_wait(0);
         reg_rd_addr=9'h0a8;#1;if(reg_rd_data!==nnue_golden[0])fail("batch complete score");
         reg_rd_addr=9'h0a4;#1;if(reg_rd_data!=4)fail("batch completed count");
         reg_rd_addr=9'h0b4;#1;if(reg_rd_data!=1024)fail("batch local base reads");
         reg_rd_addr=9'h0b8;#1;if(reg_rd_data!=2048)fail("batch local output writes");
         reg_rd_addr=9'h0bc;#1;if(reg_rd_data!=2048)fail("batch rollback export words");
         for(nv=0;nv<4;nv=nv+1)for(i=0;i<512;i=i+1)begin
          cpu_read_word(32'h1b022000+nv*2048+i*4,value);
          // Independent S16 lane arithmetic for synthetic known rows.
          if(nv<3)begin
           if(value!=={16'(512-(nv==0?1:2)*(i[0]?1:3)),16'(512-(nv==0?1:2)*(i[0]?2:4))})
            fail("batch dependent exported accumulator");
          end else begin
           if(value!==(i[0]?32'h0180027f:32'h01ff0201))fail("batch independent exported accumulator");
          end
         end
         $display("PIKAFISH_BATCH_DEPENDENT_PASS jobs=4 local_reads=1024 local_writes=2048 exports=2048 exact_score=pass");
         // Reuse the preceding two evaluation inputs without any DDR base read.
         batch_job(0,32'h1b0f1000,0,32'h1b029000);
         batch_job(1,32'h1b0f1800,0,32'h1b029800);
         reg_write(9'h094,2);reg_write(9'h09c,32'h610);
         reg_write(9'h088,1);batch_wait(0);
         reg_rd_addr=9'h0a8;#1;if(reg_rd_data!==nnue_golden[0])fail("resident exact score");
         reg_rd_addr=9'h0b0;#1;if(reg_rd_data!=0)fail("resident external base reads");
         reg_rd_addr=9'h0b4;#1;if(reg_rd_data!=1024)fail("resident local base reads");
         reg_rd_addr=9'h0bc;#1;if(reg_rd_data!=1024)fail("resident export count");
         reg_rd_addr=9'h0a0;#1;resident_cycle_count=reg_rd_data;
         for(i=0;i<512;i=i+1)begin
          cpu_read_word(32'h1b029000+i*4,value);
          if(value!=={16'(512-2*(i[0]?1:3)),16'(512-2*(i[0]?2:4))})fail("resident reused accumulator");
          cpu_read_word(32'h1b029800+i*4,value);
          if(value!==(i[0]?32'h0180027f:32'h01ff0201))fail("resident second accumulator");
         end
         // Same two values and warm MLP cache; legacy external-base path.
         batch_job(0,32'h1b023000,0,32'h1b029000);
         batch_job(1,32'h1b023800,0,32'h1b029800);
         reg_write(9'h09c,32'h210);reg_write(9'h088,1);batch_wait(0);
         reg_rd_addr=9'h0a8;#1;if(reg_rd_data!==nnue_golden[0])fail("external comparison score");
         reg_rd_addr=9'h0b0;#1;if(reg_rd_data!=1024)fail("external comparison reads");
         reg_rd_addr=9'h0a0;#1;external_cycle_count=reg_rd_data;
         $display("ACCUM_RESIDENT_CYCLES external=%0d resident=%0d external_base_words=1024 resident_base_words=0",external_cycle_count,resident_cycle_count);
         // Reusing the same slot as its output must preserve every S16 lane.
         batch_job(0,32'h1b0f0000,0,32'h1b029000);
         batch_job(1,32'h1b0f0800,0,32'h1b029800);
         reg_write(9'h09c,32'h610);reg_write(9'h088,1);batch_wait(0);
         reg_rd_addr=9'h0a8;#1;if(reg_rd_data!==nnue_golden[0])fail("resident inplace score");
         // Legacy start cleared old slots2/3, so retain cannot resurrect them.
         batch_job(0,32'h1b0f1000,0,0);
         reg_write(9'h094,1);reg_write(9'h09c,32'h400);reg_write(9'h088,1);batch_wait(1);
         $display("ACCUM_RESIDENT_CROSS_BATCH_S16_SCORE_INPLACE_AND_INVALIDATION_PASS");
         // All eight slots, signed wrap, and a descriptor list across4KiB.
         cpu_write_repeat(32'h1b020000,256,32'h7fff8000);
         cpu_write_repeat(32'h1b020400,256,32'h7fff8000);
         cpu_write_repeat(32'h1b021ffc,1,0);
         cpu_write_repeat(32'h1b022000,1,32'hc0000000);
         cpu_write_repeat(32'h1b022004,1,32'h80000000);
         for(nv=0;nv<8;nv=nv+1)begin
          batch_job(nv,nv==0?32'h1b020000:32'h1b0f0000+(nv-1)*2048,3,nv==7?32'h1b028000:0);
          cpu_write_repeat(32'h1b024004+nv*32,1,32'h1b021ffc);
         end
         reg_write(9'h094,8);reg_write(9'h09c,0);reg_write(9'h088,1);batch_wait(0);
         for(i=0;i<512;i=i+1)begin
          cpu_read_word(32'h1b028000+i*4,value);
          if(value!=={16'(32767-8*(i[0]?1:3)),16'(32768-8*(i[0]?2:4))})fail("batch eight-slot wrapped accumulator");
         end
         reg_rd_addr=9'h0b4;#1;if(reg_rd_data!=3584)fail("batch eight-slot local reads");
         $display("PIKAFISH_BATCH_EIGHT_SLOTS_WRAP_4K_PASS jobs=8 local_reads=3584 intermediate_DDR_writes=0");
         // Per-batch validity rejects a previous batch's slot before any gather.
         batch_job(0,32'h1b0f0000,1,0);reg_write(9'h094,1);reg_write(9'h09c,0);
         reg_write(9'h088,1);batch_wait(1);
         reg_rd_addr=9'h0a4;#1;if(reg_rd_data!=0)fail("batch stale context executed");
         // Overflowing list/config fields, bad feature descriptors and DDR errors.
         reg_write(9'h094,32'h10001);reg_write(9'h088,1);batch_wait(1);
         reg_write(9'h094,1);batch_job(0,32'h1b020000,257,0);reg_write(9'h088,1);batch_wait(1);
         batch_job(0,32'h1b020000,1,0);cpu_write_repeat(32'h1b021000,1,32'h00010000);
         reg_write(9'h088,1);batch_wait(1);
         cpu_write_repeat(32'h1b021000,1,1);reg_write(9'h088,1);batch_wait(1);
         cpu_write_repeat(32'h1b021000,1,0);reg_write(9'h088,1);
         repeat(100)@(posedge clk);reg_write(9'h088,4);batch_wait(1);
         // Recovery and no-export mode retain local outputs without AXI writes.
         reg_write(9'h088,1);batch_wait(0);
         reg_rd_addr=9'h0bc;#1;if(reg_rd_data!=0)fail("batch unexpected rollback export");
         $display("PIKAFISH_BATCH_REJECT_DRAIN_RECOVERY_PASS stale=reject overflow=reject descriptor=reject ddr=reject stop=drained");
        end
        $finish;
    end
endmodule
