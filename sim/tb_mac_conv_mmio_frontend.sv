`timescale 1ns / 1ps
module tb_mac_conv_mmio_frontend;
    reg clk=0,resetn=0;
    always #5 clk=~clk;
    reg reg_wr_en=0;
    reg [7:0] reg_wr_addr=0,reg_rd_addr=0;
    reg [31:0] reg_wr_data=0;
    reg [3:0] reg_wr_strb=4'hf;
    wire [31:0] reg_rd_data;
    wire mem_req_valid,mem_req_write,mem_req_ready,mem_rsp_valid;
    wire mem_rsp_ready,mem_rsp_last,mem_rsp_error,mem_abort;
    wire [31:0] mem_req_addr,mem_rsp_rdata;
    wire [2:0] mem_req_len;
    wire mem_w_valid,mem_w_last;
    reg mem_w_ready=0;
    wire [31:0] mem_w_data;
    wire [3:0] mem_w_strb;
    wire tap_valid;
    reg tap_ready=1;
    wire [31:0] tap_data;
    wire [8:0] tap_x,tap_y;
    wire [2:0] tap_kx,tap_ky;
    wire [7:0] tap_tile;
    reg rsp_active=0;
    reg [31:0] rsp_addr=0;
    reg [3:0] rsp_left=0;
    reg [31:0] source_rom[0:100],expected_rom[0:443];
    integer taps=0,wait_count=0;

    mac_conv_mmio_frontend #(
        .DDR_BASE(32'h1000_0000),.DDR_BYTES(64*1024),
        .MAX_WIDTH(16),.TIMEOUT_CYCLES(100)
    ) dut (.*);
    initial begin
        $readmemh("sim/vectors/yolo_window_board_source.hex",source_rom);
        $readmemh("sim/vectors/yolo_window_board_expected.hex",expected_rom);
    end
    assign mem_req_ready=!rsp_active;
    assign mem_rsp_valid=rsp_active;
    assign mem_rsp_last=rsp_left==1;
    assign mem_rsp_error=0;
    assign mem_rsp_rdata=rsp_addr>=32'h1000_3000 &&
                         rsp_addr<32'h1000_30c4 ?
                         source_rom[52+((rsp_addr-32'h1000_3000)>>2)] :
                         ((rsp_addr-32'h1000_4000)>>2);
    always @(posedge clk) begin
        if (!resetn || mem_abort) begin
            rsp_active<=0;rsp_addr<=0;rsp_left<=0;
        end else if (mem_req_valid && mem_req_ready) begin
            if (mem_req_write || mem_req_len>=8 ||
                (mem_req_addr[11:0]+((mem_req_len+1)<<2))>4096)
                $fatal(1,"invalid MMIO frontend burst");
            rsp_active<=1;rsp_addr<=mem_req_addr;
            rsp_left<=mem_req_len+1;
        end else if (mem_rsp_valid && mem_rsp_ready) begin
            if (rsp_left==1)rsp_active<=0;
            else begin rsp_addr<=rsp_addr+4;rsp_left<=rsp_left-1;end
        end
        if (resetn && tap_valid && tap_ready) begin
            if (taps>=324 || tap_data!==expected_rom[120+taps] ||
                tap_x!=(taps/36)%3 || tap_y!=(taps/36)/3 ||
                tap_kx!=taps%6 || tap_ky!=(taps%36)/6 || tap_tile!=0)
                $fatal(1,"MMIO frontend tap mismatch %0d",taps);
            taps<=taps+1;
        end
    end
    task write_reg;
        input [7:0] address;
        input [31:0] value;
        begin
            @(negedge clk);reg_wr_en=1;reg_wr_addr=address;reg_wr_data=value;
            @(negedge clk);reg_wr_en=0;
        end
    endtask
    task read_reg;
        input [7:0] address;
        output [31:0] value;
        begin reg_rd_addr=address;#1;value=reg_rd_data;end
    endtask
    task wait_status;
        input [31:0] mask;
        reg [31:0] value;
        begin
            value=0;wait_count=0;
            while ((value&mask)!=mask && wait_count<3000) begin
                @(negedge clk);read_reg(8'h48,value);
                if (value[2] || value[5])
                    $fatal(1,"MMIO frontend reported error status=%h",value);
                wait_count=wait_count+1;
            end
            if (wait_count==3000) $fatal(1,"MMIO frontend status timeout mask=%h",mask);
        end
    endtask
    reg [31:0] value;
    initial begin
        repeat(4) @(negedge clk);resetn=1;
        read_reg(8'h40,value);
        if (value!=32'h4d434f4e) $fatal(1,"conv MMIO ID wrong");
        read_reg(8'h44,value);
        if (value!=32'h0003_0000) $fatal(1,"conv MMIO version wrong");
        write_reg(8'h4c,{16'd7,16'd7});
        write_reg(8'h50,32'h0226_0003); // pad 2, stride 2, kernel 6, cin 3
        write_reg(8'h54,{16'd16,16'd0});
        write_reg(8'h58,32'h1000_3000);
        write_reg(8'h5c,32'h1000_4000);
        write_reg(8'h60,32'h1000_6000);
        write_reg(8'h64,26); // short first-layer weight tile
        write_reg(8'h68,32'h9abc_def0);
        write_reg(8'h6c,32'h1234_5678);
        write_reg(8'h70,1);
        write_reg(8'h48,1);
        read_reg(8'h48,value);
        if (!value[2] || value[15:12]!=3 || mem_req_valid)
            $fatal(1,"short weight tile not rejected status=%h",value);
        write_reg(8'h48,8); // clear errors and counters
        write_reg(8'h64,27);
        write_reg(8'h48,1); // DMA load weight bank 1
        wait_status(32'h0000_0042); // weight done + pending
        write_reg(8'h48,2); // activate bank 1
        read_reg(8'h48,value);
        if (!value[7] || value[6]) $fatal(1,"weight activation failed status=%h",value);
        write_reg(8'h48,8);
        write_reg(8'h48,4); // start image DMA/window
        write_reg(8'h5c,32'h1000_5000);
        write_reg(8'h70,2);
        write_reg(8'h48,1); // prefetch bank 2 concurrently
        wait_status(32'h0000_0052); // input done + weight done + pending
        read_reg(8'h48,value);
        if (taps!=324 || !value[7])
            $fatal(1,"concurrent MMIO jobs incomplete taps=%0d status=%h",taps,value);
        write_reg(8'h78,0);read_reg(8'h7c,value);
        if (value!=196) $fatal(1,"input DDR byte counter wrong %0d",value);
        write_reg(8'h78,1);read_reg(8'h7c,value);
        if (value!=3456) $fatal(1,"weight DDR byte counter wrong %0d",value);
        write_reg(8'h78,2);read_reg(8'h7c,value);
        if (value!=324) $fatal(1,"tap counter wrong %0d",value);
        write_reg(8'h78,3);read_reg(8'h7c,value);
        if (value!=9) $fatal(1,"weight reuse counter wrong %0d",value);
        write_reg(8'h78,8);read_reg(8'h7c,value);
        if (value!=1) $fatal(1,"active generation changed before swap");
        write_reg(8'h78,11);read_reg(8'h7c,value);
        if (value==0) $fatal(1,"full 1024-bit weight read digest missing");
        write_reg(8'h48,2); // now activate generation 2
        write_reg(8'h78,8);read_reg(8'h7c,value);
        if (value!=2) $fatal(1,"generation 2 activation failed");
        $display("MAC_CONV_MMIO_FRONTEND_PASS taps=%0d input_bytes=196 weight_bytes=3456 reuse=9",taps);
        $finish;
    end
    initial begin #300000; $fatal(1,"MMIO frontend global timeout"); end
endmodule
