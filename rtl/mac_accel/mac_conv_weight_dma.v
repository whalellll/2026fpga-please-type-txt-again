`timescale 1ns / 1ps
// AXI read loader for one 1024-bit-line weight tile. The active bank can be
// read while this module fills the inactive bank from DDR.
module mac_conv_weight_dma #(
    parameter [31:0] DDR_BASE = 32'h0000_0000,
    parameter integer DDR_BYTES = 256 * 1024 * 1024,
    parameter integer TIMEOUT_CYCLES = 100000,
    parameter integer FOLD_UPPER_HALF = 0,
    parameter integer STREAM_UPPER_FOLD = 0
) (
    input wire clk,
    input wire resetn,
    input wire load_start,
    output wire load_start_ready,
    input wire [31:0] weight_src,
    input wire [5:0] weight_lines,
    input wire [63:0] model_id,
    input wire [31:0] generation,
    input wire [31:0] tile_id,
    input wire activate,
    output wire activate_ready,
    input wire compute_idle,
    input wire window_done,
    output wire active_valid,
    output wire [63:0] active_model_id,
    output wire [31:0] active_generation,
    output wire [31:0] active_tile_id,
    output wire [5:0] active_lines,
    output wire [31:0] reuse_count,
    output wire pending_valid,
    input wire read_en,
    input wire [4:0] read_addr,
    output wire read_valid,
    output wire [1023:0] read_data,
    output wire mem_req_valid,
    input wire mem_req_ready,
    output wire mem_req_write,
    output wire [31:0] mem_req_addr,
    output wire [2:0] mem_req_len,
    input wire mem_rsp_valid,
    output wire mem_rsp_ready,
    input wire [31:0] mem_rsp_rdata,
    input wire mem_rsp_last,
    input wire mem_rsp_error,
    output reg mem_abort,
    output wire load_busy,
    output reg load_done,
    output reg load_error,
    output reg [31:0] weight_ddr_bytes,
    output reg [31:0] cycles
);
    localparam [2:0] S_IDLE=0, S_BEGIN=1, S_REQ=2, S_RSP=3,
                     S_WRITE=4, S_DRAIN=5;
    localparam [32:0] DDR_LIMIT = {1'b0, DDR_BASE} + DDR_BYTES;
    localparam integer TIMEOUT_WIDTH = TIMEOUT_CYCLES > 1 ? $clog2(TIMEOUT_CYCLES) : 1;
    reg [2:0] state;
    reg [31:0] source_r;
    reg [TIMEOUT_WIDTH-1:0] timeout;
    reg [5:0] lines_r, line_index, word_index;
    reg [63:0] model_r;
    reg [31:0] generation_r, tile_r;
    reg [3:0] burst_words, rsp_index;
    localparam integer STREAM_FOLDED = FOLD_UPPER_HALF && STREAM_UPPER_FOLD;
    localparam integer SHIFT_WIDTH = STREAM_FOLDED ? 512 : 1024;
    reg [SHIFT_WIDTH-1:0] line_shift;
    reg [31:0] upper_fold;
    wire buf_load_start_ready, buf_load_ready, buf_load_error;
    wire [32:0] weight_end = {1'b0, weight_src} +
                             ({27'b0, weight_lines} << 7);
    wire descriptor_bad = weight_lines == 0 || weight_lines > 32 ||
                          weight_src[1:0] != 0 ||
                          {1'b0, weight_src} < {1'b0, DDR_BASE} ||
                          weight_end > DDR_LIMIT;
    wire [5:0] words_left = 6'd32 - word_index;
    wire [10:0] words_to_page =
        (13'd4096 - {1'b0, mem_req_addr[11:0]}) >> 2;
    wire [3:0] line_limit = words_left >= 8 ? 4'd8 : words_left[3:0];
    wire [3:0] page_limit = words_to_page >= 8 ? 4'd8 : words_to_page[3:0];
    wire [3:0] next_burst_words = line_limit < page_limit ?
                                  line_limit : page_limit;
    assign load_start_ready = state == S_IDLE && buf_load_start_ready && resetn;
    assign load_busy = state != S_IDLE;
    assign mem_req_valid = state == S_REQ;
    assign mem_req_write = 1'b0;
    assign mem_req_addr = source_r + ({26'b0, line_index} << 7) +
                          ({26'b0, word_index} << 2);
    assign mem_req_len = next_burst_words - 4'd1;
    assign mem_rsp_ready = state == S_RSP || state == S_DRAIN;

    // Only the integrated16-channel compute/window frontend enables this.
    // Keep all128DDR bytes/line. Preserve low512MAC bits and the exact upper
    // checksum contribution; default mode still returns all1024raw bits.
    localparam integer STORE_WIDTH = FOLD_UPPER_HALF ? 544 : 1024;
    function [31:0] fold_upper;
        input [1023:0] words;
        integer i;
        reg [31:0] value;
        begin
            value=0;
            for(i=16;i<32;i=i+1)
                value={value[26:0],value[31:27]}^words[i*32 +:32];
            fold_upper=value;
        end
    endfunction
    wire [STORE_WIDTH-1:0] store_load;
    wire [STORE_WIDTH-1:0] store_read;
    generate if(FOLD_UPPER_HALF) begin:g_folded
        if (STREAM_FOLDED) begin : g_stream
            // Half80 native run d9ad97c: line_shift[120] -> bank0_60/DIL
            // has -28ps/-15ps hold. Keep the complete capture/publication
            // boundaries; one preserved identity LUT pads this data pair.
            wire [1:0] write_hold_pair;
`ifdef SYNTHESIS
            (* PAP_DONT_TOUCH *) GTP_LUT6D #(.INIT(64'hCCCCCCCC_AAAAAAAA)) u_line_write_hold_lut (
                .I0(line_shift[120]), .I1(line_shift[121]),
                .I2(1'b0), .I3(1'b0), .I4(1'b0), .I5(1'b1),
                .Z5(write_hold_pair[0]), .Z(write_hold_pair[1])
            );
