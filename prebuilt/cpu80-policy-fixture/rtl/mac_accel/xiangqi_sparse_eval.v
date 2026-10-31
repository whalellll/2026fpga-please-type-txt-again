`timescale 1ns / 1ps

// Sparse fused NNUE child evaluator for Xiangqi search.
//
// Software supplies the two already-scaled parent accumulators and up to six
// feature-row changes for each child.  The engine reads the changed rows from
// DDR, applies them locally, performs clipped-ReLU/output accumulation and
// returns as many as 16 exact integer scores through MMIO registers.  Keeping
// results in registers avoids a DDR write/read round trip for a sibling batch.
module xiangqi_sparse_eval #(
    parameter [31:0] DDR_BASE = 32'h0000_0000,
    parameter integer DDR_BYTES = 256 * 1024 * 1024,
    parameter integer MODEL_ROWS = 1620
) (
    input  wire        clk,
    input  wire        resetn,

    input  wire        reg_wr_en,
    input  wire [7:0]  reg_wr_addr,
    input  wire [31:0] reg_wr_data,
    input  wire [3:0]  reg_wr_strb,
    input  wire [7:0]  reg_rd_addr,
    output reg  [31:0] reg_rd_data,

    output reg         mem_req_valid,
    input  wire        mem_req_ready,
    output wire        mem_req_write,
    output reg  [31:0] mem_req_addr,
    output reg  [2:0]  mem_req_len,

    output wire        mem_w_valid,
    input  wire        mem_w_ready,
    output wire [31:0] mem_w_data,
    output wire [3:0]  mem_w_strb,
    output wire        mem_w_last,

    input  wire        mem_rsp_valid,
    output reg         mem_rsp_ready,
    input  wire [31:0] mem_rsp_rdata,
    input  wire        mem_rsp_last,
    input  wire        mem_rsp_error,

    output wire        irq
);

    localparam [3:0] S_IDLE       = 4'd0;
    localparam [3:0] S_BASE_REQ   = 4'd1;
    localparam [3:0] S_BASE_DATA  = 4'd2;
    localparam [3:0] S_OW_REQ     = 4'd3;
    localparam [3:0] S_OW_DATA    = 4'd4;
    localparam [3:0] S_DESC_REQ   = 4'd5;
    localparam [3:0] S_DESC_DATA  = 4'd6;
    localparam [3:0] S_CLEAR      = 4'd7;
    localparam [3:0] S_ROW_PICK   = 4'd8;
    localparam [3:0] S_ROW_REQ    = 4'd9;
    localparam [3:0] S_ROW_DATA   = 4'd10;
    localparam [3:0] S_COMPUTE    = 4'd11;
    localparam [3:0] S_DIV_PREP   = 4'd12;
    localparam [3:0] S_DIV_RUN    = 4'd13;
    localparam [3:0] S_NEXT       = 4'd14;

    localparam [3:0] ERR_NONE      = 4'd0;
    localparam [3:0] ERR_CONFIG    = 4'd1;
    localparam [3:0] ERR_DDR_RANGE = 4'd2;
    localparam [3:0] ERR_DDR_READ  = 4'd3;
    localparam [3:0] ERR_ROW_ID    = 4'd4;
    localparam [3:0] ERR_INTERNAL  = 4'd15;

    localparam [63:0] SCORE_DIVISOR = 64'd66064384;
    localparam [32:0] DDR_LIMIT = {1'b0, DDR_BASE} + DDR_BYTES;
    localparam [31:0] MODEL_BYTES = MODEL_ROWS * 128;

    reg [3:0] state;
    reg busy;
    reg done;
    reg error;
    reg [3:0] error_code;
    reg irq_enable;

    reg [4:0] child_count;
    reg [31:0] model_base;
    reg [31:0] parent_base;
    reg [31:0] output_weight_src;
    reg [31:0] descriptor_src;
    reg signed [63:0] score_bias_numerator;
    reg [31:0] cycle_count;
    reg [31:0] completed_runs;

    reg signed [31:0] parent_red [0:127];
    reg signed [31:0] parent_black [0:127];
    // Keep the four lanes of each DDR word in one memory word.  This turns
    // the weight store into two 32x32 single-write memories instead of 2048
    // individually enabled flip-flops.
    reg [31:0] output_weight_red [0:31];
    reg [31:0] output_weight_black [0:31];

    // Four explicit 32x10 banks match the four feature bytes updated by each
    // DDR beat.  Every bank now has only one write per clock and one shared
    // asynchronous read address, allowing PDS to map it as compact memory.
    reg signed [9:0] delta_red_b0 [0:31];
    reg signed [9:0] delta_red_b1 [0:31];
    reg signed [9:0] delta_red_b2 [0:31];
    reg signed [9:0] delta_red_b3 [0:31];
    reg signed [9:0] delta_black_b0 [0:31];
    reg signed [9:0] delta_black_b1 [0:31];
    reg signed [9:0] delta_black_b2 [0:31];
    reg signed [9:0] delta_black_b3 [0:31];
    reg [31:0] row_id [0:5];
    reg [31:0] score_result [0:15];

    reg [8:0] base_word;
    reg [6:0] weight_word;
    reg [3:0] descriptor_word;
    reg [5:0] row_word;
    reg [2:0] row_slot;
    reg [6:0] lane_index;
    reg [6:0] clear_index;
    reg [3:0] child_index;
    reg child_side;
    reg signed [63:0] mac_sum;
    reg signed [63:0] numerator;

    reg div_negative;
    reg [63:0] dividend;
    reg [63:0] quotient;
    reg [63:0] remainder;
    reg [6:0] div_count;

    integer i;

    wire control_write = reg_wr_en && (reg_wr_addr[7:2] == 6'h22);
    wire command_start = control_write && reg_wr_strb[0] && reg_wr_data[0];
    wire command_clear = control_write && reg_wr_strb[0] && reg_wr_data[1];
    wire config_aligned = (model_base[6:0] == 7'b0) &&
                          (parent_base[4:0] == 5'b0) &&
                          (output_weight_src[4:0] == 5'b0) &&
                          (descriptor_src[4:0] == 5'b0);
    localparam [32:0] DDR_FIRST = {1'b0, DDR_BASE};
    localparam [32:0] MODEL_LAST_BASE = DDR_LIMIT - MODEL_BYTES;
    localparam [32:0] PARENT_LAST_BASE = DDR_LIMIT - 33'd1024;
    localparam [32:0] WEIGHT_LAST_BASE = DDR_LIMIT - 33'd256;
    wire [32:0] descriptor_end = {1'b0, descriptor_src} +
                                 {23'b0, child_count, 5'b0};
    wire config_ranges = (MODEL_BYTES <= DDR_BYTES) &&
                         ({1'b0, model_base} >= DDR_FIRST) &&
                         ({1'b0, model_base} <= MODEL_LAST_BASE) &&
                         ({1'b0, parent_base} >= DDR_FIRST) &&
                         ({1'b0, parent_base} <= PARENT_LAST_BASE) &&
                         ({1'b0, output_weight_src} >= DDR_FIRST) &&
                         ({1'b0, output_weight_src} <= WEIGHT_LAST_BASE) &&
                         ({1'b0, descriptor_src} >= DDR_FIRST) &&
                         (descriptor_end <= DDR_LIMIT) &&
                         (descriptor_end > {1'b0, descriptor_src});
    wire config_count_ok = (child_count >= 5'd1) &&
                           (child_count <= 5'd16);

    wire selected_red = row_slot < 3;
    wire selected_negative = (row_slot == 0) || (row_slot == 2) ||
                             (row_slot == 3) || (row_slot == 5);
    reg [31:0] selected_row_id;

    // Keep this state-transition selector constant-indexed for PDS.  A
    // variable row_id[row_slot] read here directly controls error/next-state
    // decisions and has previously been unsafe in critical control paths.
    always @(*) begin
        case (row_slot)
            3'd0: selected_row_id = row_id[0];
            3'd1: selected_row_id = row_id[1];
            3'd2: selected_row_id = row_id[2];
            3'd3: selected_row_id = row_id[3];
            3'd4: selected_row_id = row_id[4];
            3'd5: selected_row_id = row_id[5];
            default: selected_row_id = 32'hffff_ffff;
        endcase
    end

    wire [4:0] delta_word_index = (state == S_ROW_DATA) ?
                                  row_word[4:0] : lane_index[6:2];
    wire signed [9:0] delta_red_b0_q = delta_red_b0[delta_word_index];
    wire signed [9:0] delta_red_b1_q = delta_red_b1[delta_word_index];
    wire signed [9:0] delta_red_b2_q = delta_red_b2[delta_word_index];
    wire signed [9:0] delta_red_b3_q = delta_red_b3[delta_word_index];
    wire signed [9:0] delta_black_b0_q = delta_black_b0[delta_word_index];
    wire signed [9:0] delta_black_b1_q = delta_black_b1[delta_word_index];
    wire signed [9:0] delta_black_b2_q = delta_black_b2[delta_word_index];
    wire signed [9:0] delta_black_b3_q = delta_black_b3[delta_word_index];
    wire signed [9:0] mem_rsp_byte0_extended =
        {{2{mem_rsp_rdata[7]}}, mem_rsp_rdata[7:0]};
    wire signed [9:0] mem_rsp_byte1_extended =
        {{2{mem_rsp_rdata[15]}}, mem_rsp_rdata[15:8]};
    wire signed [9:0] mem_rsp_byte2_extended =
        {{2{mem_rsp_rdata[23]}}, mem_rsp_rdata[23:16]};
    wire signed [9:0] mem_rsp_byte3_extended =
        {{2{mem_rsp_rdata[31]}}, mem_rsp_rdata[31:24]};
    reg signed [9:0] delta_red_lane;
    reg signed [9:0] delta_black_lane;

    always @(*) begin
        case (lane_index[1:0])
            2'd0: begin
                delta_red_lane = delta_red_b0_q;
                delta_black_lane = delta_black_b0_q;
            end
            2'd1: begin
                delta_red_lane = delta_red_b1_q;
                delta_black_lane = delta_black_b1_q;
            end
            2'd2: begin
                delta_red_lane = delta_red_b2_q;
                delta_black_lane = delta_black_b2_q;
            end
            default: begin
                delta_red_lane = delta_red_b3_q;
                delta_black_lane = delta_black_b3_q;
            end
        endcase
    end

    wire signed [31:0] delta_red_scaled =
        $signed(delta_red_lane) * 32'sd627;
    wire signed [31:0] delta_black_scaled =
        $signed(delta_black_lane) * 32'sd627;
    wire signed [31:0] red_hidden =
        $signed(parent_red[lane_index]) + delta_red_scaled;
    wire signed [31:0] black_hidden =
        $signed(parent_black[lane_index]) + delta_black_scaled;
    wire [31:0] weight_red_word = output_weight_red[lane_index[6:2]];
    wire [31:0] weight_black_word = output_weight_black[lane_index[6:2]];
    reg signed [7:0] weight_red_lane;
    reg signed [7:0] weight_black_lane;

    always @(*) begin
        case (lane_index[1:0])
            2'd0: begin
                weight_red_lane = weight_red_word[7:0];
                weight_black_lane = weight_black_word[7:0];
            end
            2'd1: begin
                weight_red_lane = weight_red_word[15:8];
                weight_black_lane = weight_black_word[15:8];
            end
            2'd2: begin
                weight_red_lane = weight_red_word[23:16];
                weight_black_lane = weight_black_word[23:16];
            end
            default: begin
                weight_red_lane = weight_red_word[31:24];
                weight_black_lane = weight_black_word[31:24];
            end
        endcase
    end
    wire signed [7:0] red_weight = child_side ?
        weight_black_lane : weight_red_lane;
    wire signed [7:0] black_weight = child_side ?
        weight_red_lane : weight_black_lane;
    wire signed [39:0] red_product = $signed(red_hidden) *
                                     $signed(red_weight);
    wire signed [39:0] black_product = $signed(black_hidden) *
                                       $signed(black_weight);
    wire signed [63:0] red_term = (red_hidden > 0) ?
        {{24{red_product[39]}}, red_product} : 64'sd0;
    wire signed [63:0] black_term = (black_hidden > 0) ?
        {{24{black_product[39]}}, black_product} : 64'sd0;
    wire signed [63:0] lane_sum_next = mac_sum + red_term + black_term;
    wire signed [63:0] scaled_lane_sum =
        (lane_sum_next <<< 10) + (lane_sum_next <<< 6) +
        (lane_sum_next <<< 2);

    wire [63:0] remainder_shift = {remainder[62:0], dividend[63]};
    wire divide_ge = remainder_shift >= SCORE_DIVISOR;
    wire [63:0] remainder_next = divide_ge ?
        remainder_shift - SCORE_DIVISOR : remainder_shift;
    wire [63:0] quotient_next = {quotient[62:0], divide_ge};
    wire [31:0] signed_quotient = div_negative ?
        (~quotient_next[31:0] + 32'd1) : quotient_next[31:0];

    assign mem_req_write = 1'b0;
    assign mem_w_valid = 1'b0;
    assign mem_w_data = 32'b0;
    assign mem_w_strb = 4'b0;
    assign mem_w_last = 1'b0;
    assign irq = irq_enable && done;

    always @(*) begin
        mem_req_valid = 1'b0;
        mem_req_addr = 32'b0;
        mem_req_len = 3'd7;
        mem_rsp_ready = 1'b0;
        case (state)
            S_BASE_REQ: begin
                mem_req_valid = 1'b1;
                mem_req_addr = parent_base + ({23'b0, base_word} << 2);
            end
            S_BASE_DATA: mem_rsp_ready = 1'b1;
            S_OW_REQ: begin
                mem_req_valid = 1'b1;
                mem_req_addr = output_weight_src +
                               ({25'b0, weight_word} << 2);
            end
            S_OW_DATA: mem_rsp_ready = 1'b1;
            S_DESC_REQ: begin
                mem_req_valid = 1'b1;
                mem_req_addr = descriptor_src +
                               ({28'b0, child_index} << 5);
            end
            S_DESC_DATA: mem_rsp_ready = 1'b1;
            S_ROW_REQ: begin
                mem_req_valid = 1'b1;
                mem_req_addr = model_base + (selected_row_id << 7) +
                               ({26'b0, row_word} << 2);
            end
            S_ROW_DATA: mem_rsp_ready = 1'b1;
            default: begin end
        endcase
    end

    always @(*) begin
        if (reg_rd_addr[7:6] == 2'b11) begin
            reg_rd_data = score_result[reg_rd_addr[5:2]];
        end else case (reg_rd_addr[7:2])
            6'h20: reg_rd_data = 32'h5851_5345; // XQSE
            6'h21: reg_rd_data = 32'h0001_0000;
            6'h22: reg_rd_data = {23'b0, irq_enable, 8'b0};
            6'h23: reg_rd_data = {
                12'b0, error_code, 7'b0, state, 2'b0,
                error, done, busy
            };
            6'h24: reg_rd_data = {27'b0, child_count};
            6'h25: reg_rd_data = model_base;
            6'h26: reg_rd_data = parent_base;
            6'h27: reg_rd_data = output_weight_src;
            6'h28: reg_rd_data = descriptor_src;
            6'h29: reg_rd_data = score_bias_numerator[31:0];
            6'h2a: reg_rd_data = score_bias_numerator[63:32];
            6'h2b: reg_rd_data = cycle_count;
            6'h2c: reg_rd_data = completed_runs;
            6'h2d: reg_rd_data = MODEL_ROWS;
            6'h2e: reg_rd_data = SCORE_DIVISOR[31:0];
            default: reg_rd_data = 32'b0;
        endcase
    end

    always @(posedge clk) begin
        if (!resetn) begin
            state <= S_IDLE;
            busy <= 1'b0;
            done <= 1'b0;
            error <= 1'b0;
            error_code <= ERR_NONE;
            irq_enable <= 1'b0;
            child_count <= 5'd1;
            model_base <= DDR_BASE;
            parent_base <= DDR_BASE;
            output_weight_src <= DDR_BASE;
            descriptor_src <= DDR_BASE;
            score_bias_numerator <= 64'sd0;
            cycle_count <= 32'b0;
            completed_runs <= 32'b0;
            base_word <= 9'b0;
            weight_word <= 7'b0;
            descriptor_word <= 4'b0;
            row_word <= 6'b0;
            row_slot <= 3'b0;
            lane_index <= 7'b0;
            clear_index <= 7'b0;
            child_index <= 4'b0;
            child_side <= 1'b0;
            mac_sum <= 64'sd0;
            numerator <= 64'sd0;
            div_negative <= 1'b0;
            dividend <= 64'b0;
            quotient <= 64'b0;
            remainder <= 64'b0;
            div_count <= 7'b0;
            for (i = 0; i < 6; i = i + 1)
                row_id[i] <= 32'hffff_ffff;
        end else begin
            if (busy)
                cycle_count <= cycle_count + 32'd1;

            if (reg_wr_en && !busy) begin
                case (reg_wr_addr[7:2])
                    6'h22: if (reg_wr_strb[1])
                        irq_enable <= reg_wr_data[8];
                    6'h24: if (reg_wr_strb[0])
                        child_count <= reg_wr_data[4:0];
                    6'h25: begin
                        if (reg_wr_strb[0])
                            model_base[7:0] <= reg_wr_data[7:0];
                        if (reg_wr_strb[1])
                            model_base[15:8] <= reg_wr_data[15:8];
                        if (reg_wr_strb[2])
                            model_base[23:16] <= reg_wr_data[23:16];
                        if (reg_wr_strb[3])
                            model_base[31:24] <= reg_wr_data[31:24];
                    end
                    6'h26: begin
                        if (reg_wr_strb[0])
                            parent_base[7:0] <= reg_wr_data[7:0];
                        if (reg_wr_strb[1])
                            parent_base[15:8] <= reg_wr_data[15:8];
                        if (reg_wr_strb[2])
                            parent_base[23:16] <= reg_wr_data[23:16];
                        if (reg_wr_strb[3])
                            parent_base[31:24] <= reg_wr_data[31:24];
                    end
                    6'h27: begin
                        if (reg_wr_strb[0])
                            output_weight_src[7:0] <= reg_wr_data[7:0];
                        if (reg_wr_strb[1])
                            output_weight_src[15:8] <= reg_wr_data[15:8];
                        if (reg_wr_strb[2])
                            output_weight_src[23:16] <= reg_wr_data[23:16];
                        if (reg_wr_strb[3])
                            output_weight_src[31:24] <= reg_wr_data[31:24];
                    end
                    6'h28: begin
                        if (reg_wr_strb[0])
                            descriptor_src[7:0] <= reg_wr_data[7:0];
                        if (reg_wr_strb[1])
                            descriptor_src[15:8] <= reg_wr_data[15:8];
                        if (reg_wr_strb[2])
                            descriptor_src[23:16] <= reg_wr_data[23:16];
                        if (reg_wr_strb[3])
                            descriptor_src[31:24] <= reg_wr_data[31:24];
                    end
                    6'h29: begin
                        if (reg_wr_strb[0])
                            score_bias_numerator[7:0] <= reg_wr_data[7:0];
                        if (reg_wr_strb[1])
                            score_bias_numerator[15:8] <= reg_wr_data[15:8];
                        if (reg_wr_strb[2])
                            score_bias_numerator[23:16] <= reg_wr_data[23:16];
                        if (reg_wr_strb[3])
                            score_bias_numerator[31:24] <= reg_wr_data[31:24];
                    end
                    6'h2a: begin
                        if (reg_wr_strb[0])
                            score_bias_numerator[39:32] <= reg_wr_data[7:0];
                        if (reg_wr_strb[1])
                            score_bias_numerator[47:40] <= reg_wr_data[15:8];
                        if (reg_wr_strb[2])
                            score_bias_numerator[55:48] <= reg_wr_data[23:16];
                        if (reg_wr_strb[3])
                            score_bias_numerator[63:56] <= reg_wr_data[31:24];
                    end
                    default: begin end
                endcase
            end

            if (command_clear && !busy) begin
                done <= 1'b0;
                error <= 1'b0;
                error_code <= ERR_NONE;
            end

            case (state)
                S_IDLE: begin
                    if (command_start) begin
                        done <= 1'b0;
                        error <= 1'b0;
                        error_code <= ERR_NONE;
                        cycle_count <= 32'b0;
                        if (!config_count_ok || !config_aligned) begin
                            done <= 1'b1;
                            error <= 1'b1;
                            error_code <= ERR_CONFIG;
                        end else if (!config_ranges) begin
                            done <= 1'b1;
                            error <= 1'b1;
                            error_code <= ERR_DDR_RANGE;
                        end else begin
                            busy <= 1'b1;
                            base_word <= 9'b0;
                            child_index <= 4'b0;
                            state <= S_BASE_REQ;
                        end
                    end
                end

                S_BASE_REQ: begin
                    if (mem_req_valid && mem_req_ready)
                        state <= S_BASE_DATA;
                end

                S_BASE_DATA: begin
                    if (mem_rsp_valid && mem_rsp_ready) begin
                        if (mem_rsp_error) begin
                            busy <= 1'b0;
                            done <= 1'b1;
                            error <= 1'b1;
                            error_code <= ERR_DDR_READ;
                            state <= S_IDLE;
                        end else begin
                            if (base_word < 9'd128)
                                parent_red[base_word[6:0]] <=
                                    mem_rsp_rdata;
                            else
                                parent_black[base_word[6:0]] <=
                                    mem_rsp_rdata;
                            base_word <= base_word + 9'd1;
                            if (mem_rsp_last) begin
                                if (base_word == 9'd255) begin
                                    weight_word <= 7'b0;
                                    state <= S_OW_REQ;
                                end else begin
                                    state <= S_BASE_REQ;
                                end
                            end
                        end
                    end
                end

                S_OW_REQ: begin
                    if (mem_req_valid && mem_req_ready)
                        state <= S_OW_DATA;
                end

                S_OW_DATA: begin
                    if (mem_rsp_valid && mem_rsp_ready) begin
                        if (mem_rsp_error) begin
                            busy <= 1'b0;
                            done <= 1'b1;
                            error <= 1'b1;
                            error_code <= ERR_DDR_READ;
                            state <= S_IDLE;
                        end else begin
                            if (weight_word[5])
                                output_weight_black[weight_word[4:0]] <=
                                    mem_rsp_rdata;
                            else
                                output_weight_red[weight_word[4:0]] <=
                                    mem_rsp_rdata;
                            weight_word <= weight_word + 7'd1;
                            if (mem_rsp_last) begin
                                if (weight_word == 7'd63) begin
                                    descriptor_word <= 4'b0;
                                    state <= S_DESC_REQ;
                                end else begin
                                    state <= S_OW_REQ;
                                end
                            end
                        end
                    end
                end

                S_DESC_REQ: begin
                    if (mem_req_valid && mem_req_ready) begin
                        descriptor_word <= 4'b0;
                        state <= S_DESC_DATA;
                    end
                end

                S_DESC_DATA: begin
                    if (mem_rsp_valid && mem_rsp_ready) begin
                        if (mem_rsp_error) begin
                            busy <= 1'b0;
                            done <= 1'b1;
                            error <= 1'b1;
                            error_code <= ERR_DDR_READ;
                            state <= S_IDLE;
                        end else begin
                            if (descriptor_word == 0)
                                child_side <= mem_rsp_rdata[0];
                            else if (descriptor_word <= 6)
                                row_id[descriptor_word-1] <= mem_rsp_rdata;
                            descriptor_word <= descriptor_word + 4'd1;
                            if (mem_rsp_last) begin
                                clear_index <= 7'b0;
                                state <= S_CLEAR;
                            end
                        end
                    end
                end

                S_CLEAR: begin
                    case (clear_index[1:0])
                        2'd0: begin
                            delta_red_b0[clear_index[6:2]] <= 10'sd0;
                            delta_black_b0[clear_index[6:2]] <= 10'sd0;
                        end
                        2'd1: begin
                            delta_red_b1[clear_index[6:2]] <= 10'sd0;
                            delta_black_b1[clear_index[6:2]] <= 10'sd0;
                        end
                        2'd2: begin
                            delta_red_b2[clear_index[6:2]] <= 10'sd0;
                            delta_black_b2[clear_index[6:2]] <= 10'sd0;
                        end
                        default: begin
                            delta_red_b3[clear_index[6:2]] <= 10'sd0;
                            delta_black_b3[clear_index[6:2]] <= 10'sd0;
                        end
                    endcase
                    if (clear_index == 7'd127) begin
                        row_slot <= 3'b0;
                        state <= S_ROW_PICK;
                    end else begin
                        clear_index <= clear_index + 7'd1;
                    end
                end

                S_ROW_PICK: begin
                    if (row_slot == 3'd6) begin
                        lane_index <= 7'b0;
                        mac_sum <= 64'sd0;
                        state <= S_COMPUTE;
                    end else if (selected_row_id == 32'hffff_ffff) begin
                        row_slot <= row_slot + 3'd1;
                    end else if (selected_row_id >= MODEL_ROWS) begin
                        busy <= 1'b0;
                        done <= 1'b1;
                        error <= 1'b1;
                        error_code <= ERR_ROW_ID;
                        state <= S_IDLE;
                    end else begin
                        row_word <= 6'b0;
                        state <= S_ROW_REQ;
                    end
                end

                S_ROW_REQ: begin
                    if (mem_req_valid && mem_req_ready)
                        state <= S_ROW_DATA;
                end

                S_ROW_DATA: begin
                    if (mem_rsp_valid && mem_rsp_ready) begin
                        if (mem_rsp_error) begin
                            busy <= 1'b0;
                            done <= 1'b1;
                            error <= 1'b1;
                            error_code <= ERR_DDR_READ;
                            state <= S_IDLE;
                        end else begin
                            if (selected_red) begin
                                delta_red_b0[row_word[4:0]] <=
                                    delta_red_b0_q +
                                    (selected_negative ?
                                     -mem_rsp_byte0_extended :
                                      mem_rsp_byte0_extended);
                                delta_red_b1[row_word[4:0]] <=
                                    delta_red_b1_q +
                                    (selected_negative ?
                                     -mem_rsp_byte1_extended :
                                      mem_rsp_byte1_extended);
                                delta_red_b2[row_word[4:0]] <=
                                    delta_red_b2_q +
                                    (selected_negative ?
                                     -mem_rsp_byte2_extended :
                                      mem_rsp_byte2_extended);
                                delta_red_b3[row_word[4:0]] <=
                                    delta_red_b3_q +
                                    (selected_negative ?
                                     -mem_rsp_byte3_extended :
                                      mem_rsp_byte3_extended);
                            end else begin
                                delta_black_b0[row_word[4:0]] <=
                                    delta_black_b0_q +
                                    (selected_negative ?
                                     -mem_rsp_byte0_extended :
                                      mem_rsp_byte0_extended);
                                delta_black_b1[row_word[4:0]] <=
                                    delta_black_b1_q +
                                    (selected_negative ?
                                     -mem_rsp_byte1_extended :
                                      mem_rsp_byte1_extended);
                                delta_black_b2[row_word[4:0]] <=
                                    delta_black_b2_q +
                                    (selected_negative ?
                                     -mem_rsp_byte2_extended :
                                      mem_rsp_byte2_extended);
                                delta_black_b3[row_word[4:0]] <=
                                    delta_black_b3_q +
                                    (selected_negative ?
                                     -mem_rsp_byte3_extended :
                                      mem_rsp_byte3_extended);
                            end
                            row_word <= row_word + 6'd1;
                            if (mem_rsp_last) begin
                                if (row_word == 6'd31) begin
                                    row_slot <= row_slot + 3'd1;
                                    state <= S_ROW_PICK;
                                end else begin
                                    state <= S_ROW_REQ;
                                end
                            end
                        end
                    end
                end

                S_COMPUTE: begin
                    mac_sum <= lane_sum_next;
                    if (lane_index == 7'd127) begin
                        numerator <= score_bias_numerator + scaled_lane_sum;
                        state <= S_DIV_PREP;
                    end else begin
                        lane_index <= lane_index + 7'd1;
                    end
                end

                S_DIV_PREP: begin
                    div_negative <= numerator[63];
                    dividend <= numerator[63] ?
                        (~numerator + 64'd1) : numerator;
                    quotient <= 64'b0;
                    remainder <= 64'b0;
                    div_count <= 7'b0;
                    state <= S_DIV_RUN;
                end

                S_DIV_RUN: begin
                    dividend <= {dividend[62:0], 1'b0};
                    quotient <= quotient_next;
                    remainder <= remainder_next;
                    if (div_count == 7'd63) begin
                        score_result[child_index] <= signed_quotient;
                        state <= S_NEXT;
                    end else begin
                        div_count <= div_count + 7'd1;
                    end
                end

                S_NEXT: begin
                    if (child_index + 5'd1 >= child_count) begin
                        busy <= 1'b0;
                        done <= 1'b1;
                        completed_runs <= completed_runs + 32'd1;
                        state <= S_IDLE;
                    end else begin
                        child_index <= child_index + 4'd1;
                        descriptor_word <= 4'b0;
                        state <= S_DESC_REQ;
                    end
                end

                default: begin
                    busy <= 1'b0;
                    done <= 1'b1;
                    error <= 1'b1;
                    error_code <= ERR_INTERNAL;
                    state <= S_IDLE;
                end
            endcase
        end
    end

endmodule
