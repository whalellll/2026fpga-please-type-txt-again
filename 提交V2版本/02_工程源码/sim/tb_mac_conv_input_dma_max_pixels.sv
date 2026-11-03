`timescale 1ns / 1ps
module tb_mac_conv_input_dma_max_pixels;
    reg clk=0, resetn=0, start=0;
    always #5 clk=~clk;
    localparam [31:0] BASE=32'h1000_0000;
    localparam [31:0] SOURCE=BASE+32'h1000;
    localparam integer PIXELS=320*320;
    wire start_ready,busy,done,error,mem_abort;
    wire mem_req_valid,mem_req_write,mem_rsp_ready,out_valid;
    wire [31:0] mem_req_addr,out_data,input_ddr_bytes,window_taps;
    wire [31:0] stall_cycles,cycles;
    wire [2:0] mem_req_len,out_kx,out_ky;
    wire [8:0] out_x,out_y;
    wire [7:0] out_tile_id;
    reg rsp_active=0;
    reg [31:0] rsp_addr=0;
    reg [3:0] rsp_left=0;
    integer produced=0,requests=0,requested_words=0;

    mac_conv_input_dma #(.DDR_BASE(BASE),.DDR_BYTES(1024*1024),
        .TIMEOUT_CYCLES(100)) dut (
        .clk(clk),.resetn(resetn),.start(start),.start_ready(start_ready),
        .width(9'd320),.height(9'd320),.channels(16'd1),
        .channel_tile(8'd0),.kernel(3'd1),.stride(2'd1),
        .padding(3'd0),.input_src(SOURCE),
        .mem_req_valid(mem_req_valid),.mem_req_ready(!rsp_active),
        .mem_req_write(mem_req_write),.mem_req_addr(mem_req_addr),
        .mem_req_len(mem_req_len),.mem_rsp_valid(rsp_active),
        .mem_rsp_ready(mem_rsp_ready),
        .mem_rsp_rdata((rsp_addr-SOURCE)>>2),
        .mem_rsp_last(rsp_left==1),.mem_rsp_error(1'b0),
        .mem_abort(mem_abort),.out_valid(out_valid),.out_ready(1'b1),
        .out_data(out_data),.out_x(out_x),.out_y(out_y),
        .out_kx(out_kx),.out_ky(out_ky),.out_tile_id(out_tile_id),
        .busy(busy),.done(done),.error(error),
        .input_ddr_bytes(input_ddr_bytes),.window_taps(window_taps),
        .stall_cycles(stall_cycles),.cycles(cycles)
    );

    always @(posedge clk) begin
        if (!resetn) begin
            rsp_active<=0; rsp_addr<=0; rsp_left<=0;
            produced<=0;requests<=0;requested_words<=0;
        end else begin
            if (mem_abort) $fatal(1,"unexpected DMA abort");
            if (mem_req_valid && !rsp_active) begin
                if (mem_req_write ||
                    mem_req_addr!==SOURCE+requested_words*4 ||
                    mem_req_addr>=SOURCE+PIXELS*4 ||
                    mem_req_addr[11:0]+((mem_req_len+1)<<2)>4096)
                    $fatal(1,"invalid maximum-image request");
                rsp_active<=1; rsp_addr<=mem_req_addr;
                rsp_left<=mem_req_len+1; requests<=requests+1;
                requested_words<=requested_words+mem_req_len+1;
            end else if (rsp_active && mem_rsp_ready) begin
                if (rsp_left==1) rsp_active<=0;
                else begin rsp_addr<=rsp_addr+4; rsp_left<=rsp_left-1; end
            end
            if (out_valid) begin
                if (produced>=PIXELS || out_data!==(produced & 8'hff) ||
                    out_x!==produced%320 || out_y!==produced/320 ||
                    out_kx!==0 || out_ky!==0 || out_tile_id!==0)
                    $fatal(1,"maximum-image tap mismatch at %0d data=%h x=%0d y=%0d kx=%0d ky=%0d tile=%0d",
                           produced,out_data,out_x,out_y,out_kx,out_ky,out_tile_id);
                produced<=produced+1;
            end
        end
    end

    initial begin
        repeat(4) @(negedge clk); resetn=1;
        @(negedge clk); if (!start_ready) $fatal(1,"DMA not ready");
        start=1;
        @(negedge clk); start=0;
        wait(done || error);
        @(negedge clk);
        if (error || produced!=PIXELS || input_ddr_bytes!=PIXELS*4 ||
            window_taps!=PIXELS || requests!=PIXELS/8 ||
            requested_words!=PIXELS)
            $fatal(1,"maximum-image totals mismatch pixels=%0d bytes=%0d taps=%0d requests=%0d",
                   produced,input_ddr_bytes,window_taps,requests);
        $display("MAC_CONV_INPUT_DMA_MAX_PIXELS_PASS pixels=%0d bytes=%0d requests=%0d cycles=%0d",
                 produced,input_ddr_bytes,requests,cycles);
        $finish;
    end
    initial begin #10000000; $fatal(1,"maximum-image global timeout"); end
endmodule
