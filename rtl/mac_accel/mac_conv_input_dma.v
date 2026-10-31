`timescale 1ns / 1ps
// One channel tile of NHWC4 image data through a bounded AXI read port and
// the stage-2 window. One command is outstanding; no request crosses 4 KiB.
module mac_conv_input_dma #(
    parameter [31:0] DDR_BASE = 32'h0000_0000,
    parameter integer DDR_BYTES = 256 * 1024 * 1024,
    parameter integer MAX_WIDTH = 320,
    parameter integer TIMEOUT_CYCLES = 100000
) (
    input wire clk,
    input wire resetn,
    input wire start,
    output wire start_ready,
    input wire [8:0] width,
    input wire [8:0] height,
    input wire [15:0] channels,
    input wire [7:0] channel_tile,
    input wire [2:0] kernel,
    input wire [1:0] stride,
    input wire [2:0] padding,
    input wire [31:0] input_src,
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
    output wire out_valid,
    input wire out_ready,
    output wire [31:0] out_data,
    output wire [8:0] out_x,
    output wire [8:0] out_y,
    output wire [2:0] out_kx,
    output wire [2:0] out_ky,
    output wire [7:0] out_tile_id,
    output wire busy,
    output reg done,
    output reg error,
    output reg [31:0] input_ddr_bytes,
    output wire [31:0] window_taps,
    output wire [31:0] stall_cycles,
    output reg [31:0] cycles
);
    localparam [2:0] S_IDLE=0, S_CFG=1, S_REQ=2, S_RSP=3,
                     S_FEED=4, S_WAIT=5, S_DRAIN=6;
    localparam [32:0] DDR_LIMIT = {1'b0, DDR_BASE} + DDR_BYTES;
    localparam integer TIMEOUT_WIDTH = TIMEOUT_CYCLES > 1 ? $clog2(TIMEOUT_CYCLES) : 1;
    reg [2:0] state;
    reg [8:0] width_r, height_r;
    reg [15:0] channels_r;
    reg [7:0] tile_r;
    reg [2:0] kernel_r, padding_r;
    reg [1:0] stride_r;
    reg [31:0] source_r;
    // Even all 9-bit width/height values fit an 18-bit pixel count.
    reg [17:0] source_pixel,total_pixels;
    reg [10:0] pixel_step_r;
    reg [3:0] burst_words, rsp_index, feed_index;
    reg [31:0] buffer [0:7];
    reg [TIMEOUT_WIDTH-1:0] timeout;
    wire [15:0] tiles = (channels + 16'd3) >> 2;
    wire [31:0] tensor_bytes = width * height * tiles * 32'd4;
    wire [32:0] input_end = {1'b0, input_src} + {1'b0, tensor_bytes};
    wire cfg_bad = width == 0 || width > MAX_WIDTH ||
                   height == 0 || height > 320 ||
                   channels == 0 || channels > 1024 ||
                   {8'b0, channel_tile} >= tiles ||
                   (kernel != 1 && kernel != 3 && kernel != 6) ||
                   (stride != 1 && stride != 2) ||
                   padding >= kernel ||
                   (kernel == 1 && padding != 0) ||
                   width + ({6'b0, padding} << 1) < kernel ||
                   height + ({6'b0, padding} << 1) < kernel ||
                   input_src[1:0] != 0 ||
                   {1'b0, input_src} < {1'b0, DDR_BASE} ||
                   input_end > DDR_LIMIT;
    // The checked Cin range gives a 4..1024-byte pixel step. Maintain the
    // selected tile address on each accepted pixel instead of multiplying
    // the pixel index by channel tiles on the request/4-KiB boundary path.
    wire [31:0] next_addr = source_r;
    wire contiguous = channels_r <= 4;
    wire [31:0] pixels_left = total_pixels - source_pixel;
    wire [10:0] words_to_page = (13'd4096 - {1'b0, next_addr[11:0]}) >> 2;
    wire [3:0] burst_limit = pixels_left >= 8 ? 4'd8 : pixels_left[3:0];
    wire [3:0] page_limit = words_to_page >= 8 ? 4'd8 : words_to_page[3:0];
    wire [3:0] next_burst_words = !contiguous ? 4'd1 :
                                  burst_limit < page_limit ? burst_limit :
                                  page_limit;
    wire cfg_ready, win_in_ready, win_done, win_error;
    wire [31:0] win_input_beats;
    wire win_in_valid = state == S_FEED;
    wire [15:0] lane_base = {6'b0,tile_r,2'b0};
    wire [31:0] raw_word = buffer[feed_index[2:0]];
    wire [31:0] win_in_data = {
        channels_r > lane_base + 3 ? raw_word[31:24] : 8'b0,
        channels_r > lane_base + 2 ? raw_word[23:16] : 8'b0,
        channels_r > lane_base + 1 ? raw_word[15:8] : 8'b0,
        raw_word[7:0]
    };
    assign start_ready = state == S_IDLE && resetn;
    assign busy = state != S_IDLE;
    assign mem_req_valid = state == S_REQ;
    assign mem_req_write = 1'b0;
    assign mem_req_addr = next_addr;
    assign mem_req_len = next_burst_words - 4'd1;
    assign mem_rsp_ready = state == S_RSP || state == S_DRAIN;

    mac_conv_window #(.MAX_WIDTH(MAX_WIDTH)) u_window (
        .clk(clk), .resetn(resetn), .flush(error),
        .cfg_valid(state == S_CFG), .cfg_ready(cfg_ready),
        .cfg_width(width_r), .cfg_height(height_r),
        .cfg_kernel(kernel_r), .cfg_stride(stride_r),
        .cfg_padding(padding_r), .cfg_tile_id(tile_r),
        .in_valid(win_in_valid), .in_ready(win_in_ready),
        .in_data(win_in_data), .out_valid(out_valid),
        .out_ready(out_ready), .out_data(out_data),
        .out_x(out_x), .out_y(out_y),
        .out_kx(out_kx), .out_ky(out_ky),
        .out_tile_id(out_tile_id), .done(win_done),
        .error(win_error), .input_beats(win_input_beats),
        .output_beats(window_taps), .stall_cycles(stall_cycles)
    );

    always @(posedge clk) begin
        if (!resetn) begin
            state <= S_IDLE;
            done <= 0; error <= 0;
            mem_abort <= 0;
            input_ddr_bytes <= 0; cycles <= 0; timeout <= 0;
            width_r <= 0; height_r <= 0; channels_r <= 0;
            tile_r <= 0; kernel_r <= 0; stride_r <= 0; padding_r <= 0;
            source_r <= 0; source_pixel <= 0; total_pixels <= 0;pixel_step_r <= 0;
            burst_words <= 0; rsp_index <= 0; feed_index <= 0;
        end else begin
            done <= 0; error <= 0; mem_abort <= 0;
            if (state != S_IDLE) cycles <= cycles + 1'b1;
            if (win_error) begin
                state <= S_IDLE;
                error <= 1;
            end else case (state)
                S_IDLE: if (start) begin
                    cycles <= 0;
                    input_ddr_bytes <= 0;
                    if (cfg_bad) error <= 1;
                    else begin
                        width_r <= width; height_r <= height;
                        channels_r <= channels; tile_r <= channel_tile;
                        kernel_r <= kernel; padding_r <= padding;
                        stride_r <= stride;
                        source_r <= input_src + {22'b0,channel_tile,2'b0};
                        pixel_step_r <= tiles << 2;
                        source_pixel <= 0;
                        total_pixels <= width * height;
                        state <= S_CFG;
                    end
                end
                S_CFG: if (cfg_ready) begin
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
                    error <= 1;
                end else timeout <= timeout + 1'b1;
                S_RSP: if (mem_rsp_valid && mem_rsp_ready) begin
                    timeout <= 0;
                    input_ddr_bytes <= input_ddr_bytes + 4;
                    if (mem_rsp_error || mem_rsp_last !=
                        (rsp_index + 1 == burst_words)) begin
                        if (mem_rsp_last) begin
                            state <= S_IDLE;
                            error <= 1;
                        end else state <= S_DRAIN;
                    end else begin
                        buffer[rsp_index[2:0]] <= mem_rsp_rdata;
                        if (mem_rsp_last) begin
                            feed_index <= 0;
                            state <= S_FEED;
                        end else rsp_index <= rsp_index + 1'b1;
                    end
                end else if (timeout == TIMEOUT_CYCLES-1) begin
                    state <= S_IDLE;
                    error <= 1;
                    mem_abort <= 1;
                end else timeout <= timeout + 1'b1;
                S_FEED: if (win_in_valid && win_in_ready) begin
                    source_pixel <= source_pixel + 1'b1;
                    source_r <= source_r + {21'b0,pixel_step_r};
                    if (feed_index + 1 == burst_words) begin
                        if (source_pixel + 1 == total_pixels)
                            state <= S_WAIT;
                        else begin
                            state <= S_REQ;
                            timeout <= 0;
                        end
                    end else feed_index <= feed_index + 1'b1;
                end
                S_WAIT: if (win_done) begin
                    done <= 1;
                    state <= S_IDLE;
                end
                S_DRAIN: if (mem_rsp_valid && mem_rsp_ready) begin
                    timeout <= 0;
                    if (mem_rsp_last) begin
                        error <= 1;
                        state <= S_IDLE;
                    end
                end else if (timeout == TIMEOUT_CYCLES-1) begin
                    state <= S_IDLE;
                    error <= 1;
                    mem_abort <= 1;
                end else timeout <= timeout + 1'b1;
                default: state <= S_IDLE;
            endcase
        end
    end
endmodule
