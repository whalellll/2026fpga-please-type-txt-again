`timescale 1ns/1ps
module tb_mac_conv_mmio_compute;
    parameter integer CASE_ID=0;
    localparam integer WIDTH=CASE_ID==0 ? 2 : CASE_ID==1 ? 3 : CASE_ID==2 ? 7 : 1;
    localparam integer HEIGHT=WIDTH;
    localparam integer CIN=CASE_ID==2 ? 3 : 4;
    localparam integer KERNEL=CASE_ID==0 || CASE_ID>=3 ? 1 : CASE_ID==1 ? 3 : 6;
    localparam integer STRIDE=CASE_ID==2 ? 2 : 1;
    localparam integer PADDING=CASE_ID==0 || CASE_ID>=3 ? 0 : CASE_ID==1 ? 1 : 2;
    localparam integer COUT=CASE_ID==0 || CASE_ID==4 ? 5 : CASE_ID==1 ? 8 : 16;
    localparam integer SOURCE_BYTES=WIDTH*HEIGHT*4;
    localparam integer WEIGHT_LINES=(CIN*KERNEL*KERNEL+3)/4;
    localparam integer OUTPUT_BYTES=CASE_ID==0 ? 20 : CASE_ID==1 ? 72 : CASE_ID==2 ? 144 : CASE_ID==3 ? 16 : 5;
    reg clk=0,resetn=0;
    always #5 clk=~clk;
    reg reg_wr_en=0;
    reg [7:0] reg_wr_addr=0,reg_rd_addr=0;
    reg [31:0] reg_wr_data=0;
    reg [3:0] reg_wr_strb=4'hf;
    wire [31:0] reg_rd_data;
    wire mem_req_valid,mem_req_ready,mem_req_write;
    wire [31:0] mem_req_addr;
    wire [2:0] mem_req_len;
    wire mem_w_valid,mem_w_ready,mem_w_last;
    wire [31:0] mem_w_data;
    wire [3:0] mem_w_strb;
    wire mem_rsp_valid,mem_rsp_ready,mem_rsp_last,mem_rsp_error;
    wire [31:0] mem_rsp_rdata;
    wire mem_abort;
    wire tap_valid;
    wire [31:0] tap_data;
    wire [8:0] tap_x,tap_y;
    wire [2:0] tap_kx,tap_ky;
    wire [7:0] tap_tile;
    reg [31:0] source_rom[0:48],weight_rom[0:863];
    reg [7:0] expected[0:143],actual[0:143];
    reg [1:0] mem_state=0;
    reg [31:0] rsp_addr=0;
    reg [3:0] rsp_left=0;
    reg response_write=0;
    reg inject_write_error=0;
    integer read_bytes=0,write_bytes=0,write_words=0,cycles=0,i,start_cycle,strobes;
    reg [31:0] status,value;

    mac_conv_mmio_frontend #(
        .DDR_BASE(32'h1000_0000),.DDR_BYTES(64*1024),
        .MAX_WIDTH(16),.TIMEOUT_CYCLES(100)
    ) dut (.*,.tap_ready(1'b1));
    initial begin
        if (CASE_ID==0) begin
            $readmemh("sim/vectors/yolo_compute_point_tail_source.hex",source_rom,0,SOURCE_BYTES/4-1);
            $readmemh("sim/vectors/yolo_compute_point_tail_weights.hex",weight_rom,0,WEIGHT_LINES*32-1);
            $readmemh("sim/vectors/yolo_compute_point_tail_expected.hex",expected,0,OUTPUT_BYTES-1);
        end else if (CASE_ID==1) begin
            $readmemh("sim/vectors/yolo_compute_border_source.hex",source_rom,0,SOURCE_BYTES/4-1);
            $readmemh("sim/vectors/yolo_compute_border_weights.hex",weight_rom,0,WEIGHT_LINES*32-1);
            $readmemh("sim/vectors/yolo_compute_border_expected.hex",expected,0,OUTPUT_BYTES-1);
        end else if (CASE_ID==2) begin
            $readmemh("sim/vectors/yolo_compute_first_kernel_source.hex",source_rom,0,SOURCE_BYTES/4-1);
            $readmemh("sim/vectors/yolo_compute_first_kernel_weights.hex",weight_rom,0,WEIGHT_LINES*32-1);
            $readmemh("sim/vectors/yolo_compute_first_kernel_expected.hex",expected,0,OUTPUT_BYTES-1);
        end else if (CASE_ID==3) begin
            $readmemh("sim/vectors/yolo_compute_baseline_source.hex",source_rom,0,SOURCE_BYTES/4-1);
            $readmemh("sim/vectors/yolo_compute_baseline_weights.hex",weight_rom,0,WEIGHT_LINES*32-1);
            $readmemh("sim/vectors/yolo_compute_baseline_expected.hex",expected,0,OUTPUT_BYTES-1);
        end else begin
            $readmemh("sim/vectors/yolo_compute_partial_source.hex",source_rom,0,SOURCE_BYTES/4-1);
            $readmemh("sim/vectors/yolo_compute_partial_weights.hex",weight_rom,0,WEIGHT_LINES*32-1);
            $readmemh("sim/vectors/yolo_compute_partial_expected.hex",expected,0,OUTPUT_BYTES-1);
        end
    end
    assign mem_req_ready=mem_state==0;
    assign mem_w_ready=mem_state==2;
    assign mem_rsp_valid=mem_state==1 || mem_state==3;
    assign mem_rsp_last=mem_state==3 || rsp_left==1;
    assign mem_rsp_error=mem_state==3 && inject_write_error;
    assign mem_rsp_rdata=rsp_addr>=32'h1000_1000 && rsp_addr<32'h1000_1000+SOURCE_BYTES ?
        source_rom[(rsp_addr-32'h1000_1000)>>2] :
        weight_rom[(rsp_addr-32'h1000_2000)>>2];
    always @(posedge clk) begin
        if (!resetn || mem_abort) begin
            mem_state<=0;rsp_addr<=0;rsp_left<=0;response_write<=0;
        end else begin
            cycles<=cycles+1;
            if (mem_req_valid && mem_req_ready) begin
                if (mem_req_addr[11:0]+((mem_req_len+1)<<2)>4096)
                    $fatal(1,"compute burst crossed 4 KiB");
                rsp_addr<=mem_req_addr;rsp_left<=mem_req_len+1;
                response_write<=mem_req_write;
                mem_state<=mem_req_write ? 2 : 1;
                if (mem_req_write && mem_req_len!=0)
                    $fatal(1,"compact writer must use one beat");
            end else if (mem_state==1 && mem_rsp_ready) begin
                read_bytes<=read_bytes+4;
                if (rsp_left==1) mem_state<=0;
                else begin rsp_addr<=rsp_addr+4;rsp_left<=rsp_left-1;end
            end else if (mem_state==2 && mem_w_valid) begin
                if (!mem_w_last || rsp_addr<32'h1000_3000 ||
                    rsp_addr>=32'h1000_3000+OUTPUT_BYTES ||
                    mem_w_strb!=(rsp_addr+4>32'h1000_3000+OUTPUT_BYTES ?
                                 4'h1 : 4'hf))
                    $fatal(1,"bad compact output beat addr=%h strobe=%h",rsp_addr,mem_w_strb);
                strobes=0;
                for (integer lane=0;lane<4;lane=lane+1)
                    if (mem_w_strb[lane]) begin
                        actual[rsp_addr-32'h1000_3000+lane]<=mem_w_data[lane*8+:8];
                        strobes=strobes+1;
                    end
                write_bytes<=write_bytes+strobes;
                write_words<=write_words+1;
                mem_state<=3;
            end else if (mem_state==3 && mem_rsp_ready) mem_state<=0;
        end
    end
    task write_reg(input [7:0] address,input [31:0] data);
        begin
            @(negedge clk);reg_wr_en=1;reg_wr_addr=address;reg_wr_data=data;
            @(negedge clk);reg_wr_en=0;
        end
    endtask
    task read_reg(input [7:0] address,output [31:0] data);
        begin reg_rd_addr=address;#1;data=reg_rd_data;end
    endtask
    task wait_bit(input integer bit_index);
        integer count;
        begin
            count=0;status=0;
            while (!status[bit_index] && count<10000) begin
                @(negedge clk);read_reg(8'h48,status);
                if (status[9] || status[5] || status[2])
                    $fatal(1,"compute MMIO error status=%h",status);
                count=count+1;
            end
            if (!status[bit_index]) $fatal(1,"compute MMIO timeout bit=%0d",bit_index);
        end
    endtask
    initial begin
        repeat(4) @(negedge clk);resetn=1;
        read_reg(8'h44,value);
        if (value!=32'h0003_0000) $fatal(1,"compute capability version missing");
        write_reg(8'h4c,{HEIGHT[15:0],WIDTH[15:0]});
        write_reg(8'h50,(PADDING<<24)|(STRIDE<<20)|(KERNEL<<16)|CIN);
        write_reg(8'h54,COUT<<16);
        write_reg(8'h58,32'h1000_1000);
        write_reg(8'h5c,32'h1000_2000);
        write_reg(8'h60,32'h1000_3000);
        write_reg(8'h64,WEIGHT_LINES);
        write_reg(8'h68,32'h1122_3344);
        write_reg(8'h6c,32'h5566_7788);
        write_reg(8'h70,1);
        for (i=0;i<COUT;i=i+1) begin
            write_reg(8'h78,8'h20+i);write_reg(8'h7c,i*13-50);
            write_reg(8'h78,8'h40+i);write_reg(8'h7c,i%4+2);
        end
        write_reg(8'h48,1);wait_bit(1);
        write_reg(8'h48,2);
        write_reg(8'h48,8);
        write_reg(8'h48,16);
        start_cycle=cycles;
        if (CASE_ID==2) begin
            // A pending next-layer descriptor must not alter the in-flight tile.
            write_reg(8'h4c,{16'd1,16'd1});
            write_reg(8'h50,32'h0011_0004);
            write_reg(8'h54,32'h0001_0000);
        end
        wait_bit(8);
        if (write_bytes!=OUTPUT_BYTES || write_words!=(OUTPUT_BYTES+3)/4 ||
            read_bytes!=SOURCE_BYTES+WEIGHT_LINES*128)
            $fatal(1,"compute traffic read=%0d write=%0d words=%0d",read_bytes,write_bytes,write_words);
        for (i=0;i<OUTPUT_BYTES;i=i+1)
            if (actual[i]!==expected[i])
                $fatal(1,"compute output mismatch byte=%0d actual=%h expected=%h",i,actual[i],expected[i]);
        write_reg(8'h78,12);read_reg(8'h7c,value);
        if (value!=OUTPUT_BYTES) $fatal(1,"output byte counter=%0d",value);
        write_reg(8'h78,2);read_reg(8'h7c,value);
        if (value!=(CASE_ID==0 ? 4 : CASE_ID==1 ? 81 : CASE_ID==2 ? 324 : 1))
            $fatal(1,"window tap counter=%0d",value);
        write_reg(8'h78,3);read_reg(8'h7c,value);
        if (value!=(CASE_ID==0 ? 4 : CASE_ID>=3 ? 1 : 9))
            $fatal(1,"weight reuse counter=%0d",value);
        write_reg(8'h78,13);read_reg(8'h7c,value);
        if (value==0) $fatal(1,"compute cycle counter missing");
        $display("MAC_CONV_MMIO_COMPUTE_PASS case=%0d read=%0d write=%0d job_cycles=%0d",CASE_ID,read_bytes,write_bytes,cycles-start_cycle);
        if (CASE_ID==3) begin
            write_reg(8'h48,8);
            inject_write_error=1;
            write_reg(8'h48,16);
            status=0;i=0;
            while (!status[9] && i<1000) begin
                @(negedge clk);read_reg(8'h48,status);i=i+1;
            end
            if (!status[9]) $fatal(1,"write error not reported");
            inject_write_error=0;
            i=0;
            while (status[3] && i<1000) begin
                @(negedge clk);read_reg(8'h48,status);i=i+1;
            end
            if (status[3]) $fatal(1,"input DMA did not drain after write error");
            write_reg(8'h48,8);
            write_reg(8'h48,16);
            wait_bit(8);
            for (i=0;i<OUTPUT_BYTES;i=i+1)
                if (actual[i]!==expected[i])
                    $fatal(1,"compute retry mismatch byte=%0d",i);
            $display("MAC_CONV_MMIO_COMPUTE_RETRY_PASS case=3");
            write_reg(8'h48,8);
            write_reg(8'h48,16);
            write_reg(8'h48,32); // explicit timeout recovery/engine abort
            write_reg(8'h78,14);read_reg(8'h7c,value);
            if (value!=0) $fatal(1,"compute abort left engine active");
            write_reg(8'h48,8);
            write_reg(8'h48,1);wait_bit(1);
            write_reg(8'h48,2);
            write_reg(8'h48,8);
            write_reg(8'h48,16);wait_bit(8);
            for (i=0;i<OUTPUT_BYTES;i=i+1)
                if (actual[i]!==expected[i])
                    $fatal(1,"compute abort recovery mismatch byte=%0d",i);
            $display("MAC_CONV_MMIO_COMPUTE_ABORT_PASS case=3");
        end
        $finish;
    end
    initial begin #1000000;$fatal(1,"global timeout");end
endmodule
