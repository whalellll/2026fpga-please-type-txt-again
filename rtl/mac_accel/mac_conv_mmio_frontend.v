`timescale 1ns / 1ps
// Stage-2 convolution descriptor and read-only DMA path at MMIO 0x40..0x7c.
// The legacy dense OUTPUT_DST register at 0x24 belongs to another module.
// This path emits ordered window taps for the stage-2 MAC adapter.
module mac_conv_mmio_frontend #(
    parameter [31:0] DDR_BASE = 32'h0000_0000,
    parameter integer DDR_BYTES = 256 * 1024 * 1024,
    parameter integer MAX_WIDTH = 320,
    parameter integer TIMEOUT_CYCLES = 100000
) (
    input wire clk,
    input wire resetn,
    input wire reg_wr_en,
    input wire [7:0] reg_wr_addr,
    input wire [31:0] reg_wr_data,
    input wire [3:0] reg_wr_strb,
    input wire [7:0] reg_rd_addr,
    output reg [31:0] reg_rd_data,
    output wire busy_out,
    output wire mem_req_valid,
    input wire mem_req_ready,
    output wire mem_req_write,
    output wire [31:0] mem_req_addr,
    output wire [2:0] mem_req_len,
    output wire mem_w_valid,
    input wire mem_w_ready,
    output wire [31:0] mem_w_data,
    output wire [3:0] mem_w_strb,
    output wire mem_w_last,
    input wire mem_rsp_valid,
    output wire mem_rsp_ready,
    input wire [31:0] mem_rsp_rdata,
    input wire mem_rsp_last,
    input wire mem_rsp_error,
    output wire mem_abort,
    output wire tap_valid,
    input wire tap_ready,
    output wire [31:0] tap_data,
    output wire [8:0] tap_x,
    output wire [8:0] tap_y,
    output wire [2:0] tap_kx,
    output wire [2:0] tap_ky,
    output wire [7:0] tap_tile
);
    reg [8:0] cfg_width,cfg_height;
    reg [15:0] cfg_channels,cfg_output_channels;
    reg [2:0] cfg_kernel,cfg_padding;
    reg [1:0] cfg_stride;
    reg [7:0] cfg_tile;
    reg [31:0] cfg_input_src,cfg_weight_src,cfg_output_dst;
    reg [5:0] cfg_weight_lines;
    reg [63:0] cfg_model_id;
    reg [31:0] cfg_generation;
    reg [7:0] counter_select;
    reg weight_done_sticky,weight_error_sticky;
    reg input_done_sticky,input_error_sticky;
    reg compute_done_sticky,compute_error_sticky,compute_active;
    reg [2:0] compute_kernel_r;
    reg [31:0] quant_bias_words[0:15];
    reg [4:0] quant_shift_words[0:15];
    wire [511:0] quant_bias_bus;
    wire [79:0] quant_shift_bus;
    genvar quant_index;
    generate for (quant_index=0;quant_index<16;quant_index=quant_index+1) begin: g_quant
        assign quant_bias_bus[quant_index*32 +: 32]=quant_bias_words[quant_index];
        assign quant_shift_bus[quant_index*5 +: 5]=quant_shift_words[quant_index];
    end endgenerate
    reg [3:0] error_code;
    reg [31:0] tap_xor,weight_read_xor;
    wire [1023:0] weight_read_data;
    reg [31:0] folded_weight_read;
    integer fold_index;
    always @* begin
        folded_weight_read = 0;
        for (fold_index = 0; fold_index < 32; fold_index = fold_index + 1)
            folded_weight_read = {folded_weight_read[26:0],
                                  folded_weight_read[31:27]} ^
                                 weight_read_data[fold_index*32 +: 32];
    end
    wire guard_valid;
    wire [3:0] guard_error;
    wire [8:0] output_width,output_height;
    wire [31:0] input_tensor_bytes,weight_guard_bytes,output_bytes;
    wire input_start_ready,input_busy,input_done,input_error,input_abort;
    wire [31:0] input_ddr_bytes,window_taps,stall_cycles,input_cycles;
    wire weight_start_ready,weight_busy,weight_done,weight_error,weight_abort;
    assign busy_out=input_busy || weight_busy || compute_active;
    wire activate_ready,active_valid,pending_valid,weight_read_valid;
    wire [63:0] active_model_id;
    wire [31:0] active_generation,active_tile_id,reuse_count;
    wire [5:0] active_lines;
    wire [31:0] weight_ddr_bytes,weight_cycles;
    wire a_req_valid,a_req_ready,a_rsp_valid,a_rsp_ready,a_rsp_last,a_rsp_error;
    wire [31:0] a_req_addr,a_rsp_rdata;
    wire [2:0] a_req_len;
    wire b_req_valid,b_req_ready,b_rsp_valid,b_rsp_ready,b_rsp_last,b_rsp_error;
    wire [31:0] b_req_addr,b_rsp_rdata;
    wire [2:0] b_req_len;
    wire command_write = reg_wr_en && reg_wr_addr == 8'h48 &&
                         reg_wr_strb[0];
    wire command_load = command_write && reg_wr_data[0];
    wire command_activate = command_write && reg_wr_data[1];
    wire command_input = command_write && reg_wr_data[2];
    wire command_clear = command_write && reg_wr_data[3];
    wire command_compute = command_write && reg_wr_data[4];
    wire command_abort = command_write && reg_wr_data[5];
    wire engine_resetn = resetn && !command_abort;
    wire active_match = active_valid &&
                        active_model_id == cfg_model_id &&
                        active_generation == cfg_generation &&
                        active_tile_id == {24'b0,cfg_tile} &&
                        active_lines == cfg_weight_lines;
    wire launch_weight = command_load && guard_valid && weight_start_ready;
    wire launch_input = command_input && !compute_active && guard_valid &&
                        input_start_ready && active_match;
    wire core_start_ready,packer_start_ready;
    wire compute_launch=command_compute && guard_valid && active_match &&
                        cfg_tile==0 && cfg_channels<=4 &&
                        cfg_output_channels<=16 && !compute_active &&
                        input_start_ready && core_start_ready &&
                        packer_start_ready;
    wire start_input=launch_input || compute_launch;
    wire do_activate = command_activate && activate_ready;
    wire core_tap_ready,core_weight_read_en,core_weight_read_valid;
    wire [4:0] core_weight_read_addr;
    wire core_out_valid,core_out_ready,core_out_last,core_done,core_error;
    wire [7:0] core_out_data;
    wire [31:0] core_cycles;
    wire packer_word_valid,packer_word_ready,packer_done,packer_error;
    wire [31:0] packer_word_addr,packer_word_data,output_ddr_bytes;
    wire [3:0] packer_word_strb;
    wire writer_error,writer_abort;
    wire compute_abort=compute_active &&
                       (core_error || packer_error || writer_error || input_error);
    wire dma_tap_ready=compute_active ? core_tap_ready : tap_ready;
    wire weight_read_en=compute_active ? core_weight_read_en :
                       tap_valid && tap_ready && active_valid;
    wire output_window_done = tap_valid && dma_tap_ready &&
                              tap_kx + 1 == (compute_active ? compute_kernel_r : cfg_kernel) &&
                              tap_ky + 1 == (compute_active ? compute_kernel_r : cfg_kernel);

    mac_conv_descriptor_guard #(
        .DDR_BASE(DDR_BASE),.DDR_BYTES(DDR_BYTES)
    ) u_guard (
        .width(cfg_width),.height(cfg_height),
        .channels(cfg_channels),.output_channels(cfg_output_channels),
        .kernel(cfg_kernel),.stride(cfg_stride),.padding(cfg_padding),
        .channel_tile(cfg_tile),.weight_lines(cfg_weight_lines),
        .input_src(cfg_input_src),.weight_src(cfg_weight_src),
        .output_dst(cfg_output_dst),.valid(guard_valid),
        .error_code(guard_error),.output_width(output_width),
        .output_height(output_height),
        .input_tensor_bytes(input_tensor_bytes),
        .weight_bytes(weight_guard_bytes),.output_bytes(output_bytes)
    );
    mac_conv_input_dma #(
        .DDR_BASE(DDR_BASE),.DDR_BYTES(DDR_BYTES),
        .MAX_WIDTH(MAX_WIDTH),.TIMEOUT_CYCLES(TIMEOUT_CYCLES)
    ) u_input (
        .clk(clk),.resetn(engine_resetn),.start(start_input),
        .start_ready(input_start_ready),
        .width(cfg_width),.height(cfg_height),
        .channels(cfg_channels),.channel_tile(cfg_tile),
        .kernel(cfg_kernel),.stride(cfg_stride),.padding(cfg_padding),
        .input_src(cfg_input_src),.mem_req_valid(a_req_valid),
        .mem_req_ready(a_req_ready),.mem_req_write(),
        .mem_req_addr(a_req_addr),.mem_req_len(a_req_len),
        .mem_rsp_valid(a_rsp_valid),.mem_rsp_ready(a_rsp_ready),
        .mem_rsp_rdata(a_rsp_rdata),.mem_rsp_last(a_rsp_last),
        .mem_rsp_error(a_rsp_error),.mem_abort(input_abort),
        .out_valid(tap_valid),.out_ready(dma_tap_ready),
        .out_data(tap_data),.out_x(tap_x),.out_y(tap_y),
        .out_kx(tap_kx),.out_ky(tap_ky),.out_tile_id(tap_tile),
        .busy(input_busy),.done(input_done),.error(input_error),
        .input_ddr_bytes(input_ddr_bytes),.window_taps(window_taps),
        .stall_cycles(stall_cycles),.cycles(input_cycles)
    );
    mac_conv_weight_dma #(
        .DDR_BASE(DDR_BASE),.DDR_BYTES(DDR_BYTES),
        .TIMEOUT_CYCLES(TIMEOUT_CYCLES),.FOLD_UPPER_HALF(1),.STREAM_UPPER_FOLD(1)
    ) u_weight (
        .clk(clk),.resetn(engine_resetn),.load_start(launch_weight),
        .load_start_ready(weight_start_ready),
        .weight_src(cfg_weight_src),.weight_lines(cfg_weight_lines),
        .model_id(cfg_model_id),.generation(cfg_generation),
        .tile_id({24'b0,cfg_tile}),.activate(do_activate),
        .activate_ready(activate_ready),.compute_idle(!input_busy && !compute_active),
        .window_done(output_window_done),
        .active_valid(active_valid),.active_model_id(active_model_id),
        .active_generation(active_generation),
        .active_tile_id(active_tile_id),.active_lines(active_lines),
        .reuse_count(reuse_count),.pending_valid(pending_valid),
        .read_en(weight_read_en),
        .read_addr(compute_active ? core_weight_read_addr : 5'd0),
        .read_valid(weight_read_valid),.read_data(weight_read_data),
        .mem_req_valid(b_req_valid),.mem_req_ready(b_req_ready),
        .mem_req_write(),.mem_req_addr(b_req_addr),
        .mem_req_len(b_req_len),.mem_rsp_valid(b_rsp_valid),
        .mem_rsp_ready(b_rsp_ready),.mem_rsp_rdata(b_rsp_rdata),
        .mem_rsp_last(b_rsp_last),.mem_rsp_error(b_rsp_error),
        .mem_abort(weight_abort),.load_busy(weight_busy),
        .load_done(weight_done),.load_error(weight_error),
        .weight_ddr_bytes(weight_ddr_bytes),.cycles(weight_cycles)
    );
    mac_conv_compute_core u_compute (
        .clk(clk),.resetn(engine_resetn),.start(compute_launch),.abort(compute_abort),
        .start_ready(core_start_ready),.width(cfg_width),.height(cfg_height),
        .channels(cfg_channels),.output_channels(cfg_output_channels),
        .kernel(cfg_kernel),.stride(cfg_stride),.padding(cfg_padding),
        .weight_lines(cfg_weight_lines),.quant_bias(quant_bias_bus),
        .quant_shift(quant_shift_bus),.tap_valid(tap_valid),
        .tap_ready(core_tap_ready),.tap_data(tap_data),.tap_x(tap_x),
        .tap_y(tap_y),.tap_kx(tap_kx),.tap_ky(tap_ky),.tap_tile(tap_tile),
        .weight_read_en(core_weight_read_en),
        .weight_read_addr(core_weight_read_addr),
        .weight_read_valid(weight_read_valid),.weight_read_data(weight_read_data),
        .out_valid(core_out_valid),.out_ready(core_out_ready),
        .out_data(core_out_data),.out_last(core_out_last),
        .done(core_done),.error(core_error),.cycles(core_cycles)
    );
    mac_conv_compact_packer u_packer (
        .clk(clk),.resetn(engine_resetn),.start(compute_launch),.abort(compute_abort),
        .start_ready(packer_start_ready),.base_addr(cfg_output_dst),
        .total_bytes(output_bytes),.byte_valid(core_out_valid),
        .byte_ready(core_out_ready),.byte_data(core_out_data),
        .byte_last(core_out_last),.word_valid(packer_word_valid),
        .word_ready(packer_word_ready),.word_addr(packer_word_addr),
        .word_data(packer_word_data),.word_strb(packer_word_strb),
        .done(packer_done),.error(packer_error),
        .output_ddr_bytes(output_ddr_bytes)
    );
    wire w_req_valid,w_req_ready,w_rsp_valid,w_rsp_ready,w_rsp_last,w_rsp_error;
    wire [31:0] w_req_addr,w_w_data;
    wire [2:0] w_req_len;
    wire w_w_valid,w_w_ready,w_w_last;
    wire [3:0] w_w_strb;
    mac_conv_compact_writer #(
        .DDR_BASE(DDR_BASE),.DDR_BYTES(DDR_BYTES),
        .TIMEOUT_CYCLES(TIMEOUT_CYCLES)
    ) u_writer (
        .clk(clk),.resetn(engine_resetn),.word_valid(packer_word_valid),
        .word_ready(packer_word_ready),.word_addr(packer_word_addr),
        .word_data(packer_word_data),.word_strb(packer_word_strb),
        .mem_req_valid(w_req_valid),.mem_req_ready(w_req_ready),
        .mem_req_write(),.mem_req_addr(w_req_addr),.mem_req_len(w_req_len),
        .mem_w_valid(w_w_valid),.mem_w_ready(w_w_ready),
        .mem_w_data(w_w_data),.mem_w_strb(w_w_strb),.mem_w_last(w_w_last),
        .mem_rsp_valid(w_rsp_valid),.mem_rsp_ready(w_rsp_ready),
        .mem_rsp_last(w_rsp_last),.mem_rsp_error(w_rsp_error),
        .mem_abort(writer_abort),.error(writer_error)
    );
    wire r_req_valid,r_req_ready,r_rsp_valid,r_rsp_ready,r_rsp_last,r_rsp_error,r_abort;
    wire [31:0] r_req_addr,r_rsp_rdata;
    wire [2:0] r_req_len;
    mac_conv_read_arbiter2 u_reads (
        .clk(clk),.resetn(engine_resetn),
        .a_req_valid(a_req_valid),.a_req_ready(a_req_ready),
        .a_req_addr(a_req_addr),.a_req_len(a_req_len),
        .a_rsp_valid(a_rsp_valid),.a_rsp_ready(a_rsp_ready),
        .a_rsp_rdata(a_rsp_rdata),.a_rsp_last(a_rsp_last),
        .a_rsp_error(a_rsp_error),.a_abort(input_abort),
        .b_req_valid(b_req_valid),.b_req_ready(b_req_ready),
        .b_req_addr(b_req_addr),.b_req_len(b_req_len),
        .b_rsp_valid(b_rsp_valid),.b_rsp_ready(b_rsp_ready),
        .b_rsp_rdata(b_rsp_rdata),.b_rsp_last(b_rsp_last),
        .b_rsp_error(b_rsp_error),.b_abort(weight_abort),
        .mem_req_valid(r_req_valid),.mem_req_ready(r_req_ready),
        .mem_req_addr(r_req_addr),.mem_req_len(r_req_len),
        .mem_rsp_valid(r_rsp_valid),.mem_rsp_ready(r_rsp_ready),
        .mem_rsp_rdata(r_rsp_rdata),.mem_rsp_last(r_rsp_last),
        .mem_rsp_error(r_rsp_error),.mem_abort(r_abort)
    );
    wire rw_mem_abort;
    mac_conv_rw_arbiter2 u_rw (
        .clk(clk),.resetn(engine_resetn),
        .r_req_valid(r_req_valid),.r_req_ready(r_req_ready),
        .r_req_addr(r_req_addr),.r_req_len(r_req_len),
        .r_rsp_valid(r_rsp_valid),.r_rsp_ready(r_rsp_ready),
        .r_rsp_rdata(r_rsp_rdata),.r_rsp_last(r_rsp_last),
        .r_rsp_error(r_rsp_error),.r_abort(r_abort),
        .w_req_valid(w_req_valid),.w_req_ready(w_req_ready),
        .w_req_addr(w_req_addr),.w_req_len(w_req_len),
        .w_w_valid(w_w_valid),.w_w_ready(w_w_ready),
        .w_w_data(w_w_data),.w_w_strb(w_w_strb),.w_w_last(w_w_last),
        .w_rsp_valid(w_rsp_valid),.w_rsp_ready(w_rsp_ready),
        .w_rsp_last(w_rsp_last),.w_rsp_error(w_rsp_error),.w_abort(writer_abort),
        .mem_req_valid(mem_req_valid),.mem_req_ready(mem_req_ready),
        .mem_req_write(mem_req_write),.mem_req_addr(mem_req_addr),
        .mem_req_len(mem_req_len),.mem_w_valid(mem_w_valid),
        .mem_w_ready(mem_w_ready),.mem_w_data(mem_w_data),
        .mem_w_strb(mem_w_strb),.mem_w_last(mem_w_last),
        .mem_rsp_valid(mem_rsp_valid),.mem_rsp_ready(mem_rsp_ready),
        .mem_rsp_rdata(mem_rsp_rdata),.mem_rsp_last(mem_rsp_last),
        .mem_rsp_error(mem_rsp_error),.mem_abort(rw_mem_abort)
    );
    assign mem_abort = command_abort || rw_mem_abort;

    always @* begin
        reg_rd_data = 0;
        case (reg_rd_addr)
            8'h40: reg_rd_data = 32'h4d43_4f4e; // MCON
            8'h44: reg_rd_data = 32'h0003_0000;
            8'h48: reg_rd_data = {16'b0,error_code,2'b0,
                compute_error_sticky,compute_done_sticky,
                active_valid,pending_valid,input_error_sticky,
                input_done_sticky,input_busy,weight_error_sticky,
                weight_done_sticky,weight_busy};
            8'h4c: reg_rd_data = {7'b0,cfg_height,7'b0,cfg_width};
            8'h50: reg_rd_data = {5'b0,cfg_padding,2'b0,
                                 cfg_stride,1'b0,cfg_kernel,cfg_channels};
            8'h54: reg_rd_data = {cfg_output_channels,8'b0,cfg_tile};
            8'h58: reg_rd_data = cfg_input_src;
            8'h5c: reg_rd_data = cfg_weight_src;
            8'h60: reg_rd_data = cfg_output_dst;
            8'h64: reg_rd_data = {26'b0,cfg_weight_lines};
            8'h68: reg_rd_data = cfg_model_id[31:0];
            8'h6c: reg_rd_data = cfg_model_id[63:32];
            8'h70: reg_rd_data = cfg_generation;
            8'h74: reg_rd_data = input_cycles;
            8'h78: reg_rd_data = {24'b0,counter_select};
            8'h7c: case (counter_select)
                0: reg_rd_data = input_ddr_bytes;
                1: reg_rd_data = weight_ddr_bytes;
                2: reg_rd_data = window_taps;
                3: reg_rd_data = reuse_count;
                4: reg_rd_data = stall_cycles;
                5: reg_rd_data = input_cycles;
                6: reg_rd_data = weight_cycles;
                7: reg_rd_data = tap_xor;
                8: reg_rd_data = active_generation;
                9: reg_rd_data = active_tile_id;
                10: reg_rd_data = {26'b0,active_lines};
                11: reg_rd_data = weight_read_xor;
                12: reg_rd_data = output_ddr_bytes;
                13: reg_rd_data = core_cycles;
                14: reg_rd_data = {31'b0,compute_active};
                8'h20,8'h21,8'h22,8'h23,8'h24,8'h25,8'h26,8'h27,
                8'h28,8'h29,8'h2a,8'h2b,8'h2c,8'h2d,8'h2e,8'h2f:
                    reg_rd_data=quant_bias_words[counter_select[3:0]];
                8'h40,8'h41,8'h42,8'h43,8'h44,8'h45,8'h46,8'h47,
                8'h48,8'h49,8'h4a,8'h4b,8'h4c,8'h4d,8'h4e,8'h4f:
                    reg_rd_data={27'b0,quant_shift_words[counter_select[3:0]]};
                default: reg_rd_data = 0;
            endcase
            default: reg_rd_data = 0;
        endcase
    end
    integer quant_reset_index;
    always @(posedge clk) begin
        if (!resetn) begin
            cfg_width<=0;cfg_height<=0;cfg_channels<=0;
            cfg_output_channels<=0;cfg_kernel<=0;cfg_stride<=0;
            cfg_padding<=0;cfg_tile<=0;cfg_input_src<=0;
            cfg_weight_src<=0;cfg_output_dst<=0;cfg_weight_lines<=0;
            cfg_model_id<=0;cfg_generation<=0;counter_select<=0;
            weight_done_sticky<=0;weight_error_sticky<=0;
            input_done_sticky<=0;input_error_sticky<=0;
            compute_done_sticky<=0;compute_error_sticky<=0;compute_active<=0;
            compute_kernel_r<=0;
            for (quant_reset_index=0;quant_reset_index<16;quant_reset_index=quant_reset_index+1) begin
                quant_bias_words[quant_reset_index]<=0;
                quant_shift_words[quant_reset_index]<=0;
            end
            error_code<=0;tap_xor<=0;weight_read_xor<=0;
        end else begin
            if (weight_done) weight_done_sticky<=1;
            if (input_done) input_done_sticky<=1;
            if (compute_launch) begin
                compute_active<=1;
                compute_kernel_r<=cfg_kernel;
            end
            if (command_abort) compute_active<=0;
            if (packer_done) begin
                compute_done_sticky<=1;compute_active<=0;
            end
            if (core_error || packer_error || writer_error ||
                (compute_active && input_error)) begin
                compute_error_sticky<=1;compute_active<=0;error_code<=6;
            end
            if (weight_error) begin weight_error_sticky<=1;error_code<=6;end
            if (input_error) begin input_error_sticky<=1;error_code<=6;end
            if (tap_valid && dma_tap_ready) tap_xor<=tap_xor^tap_data;
            if (weight_read_valid)
                weight_read_xor <= {weight_read_xor[30:0],weight_read_xor[31]} +
                                   folded_weight_read + 32'h9e37_79b9;
            if (command_clear) begin
                weight_done_sticky<=0;weight_error_sticky<=0;
                input_done_sticky<=0;input_error_sticky<=0;
                compute_done_sticky<=0;compute_error_sticky<=0;
                error_code<=0;tap_xor<=0;weight_read_xor<=0;
            end
            if (command_load && !launch_weight) begin
                weight_error_sticky<=1;
                error_code<=guard_valid ? 5 : guard_error;
            end
            if (command_input && !launch_input) begin
                input_error_sticky<=1;
                error_code<=guard_valid ? 5 : guard_error;
            end
            if (command_compute && !compute_launch) begin
                compute_error_sticky<=1;
                error_code<=guard_valid ? 5 : guard_error;
            end
            if (command_activate && !do_activate) begin
                weight_error_sticky<=1;
                error_code<=5;
            end
            if (reg_wr_en && reg_wr_strb[0]) begin
                case (reg_wr_addr)
                    8'h4c: begin
                        cfg_width<=reg_wr_data[8:0];
                        cfg_height<=reg_wr_data[24:16];
                    end
                    8'h50: begin
                        cfg_channels<=reg_wr_data[15:0];
                        cfg_kernel<=reg_wr_data[18:16];
                        cfg_stride<=reg_wr_data[21:20];
                        cfg_padding<=reg_wr_data[26:24];
                    end
                    8'h54: begin
                        cfg_tile<=reg_wr_data[7:0];
                        cfg_output_channels<=reg_wr_data[31:16];
                    end
                    8'h58: cfg_input_src<=reg_wr_data;
                    8'h5c: cfg_weight_src<=reg_wr_data;
                    8'h60: cfg_output_dst<=reg_wr_data;
                    8'h64: cfg_weight_lines<=reg_wr_data[5:0];
                    8'h68: cfg_model_id[31:0]<=reg_wr_data;
                    8'h6c: cfg_model_id[63:32]<=reg_wr_data;
                    8'h70: cfg_generation<=reg_wr_data;
                    8'h78: counter_select<=reg_wr_data[7:0];
                    8'h7c: if (!input_busy && !compute_active) begin
                        if (counter_select>=8'h20 && counter_select<=8'h2f)
                            quant_bias_words[counter_select[3:0]]<=reg_wr_data;
                        if (counter_select>=8'h40 && counter_select<=8'h4f)
                            quant_shift_words[counter_select[3:0]]<=reg_wr_data[4:0];
                    end
                    default: begin end
                endcase
            end
        end
    end
endmodule