`else
            assign write_hold_pair=line_shift[121:120];
`endif
            assign store_load={upper_fold,line_shift[511:122],write_hold_pair,line_shift[119:0]};
        end else begin : g_parallel
            assign store_load={fold_upper(line_shift),line_shift[511:0]};
        end
        assign read_data={store_read[543:512],480'b0,store_read[511:0]};
    end else begin:g_raw
        assign store_load=line_shift;
        assign read_data=store_read;
    end endgenerate
    mac_weight_double_buffer #(.DATA_WIDTH(STORE_WIDTH)) u_buffer (
        .clk(clk), .resetn(resetn),
        .load_start(state == S_BEGIN && buf_load_start_ready),
        .load_start_ready(buf_load_start_ready),
        .load_lines(lines_r), .load_model_id(model_r),
        .load_generation(generation_r), .load_tile_id(tile_r),
        .load_valid(state == S_WRITE && buf_load_ready),
        .load_ready(buf_load_ready), .load_data(store_load),
        .load_last(line_index + 1 == lines_r),
        .load_abort(load_error || mem_abort),
        .load_error(buf_load_error),
        .activate(activate), .activate_ready(activate_ready),
        .compute_idle(compute_idle), .active_valid(active_valid),
        .active_model_id(active_model_id),
        .active_generation(active_generation),
        .active_tile_id(active_tile_id), .active_lines(active_lines),
        .reuse_count(reuse_count), .window_done(window_done),
        .read_en(read_en), .read_addr(read_addr),
        .read_valid(read_valid), .read_data(store_read),
        .pending_valid(pending_valid)
    );

    always @(posedge clk) begin
        if (!resetn) begin
            state <= S_IDLE;
            source_r <= 0; lines_r <= 0;
            model_r <= 0; generation_r <= 0; tile_r <= 0;
            line_index <= 0; word_index <= 0;
            burst_words <= 0; rsp_index <= 0;
            line_shift <= 0; upper_fold <= 0; timeout <= 0;
            mem_abort <= 0; load_done <= 0; load_error <= 0;
            weight_ddr_bytes <= 0; cycles <= 0;
        end else begin
            mem_abort <= 0; load_done <= 0; load_error <= 0;
            if (state != S_IDLE) cycles <= cycles + 1'b1;
            if (buf_load_error) begin
                state <= S_IDLE;
                load_error <= 1;
            end else case (state)
                S_IDLE: if (load_start) begin
                    cycles <= 0;
                    weight_ddr_bytes <= 0;
                    if (descriptor_bad || !buf_load_start_ready)
                        load_error <= 1;
                    else begin
                        source_r <= weight_src;
                        lines_r <= weight_lines;
                        model_r <= model_id;
                        generation_r <= generation;
                        tile_r <= tile_id;
                        line_index <= 0;
                        word_index <= 0;
                        state <= S_BEGIN;
                    end
                end
                S_BEGIN: if (buf_load_start_ready) begin
                    state <= S_REQ;
                    timeout <= 0;
                end
                S_REQ: if (mem_req_valid && mem_req_ready) begin
                    burst_words <= next_burst_words;
                    rsp_index <= 0;
                    timeout <= 0;
                    state <= S_RSP;
                end else if (timeout == TIMEOUT_CYCLES-1) begin
                    state <= S_IDLE;
                    load_error <= 1;
                end else timeout <= timeout + 1'b1;
                S_RSP: if (mem_rsp_valid && mem_rsp_ready) begin
                    timeout <= 0;
                    weight_ddr_bytes <= weight_ddr_bytes + 4;
                    if (mem_rsp_error || mem_rsp_last !=
                        (rsp_index + 1 == burst_words)) begin
                        if (mem_rsp_last) begin
                            state <= S_IDLE;
                            load_error <= 1;
                        end else state <= S_DRAIN;
                    end else begin
                        // Capture the same 128 DDR bytes and publish on the
                        // original S_WRITE cycle. Only the low sixteen words
                        // are MAC data; fold the high words as they arrive.
                        if (!STREAM_FOLDED || !word_index[4])
                            line_shift <= {mem_rsp_rdata, line_shift[SHIFT_WIDTH-1:32]};
                        if (STREAM_FOLDED && word_index[4])
                            upper_fold <= word_index == 6'd16 ? mem_rsp_rdata :
                                {upper_fold[26:0], upper_fold[31:27]} ^ mem_rsp_rdata;
                        word_index <= word_index + 1'b1;
                        if (mem_rsp_last) begin
                            if (word_index + 1 == 32) state <= S_WRITE;
                            else state <= S_REQ;
                        end else rsp_index <= rsp_index + 1'b1;
                    end
                end else if (timeout == TIMEOUT_CYCLES-1) begin
                    state <= S_IDLE;
                    load_error <= 1;
                    mem_abort <= 1;
                end else timeout <= timeout + 1'b1;
                S_WRITE: if (buf_load_ready) begin
                    if (line_index + 1 == lines_r) begin
                        load_done <= 1;
                        state <= S_IDLE;
                    end else begin
                        line_index <= line_index + 1'b1;
                        word_index <= 0;
                        state <= S_REQ;
                    end
                end
                S_DRAIN: if (mem_rsp_valid && mem_rsp_ready) begin
                    timeout <= 0;
                    if (mem_rsp_last) begin
                        state <= S_IDLE;
                        load_error <= 1;
                    end
                end else if (timeout == TIMEOUT_CYCLES-1) begin
                    state <= S_IDLE;
                    load_error <= 1;
                    mem_abort <= 1;
                end else timeout <= timeout + 1'b1;
                default: state <= S_IDLE;
            endcase
        end
    end
endmodule
