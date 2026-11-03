`timescale 1ns/1ps
module tb_soc_mac_conv_full_layer;
    reg clk=0,resetn=0;
    always #5 clk=~clk;
    reg reg_wr_en=0;
    reg [8:0] reg_wr_addr=0,reg_rd_addr=0;
    reg [31:0] reg_wr_data=0;
    reg [3:0] reg_wr_strb=4'hf;
    wire [31:0] reg_rd_data;
    wire irq;
    wire [31:0] m_axi_awaddr,m_axi_wdata,m_axi_araddr,m_axi_rdata;
    wire [7:0] m_axi_awlen,m_axi_arlen;
    wire [2:0] m_axi_awsize,m_axi_arsize;
    wire [1:0] m_axi_awburst,m_axi_bresp,m_axi_arburst,m_axi_rresp;
    wire [3:0] m_axi_wstrb;
    wire m_axi_awvalid,m_axi_awready,m_axi_wlast,m_axi_wvalid,m_axi_wready;
    wire m_axi_bvalid,m_axi_bready,m_axi_arvalid,m_axi_arready;
    wire m_axi_rlast,m_axi_rvalid,m_axi_rready;
    wire [3:0] ram_rid,ram_bid;
    integer i,lane,oc,scalar,logical,word_index;
    integer wall_cycles=0,compute_start_cycles;
    reg [31:0] value,crc,word;

    mac_accel_ddr_kernel_top #(
        .DDR_BASE(32'h1b00_0000),.DDR_BYTES(1024*1024),
        .SPARSE_MODEL_ROWS(16),.ENABLE_CONV(1),.ENABLE_H128_SPARSE(0),.WEIGHT_BANK_LINES(64),.ENABLE_FP8(0)
    ) dut (.*);
    axi_shared_ram #(.BASE(32'h1b00_0000),.BYTES(1024*1024)) ram (
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
        for (i=0;i<102400;i=i+1) begin
            word=0;
            for (lane=0;lane<4;lane=lane+1)
                word[lane*8 +: 8]=((i*4+lane)*29+
                    ((i*4+lane)/7)*13+34)&255;
            ram.memory[i]=word;
            ram.memory[(32'h80000>>2)+i]=32'ha5a5_a5a5;
        end
        for (i=0;i<864;i=i+1)
            ram.memory[(32'h70000>>2)+i]=0;
        for (oc=0;oc<16;oc=oc+1)
            for (scalar=0;scalar<108;scalar=scalar+1) begin
                logical=((oc*3+scalar%3)*6+
                         (scalar/3)/6)*6+(scalar/3)%6;
                word_index=(32'h70000>>2)+(scalar/4)*32+oc;
                ram.memory[word_index][(scalar%4)*8 +: 8]=
                    ((logical*11+(logical/108)*3)&15)-8;
            end
    end
    always @(posedge clk) if (resetn) begin
        wall_cycles<=wall_cycles+1;
        if (m_axi_awvalid && m_axi_awready &&
            (m_axi_awaddr<32'h1b08_0000 ||
             m_axi_awaddr>=32'h1b0e_4000 || m_axi_awlen!=0))
            $fatal(1,"full layer unexpected DDR write addr=%h",m_axi_awaddr);
        if (m_axi_arvalid && m_axi_arready &&
            (m_axi_arlen>=8 ||
             m_axi_araddr[11:0]+((m_axi_arlen+1)<<2)>4096))
            $fatal(1,"full layer illegal DDR read burst");
    end
    task write_reg(input [7:0] addr,input [31:0] data);
        begin
            @(negedge clk);reg_wr_en=1;reg_wr_addr=addr;reg_wr_data=data;
            @(negedge clk);reg_wr_en=0;
        end
    endtask
    task read_reg(input [7:0] addr,output [31:0] data);
        begin reg_rd_addr=addr;#1;data=reg_rd_data;end
    endtask
    task wait_bit(input integer bit_index);
        integer count;
        reg [31:0] status;
        begin
            count=0;status=0;
            while (!status[bit_index] && count<20000000) begin
                @(negedge clk);read_reg(8'h48,status);
                if (status[9] || status[5] || status[2])
                    $fatal(1,"full layer status error=%h",status);
                count=count+1;
            end
            if (!status[bit_index]) $fatal(1,"full layer timeout bit=%0d",bit_index);
        end
    endtask
    task counter(input [7:0] select,output [31:0] result);
        begin write_reg(8'h78,select);read_reg(8'h7c,result);end
    endtask
    initial begin
        repeat(4) @(negedge clk);resetn=1;
        write_reg(8'h4c,{16'd320,16'd320});
        write_reg(8'h50,32'h0226_0003);
        write_reg(8'h54,32'h0010_0000);
        write_reg(8'h58,32'h1b00_0000);
        write_reg(8'h5c,32'h1b07_0000);
        write_reg(8'h60,32'h1b08_0000);
        write_reg(8'h64,27);
        write_reg(8'h68,32'h4d43_4f4e);
        write_reg(8'h6c,32'h40);
        write_reg(8'h70,32'h40);
        for (oc=0;oc<16;oc=oc+1) begin
            write_reg(8'h78,8'h20+oc);write_reg(8'h7c,oc*13-50);
            write_reg(8'h78,8'h40+oc);write_reg(8'h7c,oc%4+2);
        end
        write_reg(8'h48,1);wait_bit(1);
        write_reg(8'h48,2);
        write_reg(8'h48,8);
        write_reg(8'h48,16);
        compute_start_cycles=wall_cycles;
        wait_bit(8);
        counter(0,value);if (value!=409600) $fatal(1,"full input bytes=%0d",value);
        counter(1,value);if (value!=3456) $fatal(1,"full weight bytes=%0d",value);
        counter(2,value);if (value!=921600) $fatal(1,"full taps=%0d",value);
        counter(3,value);if (value!=25600) $fatal(1,"full reuse=%0d",value);
        counter(12,value);if (value!=409600) $fatal(1,"full output bytes=%0d",value);
        counter(13,value);if (value==0) $fatal(1,"full compute cycles missing");
        crc=32'hffff_ffff;
        for (i=0;i<102400;i=i+1) begin
            word=ram.memory[(32'h80000>>2)+i];
            for (lane=0;lane<4;lane=lane+1) begin
                crc=crc^(word>>(lane*8)&255);
                for (integer bit_index=0;bit_index<8;bit_index=bit_index+1)
                    crc=(crc>>1)^((crc&1) ? 32'hedb8_8320 : 0);
            end
        end
        crc=crc^32'hffff_ffff;
        if (crc!=32'heb24_0272) $fatal(1,"full output CRC=%h",crc);
        if (wall_cycles-compute_start_cycles > 16000000)
            $fatal(1,"full first layer exceeds stage-2 cycle budget: %0d",wall_cycles-compute_start_cycles);
        $display("SOC_MAC_CONV_FULL_FIRST_LAYER_PASS input=409600 weight=3456 output=409600 taps=921600 reuse=25600 crc=eb240272 job_cycles=%0d",wall_cycles-compute_start_cycles);
        $finish;
    end
    initial begin #500000000;$fatal(1,"full layer global timeout");end
endmodule
