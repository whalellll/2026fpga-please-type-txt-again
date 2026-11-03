`timescale 1ns / 1ps
module tb_mac_conv_input_dma;
    reg clk=0, resetn=0;
    always #5 clk=~clk;
    reg start=0;
    wire start_ready, busy, done, error;
    reg [8:0] width=4, height=3;
    reg [15:0] channels=3;
    reg [7:0] channel_tile=0;
    reg [2:0] kernel=1, padding=0;
    reg [1:0] stride=1;
    reg [31:0] input_src=32'h1000_0ff8;
    wire mem_req_valid, mem_req_write;
    wire [31:0] mem_req_addr;
    wire [2:0] mem_req_len;
    wire mem_req_ready;
    wire mem_rsp_valid, mem_rsp_last;
    wire [31:0] mem_rsp_rdata;
    wire mem_rsp_error = inject_error;
    wire mem_rsp_ready;
    wire mem_abort;
    wire out_valid;
    reg out_ready=0;
    wire [31:0] out_data, input_ddr_bytes, window_taps, stall_cycles, cycles;
    wire [8:0] out_x, out_y;
    wire [2:0] out_kx, out_ky;
    wire [7:0] out_tile_id;
    reg [31:0] source_rom [0:100];
    reg [31:0] expected_rom [0:443];
    integer output_index=0, bursts=0, tick_count=0, expected_base=0;
    integer expected_count=12, expected_bytes=48;
    reg rsp_active=0;
    reg [31:0] rsp_addr=0;
    reg [3:0] rsp_left=0;
    reg inject_error=0;
    reg hold_req=0;
    reg hold_rsp=0;
    reg [31:0] word;
    integer pixel;

    mac_conv_input_dma #(
        .DDR_BASE(32'h1000_0000), .DDR_BYTES(64*1024),
        .MAX_WIDTH(16), .TIMEOUT_CYCLES(100)
    ) dut (.*);

    initial begin
        $readmemh("sim/vectors/yolo_window_board_source.hex", source_rom);
        $readmemh("sim/vectors/yolo_window_board_expected.hex", expected_rom);
    end

    assign mem_req_ready = !rsp_active && !hold_req;
    assign mem_rsp_valid = rsp_active && !hold_rsp;
    assign mem_rsp_last = rsp_left == 1;
    assign mem_rsp_rdata = word;
    always @* begin
        word = 32'hdead_beef;
        if (rsp_addr >= 32'h1000_0ff8 && rsp_addr < 32'h1000_1028)
            word = source_rom[(rsp_addr - 32'h1000_0ff8) >> 2];
        else if (rsp_addr >= 32'h1000_2000 && rsp_addr < 32'h1000_20a0) begin
            pixel = (rsp_addr - 32'h1000_2000) >> 3;
            word = rsp_addr[2] ? source_rom[32+pixel] : source_rom[12+pixel];
        end
        else if (rsp_addr >= 32'h1000_3000 && rsp_addr < 32'h1000_30c4)
            word = source_rom[52+((rsp_addr-32'h1000_3000)>>2)];
    end
    always @(posedge clk) begin
        if (!resetn) begin
            rsp_active <= 0; rsp_left <= 0; rsp_addr <= 0;
            tick_count <= 0;
        end else begin
            tick_count <= tick_count+1;
            if (mem_abort) begin
                rsp_active <= 0;
                rsp_left <= 0;
            end else if (mem_req_valid && mem_req_ready) begin
                if (mem_req_write || mem_req_len >= 8 ||
                    (mem_req_addr[11:0] + ((mem_req_len+1)<<2)) > 4096)
                    $fatal(1,"invalid DMA read burst addr=%h len=%0d",mem_req_addr,mem_req_len);
                bursts <= bursts+1;
                rsp_active <= 1;
                rsp_addr <= mem_req_addr;
                rsp_left <= mem_req_len+1;
            end else if (mem_rsp_valid && mem_rsp_ready) begin
                if (rsp_left == 1) rsp_active <= 0;
                else begin rsp_addr <= rsp_addr+4; rsp_left <= rsp_left-1; end
            end
        end
    end
    always @(posedge clk) if (resetn && out_valid && out_ready) begin
        if (output_index >= expected_count ||
            out_data !== expected_rom[expected_base+output_index] ||
            out_tile_id != channel_tile)
            $fatal(1,"tap mismatch job base=%0d index=%0d got=%h expected=%h",
                   expected_base,output_index,out_data,
                   expected_rom[expected_base+output_index]);
        if (kernel==1) begin
            if (out_x != output_index%4 || out_y != output_index/4 ||
                out_kx != 0 || out_ky != 0)
                $fatal(1,"1x1 coordinate mismatch");
        end else if (kernel==3) begin
            if (out_x != (output_index/9)%3 ||
                out_y != (output_index/9)/3 ||
                out_kx != output_index%3 ||
                out_ky != (output_index%9)/3)
                $fatal(1,"3x3 coordinate mismatch");
        end else if (out_x != (output_index/36)%3 ||
                     out_y != (output_index/36)/3 ||
                     out_kx != output_index%6 ||
                     out_ky != (output_index%36)/6)
            $fatal(1,"6x6 coordinate mismatch");
        output_index <= output_index+1;
    end
    always @(negedge clk) out_ready = (tick_count%7 != 2);

    task run_job;
        input [31:0] source;
        input [8:0] w,h;
        input [15:0] cin;
        input [7:0] tile;
        input [2:0] k,pad;
        input [1:0] step;
        input integer base,count,bytes,request_count;
        integer timeout;
        begin
            @(negedge clk);
            if (!start_ready) $fatal(1,"DMA not ready for next job");
            input_src=source;width=w;height=h;channels=cin;
            channel_tile=tile;kernel=k;padding=pad;stride=step;
            expected_base=base;expected_count=count;expected_bytes=bytes;
            output_index=0;bursts=0;start=1;
            @(negedge clk);start=0;
            timeout=0;
            while (!done && !error && timeout<2000) begin
                @(negedge clk);timeout=timeout+1;
            end
            if (timeout==2000 || error || !done || output_index!=count ||
                input_ddr_bytes!=bytes || window_taps!=count ||
                bursts!=request_count || cycles==0 || stall_cycles==0)
                $fatal(1,"DMA job failed done=%b err=%b taps=%0d bytes=%0d bursts=%0d cycles=%0d stalls=%0d",
                       done,error,output_index,input_ddr_bytes,bursts,cycles,stall_cycles);
            $display("MAC_CONV_INPUT_DMA_JOB_PASS k=%0d tile=%0d bytes=%0d taps=%0d bursts=%0d cycles=%0d stalls=%0d",
                     k,tile,bytes,count,bursts,cycles,stall_cycles);
        end
    endtask

    initial begin
        repeat(4) @(negedge clk); resetn=1;
        run_job(32'h1000_0ff8,4,3,3,0,1,0,1,0,12,48,3);
        // The invalid lanes of the five-channel tail tile contain poison.
        // Hardware must emit zero for those lanes regardless of DDR contents.
        for (integer i=0; i<20; i=i+1)
            source_rom[32+i] = {24'ha5_b6_c7,source_rom[32+i][7:0]};
        run_job(32'h1000_2000,5,4,5,1,3,1,2,66,54,80,20);
        run_job(32'h1000_3000,7,7,3,0,6,2,2,120,324,196,7);
        // A bad descriptor must fail before any AXI command, then recover.
        @(negedge clk); input_src=32'h1000_0ff9; start=1;
        @(negedge clk);
        if (!error || mem_req_valid || !start_ready)
            $fatal(1,"unaligned descriptor not rejected cleanly");
        start=0;
        // A response error drains the accepted burst and allows a new job.
        @(negedge clk); input_src=32'h1000_0ff8;
        width=4;height=3;channels=3;channel_tile=0;
        kernel=1;padding=0;stride=1;
        inject_error=1;start=1;
        @(negedge clk); start=0;
        wait(error);
        @(negedge clk); inject_error=0;
        if (!start_ready || rsp_active)
            $fatal(1,"response error did not drain and recover");
        // An unaccepted command times out without leaving AXI ownership.
        hold_req=1;start=1;
        @(negedge clk); start=0;
        wait(error);
        @(negedge clk); hold_req=0;
        if (!start_ready || rsp_active)
            $fatal(1,"request timeout did not recover");
        // An accepted read that never responds must ask the AXI adapter to
        // abandon ownership before the next descriptor can start.
        hold_rsp=1;start=1;
        @(negedge clk); start=0;
        wait(mem_abort && error);
        @(negedge clk); hold_rsp=0;
        @(negedge clk);
        if (!start_ready || rsp_active)
            $fatal(1,"response timeout did not abort ownership");
        run_job(32'h1000_0ff8,4,3,3,0,1,0,1,0,12,48,3);
        $display("MAC_CONV_INPUT_DMA_PASS");
        $finish;
    end
    initial begin
        #100000;
        $fatal(1,"DMA global timeout");
    end
endmodule
