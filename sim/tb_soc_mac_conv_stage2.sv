`timescale 1ns / 1ps
module tb_soc_mac_conv_stage2;
    reg clk=0,resetn=0;
    always #5 clk=~clk;
    reg reg_wr_en=0;
    reg [8:0]reg_wr_addr=0,reg_rd_addr=0;
    reg [31:0]reg_wr_data=0;
    reg [3:0]reg_wr_strb=4'hf;
    wire [31:0]reg_rd_data;
    wire irq;
    wire [31:0]m_axi_awaddr,m_axi_wdata,m_axi_araddr,m_axi_rdata;
    wire [7:0]m_axi_awlen,m_axi_arlen;
    wire [2:0]m_axi_awsize,m_axi_arsize;
    wire [1:0]m_axi_awburst,m_axi_bresp,m_axi_arburst,m_axi_rresp;
    wire [3:0]m_axi_wstrb;
    wire m_axi_awvalid,m_axi_awready,m_axi_wlast,m_axi_wvalid,m_axi_wready;
    wire m_axi_bvalid,m_axi_bready,m_axi_arvalid,m_axi_arready;
    wire m_axi_rlast,m_axi_rvalid,m_axi_rready;
    wire [3:0] ram_rid,ram_bid;
    reg [31:0] source_rom[0:100],expected_rom[0:443];
    reg [31:0] compute_source[0:3],compute_weight[0:31];
    reg [7:0] compute_expected[0:19];
    reg [31:0] baseline_source[0:0],baseline_weight[0:31];
    reg [7:0] baseline_expected[0:15];
    reg [31:0] partial_source[0:0],partial_weight[0:31];
    reg [7:0] partial_expected[0:4];
    integer i,j,dense_wait,taps=0,input_bursts=0,weight_bursts=0,clock_count=0,start_clock;
    reg [31:0] value;

    mac_accel_ddr_kernel_top #(
        .DDR_BASE(32'h1b00_0000),.DDR_BYTES(64*1024),
        .SPARSE_MODEL_ROWS(16),.ENABLE_CONV(1)
    ) dut (.*);
    axi_shared_ram #(.BASE(32'h1b00_0000),.BYTES(64*1024)) ram (
        .clk(clk),.resetn(resetn),
        .arid(4'd0),.araddr(m_axi_araddr),.arlen(m_axi_arlen),
        .arsize(m_axi_arsize),.arburst(m_axi_arburst),
        .arvalid(m_axi_arvalid),.arready(m_axi_arready),
        .rid(ram_rid),.rdata(m_axi_rdata),.rresp(m_axi_rresp),
        .rlast(m_axi_rlast),.rvalid(m_axi_rvalid),.rready(m_axi_rready),
        .awid(4'd0),.awaddr(m_axi_awaddr),.awlen(m_axi_awlen),
        .awsize(m_axi_awsize),.awburst(m_axi_awburst),
        .awvalid(m_axi_awvalid),.awready(m_axi_awready),
        .wid(4'd0),.wdata(m_axi_wdata),.wstrb(m_axi_wstrb),
        .wlast(m_axi_wlast),.wvalid(m_axi_wvalid),.wready(m_axi_wready),
        .bid(ram_bid),.bresp(m_axi_bresp),.bvalid(m_axi_bvalid),
        .bready(m_axi_bready)
    );
    initial begin
        $readmemh("sim/vectors/yolo_window_board_source.hex",source_rom);
        $readmemh("sim/vectors/yolo_window_board_expected.hex",expected_rom);
        $readmemh("sim/vectors/yolo_compute_point_tail_source.hex",compute_source);
        $readmemh("sim/vectors/yolo_compute_point_tail_weights.hex",compute_weight);
        $readmemh("sim/vectors/yolo_compute_point_tail_expected.hex",compute_expected);
        $readmemh("sim/vectors/yolo_compute_baseline_source.hex",baseline_source);
        $readmemh("sim/vectors/yolo_compute_baseline_weights.hex",baseline_weight);
        $readmemh("sim/vectors/yolo_compute_baseline_expected.hex",baseline_expected);
        $readmemh("sim/vectors/yolo_compute_partial_source.hex",partial_source);
        $readmemh("sim/vectors/yolo_compute_partial_weights.hex",partial_weight);
        $readmemh("sim/vectors/yolo_compute_partial_expected.hex",partial_expected);
        for (i=0;i<49;i=i+1)
            ram.memory[(16'h6000>>2)+i]=source_rom[52+i];
        for (i=0;i<864;i=i+1) begin
            ram.memory[(16'h7000>>2)+i]=i;
            ram.memory[(16'h9000>>2)+i]=1024+i;
        end
        for (i=0;i<4;i=i+1)
            ram.memory[(16'ha000>>2)+i]=compute_source[i];
        for (i=0;i<32;i=i+1)
            ram.memory[(16'hc000>>2)+i]=compute_weight[i];
    end
    always @(posedge clk) if (resetn) begin
        clock_count<=clock_count+1;
        if (m_axi_arvalid && m_axi_arready) begin
            if (m_axi_arlen>=8 ||
                (m_axi_araddr[11:0]+((m_axi_arlen+1)<<2))>4096)
                $fatal(1,"SoC convolution burst invalid");
            if (m_axi_araddr>=32'h1b00_6000 && m_axi_araddr<32'h1b00_7000)
                input_bursts<=input_bursts+1;
            else if (m_axi_araddr>=32'h1b00_7000 &&
                     m_axi_araddr<32'h1b00_a000)
                weight_bursts<=weight_bursts+1;
            else if (m_axi_araddr>=32'h1b00_a000 &&
                     m_axi_araddr<32'h1b00_a010) input_bursts<=input_bursts+1;
            else if (m_axi_araddr>=32'h1b00_c000 &&
                     m_axi_araddr<32'h1b00_c080) weight_bursts<=weight_bursts+1;
            else if ((m_axi_araddr>=32'h1b00_0000 &&
                      m_axi_araddr<32'h1b00_0008) ||
                     (m_axi_araddr>=32'h1b00_1000 &&
                      m_axi_araddr<32'h1b00_1080)) begin end
            else $fatal(1,"SoC unexpected DDR read %h",m_axi_araddr);
        end
        if (dut.g_conv.u_conv.tap_valid && dut.g_conv.u_conv.tap_ready &&
            !dut.g_conv.u_conv.compute_active) begin
            if (taps>=324 || dut.g_conv.u_conv.tap_data!==expected_rom[120+taps])
                $fatal(1,"SoC convolution tap mismatch %0d",taps);
            taps<=taps+1;
        end
    end
    task write_reg;
        input [7:0]address;
        input [31:0]data;
        begin
            @(negedge clk);reg_wr_addr=address;reg_wr_data=data;reg_wr_en=1;
            @(negedge clk);reg_wr_en=0;
        end
    endtask
    task read_reg;
        input [7:0]address;
        output [31:0]data;
        begin reg_rd_addr=address;#1;data=reg_rd_data;end
    endtask
    task wait_status;
        input [31:0] mask;
        integer count;
        begin
            count=0;value=0;
            while ((value&mask)!=mask && count<8000) begin
                @(negedge clk);read_reg(8'h48,value);
                if (value[2] || value[5])
                    $fatal(1,"SoC convolution status error %h",value);
                count=count+1;
            end
            if (count==8000) $fatal(1,"SoC convolution timeout mask=%h",mask);
        end
    endtask
    initial begin
        repeat(4) @(negedge clk);resetn=1;
        read_reg(8'h00,value);
        if (value!=32'h4d41_434b) $fatal(1,"legacy MAC ID changed");
        write_reg(8'h24,32'h1b00_b000);
        read_reg(8'h24,value);
        if (value!=32'h1b00_b000) $fatal(1,"legacy OUTPUT_DST changed");
        read_reg(8'h80,value);
        if (value!=32'h5851_5345) $fatal(1,"sparse engine ID changed");
        read_reg(8'h40,value);
        if (value!=32'h4d43_4f4e) $fatal(1,"new convolution ID missing");
        write_reg(8'h4c,{16'd7,16'd7});
        write_reg(8'h50,32'h0226_0003);
        write_reg(8'h54,{16'd16,16'd0});
        write_reg(8'h58,32'h1b00_6000);
        write_reg(8'h5c,32'h1b00_7000);
        write_reg(8'h60,32'h1b00_8000);
        write_reg(8'h64,27);
        write_reg(8'h68,32'h9abc_def0);
        write_reg(8'h6c,32'h1234_5678);
        write_reg(8'h70,1);
        write_reg(8'h48,1);
        wait_status(32'h42);
        write_reg(8'h48,2);
        write_reg(8'h48,8);
        write_reg(8'h48,4);
        write_reg(8'h5c,32'h1b00_9000);
        write_reg(8'h70,2);
        write_reg(8'h48,1);
        wait_status(32'h52);
        if (taps!=324 || input_bursts!=7 || weight_bursts!=216)
            $fatal(1,"SoC conv counts wrong taps=%0d in_bursts=%0d wt_bursts=%0d",
                   taps,input_bursts,weight_bursts);
        write_reg(8'h78,0);read_reg(8'h7c,value);
        if (value!=196) $fatal(1,"SoC input bytes wrong %0d",value);
        write_reg(8'h78,1);read_reg(8'h7c,value);
        if (value!=3456) $fatal(1,"SoC weight bytes wrong %0d",value);
        $display("SOC_MAC_CONV_STAGE2_PASS taps=%0d input_bytes=196 weight_bytes=3456 legacy_output_dst=1b00b000",taps);
        write_reg(8'h48,2); // Activate the previously prefetched bank.
        write_reg(8'h4c,{16'd2,16'd2});
        write_reg(8'h50,32'h0011_0004);
        write_reg(8'h54,32'h0005_0000);
        write_reg(8'h58,32'h1b00_a000);
        write_reg(8'h5c,32'h1b00_c000);
        write_reg(8'h60,32'h1b00_e000);
        write_reg(8'h64,1);
        write_reg(8'h70,3);
        write_reg(8'h48,8);
        write_reg(8'h48,1);wait_status(32'h42);
        write_reg(8'h48,2);
        for (i=0;i<5;i=i+1) begin
            write_reg(8'h78,8'h20+i);write_reg(8'h7c,i*13-50);
            write_reg(8'h78,8'h40+i);write_reg(8'h7c,i%4+2);
        end
        write_reg(8'h48,8);
        write_reg(8'h48,16);wait_status(32'h100);
        for (i=0;i<20;i=i+1)
            if (ram.memory[(16'he000>>2)+(i>>2)][(i%4)*8 +: 8] !==
                compute_expected[i])
                $fatal(1,"SoC compute mismatch byte=%0d",i);
        write_reg(8'h78,12);read_reg(8'h7c,value);
        if (value!=20) $fatal(1,"SoC compact output bytes=%0d",value);
        read_reg(8'h24,value);
        if (value!=32'h1b00_b000) $fatal(1,"legacy OUTPUT_DST altered");
        $display("SOC_MAC_CONV_COMPUTE_PASS output_bytes=20 legacy_output_dst=1b00b000");
        ram.memory[(16'ha000>>2)]=baseline_source[0];
        for (i=0;i<32;i=i+1)
            ram.memory[(16'hc000>>2)+i]=baseline_weight[i];
        write_reg(8'h4c,{16'd1,16'd1});
        write_reg(8'h50,32'h0011_0004);
        write_reg(8'h54,32'h0010_0000);
        write_reg(8'h64,1);
        write_reg(8'h70,4);
        write_reg(8'h48,8);
        write_reg(8'h48,1);wait_status(32'h42);
        write_reg(8'h48,2);
        for (i=0;i<16;i=i+1) begin
            write_reg(8'h78,8'h20+i);write_reg(8'h7c,i*13-50);
            write_reg(8'h78,8'h40+i);write_reg(8'h7c,i%4+2);
        end
        write_reg(8'h48,8);
        write_reg(8'h48,16);start_clock=clock_count;
        wait_status(32'h100);
        for (i=0;i<16;i=i+1)
            if (ram.memory[(16'he000>>2)+(i>>2)][(i%4)*8 +: 8] !==
                baseline_expected[i])
                $fatal(1,"SoC baseline compute mismatch byte=%0d",i);
        write_reg(8'h78,0);read_reg(8'h7c,value);
        if (value!=4) $fatal(1,"SoC baseline input bytes=%0d",value);
        write_reg(8'h78,1);read_reg(8'h7c,value);
        if (value!=128) $fatal(1,"SoC baseline weight bytes=%0d",value);
        write_reg(8'h78,12);read_reg(8'h7c,value);
        if (value!=16) $fatal(1,"SoC baseline output bytes=%0d",value);
        if (clock_count-start_clock>161)
            $fatal(1,"SoC compact compute slower than legacy baseline cycles=%0d",clock_count-start_clock);
        $display("SOC_MAC_CONV_SAME_SHAPE_PASS input=4 weight=128 output=16 cycles=%0d legacy_input=8 legacy_weight=128 legacy_output=64 legacy_cycles=161",clock_count-start_clock);
        ram.memory[(16'ha000>>2)]=partial_source[0];
        for (i=0;i<32;i=i+1)
            ram.memory[(16'hc000>>2)+i]=partial_weight[i];
        ram.memory[(16'he000>>2)]=32'haaaa_aaaa;
        ram.memory[(16'he004>>2)]=32'haabb_ccdd;
        write_reg(8'h54,32'h0005_0000);
        write_reg(8'h70,5);
        write_reg(8'h48,8);
        write_reg(8'h48,1);wait_status(32'h42);
        write_reg(8'h48,2);
        write_reg(8'h48,8);
        write_reg(8'h48,16);wait_status(32'h100);
        for (i=0;i<5;i=i+1)
            if (ram.memory[(16'he000>>2)+(i>>2)][(i%4)*8 +: 8] !==
                partial_expected[i])
                $fatal(1,"SoC partial byte mismatch index=%0d",i);
        if (ram.memory[(16'he004>>2)][31:8] !== 24'haabbcc)
            $fatal(1,"SoC partial write corrupted inactive byte lanes");
        write_reg(8'h78,12);read_reg(8'h7c,value);
        if (value!=5) $fatal(1,"SoC partial output byte counter=%0d",value);
        $display("SOC_MAC_CONV_PARTIAL_STROBE_PASS output_bytes=5 high_lanes=aabbcc");
        // Match the Linux scheduler's 384 sequential dense jobs after
        // convolution traffic, then prove CPU MMIO and DDR remain live.
        ram.memory[0]=32'h0001_0001;
        ram.memory[1]=32'h0001_0001;
        for (i=0;i<32;i=i+1)
            ram.memory[(16'h1000>>2)+i]=32'h0001_0001;
        write_reg(8'h10,32'h0004_0001);
        write_reg(8'h14,32'h4300_0010);
        write_reg(8'h18,32'h1b00_0000);
        write_reg(8'h1c,32'h1b00_1000);
        write_reg(8'h20,32'h1b00_2000);
        write_reg(8'h24,32'h1b00_3000);
        start_clock=clock_count;
        for (j=0;j<384;j=j+1) begin
            write_reg(8'h08,2);
            write_reg(8'h08,1);
            dense_wait=0;
            read_reg(8'h0c,value);
            while (!value[1] && !value[2] && dense_wait<3000) begin
                @(negedge clk);read_reg(8'h0c,value);
                dense_wait=dense_wait+1;
            end
            if (dense_wait==3000 || value[2])
                $fatal(1,"SoC dense scheduler stress failed job=%0d status=%h",j,value);
        end
        read_reg(8'h00,value);
        if (value!=32'h4d41_434b) $fatal(1,"SoC MMIO dead after dense stress");
        for (i=0;i<16;i=i+1)
            if (ram.memory[(16'h3000>>2)+i]!==32'd4)
                $fatal(1,"SoC dense stress output mismatch lane=%0d",i);
        if (clock_count-start_clock>384*250)
            $fatal(1,"SoC dense scheduler stress slower than budget cycles=%0d",clock_count-start_clock);
        $display("SOC_MAC_CONV_DENSE_SCHEDULER_STRESS_PASS jobs=384 cycles=%0d",clock_count-start_clock);
        $finish;
    end
    initial begin #2000000; $fatal(1,"SoC conv global timeout"); end
endmodule
