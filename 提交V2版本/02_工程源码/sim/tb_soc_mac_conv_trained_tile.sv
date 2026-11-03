`timescale 1ns/1ps
module tb_soc_mac_conv_trained_tile;
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
    reg [31:0] expected[0:255];
    integer i,cycles=0,begin_cycles;
    reg [31:0] value,word;
`include "sim/vectors/trained_conv_tile/bias.vh"

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
        $readmemh("sim/vectors/trained_conv_tile/input.hex",ram.memory,0,255);
        $readmemh("sim/vectors/trained_conv_tile/weights.hex",ram.memory,
                  (32'h70000>>2),(32'h70000>>2)+863);
        $readmemh("sim/vectors/trained_conv_tile/expected.hex",expected);
        for(i=0;i<256;i=i+1) ram.memory[(32'h80000>>2)+i]=32'ha5a5a5a5;
    end
    always @(posedge clk) if (resetn) begin
        cycles<=cycles+1;
        if(m_axi_awvalid && m_axi_awready &&
           (m_axi_awaddr<32'h1b08_0000 ||
            m_axi_awaddr>=32'h1b08_0400 || m_axi_awlen!=0))
            $fatal(1,"unexpected DDR write addr=%h",m_axi_awaddr);
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
            while(!status[bit_index] && count<200000) begin
                @(negedge clk);read_reg(8'h48,status);
                if(status[9] || status[5] || status[2])
                    $fatal(1,"trained tile status error=%h",status);
                count=count+1;
            end
            if(!status[bit_index]) $fatal(1,"trained tile timeout");
        end
    endtask
    task counter(input [7:0] select,output [31:0] result);
        begin write_reg(8'h78,select);read_reg(8'h7c,result);end
    endtask
    initial begin
        repeat(4) @(negedge clk);resetn=1;
        write_reg(8'h4c,{16'd16,16'd16});
        write_reg(8'h50,32'h0226_0003);
        write_reg(8'h54,32'h0010_0000);
        write_reg(8'h58,32'h1b00_0000);
        write_reg(8'h5c,32'h1b07_0000);
        write_reg(8'h60,32'h1b08_0000);
        write_reg(8'h64,27);
        write_reg(8'h68,32'h4d43_4f4e);
        write_reg(8'h6c,32'h8ff15d34);
        write_reg(8'h70,32'h885fe98e);
        for(i=0;i<16;i=i+1) begin
            // This vector's bias/shift values are loaded from a generated
            // include so simulation and bare-metal use identical parameters.
            write_reg(8'h78,8'h20+i);write_reg(8'h7c,tile_bias(i));
            write_reg(8'h78,8'h40+i);write_reg(8'h7c,10);
        end
        write_reg(8'h48,1);wait_bit(1);
        write_reg(8'h48,2);
        write_reg(8'h48,8);
        write_reg(8'h48,16);
        begin_cycles=cycles;
        wait_bit(8);
        counter(0,value);if(value!=1024) $fatal(1,"input bytes=%0d",value);
        counter(1,value);if(value!=3456) $fatal(1,"weight bytes=%0d",value);
        counter(2,value);if(value!=2304) $fatal(1,"tap count=%0d",value);
        counter(3,value);if(value!=64) $fatal(1,"reuse count=%0d",value);
        counter(12,value);if(value!=1024) $fatal(1,"output bytes=%0d",value);
        counter(13,value);if(value==0) $fatal(1,"compute cycles absent");
        for(i=0;i<256;i=i+1) begin
            word=ram.memory[(32'h80000>>2)+i];
            if(word!==expected[i])
                $fatal(1,"trained tile mismatch word=%0d actual=%h expected=%h",
                       i,word,expected[i]);
        end
        if(cycles-begin_cycles>100000)
            $fatal(1,"trained tile performance regression cycles=%0d",
                   cycles-begin_cycles);
        $display("SOC_MAC_CONV_TRAINED_TILE_PASS input=1024 weight=3456 output=1024 taps=2304 cycles=%0d",cycles-begin_cycles);
        $finish;
    end
    initial begin #5000000;$fatal(1,"global timeout");end
endmodule
