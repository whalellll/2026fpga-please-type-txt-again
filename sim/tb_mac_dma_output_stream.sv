`timescale 1ns/1ps

// The bank model has the same enabled, one-clock read as MacAccelCore.
// Distinct words expose duplicated, skipped and stale reads under W stalls.
module MacAccelCore #(
    parameter COMPACT_S16_OUTPUT=0,
    parameter integer WEIGHT_BANK_LINES=1024,
    parameter ENABLE_FP8=1,
    parameter BIAS_WORD_WRITE=0,
    parameter WEIGHT_WORD_WRITE=0
)(
    input io_clk, io_rstN, io_start, io_doneClear,
    output reg io_busy, io_done,
    input [15:0] io_cfgPixels, io_cfgCin, io_cfgCout,
    input [1:0] io_cfgComputeMode, io_cfgActivation, io_cfgOutputFormat,
    input [7:0] io_cfgOutShift,
    input io_hostInWe, io_hostWtWe, io_hostBiasWe,
    input [31:0] io_hostInWaddr, io_hostWtWaddr, io_hostBiasWaddr,
    input [63:0] io_hostInWdata,
    input [1023:0] io_hostWtWdata,
    input io_hostWtWordWe,
    input [4:0] io_hostWtWordIndex,
    input [31:0] io_hostWtWordData,
    input [1535:0] io_hostBiasWdata,
    input io_hostBiasWordWe, io_hostBiasZeroWe,
    input [5:0] io_hostBiasWordIndex,
    input [31:0] io_hostBiasWordData,
    input io_hostOutRe, input [31:0] io_hostOutRaddr,
    output reg [31:0] io_hostOutRdata
);
    always @(posedge io_clk) begin
        if (!io_rstN) begin io_busy<=0; io_done<=0; end
        else begin
            if (io_doneClear) io_done<=0;
            if (io_start) begin io_busy<=1; io_done<=0; end
            else if (io_busy) begin io_busy<=0; io_done<=1; end
        end
        if (io_hostOutRe) begin
            if (!COMPACT_S16_OUTPUT || io_hostOutRaddr>=4096)
                $fatal(1,"DMA must use the compact bank layout");
            io_hostOutRdata <= 32'h8ace0000 ^ (io_hostOutRaddr * 32'h10201);
        end
    end
endmodule

module tb_mac_dma_output_stream;
    reg clk=0, resetn=0;
    always #5 clk=~clk;
    reg reg_wr_en=0; reg [7:0] reg_wr_addr=0, reg_rd_addr=0;
    reg [31:0] reg_wr_data=0; reg [3:0] reg_wr_strb=15;
    wire [31:0] reg_rd_data;
    wire req_valid, req_ready, req_write;
    wire [31:0] req_addr; wire [2:0] req_len;
    wire wvalid, wready, wlast; wire [31:0] wdata; wire [3:0] wstrb;
    wire rsp_valid, rsp_ready, rsp_last, rsp_error, irq;
    mac_accel_dma_kernel #(.DDR_BASE(32'h1b000000), .DDR_BYTES(1048576)) dut(
        .clk(clk), .resetn(resetn), .reg_wr_en(reg_wr_en),
        .reg_wr_addr(reg_wr_addr), .reg_wr_data(reg_wr_data),
        .reg_wr_strb(reg_wr_strb), .reg_rd_addr(reg_rd_addr),
        .reg_rd_data(reg_rd_data), .mem_req_valid(req_valid),
        .mem_req_ready(req_ready), .mem_req_write(req_write),
        .mem_req_addr(req_addr), .mem_req_len(req_len),
        .mem_w_valid(wvalid), .mem_w_ready(wready), .mem_w_data(wdata),
        .mem_w_strb(wstrb), .mem_w_last(wlast), .mem_rsp_valid(rsp_valid),
        .mem_rsp_ready(rsp_ready), .mem_rsp_rdata(32'b0),
        .mem_rsp_last(rsp_last), .mem_rsp_error(rsp_error), .irq(irq)
    );
    integer tick=0, phase=0, beats=0, burst_sent=0;
    integer case_id=0, pixels=0, cout=0, lanes=0, output_count=0;
    integer last_write_tick=0, bubbles=0, write_bursts=0, cases=0;
    integer write_command_tick=0, launch_checks=0;
    reg stalled=0; reg [31:0] stalled_data; reg stalled_last;
    reg inject_error=0;
    reg [31:0] destination;
    wire stall_case=case_id!=0;
    assign req_ready=(phase==0) && (!stall_case || tick%7!=0);
    assign wready=(phase==2) && (!stall_case || tick%19>=7);
    assign rsp_valid=(phase==1 || phase==3) && (!stall_case || tick%5!=0);
    assign rsp_last=(phase==3 || beats==1);
    assign rsp_error=phase==3 && inject_error;
    integer p, co, bank, expected;
    // Drive ready/valid between sampling edges, as an external AXI sink does.
    always @(negedge clk) tick=tick+1;
    always @(posedge clk) begin
        if (!resetn) begin phase<=0; stalled<=0; end
        else begin
            if (stalled && (!wvalid || wdata!==stalled_data || wlast!==stalled_last))
                $fatal(1,"write payload changed under backpressure case=%0d",case_id);
            stalled<=wvalid && !wready;
            if (wvalid && !wready) begin stalled_data<=wdata; stalled_last<=wlast; end
            if (req_valid && req_ready) begin
                if (req_addr[4:0]+((req_len+1)*4)>32)
                    $fatal(1,"burst crossed native DDR line");
                beats<=req_len+1;
                phase<=req_write ? 2 : 1;
                burst_sent=0;
                if (req_write) begin
                    write_command_tick=tick;
                    if (req_addr!==destination+output_count*4)
                        $fatal(1,"noncompact output address");
                    write_bursts=write_bursts+1;
                end
            end
            if (phase==1 && rsp_valid && rsp_ready) begin
                if (beats==1) phase<=0;
                else beats<=beats-1;
            end
            if (wvalid && wready) begin
                if (!stall_case && burst_sent==0) begin
                    if (tick!=write_command_tick+1)
                        $fatal(1,"DMA_OUTPUT_LAUNCH_BUBBLE command=%0d first_w=%0d",write_command_tick,tick);
                    launch_checks=launch_checks+1;
                end
                p=output_count/cout; co=output_count%cout;
                bank=(p*((cout+lanes-1)/lanes)+co/lanes)*lanes+co%lanes;
                expected=32'h8ace0000 ^ (bank*32'h10201);
                if (wdata!==expected || wstrb!==4'hf || wlast!==(beats==1))
                    $fatal(1,"wrong output case=%0d element=%0d got=%h expected=%h last=%b",case_id,output_count,wdata,expected,wlast);
                if (!stall_case && burst_sent>0 && tick!=last_write_tick+1)
                    bubbles=bubbles+tick-last_write_tick-1;
                last_write_tick=tick;
                burst_sent=burst_sent+1;
                output_count=output_count+1;
                if (beats==1) phase<=3;
                else beats<=beats-1;
            end
            if (phase==3 && rsp_valid && rsp_ready) phase<=0;
        end
    end
    task write_reg(input [7:0] address, input [31:0] value);
        begin
            @(negedge clk); reg_wr_addr=address; reg_wr_data=value; reg_wr_en=1;
            @(negedge clk); reg_wr_en=0;
        end
    endtask
    task run_case(input integer np, nc, mode, format, offset, error_case);
        integer timeout;
        reg [31:0] cycle_count;
        begin
            pixels=np; cout=nc; lanes=mode==0 ? 16 : 32;
            output_count=0; inject_error=error_case;
            destination=32'h1b020000+offset;
            write_reg('h08,2);
            write_reg('h10,(4<<16)|pixels);
            write_reg('h14,(1<<30)|(mode<<28)|(format<<24)|cout);
            write_reg('h18,32'h1b000004);
            write_reg('h1c,32'h1b004000);
            write_reg('h20,32'h1b008000);
            write_reg('h24,destination);
            write_reg('h08,1);
            reg_rd_addr='h0c; #1; timeout=0;
            while (!reg_rd_data[1] && timeout<100000) begin
                @(negedge clk); timeout=timeout+1;
            end
            if (timeout==100000 || reg_rd_data[2]!==error_case[0])
                $fatal(1,"job status failed case=%0d status=%h",case_id,reg_rd_data);
            if (!error_case && output_count!=pixels*cout)
                $fatal(1,"output count mismatch");
            if (error_case && reg_rd_data[15:12]!=4)
                $fatal(1,"write error was not reported");
            reg_rd_addr='h28; #1; cycle_count=reg_rd_data;
            $display("DMA_OUTPUT_CASE_PASS case=%0d p=%0d cout=%0d mode=%0d format=%0d words=%0d cycles=%0d",case_id,np,nc,mode,format,output_count,cycle_count);
            if (!stall_case) $display("DMA_OUTPUT_PERF bubbles=%0d",bubbles);
            cases=cases+1; case_id=case_id+1;
        end
    endtask
    initial begin
        repeat(4) @(negedge clk); resetn=1;
        // Performance is measured on a sink that accepts one word each clock.
        run_case(16,256,1,3,0,0);
        run_case(3,1,0,2,4,0);
        run_case(3,15,0,2,28,0);
        run_case(3,16,0,0,0,0);
        run_case(3,17,0,1,4092,0);
        run_case(3,31,1,3,4,0);
        run_case(3,32,1,2,0,0);
        run_case(3,33,1,3,28,0);
        run_case(16,57,1,3,4092,0);
        run_case(16,255,1,3,4,0);
        run_case(16,256,0,2,0,0);
        run_case(3,33,2,1,4,0);
        run_case(3,57,3,0,28,0);
        run_case(16,57,1,3,0,1);
        run_case(3,33,1,3,4,0); // A normal job must recover after a write error.
        if (bubbles!=0) $fatal(1,"DMA_OUTPUT_PERF_FAIL avoidable_bubbles=%0d",bubbles);
        if (launch_checks!=512) $fatal(1,"incomplete first-write latency coverage");
        $display("DMA_OUTPUT_STREAM_PASS cases=%0d bubbles=%0d bursts=%0d launch_checks=%0d",cases,bubbles,write_bursts,launch_checks);
        $finish;
    end
    initial begin repeat(1000000) @(posedge clk); $fatal(1,"timeout"); end
endmodule
