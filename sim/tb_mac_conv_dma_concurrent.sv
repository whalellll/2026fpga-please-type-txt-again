`timescale 1ns / 1ps
module tb_mac_conv_dma_concurrent;
    reg clk=0, resetn=0;
    always #5 clk=~clk;
    reg input_start=0, weight_load_start=0, activate=0;
    wire input_start_ready, weight_start_ready, activate_ready;
    reg [31:0] weight_src=32'h1000_4000;
    reg [31:0] generation=1;
    wire active_valid, pending_valid, weight_read_valid;
    wire [63:0] active_model_id;
    wire [31:0] active_generation, active_tile_id, reuse_count;
    wire [5:0] active_lines;
    reg weight_read_en=0;
    reg [4:0] weight_read_addr=0;
    wire [1023:0] weight_read_data;
    wire input_busy,input_done,input_error,weight_busy,weight_done,weight_error;
    wire [31:0] input_bytes,weight_bytes,input_cycles,weight_cycles;
    wire [31:0] window_taps,stall_cycles;
    wire tap_valid;
    reg tap_ready=0;
    wire [31:0] tap_data;
    wire [8:0] tap_x,tap_y;
    wire [2:0] tap_kx,tap_ky;
    wire [7:0] tap_tile;
    wire a_req_valid,a_req_ready,a_rsp_valid,a_rsp_ready,a_rsp_last,a_rsp_error,a_abort;
    wire [31:0] a_req_addr,a_rsp_rdata;
    wire [2:0] a_req_len;
    wire b_req_valid,b_req_ready,b_rsp_valid,b_rsp_ready,b_rsp_last,b_rsp_error,b_abort;
    wire [31:0] b_req_addr,b_rsp_rdata;
    wire [2:0] b_req_len;
    wire mem_req_valid,mem_req_ready,mem_rsp_valid,mem_rsp_ready,mem_rsp_last;
    wire mem_rsp_error,mem_abort;
    wire [31:0] mem_req_addr,mem_rsp_rdata;
    wire [2:0] mem_req_len;
    reg rsp_active=0;
    reg [31:0] rsp_addr=0;
    reg [3:0] rsp_left=0;
    reg [31:0] source_rom [0:100];
    reg [31:0] expected_rom [0:443];
    integer taps=0, read_overlap=0, input_bursts=0, weight_bursts=0;
    reg seen_input_done=0, seen_weight_done=0;
    integer tick_count=0;

    initial begin
        $readmemh("sim/vectors/yolo_window_board_source.hex",source_rom);
        $readmemh("sim/vectors/yolo_window_board_expected.hex",expected_rom);
    end
    mac_conv_input_dma #(
        .DDR_BASE(32'h1000_0000),.DDR_BYTES(64*1024),
        .MAX_WIDTH(16),.TIMEOUT_CYCLES(100)
    ) u_input (
        .clk(clk),.resetn(resetn),.start(input_start),
        .start_ready(input_start_ready),
        .width(9'd7),.height(9'd7),.channels(16'd3),
        .channel_tile(8'd0),.kernel(3'd6),.stride(2'd2),
        .padding(3'd2),.input_src(32'h1000_3000),
        .mem_req_valid(a_req_valid),.mem_req_ready(a_req_ready),
        .mem_req_write(),.mem_req_addr(a_req_addr),.mem_req_len(a_req_len),
        .mem_rsp_valid(a_rsp_valid),.mem_rsp_ready(a_rsp_ready),
        .mem_rsp_rdata(a_rsp_rdata),.mem_rsp_last(a_rsp_last),
        .mem_rsp_error(a_rsp_error),.mem_abort(a_abort),
        .out_valid(tap_valid),.out_ready(tap_ready),.out_data(tap_data),
        .out_x(tap_x),.out_y(tap_y),.out_kx(tap_kx),.out_ky(tap_ky),
        .out_tile_id(tap_tile),.busy(input_busy),.done(input_done),
        .error(input_error),.input_ddr_bytes(input_bytes),
        .window_taps(window_taps),.stall_cycles(stall_cycles),
        .cycles(input_cycles)
    );
    mac_conv_weight_dma #(
        .DDR_BASE(32'h1000_0000),.DDR_BYTES(64*1024),
        .TIMEOUT_CYCLES(100)
    ) u_weight (
        .clk(clk),.resetn(resetn),.load_start(weight_load_start),
        .load_start_ready(weight_start_ready),.weight_src(weight_src),
        .weight_lines(6'd27),.model_id(64'h1234_5678_9abc_def0),
        .generation(generation),.tile_id(generation+32'd6),
        .activate(activate),.activate_ready(activate_ready),
        .compute_idle(!input_busy),.window_done(tap_valid&&tap_ready&&tap_kx==5&&tap_ky==5),
        .active_valid(active_valid),.active_model_id(active_model_id),
        .active_generation(active_generation),.active_tile_id(active_tile_id),
        .active_lines(active_lines),.reuse_count(reuse_count),
        .pending_valid(pending_valid),.read_en(weight_read_en),
        .read_addr(weight_read_addr),.read_valid(weight_read_valid),
        .read_data(weight_read_data),.mem_req_valid(b_req_valid),
        .mem_req_ready(b_req_ready),.mem_req_write(),
        .mem_req_addr(b_req_addr),.mem_req_len(b_req_len),
        .mem_rsp_valid(b_rsp_valid),.mem_rsp_ready(b_rsp_ready),
        .mem_rsp_rdata(b_rsp_rdata),.mem_rsp_last(b_rsp_last),
        .mem_rsp_error(b_rsp_error),.mem_abort(b_abort),
        .load_busy(weight_busy),.load_done(weight_done),
        .load_error(weight_error),.weight_ddr_bytes(weight_bytes),
        .cycles(weight_cycles)
    );
    mac_conv_read_arbiter2 u_arb (
        .clk(clk),.resetn(resetn),
        .a_req_valid(a_req_valid),.a_req_ready(a_req_ready),
        .a_req_addr(a_req_addr),.a_req_len(a_req_len),
        .a_rsp_valid(a_rsp_valid),.a_rsp_ready(a_rsp_ready),
        .a_rsp_rdata(a_rsp_rdata),.a_rsp_last(a_rsp_last),
        .a_rsp_error(a_rsp_error),.a_abort(a_abort),
        .b_req_valid(b_req_valid),.b_req_ready(b_req_ready),
        .b_req_addr(b_req_addr),.b_req_len(b_req_len),
        .b_rsp_valid(b_rsp_valid),.b_rsp_ready(b_rsp_ready),
        .b_rsp_rdata(b_rsp_rdata),.b_rsp_last(b_rsp_last),
        .b_rsp_error(b_rsp_error),.b_abort(b_abort),
        .mem_req_valid(mem_req_valid),.mem_req_ready(mem_req_ready),
        .mem_req_addr(mem_req_addr),.mem_req_len(mem_req_len),
        .mem_rsp_valid(mem_rsp_valid),.mem_rsp_ready(mem_rsp_ready),
        .mem_rsp_rdata(mem_rsp_rdata),.mem_rsp_last(mem_rsp_last),
        .mem_rsp_error(mem_rsp_error),.mem_abort(mem_abort)
    );
    assign mem_req_ready=!rsp_active;
    assign mem_rsp_error=0;
    assign mem_rsp_valid=rsp_active;
    assign mem_rsp_last=rsp_left==1;
    assign mem_rsp_rdata = rsp_addr>=32'h1000_3000 &&
                           rsp_addr<32'h1000_30c4 ?
                           source_rom[52+((rsp_addr-32'h1000_3000)>>2)] :
                           ((rsp_addr-32'h1000_4000)>>2);
    always @(posedge clk) begin
        if (!resetn || mem_abort) begin
            rsp_active<=0;rsp_left<=0;rsp_addr<=0;tick_count<=0;
        end else begin
            tick_count<=tick_count+1;
            if (input_done) seen_input_done<=1;
            if (weight_done) seen_weight_done<=1;
            if (mem_req_valid && mem_req_ready) begin
                if (mem_req_addr>=32'h1000_4000) weight_bursts<=weight_bursts+1;
                else input_bursts<=input_bursts+1;
                rsp_active<=1;rsp_addr<=mem_req_addr;
                rsp_left<=mem_req_len+1;
            end else if (mem_rsp_valid && mem_rsp_ready) begin
                if (rsp_left==1) rsp_active<=0;
                else begin rsp_addr<=rsp_addr+4;rsp_left<=rsp_left-1;end
            end
            if (tap_valid && tap_ready) begin
                if (taps>=324 || tap_data!==expected_rom[120+taps] || tap_tile!=0 ||
                    tap_x!=(taps/36)%3 || tap_y!=(taps/36)/3 ||
                    tap_kx!=taps%6 || tap_ky!=(taps%36)/6)
                    $fatal(1,"concurrent DMA tap mismatch at %0d",taps);
                taps<=taps+1;
            end
            if (weight_read_valid && weight_busy) begin
                if (weight_read_data[31:0]!==32'd0 || active_generation!=1)
                    $fatal(1,"active weight changed during prefetch");
                read_overlap<=read_overlap+1;
            end
        end
    end
    always @(negedge clk) begin
        tap_ready=(tick_count%7!=3);
        weight_read_en=active_valid && weight_busy;
        weight_read_addr=0;
    end
    initial begin
        repeat(4) @(negedge clk);resetn=1;
        @(negedge clk);weight_load_start=1;
        @(negedge clk);weight_load_start=0;
        wait(weight_done);
        @(negedge clk);activate=1;
        @(negedge clk);activate=0;
        if (!active_valid || active_generation!=1)
            $fatal(1,"first bank not active");
        weight_src=32'h1000_5000;generation=2;
        seen_input_done=0;seen_weight_done=0;
        input_start=1;weight_load_start=1;
        @(negedge clk);input_start=0;weight_load_start=0;
        wait(seen_input_done && seen_weight_done);
        @(negedge clk);
        if (input_error || weight_error || taps!=324 ||
            input_bytes!=196 || weight_bytes!=3456 ||
            input_bursts!=7 || weight_bursts!=216 ||
            read_overlap<27 || !pending_valid || active_generation!=1)
            $fatal(1,"concurrent DMA counters failed taps=%0d input=%0d weight=%0d i_bursts=%0d w_bursts=%0d overlap=%0d",
                   taps,input_bytes,weight_bytes,input_bursts,weight_bursts,read_overlap);
        $display("MAC_CONV_DMA_CONCURRENT_PASS taps=%0d input_bytes=%0d weight_bytes=%0d input_bursts=%0d weight_bursts=%0d overlap=%0d",
                 taps,input_bytes,weight_bytes,input_bursts,weight_bursts,read_overlap);
        $finish;
    end
    initial begin #200000; $fatal(1,"concurrent DMA timeout"); end
endmodule
