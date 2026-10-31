`timescale 1ns / 1ps

// Descriptor DMA front end for the pCi=4, pCo=16 MacAccelCore.
//
// No CPU is instantiated here. A software-visible control fabric writes the
// register port, while the streaming memory port connects to the supplied
// 32-bit AXI4 adapter. Transfers use up to eight beats and never cross a 4 KiB
// boundary. Only one memory command is outstanding.
module mac_accel_dma_kernel #(
    parameter [31:0] DDR_BASE = 32'h0000_0000,
    parameter integer DDR_BYTES = 256 * 1024 * 1024,
    parameter integer WEIGHT_BANK_LINES = 1024,
    parameter ENABLE_FP8 = 1
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
    output reg         mem_req_write,
    output reg  [31:0] mem_req_addr,
    output reg  [2:0]  mem_req_len,

    output reg         mem_w_valid,
    input  wire        mem_w_ready,
    output reg  [31:0] mem_w_data,
    output reg  [3:0]  mem_w_strb,
    output reg         mem_w_last,

    input  wire        mem_rsp_valid,
    output reg         mem_rsp_ready,
    input  wire [31:0] mem_rsp_rdata,
    input  wire        mem_rsp_last,
    input  wire        mem_rsp_error,

    output wire        irq
);

    localparam [3:0] S_IDLE          = 4'd0;
    localparam [3:0] S_INPUT_REQ     = 4'd1;
    localparam [3:0] S_INPUT_DATA    = 4'd2;
    localparam [3:0] S_WEIGHT_REQ    = 4'd3;
    localparam [3:0] S_WEIGHT_DATA   = 4'd4;
    localparam [3:0] S_BIAS_REQ      = 4'd5;
    localparam [3:0] S_BIAS_DATA     = 4'd6;
    localparam [3:0] S_CORE_CLEAR    = 4'd7;
    localparam [3:0] S_CORE_START    = 4'd8;
    localparam [3:0] S_CORE_WAIT     = 4'd9;
    localparam [3:0] S_OUTPUT_CMD    = 4'd13;
    localparam [3:0] S_OUTPUT_DATA   = 4'd14;
    localparam [3:0] S_OUTPUT_RESP   = 4'd15;

    localparam [3:0] ERR_NONE       = 4'd0;
    localparam [3:0] ERR_CONFIG     = 4'd1;
    localparam [3:0] ERR_DDR_RANGE  = 4'd2;
    localparam [3:0] ERR_DDR_READ   = 4'd3;
    localparam [3:0] ERR_DDR_WRITE  = 4'd4;
    localparam [3:0] ERR_INTERNAL   = 4'd15;

    localparam [32:0] DDR_LIMIT = {1'b0, DDR_BASE} + DDR_BYTES;

    reg [3:0] state;
    reg dma_busy;
    reg dma_done;
    reg dma_error;
    reg [3:0] error_code;
    reg irq_enable;

    reg [15:0] cfg_pixels;
    reg [15:0] cfg_cin;
    reg [15:0] cfg_cout;
    reg [1:0] cfg_compute_mode;
    reg [1:0] cfg_activation;
    reg [1:0] cfg_output_format;
    reg [7:0] cfg_out_shift;
    reg cfg_zero_bias;

    reg [31:0] input_src;
    reg [31:0] weight_src;
    reg [31:0] bias_src;
    reg [31:0] output_dst;

    reg [31:0] cycle_count;
    reg [31:0] completed_runs;
    reg [10:0] line_index;
    reg [5:0] word_index;
    reg [12:0] output_words_written;
    reg [8:0] output_channel_base;
    reg [5:0] output_lane_index;
    // S16 stores sixteen valid lanes in each 32-word tile.  The maximum
    // 16-pixel/256-channel descriptor therefore reaches bank word 8175.
    reg [7:0] output_bank_tile;
    reg [2:0] output_send_index;
    reg [3:0] output_burst_beats;

    // Assembly registers are fully overwritten before a core write. The
    // 64-line profile bypasses weight_shift with direct 32-bit RAM stores.
    reg [63:0] input_shift;
    reg [1023:0] weight_shift;

    reg mac_start;
    reg mac_done_clear;
    wire mac_busy;
    wire mac_done;
    reg mac_input_we;
    reg [10:0] mac_input_waddr;
    reg [63:0] mac_input_wdata;
    reg mac_weight_we;
    reg [10:0] mac_weight_waddr;
    // Registered word stores retain the legacy final-word visibility edge.
    reg mac_weight_word_we;
    reg [4:0] mac_weight_word_index;
    reg [31:0] mac_weight_word_data;
    reg mac_bias_we;
    reg mac_bias_word_we;
    reg [5:0] mac_bias_word_index;
    reg [31:0] mac_bias_word_data;
    reg [10:0] mac_bias_waddr;
    wire [15:0] output_lanes_this_tile;
    // A successful W handshake can read the following word at the same edge.
    // The synchronous bank then holds that word until its own W handshake;
    // no speculative reads occur during backpressure or at the burst tail.
    wire [5:0] output_next_lane = output_lane_index + 6'd1;
    wire output_last_lane = output_next_lane >= output_lanes_this_tile;
    // The compact bank uses 16 slots/S16 tile and 32 slots/packed tile.
    // Both modes fit all 4096 valid outputs without a 13-bit accumulator.
    wire [7:0] output_next_tile = output_last_lane ?
        output_bank_tile + 8'd1 : output_bank_tile;
    wire [4:0] output_next_bank_lane = output_last_lane ? 5'b0 : output_next_lane[4:0];
    wire [11:0] output_bank_index = cfg_compute_mode == 2'b00 ?
        {output_bank_tile, output_lane_index[3:0]} :
        {output_bank_tile[6:0], output_lane_index[4:0]};
    wire [11:0] output_next_bank_index = cfg_compute_mode == 2'b00 ?
        {output_next_tile, output_next_bank_lane[3:0]} :
        {output_next_tile[6:0], output_next_bank_lane};
    wire output_read_ahead = state == S_OUTPUT_DATA && mem_w_ready && !mem_w_last;
    // The command handshake can also capture the first synchronous bank
    // read. Its data is ready for the very next W cycle, including stalls.
    wire output_launch = state == S_OUTPUT_CMD && mem_req_valid && mem_req_ready;
    wire mac_output_re = output_launch || output_read_ahead;
    wire [11:0] mac_output_raddr = output_read_ahead ?
        output_next_bank_index : output_bank_index;
    wire [31:0] mac_output_rdata;

    wire control_write = reg_wr_en && (reg_wr_addr[7:2] == 6'h02);
    wire command_start = control_write && reg_wr_strb[0] && reg_wr_data[0];
    wire command_clear = control_write && reg_wr_strb[0] && reg_wr_data[1];

    wire packed_mode = cfg_compute_mode != 2'b00;
    wire [6:0] cin_tiles_small = cfg_cin[8:2] + {6'b0, |cfg_cin[1:0]};
    wire [4:0] cout_tiles_small = packed_mode ?
        ({1'b0, cfg_cout[8:5]} + {4'b0, |cfg_cout[4:0]}) :
        (cfg_cout[8:4] + {4'b0, |cfg_cout[3:0]});
    wire [15:0] cin_tiles = {9'b0, cin_tiles_small};
    wire [15:0] cout_tiles = {11'b0, cout_tiles_small};
    wire [15:0] output_tile_step = packed_mode ? 16'd32 : 16'd16;

    wire [10:0] input_line_count_small = cfg_pixels[4:0] * cin_tiles_small;
    wire [10:0] weight_line_count_small = cout_tiles_small * cin_tiles_small;
    wire [15:0] input_line_count = {5'b0, input_line_count_small};
    wire [15:0] weight_line_count = {5'b0, weight_line_count_small};
    wire [15:0] bias_line_count = cout_tiles;
    wire [12:0] output_word_count_small = cfg_pixels[4:0] * cfg_cout[8:0];
    wire [15:0] output_word_count = {3'b0, output_word_count_small};

    wire [15:0] output_channels_left =
        cfg_cout - {7'b0, output_channel_base};
    assign output_lanes_this_tile =
        (output_channels_left > output_tile_step) ? output_tile_step :
                                                    output_channels_left;

    localparam integer DDR_OFFSET_BITS=$clog2(DDR_BYTES);
    localparam integer NARROW_DDR=(DDR_OFFSET_BITS>0 && DDR_OFFSET_BITS<32 &&
        DDR_BYTES==(64'd1<<DDR_OFFSET_BITS) &&
        (DDR_BASE & (DDR_BYTES-1))==0);
    // Former scratch_address function, inlined as per-site offset wires:
    // NARROW_DDR keeps the high base bits and wraps the offset field,
    // otherwise the full 32-bit sum is used.

    wire [31:0] input_word_addr_off = ({21'b0,line_index}<<3)+({26'b0,word_index}<<2);
    wire [31:0] input_word_addr = NARROW_DDR ?
        {input_src[31:DDR_OFFSET_BITS],input_src[DDR_OFFSET_BITS-1:0]+input_word_addr_off[DDR_OFFSET_BITS-1:0]} :
        input_src+input_word_addr_off;
    wire [31:0] weight_word_addr_off = ({21'b0,line_index}<<7)+({26'b0,word_index}<<2);
    wire [31:0] weight_word_addr = NARROW_DDR ?
        {weight_src[31:DDR_OFFSET_BITS],weight_src[DDR_OFFSET_BITS-1:0]+weight_word_addr_off[DDR_OFFSET_BITS-1:0]} :
        weight_src+weight_word_addr_off;
    wire [31:0] bias_word_addr_off = ({21'b0,line_index}<<7)+({21'b0,line_index}<<6)+({26'b0,word_index}<<2);
    wire [31:0] bias_word_addr = NARROW_DDR ?
        {bias_src[31:DDR_OFFSET_BITS],bias_src[DDR_OFFSET_BITS-1:0]+bias_word_addr_off[DDR_OFFSET_BITS-1:0]} :
        bias_src+bias_word_addr_off;
    // Input lines are only two words wide.  Count across line boundaries so
    // one aligned AXI burst carries four complete lines instead of paying one
    // address transaction per line.
    wire [16:0] input_words_total = {1'b0, input_line_count} << 1;
    wire [16:0] input_words_consumed =
        ({6'b0, line_index} << 1) + {11'b0, word_index};
    wire [16:0] input_words_left = input_words_total -
                                   input_words_consumed;
    wire [16:0] weight_words_left = 17'd32 - {11'b0, word_index};
    wire [16:0] bias_words_left = 17'd48 - {11'b0, word_index};

    wire [31:0] output_word_addr_off = ({19'b0,output_words_written}<<2);
    wire [31:0] output_word_addr = NARROW_DDR ?
        {output_dst[31:DDR_OFFSET_BITS],output_dst[DDR_OFFSET_BITS-1:0]+output_word_addr_off[DDR_OFFSET_BITS-1:0]} :
        output_dst+output_word_addr_off;
    wire [16:0] output_words_left = {1'b0, output_word_count} -
        {4'b0, output_words_written};
    wire [13:0] output_words_after_burst =
        {1'b0, output_words_written} + {10'b0, output_burst_beats};
    wire [31:0] output_addr_after_burst_off = ({18'b0,output_words_after_burst}<<2);
    wire [31:0] output_addr_after_burst = NARROW_DDR ?
        {output_dst[31:DDR_OFFSET_BITS],output_dst[DDR_OFFSET_BITS-1:0]+output_addr_after_burst_off[DDR_OFFSET_BITS-1:0]} :
        output_dst+output_addr_after_burst_off;
    wire [16:0] output_left_after_burst = {1'b0, output_word_count} -
        {3'b0, output_words_after_burst};

    wire [3:0] input_burst_beats;
    wire [3:0] weight_burst_beats;
    wire [3:0] bias_burst_beats;
    wire [3:0] output_first_burst_beats;
    wire [3:0] output_next_burst_beats;

    // One outstanding DMA transaction needs one burst-size calculation.
    // Only bits 4:2 of the address influence the 32-byte line boundary.
    reg [2:0] burst_address_low;
    reg [16:0] burst_words_left;
    always @* begin
        burst_address_low=output_dst[4:2];
        burst_words_left={1'b0,output_word_count};
        case(state)
            S_INPUT_REQ: begin burst_address_low=input_word_addr[4:2]; burst_words_left=input_words_left; end
            S_WEIGHT_REQ: begin burst_address_low=weight_word_addr[4:2]; burst_words_left=weight_words_left; end
            S_BIAS_REQ: begin burst_address_low=bias_word_addr[4:2]; burst_words_left=bias_words_left; end
            S_OUTPUT_RESP: begin burst_address_low=output_addr_after_burst[4:2]; burst_words_left=output_left_after_burst; end
            default: begin end
        endcase
    end
    wire [3:0] shared_burst_beats;
    mac_accel_burst_sizer u_burst_sizer (
        .address({27'b0,burst_address_low,2'b0}),
        .beats_left(burst_words_left),.beats(shared_burst_beats)
    );
    assign input_burst_beats=shared_burst_beats;
    assign weight_burst_beats=shared_burst_beats;
    assign bias_burst_beats=shared_burst_beats;
    assign output_first_burst_beats=shared_burst_beats;
    assign output_next_burst_beats=shared_burst_beats;

    wire [32:0] input_end = {1'b0, input_src} +
        ({17'b0, input_line_count} << 3);
    wire [32:0] weight_end = {1'b0, weight_src} +
        ({17'b0, weight_line_count} << 7);
    wire [32:0] bias_end = {1'b0, bias_src} +
        ({17'b0, bias_line_count} << 7) +
        ({17'b0, bias_line_count} << 6);
    wire [32:0] output_end = {1'b0, output_dst} +
        ({17'b0, output_word_count} << 2);

    wire config_invalid = (cfg_pixels == 16'd0) ||
                          (cfg_pixels > 16'd16) ||
                          (cfg_cin == 16'd0) ||
                          (cfg_cin > 16'd256) ||
                          (cfg_cout == 16'd0) ||
                          (cfg_cout > 16'd256) ||
                          (weight_line_count_small > WEIGHT_BANK_LINES) ||
                          (!ENABLE_FP8 && cfg_compute_mode == 2'b11);

    wire narrow_range_invalid =
        input_src[31:DDR_OFFSET_BITS]!=DDR_BASE[31:DDR_OFFSET_BITS] ||
        weight_src[31:DDR_OFFSET_BITS]!=DDR_BASE[31:DDR_OFFSET_BITS] ||
        bias_src[31:DDR_OFFSET_BITS]!=DDR_BASE[31:DDR_OFFSET_BITS] ||
        output_dst[31:DDR_OFFSET_BITS]!=DDR_BASE[31:DDR_OFFSET_BITS] ||
        ({1'b0,input_src[DDR_OFFSET_BITS-1:0]}+({5'b0,input_line_count_small}<<3))>DDR_BYTES ||
        ({1'b0,weight_src[DDR_OFFSET_BITS-1:0]}+({5'b0,weight_line_count_small}<<7))>DDR_BYTES ||
        ({1'b0,bias_src[DDR_OFFSET_BITS-1:0]}+({16'b0,cout_tiles_small}<<7)+({16'b0,cout_tiles_small}<<6))>DDR_BYTES ||
        ({1'b0,output_dst[DDR_OFFSET_BITS-1:0]}+({8'b0,output_word_count_small}<<2))>DDR_BYTES;
    wire address_invalid = ((input_src|weight_src|bias_src|output_dst)&3)!=0 ||
        (NARROW_DDR ? narrow_range_invalid :
            input_src<DDR_BASE || weight_src<DDR_BASE || bias_src<DDR_BASE || output_dst<DDR_BASE ||
            input_end>DDR_LIMIT || weight_end>DDR_LIMIT || bias_end>DDR_LIMIT || output_end>DDR_LIMIT);

    assign irq = irq_enable && dma_done;

    MacAccelCore #(.COMPACT_S16_OUTPUT(1),
                   .WEIGHT_BANK_LINES(WEIGHT_BANK_LINES),
                   .ENABLE_FP8(ENABLE_FP8),
                   .BIAS_WORD_WRITE(1),
                   .WEIGHT_WORD_WRITE(WEIGHT_BANK_LINES == 64)) u_mac_accel (
        .io_clk(clk),
        .io_rstN(resetn),
        .io_start(mac_start),
        .io_busy(mac_busy),
        .io_done(mac_done),
        .io_doneClear(mac_done_clear),
        .io_cfgPixels(cfg_pixels),
        .io_cfgCin(cfg_cin),
        .io_cfgCout(cfg_cout),
        .io_cfgComputeMode(cfg_compute_mode),
        .io_cfgActivation(cfg_activation),
        .io_cfgOutputFormat(cfg_output_format),
        .io_cfgOutShift(cfg_out_shift),
        .io_hostInWe(mac_input_we),
        .io_hostInWaddr({21'b0, mac_input_waddr}),
        .io_hostInWdata(mac_input_wdata),
        .io_hostWtWe(mac_weight_we),
        .io_hostWtWaddr({21'b0, mac_weight_waddr}),
        .io_hostWtWdata(WEIGHT_BANK_LINES == 64 ? 1024'b0 : weight_shift),
        .io_hostWtWordWe(mac_weight_word_we),
        .io_hostWtWordIndex(mac_weight_word_index),
        .io_hostWtWordData(mac_weight_word_data),
        .io_hostBiasWe(mac_bias_we),
        .io_hostBiasWaddr({21'b0, mac_bias_waddr}),
        .io_hostBiasWdata(1536'b0),
        .io_hostBiasWordWe(mac_bias_word_we),
        .io_hostBiasZeroWe(mac_bias_we),
        .io_hostBiasWordIndex(mac_bias_word_index),
        .io_hostBiasWordData(mac_bias_word_data),
        .io_hostOutRe(mac_output_re),
        .io_hostOutRaddr({20'b0, mac_output_raddr}),
        .io_hostOutRdata(mac_output_rdata)
    );

    always @* begin
        reg_rd_data =
            ({32{reg_rd_addr[7:2]==6'h00}} & (32'h4d41_434b)) |
            ({32{reg_rd_addr[7:2]==6'h01}} & (32'h0002_0100)) |
            ({32{reg_rd_addr[7:2]==6'h02}} & ({23'b0, irq_enable, 6'b0, 2'b0})) |
            ({32{reg_rd_addr[7:2]==6'h03}} & ({
                8'b0, 1'b0, state, 3'b0, error_code, 7'b0,
                mac_done, mac_busy, dma_error, dma_done, dma_busy
            })) |
            ({32{reg_rd_addr[7:2]==6'h04}} & ({cfg_cin, cfg_pixels})) |
            ({32{reg_rd_addr[7:2]==6'h05}} & ({
                1'b0, cfg_zero_bias, cfg_compute_mode, cfg_activation,
                cfg_output_format, cfg_out_shift, cfg_cout
            })) |
            ({32{reg_rd_addr[7:2]==6'h06}} & (input_src)) |
            ({32{reg_rd_addr[7:2]==6'h07}} & (weight_src)) |
            ({32{reg_rd_addr[7:2]==6'h08}} & (bias_src)) |
            ({32{reg_rd_addr[7:2]==6'h09}} & (output_dst)) |
            ({32{reg_rd_addr[7:2]==6'h0a}} & (cycle_count)) |
            ({32{reg_rd_addr[7:2]==6'h0b}} & (completed_runs)) |
            ({32{reg_rd_addr[7:2]==6'h0c}} & (32'h0100_1004)) |
            ({32{reg_rd_addr[7:2]==6'h0d}} & (32'h0020_0010)) |
            ({32{reg_rd_addr[7:2]==6'h0e}} & ({weight_line_count, input_line_count})) |
            ({32{reg_rd_addr[7:2]==6'h0f}} & ({output_word_count, bias_line_count})) |
            ({32{reg_rd_addr[7:2]==6'h10}} & (32'h0000_0008));
    end

    always @* begin
        mem_req_valid = 1'b0;
        mem_req_write = 1'b0;
        mem_req_addr = 32'b0;
        mem_req_len = 3'b0;
        mem_w_valid = 1'b0;
        mem_w_data = 32'b0;
        mem_w_strb = 4'b0;
        mem_w_last = 1'b0;
        mem_rsp_ready = 1'b0;

        case (state)
            S_INPUT_REQ: begin
                mem_req_valid = 1'b1;
                mem_req_addr = input_word_addr;
                mem_req_len = input_burst_beats - 4'd1;
            end
            S_INPUT_DATA: mem_rsp_ready = 1'b1;

            S_WEIGHT_REQ: begin
                mem_req_valid = 1'b1;
                mem_req_addr = weight_word_addr;
                mem_req_len = weight_burst_beats - 4'd1;
            end
            S_WEIGHT_DATA: mem_rsp_ready = 1'b1;

            S_BIAS_REQ: begin
                if (!cfg_zero_bias) begin
                    mem_req_valid = 1'b1;
                    mem_req_addr = bias_word_addr;
                    mem_req_len = bias_burst_beats - 4'd1;
                end
            end
            S_BIAS_DATA: begin
                if (!cfg_zero_bias)
                    mem_rsp_ready = 1'b1;
            end

            S_OUTPUT_CMD: begin
                mem_req_valid = 1'b1;
                mem_req_write = 1'b1;
                mem_req_addr = output_word_addr;
                mem_req_len = output_burst_beats - 4'd1;
            end
            S_OUTPUT_DATA: begin
                mem_w_valid = 1'b1;
                mem_w_data = mac_output_rdata;
                mem_w_strb = 4'b1111;
                mem_w_last = {1'b0, output_send_index} + 4'd1 >=
                             output_burst_beats;
            end
            S_OUTPUT_RESP: mem_rsp_ready = 1'b1;
            default: begin end
        endcase
    end

    always @(posedge clk) begin
        if (!resetn) begin
            state <= S_IDLE;
            dma_busy <= 1'b0;
            dma_done <= 1'b0;
            dma_error <= 1'b0;
            error_code <= ERR_NONE;
            irq_enable <= 1'b0;

            cfg_pixels <= 16'd1;
            cfg_cin <= 16'd1;
            cfg_cout <= 16'd1;
            cfg_compute_mode <= 2'd0;
            cfg_activation <= 2'd0;
            cfg_output_format <= 2'd2;
            cfg_out_shift <= 8'd0;
            cfg_zero_bias <= 1'b0;
            input_src <= DDR_BASE;
            weight_src <= DDR_BASE;
            bias_src <= DDR_BASE;
            output_dst <= DDR_BASE;

            cycle_count <= 32'b0;
            completed_runs <= 32'b0;
            line_index <= 11'b0;
            word_index <= 6'b0;
            output_words_written <= 13'b0;
            output_channel_base <= 9'b0;
            output_lane_index <= 6'b0;
            output_bank_tile <= 8'b0;
            output_send_index <= 3'b0;
            output_burst_beats <= 4'd1;

            mac_start <= 1'b0;
            mac_done_clear <= 1'b0;
            mac_input_we <= 1'b0;
            mac_weight_we <= 1'b0;
            mac_weight_word_we <= 1'b0;
            mac_bias_we <= 1'b0;
            mac_bias_word_we <= 1'b0;
        end else begin
            mac_start <= 1'b0;
            mac_done_clear <= 1'b0;
            mac_input_we <= 1'b0;
            mac_weight_we <= 1'b0;
            mac_weight_word_we <= 1'b0;
            mac_bias_we <= 1'b0;
            mac_bias_word_we <= 1'b0;

            if (dma_busy)
                cycle_count <= cycle_count + 32'd1;

            if (control_write && reg_wr_strb[1])
                irq_enable <= reg_wr_data[8];

            // Descriptor registers are immutable while a transfer is active.
            if (reg_wr_en && !dma_busy) begin
                case (reg_wr_addr[7:2])
                    6'h04: begin
                        if (reg_wr_strb[0]) cfg_pixels[7:0] <= reg_wr_data[7:0];
                        if (reg_wr_strb[1]) cfg_pixels[15:8] <= reg_wr_data[15:8];
                        if (reg_wr_strb[2]) cfg_cin[7:0] <= reg_wr_data[23:16];
                        if (reg_wr_strb[3]) cfg_cin[15:8] <= reg_wr_data[31:24];
                    end
                    6'h05: begin
                        if (reg_wr_strb[0]) cfg_cout[7:0] <= reg_wr_data[7:0];
                        if (reg_wr_strb[1]) cfg_cout[15:8] <= reg_wr_data[15:8];
                        if (reg_wr_strb[2]) cfg_out_shift <= reg_wr_data[23:16];
                        if (reg_wr_strb[3]) begin
                            cfg_output_format <= reg_wr_data[25:24];
                            cfg_activation <= reg_wr_data[27:26];
                            cfg_compute_mode <= reg_wr_data[29:28];
                            cfg_zero_bias <= reg_wr_data[30];
                        end
                    end
                    6'h06: begin
                        if (reg_wr_strb[0]) input_src[7:0] <= reg_wr_data[7:0];
                        if (reg_wr_strb[1]) input_src[15:8] <= reg_wr_data[15:8];
                        if (reg_wr_strb[2]) input_src[23:16] <= reg_wr_data[23:16];
                        if (reg_wr_strb[3]) input_src[31:24] <= reg_wr_data[31:24];
                    end
                    6'h07: begin
                        if (reg_wr_strb[0]) weight_src[7:0] <= reg_wr_data[7:0];
                        if (reg_wr_strb[1]) weight_src[15:8] <= reg_wr_data[15:8];
                        if (reg_wr_strb[2]) weight_src[23:16] <= reg_wr_data[23:16];
                        if (reg_wr_strb[3]) weight_src[31:24] <= reg_wr_data[31:24];
                    end
                    6'h08: begin
                        if (reg_wr_strb[0]) bias_src[7:0] <= reg_wr_data[7:0];
                        if (reg_wr_strb[1]) bias_src[15:8] <= reg_wr_data[15:8];
                        if (reg_wr_strb[2]) bias_src[23:16] <= reg_wr_data[23:16];
                        if (reg_wr_strb[3]) bias_src[31:24] <= reg_wr_data[31:24];
                    end
                    6'h09: begin
                        if (reg_wr_strb[0]) output_dst[7:0] <= reg_wr_data[7:0];
                        if (reg_wr_strb[1]) output_dst[15:8] <= reg_wr_data[15:8];
                        if (reg_wr_strb[2]) output_dst[23:16] <= reg_wr_data[23:16];
                        if (reg_wr_strb[3]) output_dst[31:24] <= reg_wr_data[31:24];
                    end
                    default: begin end
                endcase
            end

            if (command_clear && !dma_busy) begin
                dma_done <= 1'b0;
                dma_error <= 1'b0;
                error_code <= ERR_NONE;
                mac_done_clear <= 1'b1;
            end

            case (state)
                S_IDLE: begin
                    dma_busy <= 1'b0;
                    if (command_start) begin
                        cycle_count <= 32'b0;
                        dma_done <= 1'b0;
                        line_index <= 11'b0;
                        word_index <= 6'b0;
                        if (config_invalid) begin
                            dma_error <= 1'b1;
                            dma_done <= 1'b1;
                            error_code <= ERR_CONFIG;
                        end else if (address_invalid) begin
                            dma_error <= 1'b1;
                            dma_done <= 1'b1;
                            error_code <= ERR_DDR_RANGE;
                        end else begin
                            dma_busy <= 1'b1;
                            dma_error <= 1'b0;
                            error_code <= ERR_NONE;
                            state <= S_INPUT_REQ;
                        end
                    end
                end

                S_INPUT_REQ: begin
                    if (mem_req_valid && mem_req_ready)
                        state <= S_INPUT_DATA;
                end

                S_INPUT_DATA: begin
                    if (mem_rsp_valid && mem_rsp_ready) begin
                        if (mem_rsp_error) begin
                            dma_busy <= 1'b0;
                            dma_done <= 1'b1;
                            dma_error <= 1'b1;
                            error_code <= ERR_DDR_READ;
                            state <= S_IDLE;
                        end else if (word_index == 6'd1) begin
                            mac_input_waddr <= line_index;
                            mac_input_wdata <= {
                                mem_rsp_rdata, input_shift[63:32]
                            };
                            mac_input_we <= 1'b1;
                            word_index <= 6'b0;
                            if (line_index + 11'd1 >= input_line_count) begin
                                line_index <= 11'b0;
                                state <= S_WEIGHT_REQ;
                            end else begin
                                line_index <= line_index + 11'd1;
                                if (mem_rsp_last)
                                    state <= S_INPUT_REQ;
                                else
                                    state <= S_INPUT_DATA;
                            end
                        end else begin
                            input_shift <= {
                                mem_rsp_rdata, input_shift[63:32]
                            };
                            word_index <= word_index + 6'd1;
                            if (mem_rsp_last)
                                state <= S_INPUT_REQ;
                        end
                    end
                end

                S_WEIGHT_REQ: begin
                    if (mem_req_valid && mem_req_ready)
                        state <= S_WEIGHT_DATA;
                end

                S_WEIGHT_DATA: begin
                    if (mem_rsp_valid && mem_rsp_ready) begin
                        if (!mem_rsp_error && WEIGHT_BANK_LINES == 64) begin
                            mac_weight_waddr <= line_index;
                            mac_weight_word_index <= word_index[4:0];
                            mac_weight_word_data <= mem_rsp_rdata;
                            mac_weight_word_we <= 1'b1;
                        end
                        if (mem_rsp_error) begin
                            dma_busy <= 1'b0;
                            dma_done <= 1'b1;
                            dma_error <= 1'b1;
                            error_code <= ERR_DDR_READ;
                            state <= S_IDLE;
                        end else if (word_index == 6'd31) begin
                            mac_weight_waddr <= line_index;
                            if (WEIGHT_BANK_LINES != 64) begin
                                weight_shift <= {
                                    mem_rsp_rdata, weight_shift[1023:32]
                                };
                                mac_weight_we <= 1'b1;
                            end
                            word_index <= 6'b0;
                            if (line_index + 11'd1 >= weight_line_count) begin
                                line_index <= 11'b0;
                                state <= S_BIAS_REQ;
                            end else begin
                                line_index <= line_index + 11'd1;
                                state <= S_WEIGHT_REQ;
                            end
                        end else begin
                            if (WEIGHT_BANK_LINES != 64)
                                weight_shift <= {
                                    mem_rsp_rdata, weight_shift[1023:32]
                                };
                            word_index <= word_index + 6'd1;
                            if (mem_rsp_last)
                                state <= S_WEIGHT_REQ;
                        end
                    end
                end

                S_BIAS_REQ: begin
                    if (cfg_zero_bias) begin
                        // Broadcast zero to every word bank on one clock.
                        mac_bias_waddr <= line_index;
                        mac_bias_we <= 1'b1;
                        word_index <= 6'b0;
                        if (line_index + 11'd1 >= bias_line_count) begin
                            line_index <= 11'b0;
                            state <= S_CORE_CLEAR;
                        end else begin
                            line_index <= line_index + 11'd1;
                            state <= S_BIAS_REQ;
                        end
                    end else if (mem_req_valid && mem_req_ready) begin
                        state <= S_BIAS_DATA;
                    end
                end

                S_BIAS_DATA: begin
                    if (mem_rsp_valid && mem_rsp_ready) begin
                        if (mem_rsp_error) begin
                            dma_busy <= 1'b0;
                            dma_done <= 1'b1;
                            dma_error <= 1'b1;
                            error_code <= ERR_DDR_READ;
                            state <= S_IDLE;
                        end else begin
                            mac_bias_waddr <= line_index;
                            mac_bias_word_index <= word_index;
                            mac_bias_word_data <= mem_rsp_rdata;
                            mac_bias_word_we <= 1'b1;
                            if (word_index == 6'd47) begin
                                word_index <= 6'b0;
                                if (line_index + 11'd1 >= bias_line_count) begin
                                    line_index <= 11'b0;
                                    state <= S_CORE_CLEAR;
                                end else begin
                                    line_index <= line_index + 11'd1;
                                    state <= S_BIAS_REQ;
                                end
                            end else begin
                                word_index <= word_index + 6'd1;
                                if (mem_rsp_last)
                                    state <= S_BIAS_REQ;
                            end
                        end
                    end
                end

                S_CORE_CLEAR: begin
                    mac_done_clear <= 1'b1;
                    state <= S_CORE_START;
                end

                S_CORE_START: begin
                    mac_start <= 1'b1;
                    state <= S_CORE_WAIT;
                end

                S_CORE_WAIT: begin
                    if (mac_done) begin
                        output_words_written <= 13'b0;
                        output_channel_base <= 9'b0;
                        output_lane_index <= 6'b0;
                        output_bank_tile <= 8'b0;
                        output_send_index <= 3'b0;
                        output_burst_beats <= output_first_burst_beats;
                        state <= S_OUTPUT_CMD;
                    end
                end

                S_OUTPUT_CMD: begin
                    if (mem_req_valid && mem_req_ready) begin
                        output_send_index <= 3'b0;
                        state <= S_OUTPUT_DATA;
                    end
                end

                S_OUTPUT_DATA: begin
                    if (mem_w_valid && mem_w_ready) begin
                        if (output_last_lane) begin
                            output_bank_tile <= output_bank_tile + 8'd1;
                            output_lane_index <= 6'b0;
                            if ({7'b0, output_channel_base} +
                                output_tile_step >= cfg_cout)
                                output_channel_base <= 9'b0;
                            else
                                output_channel_base <= output_channel_base +
                                    output_tile_step[8:0];
                        end else begin
                            output_lane_index <= output_next_lane;
                        end

                        if (mem_w_last) begin
                            state <= S_OUTPUT_RESP;
                        end else begin
                            output_send_index <= output_send_index + 3'd1;
                            state <= S_OUTPUT_DATA;
                        end
                    end
                end

                S_OUTPUT_RESP: begin
                    if (mem_rsp_valid && mem_rsp_ready) begin
                        if (mem_rsp_error || !mem_rsp_last) begin
                            dma_busy <= 1'b0;
                            dma_done <= 1'b1;
                            dma_error <= 1'b1;
                            error_code <= ERR_DDR_WRITE;
                            state <= S_IDLE;
                        end else if (output_words_after_burst >=
                                     output_word_count) begin
                            dma_busy <= 1'b0;
                            dma_done <= 1'b1;
                            completed_runs <= completed_runs + 32'd1;
                            state <= S_IDLE;
                        end else begin
                            output_words_written <=
                                output_words_after_burst[12:0];
                            output_burst_beats <= output_next_burst_beats;
                            state <= S_OUTPUT_CMD;
                        end
                    end
                end

                default: begin
                    dma_busy <= 1'b0;
                    dma_done <= 1'b1;
                    dma_error <= 1'b1;
                    error_code <= ERR_INTERNAL;
                    state <= S_IDLE;
                end
            endcase
        end
    end

endmodule

// The SoC DDR bridge packs one AXI transaction into a native 256-bit line.
// Keep every request inside the current 32-byte line; this also prevents a
// request from crossing a 4 KiB boundary.
module mac_accel_burst_sizer (
    input  wire [31:0] address,
    input  wire [16:0] beats_left,
    output wire [3:0]  beats
);
    wire [3:0] boundary_beats = 4'd8 - {1'b0, address[4:2]};

    assign beats = (beats_left == 17'd0) ? 4'd1 :
                   (|beats_left[16:3]) ? boundary_beats :
                   ({1'b0, beats_left[2:0]} < boundary_beats) ?
                       {1'b0, beats_left[2:0]} : boundary_beats;
endmodule
