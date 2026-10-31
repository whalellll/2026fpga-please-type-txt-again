`timescale 1ns/1ps

// Native SD reader and explicit CMD24 / streamed CMD25 writer.
//
// The controller owns CMD only while sending a command.  The top level must
// implement the CMD pin as a bidirectional pad using sd_cmd_out/sd_cmd_oe.
// DAT is driven only for the write start/data/CRC/end token, then released
// for the card's CRC-status response and programming busy interval.
// All protocol inputs are sampled on SD clock rising edges and CMD changes on
// falling edges.  The generated SD clock may pause only while it is low.
//
// Register map (32-bit words):
//   000 ID              0x53444e32 ("SDN2")
//   004 VERSION         0x00050401
//   008 CONTROL         bit 0 soft reset pulse
//                       bit 1 native 4-bit enable (read/write while idle)
//                       bit 2 clear DONE and sticky ERROR bits
//                       bit 3 abort current operation, retaining divider/bus
//   00c STATUS          busy, done, error, present, raw present, buffer ready,
//                       data active, command active, clock active, bus4,
//                       automatic CMD12 active (bits 0 through 11)
//   010 CLK_DIV         SD clock = clk / (2 * (CLK_DIV + 1))
//   014 ARG             command argument
//   018 COMMAND         write[12], start[11], multi[10], read[9], response[8:6],
//                       command index[5:0]
//   01c..028 RESP0..3   raw response (see interface contract)
//   02c ERROR           sticky: command timeout/CRC/frame, data timeout/CRC/
//                       end, removal, overflow in bits 0 through 7
//   030 BLOCK_SIZE      1 through 512 bytes
//   034 BLOCK_COUNT     1 through 32 blocks
//   038 BLOCKS_DONE     successfully received blocks in this operation
//   03c BUFFER_STATUS   ready bits; write one to release a ready buffer
//   040/044             buffer 0/1 block index
//   048 IDLE_CLOCKS     write a count to start a clock-only operation
//   04c DEBUG_DIV       actual programmed divider
//   050 TX_STATUS       bits0/1 published TX bank ownership, bit8 graceful stop,
//                       bit9 streamed write operation active
//   054 TX_PUBLISH      write-one bits0/1 publishes a completely filled bank
//   058 TX_STOP         write-one bit0 requests CMD25 stop at a block boundary
//   100..2ff            buffer 0, 128 little-endian 32-bit words
//   300..4ff            buffer 1, 128 little-endian 32-bit words
//
// Response type encoding is: 0 none, 1 R48 with CRC, 2 R48 without CRC (R3),
// 3 R136 with CRC, 4 R48b.  R48 responses are exposed as
// RESP1[15:0]:RESP0.  R136 drops its leading eight-bit response header and is
// exposed as RESP3:RESP0.
module sd_native_mmio #(
    parameter [31:0] BASE = 32'h1fe1_3000,
    parameter [15:0] RESET_DIV = 16'd63,
    parameter integer DEBOUNCE_CYCLES = 247500,
    parameter integer CMD_TIMEOUT_CLOCKS = 65535,
    // 2.5 million transfer clocks are just over 100 ms at 24.75 MHz.
    parameter integer DATA_TIMEOUT_CLOCKS = 2500000,
    parameter integer BUSY_TIMEOUT_CLOCKS = 2500000,
    parameter integer WRITE_TIMEOUT_CLOCKS = 12500000,
    parameter integer TX_WAIT_TIMEOUT_CYCLES = 24750000
)(
    input  wire        clk,
    input  wire        resetn,
    input  wire [31:0] addr,
    input  wire        wr,
    input  wire [31:0] wdata,
    input  wire [3:0]  wstrb,
    output reg  [31:0] rdata,
    output wire        hit,

    output reg         sd_clk,
    input  wire        sd_cmd_in,
    output reg         sd_cmd_out,
    output reg         sd_cmd_oe,
    input  wire [3:0]  sd_dat_in,
    output reg  [3:0]  sd_dat_out,
    output reg        sd_dat_oe,
    input  wire        sd_detect_n
);
    localparam [4:0] ST_IDLE       = 5'd0;
    localparam [4:0] ST_CMD_CRC    = 5'd1;
    localparam [4:0] ST_CMD_TX     = 5'd2;
    localparam [4:0] ST_RESP_WAIT  = 5'd3;
    localparam [4:0] ST_RESP_RECV  = 5'd4;
    localparam [4:0] ST_BUSY_WAIT  = 5'd5;
    localparam [4:0] ST_DATA_WAIT  = 5'd6;
    localparam [4:0] ST_DATA_BITS  = 5'd7;
    localparam [4:0] ST_DATA_CRC   = 5'd8;
    localparam [4:0] ST_DATA_END   = 5'd9;
    localparam [4:0] ST_TRAILING   = 5'd10;
    localparam [4:0] ST_IDLE_CLOCK = 5'd11;
    localparam [4:0] ST_WRITE_DELAY = 5'd12;
    localparam [4:0] ST_WRITE_START = 5'd13;
    localparam [4:0] ST_WRITE_BITS  = 5'd14;
    localparam [4:0] ST_WRITE_CRC   = 5'd15;
    localparam [4:0] ST_WRITE_END   = 5'd16;
    localparam [4:0] ST_WRITE_RESP  = 5'd17;
    localparam [4:0] ST_WRITE_TOKEN = 5'd18;
    localparam [4:0] ST_WRITE_BUSY  = 5'd19;
    localparam [4:0] ST_WRITE_WAIT  = 5'd20;
    localparam [4:0] ST_WRITE_STOP  = 5'd21;

    // Data reception is independent of the CMD response.  Native SD permits
    // a read-data start token to arrive before the R1 response has completed,
    // so a single protocol state machine cannot sample both pins correctly.
    localparam [2:0] DATA_IDLE = 3'd0;
    localparam [2:0] DATA_WAIT = 3'd1;
    localparam [2:0] DATA_BITS = 3'd2;
    localparam [2:0] DATA_CRC  = 3'd3;
    localparam [2:0] DATA_END  = 3'd4;
    localparam [2:0] DATA_DONE = 3'd5;
    localparam [2:0] DATA_FAIL = 3'd6;

    localparam [2:0] RESP_NONE     = 3'd0;
    localparam [2:0] RESP_R48_CRC  = 3'd1;
    localparam [2:0] RESP_R48_NOCRC= 3'd2;
    localparam [2:0] RESP_R136_CRC = 3'd3;
    localparam [2:0] RESP_R48B     = 3'd4;

    reg [4:0] state;
    reg [2:0] data_state;
    reg       busy;
    reg       done;
    reg       bus4_enable;
    reg [7:0] error_sticky;
    reg [2:0] pending_response_error;

    reg [15:0] divider;
    reg [15:0] divider_count;
    reg [31:0] argument;
    reg [12:0] command_reg;
    reg [31:0] response0;
    reg [31:0] response1;
    reg [31:0] response2;
    reg [31:0] response3;

    reg [9:0] block_size;
    reg [5:0] block_count;
    reg [5:0] blocks_done;
    reg       buffer0_ready;
    reg       buffer1_ready;
    reg [5:0] buffer0_block_index;
    reg [5:0] buffer1_block_index;
    // Two read views of each sector share one selected write port.  The CPU
    // view serves MMIO reads; the TX view serves the SD data serializer.
    wire [31:0] buffer0_cpu_word, buffer1_cpu_word;
    wire [31:0] buffer0_tx_word, buffer1_tx_word;
    wire [6:0]  buffer0_write_addr, buffer1_write_addr;
    wire [31:0] buffer0_write_data, buffer1_write_data;
    wire [3:0]  buffer0_write_strobe, buffer1_write_strobe;
    reg tx0_full, tx1_full;
    reg write_buffer_select, write_stop_requested, write_multi_active;
    reg [31:0] tx_wait_count;

    reg        detect_meta_n;
    reg        detect_sync_n;
    reg        detect_debounced_n;
    reg [31:0] detect_count;

    reg [5:0]  cmd_index_latched;
    reg [31:0] cmd_arg_latched;
    reg [2:0]  cmd_resp_latched;
    reg        cmd_data_latched;
    reg        cmd_write_latched;
    reg        cmd_multi_latched;
    reg        bus4_latched;
    reg [9:0]  block_size_latched;
    reg [5:0]  block_count_latched;
    reg        auto_stop_active;

    reg [39:0] cmd_crc_payload;
    reg [5:0]  cmd_crc_count;
    reg [6:0]  cmd_crc;
    reg [47:0] cmd_tx_shift;
    reg [5:0]  cmd_tx_count;
    reg        cmd_tx_last_sampled;

    reg [135:0] response_shift;
    reg [7:0]   response_bit_count;
    reg [6:0]   response_crc;
    reg [31:0]  timeout_count;
    reg [31:0]  data_timeout_count;

    reg        data_buffer_select;
    reg [9:0]  data_byte_count;
    reg [2:0]  data_bit_count;
    reg        data_nibble_phase;
    reg [7:0]  data_byte_shift;
    reg [31:0] data_word_build;
    reg [4:0]  data_crc_count;
    reg [15:0] data_crc0;
    reg [15:0] data_crc1;
    reg [15:0] data_crc2;
    reg [15:0] data_crc3;
    reg        data_crc_bad;

    reg [3:0]  trailing_count;
    reg        trailing_last_sampled;
    reg [31:0] idle_clocks_remaining;
    reg        idle_last_sampled;

    wire [31:0] addr_offset;
    wire [31:0] buffer0_offset;
    wire [31:0] buffer1_offset;
    wire [6:0]  buffer0_read_index;
    wire [6:0]  buffer1_read_index;
    wire        raw_present;
    wire        card_present;
    wire        free_buffer;
    wire        data_active_status;
    wire        command_active_status;
    wire        engine_clock_request;
    wire        clock_should_run;

    wire [15:0] divider_write_value;
    wire [31:0] argument_write_value;
    wire [15:0] block_size_write_value;
    wire [7:0]  block_count_write_value;
    wire [31:0] idle_clocks_write_value;

    wire [6:0] command_crc_shifted;
    wire [6:0] command_crc_next;
    wire [6:0] response_crc_shifted;
    wire [6:0] response_crc_next;
    wire [15:0] data_crc0_shifted;
    wire [15:0] data_crc1_shifted;
    wire [15:0] data_crc2_shifted;
    wire [15:0] data_crc3_shifted;
    wire [15:0] data_crc0_next;
    wire [15:0] data_crc1_next;
    wire [15:0] data_crc2_next;
    wire [15:0] data_crc3_next;
    wire [7:0]  completed_data_byte;
    wire [3:0] crc_input = sd_dat_oe ? sd_dat_out : sd_dat_in;
    wire [31:0] write_word = write_buffer_select ?
        buffer1_tx_word : buffer0_tx_word;
    reg [7:0] write_byte;
    wire [3:0] write_nibble = data_nibble_phase ? write_byte[3:0] : write_byte[7:4];
    wire write_active = (state >= ST_WRITE_DELAY) && (state <= ST_WRITE_WAIT);
    wire write_clock_active = (state >= ST_WRITE_DELAY) && (state <= ST_WRITE_BUSY);

    wire [47:0]  response48_next;
    wire [135:0] response136_next;
    wire response48_frame_bad;
    wire response48_crc_bad;
    wire response136_frame_bad;
    wire response136_crc_bad;

    assign addr_offset = addr - BASE;
    assign buffer0_offset = addr - (BASE + 32'h0000_0100);
    assign buffer1_offset = addr - (BASE + 32'h0000_0300);
    assign buffer0_read_index = buffer0_offset[8:2];
    assign buffer1_read_index = buffer1_offset[8:2];
    assign hit = (addr >= BASE) && (addr < (BASE + 32'h0000_0500));

    assign raw_present = ~detect_sync_n;
    assign card_present = ~detect_debounced_n;
    assign free_buffer = ~buffer0_ready | ~buffer1_ready;

    assign data_active_status = write_active || (data_state == DATA_WAIT) ||
                                (data_state == DATA_BITS) ||
                                (data_state == DATA_CRC) ||
                                (data_state == DATA_END);
    assign command_active_status = (state == ST_CMD_CRC) ||
                                   (state == ST_CMD_TX) ||
                                   (state == ST_RESP_WAIT) ||
                                   (state == ST_RESP_RECV) ||
                                   (state == ST_BUSY_WAIT);
    assign engine_clock_request = write_clock_active || (state == ST_CMD_TX) ||
                                  (state == ST_RESP_WAIT) ||
                                  (state == ST_RESP_RECV) ||
                                  (state == ST_BUSY_WAIT) ||
                                  ((data_state == DATA_WAIT) && free_buffer) ||
                                  (data_state == DATA_BITS) ||
                                  (data_state == DATA_CRC) ||
                                  (data_state == DATA_END) ||
                                  (data_state == DATA_DONE) ||
                                  (data_state == DATA_FAIL) ||
                                  ((state == ST_DATA_WAIT) &&
                                   (data_state == DATA_IDLE)) ||
                                  (state == ST_TRAILING) ||
                                  (state == ST_IDLE_CLOCK);
    // If an operation stops while the pin is high, always generate the final
    // falling edge before pausing or returning idle.
    assign clock_should_run = engine_clock_request | sd_clk;

    assign divider_write_value = {
        wstrb[1] ? wdata[15:8] : divider[15:8],
        wstrb[0] ? wdata[7:0]  : divider[7:0]
    };
    assign argument_write_value = {
        wstrb[3] ? wdata[31:24] : argument[31:24],
        wstrb[2] ? wdata[23:16] : argument[23:16],
        wstrb[1] ? wdata[15:8]  : argument[15:8],
        wstrb[0] ? wdata[7:0]   : argument[7:0]
    };
    assign block_size_write_value = {
        wstrb[1] ? wdata[15:8] : {6'd0, block_size[9:8]},
        wstrb[0] ? wdata[7:0]  : block_size[7:0]
    };
    assign block_count_write_value =
        wstrb[0] ? wdata[7:0] : {2'd0, block_count};
    assign idle_clocks_write_value = {
        wstrb[3] ? wdata[31:24] : idle_clocks_remaining[31:24],
        wstrb[2] ? wdata[23:16] : idle_clocks_remaining[23:16],
        wstrb[1] ? wdata[15:8]  : idle_clocks_remaining[15:8],
        wstrb[0] ? wdata[7:0]   : idle_clocks_remaining[7:0]
    };

    // CRC7 polynomial x^7 + x^3 + 1.  CRC computation is deliberately
    // expressed with fixed bit positions instead of a Verilog function.
    assign command_crc_shifted = {cmd_crc[5:0], 1'b0};
    assign command_crc_next = (cmd_crc[6] ^ cmd_crc_payload[39]) ?
                              (command_crc_shifted ^ 7'h09) :
                              command_crc_shifted;
    assign response_crc_shifted = {response_crc[5:0], 1'b0};
    assign response_crc_next = (response_crc[6] ^ sd_cmd_in) ?
                               (response_crc_shifted ^ 7'h09) :
                               response_crc_shifted;

    // Four independent CRC16 generators, one for each DAT lane.
    assign data_crc0_shifted = {data_crc0[14:0], 1'b0};
    assign data_crc1_shifted = {data_crc1[14:0], 1'b0};
    assign data_crc2_shifted = {data_crc2[14:0], 1'b0};
    assign data_crc3_shifted = {data_crc3[14:0], 1'b0};
    assign data_crc0_next = (data_crc0[15] ^ crc_input[0]) ?
                            (data_crc0_shifted ^ 16'h1021) :
                            data_crc0_shifted;
    assign data_crc1_next = (data_crc1[15] ^ crc_input[1]) ?
                            (data_crc1_shifted ^ 16'h1021) :
                            data_crc1_shifted;
    assign data_crc2_next = (data_crc2[15] ^ crc_input[2]) ?
                            (data_crc2_shifted ^ 16'h1021) :
                            data_crc2_shifted;
    assign data_crc3_next = (data_crc3[15] ^ crc_input[3]) ?
                            (data_crc3_shifted ^ 16'h1021) :
                            data_crc3_shifted;

    assign completed_data_byte = bus4_latched ?
                                 {data_byte_shift[7:4], sd_dat_in} :
                                 {data_byte_shift[6:0], sd_dat_in[0]};

    // The old whole-word RX assignment committed each partial byte. Keep the
    // same zero-filled value at each byte boundary in a single RAM write port.
    reg [31:0] rx_fullword;
    always @* begin
        case (data_byte_count[1:0])
            2'd0: rx_fullword = {24'd0, completed_data_byte};
            2'd1: rx_fullword = {16'd0, completed_data_byte,
                                  data_word_build[7:0]};
            2'd2: rx_fullword = {8'd0, completed_data_byte,
                                  data_word_build[15:0]};
            default: rx_fullword = {completed_data_byte,
                                    data_word_build[23:0]};
        endcase
    end

    wire soft_reset_write = wr && hit &&
                            (addr_offset[11:0] == 12'h008) &&
                            wstrb[0] && wdata[0];
    wire abort_write = wr && hit &&
                       (addr_offset[11:0] == 12'h008) &&
                       wstrb[0] && wdata[3];
    wire normal_path = resetn && !soft_reset_write && !abort_write;
    wire rx_byte_write = normal_path &&
                         !(busy && (state != ST_IDLE_CLOCK) && !raw_present) &&
                         clock_should_run && (divider_count >= divider) &&
                         !sd_clk && (data_state == DATA_BITS) &&
                         (!bus4_latched || data_nibble_phase) &&
                         (bus4_latched || (data_bit_count == 3'd7));
    wire cpu_write0 = normal_path && (!busy || write_multi_active) &&
                      !tx0_full && wr && hit &&
                      (addr >= BASE + 32'h100) && (addr < BASE + 32'h300);
    wire cpu_write1 = normal_path && (!busy || write_multi_active) &&
                      !tx1_full && wr && hit &&
                      (addr >= BASE + 32'h300) && (addr < BASE + 32'h500);
    wire rx_write0 = rx_byte_write && !data_buffer_select;
    wire rx_write1 = rx_byte_write && data_buffer_select;

    // RX has the same priority as the later nonblocking assignment in the
    // original block. Valid software owns only completed RX or free TX banks.
    assign buffer0_write_addr = rx_write0 ? data_byte_count[8:2] :
                                         buffer0_read_index;
    assign buffer1_write_addr = rx_write1 ? data_byte_count[8:2] :
                                         buffer1_read_index;
    assign buffer0_write_data = rx_write0 ? rx_fullword : wdata;
    assign buffer1_write_data = rx_write1 ? rx_fullword : wdata;
    assign buffer0_write_strobe = rx_write0 ? 4'hf :
                                  (cpu_write0 ? wstrb : 4'h0);
    assign buffer1_write_strobe = rx_write1 ? 4'hf :
                                  (cpu_write1 ? wstrb : 4'h0);

    sd_native_sector_bank u_buffer0 (
        .clk(clk), .write_addr(buffer0_write_addr),
        .write_data(buffer0_write_data), .write_strobe(buffer0_write_strobe),
        .cpu_read_addr(buffer0_read_index),
        .tx_read_addr(data_byte_count[8:2]),
        .cpu_read_data(buffer0_cpu_word), .tx_read_data(buffer0_tx_word)
    );
    sd_native_sector_bank u_buffer1 (
        .clk(clk), .write_addr(buffer1_write_addr),
        .write_data(buffer1_write_data), .write_strobe(buffer1_write_strobe),
        .cpu_read_addr(buffer1_read_index),
        .tx_read_addr(data_byte_count[8:2]),
        .cpu_read_data(buffer1_cpu_word), .tx_read_data(buffer1_tx_word)
    );

    assign response48_next = {response_shift[46:0], sd_cmd_in};
    assign response136_next = {response_shift[134:0], sd_cmd_in};
    assign response48_frame_bad = (response48_next[47] != 1'b0) ||
                                  (response48_next[46] != 1'b0) ||
                                  (response48_next[0]  != 1'b1) ||
                                  ((cmd_resp_latched != RESP_R48_NOCRC) &&
                                   (response48_next[45:40] !=
                                    cmd_index_latched));
    assign response48_crc_bad =
        (cmd_resp_latched != RESP_R48_NOCRC) &&
        (response48_next[7:1] != response_crc);
    assign response136_frame_bad = (response136_next[135] != 1'b0) ||
                                   (response136_next[134] != 1'b0) ||
                                   (response136_next[133:128] != 6'b111111) ||
                                   (response136_next[0] != 1'b1);
    assign response136_crc_bad =
        (response136_next[7:1] != response_crc);

    always @* begin
        case (data_byte_count[1:0])
            2'd0: write_byte = write_word[7:0];
            2'd1: write_byte = write_word[15:8];
            2'd2: write_byte = write_word[23:16];
            default: write_byte = write_word[31:24];
        endcase
    end

    always @* begin
        rdata = 32'd0;
        if (hit) begin
            case (addr_offset[11:0])
                12'h000: rdata = 32'h5344_4e32;
                12'h004: rdata = 32'h0005_0401;
                12'h008: rdata = {30'd0, bus4_enable, 1'b0};
                12'h00c: rdata = {
                    20'd0,
                    auto_stop_active,
                    bus4_enable,
                    (engine_clock_request | sd_clk),
                    command_active_status,
                    data_active_status,
                    buffer1_ready,
                    buffer0_ready,
                    raw_present,
                    card_present,
                    (|error_sticky),
                    done,
                    busy
                };
                12'h010: rdata = {16'd0, divider};
                12'h014: rdata = argument;
                12'h018: rdata = {19'd0, command_reg};
                12'h01c: rdata = response0;
                12'h020: rdata = response1;
                12'h024: rdata = response2;
                12'h028: rdata = response3;
                12'h02c: rdata = {24'd0, error_sticky};
                12'h030: rdata = {22'd0, block_size};
                12'h034: rdata = {26'd0, block_count};
                12'h038: rdata = {26'd0, blocks_done};
                12'h03c: rdata = {30'd0, buffer1_ready,
                                   buffer0_ready};
                12'h040: rdata = {26'd0, buffer0_block_index};
                12'h044: rdata = {26'd0, buffer1_block_index};
                12'h048: rdata = idle_clocks_remaining;
                12'h04c: rdata = {16'd0, divider};
                12'h050: rdata = {22'd0,write_multi_active,
                                   write_stop_requested,6'd0,tx1_full,tx0_full};
                default: begin
                    if ((addr >= (BASE + 32'h0000_0100)) &&
                        (addr <  (BASE + 32'h0000_0300)))
                        rdata = buffer0_cpu_word;
                    else if ((addr >= (BASE + 32'h0000_0300)) &&
                             (addr <  (BASE + 32'h0000_0500)))
                        rdata = buffer1_cpu_word;
                    else
                        rdata = 32'd0;
                end
            endcase
        end
    end

    // Card-detect synchronization and debounce are independent of a soft
    // reset so software can still observe physical insertion during recovery.
    always @(posedge clk) begin
        if (!resetn) begin
            detect_meta_n      <= 1'b1;
            detect_sync_n      <= 1'b1;
            detect_debounced_n <= 1'b1;
            detect_count       <= 32'd0;
        end else begin
            detect_meta_n <= sd_detect_n;
            detect_sync_n <= detect_meta_n;
            if (detect_sync_n == detect_debounced_n) begin
                detect_count <= 32'd0;
            end else if (DEBOUNCE_CYCLES <= 1) begin
                detect_debounced_n <= detect_sync_n;
                detect_count <= 32'd0;
            end else if (detect_count >= (DEBOUNCE_CYCLES - 1)) begin
                detect_debounced_n <= detect_sync_n;
                detect_count <= 32'd0;
            end else begin
                detect_count <= detect_count + 1'b1;
            end
        end
    end

    always @(posedge clk) begin
        if (!resetn) begin
            state                    <= ST_IDLE;
            data_state               <= DATA_IDLE;
            busy                     <= 1'b0;
            done                     <= 1'b0;
            bus4_enable              <= 1'b0;
            error_sticky             <= 8'd0;
            pending_response_error   <= 3'd0;
            divider                  <= RESET_DIV;
            divider_count            <= 16'd0;
            argument                 <= 32'd0;
            command_reg              <= 13'd0;
            response0                <= 32'd0;
            response1                <= 32'd0;
            response2                <= 32'd0;
            response3                <= 32'd0;
            block_size               <= 10'd512;
            block_count              <= 6'd1;
            blocks_done              <= 6'd0;
            buffer0_ready            <= 1'b0;
            buffer1_ready            <= 1'b0;
            buffer0_block_index      <= 6'd0;
            buffer1_block_index      <= 6'd0;
            tx0_full <= 1'b0; tx1_full <= 1'b0;
            write_buffer_select <= 1'b0;
            write_stop_requested <= 1'b0; write_multi_active <= 1'b0;
            tx_wait_count <= 32'd0;
            sd_clk                   <= 1'b0;
            sd_cmd_out               <= 1'b1;
            sd_cmd_oe                <= 1'b0;
            sd_dat_out               <= 4'hf;
            sd_dat_oe                <= 1'b0;
            cmd_index_latched        <= 6'd0;
            cmd_arg_latched          <= 32'd0;
            cmd_resp_latched         <= RESP_NONE;
            cmd_data_latched         <= 1'b0;
            cmd_write_latched        <= 1'b0;
            cmd_multi_latched        <= 1'b0;
            bus4_latched             <= 1'b0;
            block_size_latched       <= 10'd512;
            block_count_latched      <= 6'd1;
            auto_stop_active         <= 1'b0;
            cmd_crc_payload          <= 40'd0;
            cmd_crc_count            <= 6'd0;
            cmd_crc                  <= 7'd0;
            cmd_tx_shift             <= 48'hffff_ffff_ffff;
            cmd_tx_count             <= 6'd0;
            cmd_tx_last_sampled      <= 1'b0;
            response_shift           <= 136'd0;
            response_bit_count       <= 8'd0;
            response_crc             <= 7'd0;
            timeout_count            <= 32'd0;
            data_timeout_count       <= 32'd0;
            data_buffer_select       <= 1'b0;
            data_byte_count          <= 10'd0;
            data_bit_count           <= 3'd0;
            data_nibble_phase        <= 1'b0;
            data_byte_shift          <= 8'd0;
            data_word_build          <= 32'd0;
            data_crc_count           <= 5'd0;
            data_crc0                <= 16'd0;
            data_crc1                <= 16'd0;
            data_crc2                <= 16'd0;
            data_crc3                <= 16'd0;
            data_crc_bad             <= 1'b0;
            trailing_count           <= 4'd0;
            trailing_last_sampled    <= 1'b0;
            idle_clocks_remaining    <= 32'd0;
            idle_last_sampled        <= 1'b0;
        end else if (wr && hit &&
                     (addr_offset[11:0] == 12'h008) && wstrb[0] &&
                     wdata[0]) begin
            // Full controller soft reset.  Card-detect synchronizers remain
            // live in their independent block above.
            state                    <= ST_IDLE;
            data_state               <= DATA_IDLE;
            busy                     <= 1'b0;
            done                     <= 1'b0;
            bus4_enable              <= 1'b0;
            error_sticky             <= 8'd0;
            pending_response_error   <= 3'd0;
            divider                  <= RESET_DIV;
            divider_count            <= 16'd0;
            argument                 <= 32'd0;
            command_reg              <= 13'd0;
            response0                <= 32'd0;
            response1                <= 32'd0;
            response2                <= 32'd0;
            response3                <= 32'd0;
            block_size               <= 10'd512;
            block_count              <= 6'd1;
            blocks_done              <= 6'd0;
            buffer0_ready            <= 1'b0;
            buffer1_ready            <= 1'b0;
            buffer0_block_index      <= 6'd0;
            buffer1_block_index      <= 6'd0;
            tx0_full <= 1'b0; tx1_full <= 1'b0;
            write_buffer_select <= 1'b0;
            write_stop_requested <= 1'b0; write_multi_active <= 1'b0;
            tx_wait_count <= 32'd0;
            sd_clk                   <= 1'b0;
            sd_cmd_out               <= 1'b1;
            sd_cmd_oe                <= 1'b0;
            sd_dat_out               <= 4'hf;
            sd_dat_oe                <= 1'b0;
            cmd_write_latched        <= 1'b0;
            auto_stop_active         <= 1'b0;
            cmd_crc_count            <= 6'd0;
            cmd_crc                  <= 7'd0;
            cmd_tx_count             <= 6'd0;
            cmd_tx_last_sampled      <= 1'b0;
            response_bit_count       <= 8'd0;
            response_crc             <= 7'd0;
            timeout_count            <= 32'd0;
            data_timeout_count       <= 32'd0;
            data_byte_count          <= 10'd0;
            data_bit_count           <= 3'd0;
            data_nibble_phase        <= 1'b0;
            data_crc_count           <= 5'd0;
            data_crc_bad             <= 1'b0;
            trailing_count           <= 4'd0;
            trailing_last_sampled    <= 1'b0;
            idle_clocks_remaining    <= 32'd0;
            idle_last_sampled        <= 1'b0;
        end else if (wr && hit &&
                     (addr_offset[11:0] == 12'h008) && wstrb[0] &&
                     wdata[3]) begin
            // Abort discards queued buffers and the partial transfer, but
            // deliberately retains divider and bus-width configuration.
            state                 <= ST_IDLE;
            data_state            <= DATA_IDLE;
            pending_response_error <= 3'd0;
            busy                  <= 1'b0;
            done                  <= 1'b1;
            divider_count         <= 16'd0;
            buffer0_ready         <= 1'b0;
            buffer1_ready         <= 1'b0;
            tx0_full <= 1'b0; tx1_full <= 1'b0;
            write_stop_requested <= 1'b0; write_multi_active <= 1'b0;
            tx_wait_count <= 32'd0;
            blocks_done           <= 6'd0;
            sd_clk                <= 1'b0;
            sd_cmd_out            <= 1'b1;
            sd_cmd_oe             <= 1'b0;
            sd_dat_out            <= 4'hf;
            sd_dat_oe             <= 1'b0;
            auto_stop_active      <= 1'b0;
            trailing_last_sampled <= 1'b0;
            idle_clocks_remaining <= 32'd0;
            idle_last_sampled     <= 1'b0;
            data_timeout_count    <= 32'd0;
        end else begin
            // Byte-lane RAM banks handle CPU and RX writes above.
            if (wr && hit && (addr_offset[11:0] == 12'h054) &&
                wstrb[0] && (!busy || write_multi_active) &&
                !write_stop_requested && !auto_stop_active) begin
                if (wdata[0] && !tx0_full) tx0_full <= 1'b1;
                if (wdata[1] && !tx1_full) tx1_full <= 1'b1;
            end
            if (wr && hit && (addr_offset[11:0] == 12'h058) &&
                wstrb[0] && wdata[0] && busy && write_multi_active)
                write_stop_requested <= 1'b1;
            // Pulse and configuration registers.
            if (wr && hit && (addr_offset[11:0] == 12'h008) &&
                wstrb[0]) begin
                if (!busy)
                    bus4_enable <= wdata[1];
                if (wdata[2]) begin
                    done <= 1'b0;
                    error_sticky <= 8'd0;
                end
            end

            if (!busy && wr && hit &&
                (addr_offset[11:0] == 12'h010) &&
                (wstrb[0] || wstrb[1]))
                divider <= divider_write_value;

            if (!busy && wr && hit &&
                (addr_offset[11:0] == 12'h014) && (|wstrb))
                argument <= argument_write_value;

            if (!busy && wr && hit &&
                (addr_offset[11:0] == 12'h030) &&
                (wstrb[0] || wstrb[1])) begin
                if ((block_size_write_value >= 16'd1) &&
                    (block_size_write_value <= 16'd512))
                    block_size <= block_size_write_value[9:0];
            end

            if (!busy && wr && hit &&
                (addr_offset[11:0] == 12'h034) && wstrb[0]) begin
                if ((block_count_write_value >= 8'd1) &&
                    (block_count_write_value <= 8'd32))
                    block_count <= block_count_write_value[5:0];
            end

            if (wr && hit && (addr_offset[11:0] == 12'h03c) &&
                wstrb[0]) begin
                if (wdata[0])
                    buffer0_ready <= 1'b0;
                if (wdata[1])
                    buffer1_ready <= 1'b0;
            end

            // Start a user command.  A missing card is rejected before any
            // command line activity; clock-only startup cycles remain allowed.
            if (!busy && wr && hit &&
                (addr_offset[11:0] == 12'h018) && wstrb[1] &&
                wdata[11]) begin
                done <= 1'b0;
                pending_response_error <= 3'd0;
                command_reg <= wdata[12:0];
                response0 <= 32'd0;
                response1 <= 32'd0;
                response2 <= 32'd0;
                response3 <= 32'd0;
                blocks_done <= 6'd0;
                auto_stop_active <= 1'b0;
                if (!raw_present) begin
                    error_sticky[6] <= 1'b1;
                    done <= 1'b1;
                end else if ((wdata[8:6] > RESP_R48B) ||
                    (wdata[12] && ((wdata[8:6] != RESP_R48_CRC) || wdata[9] ||
                     !bus4_enable || (block_size != 10'd512) ||
                     (!wdata[10] && ((wdata[5:0] != 6'd24) || (block_count != 6'd1))) ||
                     (wdata[10] && ((wdata[5:0] != 6'd25) ||
                      (block_count < 6'd2) || !tx0_full))))) begin
                    error_sticky[2] <= 1'b1;
                    done <= 1'b1;
                end else begin
                    busy <= 1'b1;
                    data_state <= DATA_IDLE;
                    cmd_index_latched <= wdata[5:0];
                    cmd_arg_latched <= argument;
                    cmd_resp_latched <= wdata[8:6];
                    cmd_data_latched <= wdata[9];
                    cmd_write_latched <= wdata[12];
                    cmd_multi_latched <= wdata[10];
                    write_buffer_select <= 1'b0;
                    write_stop_requested <= 1'b0;
                    write_multi_active <= wdata[12] && wdata[10];
                    tx_wait_count <= 32'd0;
                    if (!wdata[12] || !wdata[10]) begin
                        tx0_full <= 1'b0; tx1_full <= 1'b0;
                    end
                    bus4_latched <= bus4_enable;
                    block_size_latched <= block_size;
                    block_count_latched <= block_count;
                    cmd_crc_payload <= {2'b01, wdata[5:0], argument};
                    cmd_crc_count <= 6'd0;
                    cmd_crc <= 7'd0;
                    cmd_tx_count <= 6'd0;
                    cmd_tx_last_sampled <= 1'b0;
                    timeout_count <= 32'd0;
                    data_timeout_count <= 32'd0;
                    state <= ST_CMD_CRC;
                end
            end else if (!busy && wr && hit &&
                         (addr_offset[11:0] == 12'h048) && (|wstrb)) begin
                idle_clocks_remaining <= idle_clocks_write_value;
                if (idle_clocks_write_value != 32'd0) begin
                    busy <= 1'b1;
                    done <= 1'b0;
                    idle_last_sampled <= 1'b0;
                    divider_count <= 16'd0;
                    state <= ST_IDLE_CLOCK;
                end
            end

            // A synchronized raw removal terminates protocol activity without
            // waiting for the much slower user-visible debounce interval.
            if (busy && (state != ST_IDLE_CLOCK) && !raw_present) begin
                error_sticky[6] <= 1'b1;
                state <= ST_IDLE;
                data_state <= DATA_IDLE;
                pending_response_error <= 3'd0;
                busy <= 1'b0;
                done <= 1'b1;
                divider_count <= 16'd0;
                buffer0_ready <= 1'b0;
                buffer1_ready <= 1'b0;
                tx0_full <= 1'b0; tx1_full <= 1'b0;
                write_stop_requested <= 1'b0; write_multi_active <= 1'b0;
                blocks_done <= 6'd0;
                sd_clk <= 1'b0;
                sd_cmd_out <= 1'b1;
                sd_cmd_oe <= 1'b0;
                sd_dat_out <= 4'hf;
                sd_dat_oe <= 1'b0;
                auto_stop_active <= 1'b0;
                data_timeout_count <= 32'd0;
                trailing_last_sampled <= 1'b0;
            end else begin
                // A producer gap pauses SDCLK only after it returns low.
                // This watchdog counts system clocks, so a vanished producer
                // cannot freeze the operation by withholding the next bank.
                if ((state == ST_WRITE_WAIT) && !sd_clk) begin
                    if (write_stop_requested || (|error_sticky)) begin
                        state <= ST_WRITE_STOP;
                    end else if (write_buffer_select ? tx1_full : tx0_full) begin
                        timeout_count <= 32'd0;
                        tx_wait_count <= 32'd0;
                        state <= ST_WRITE_DELAY;
                    end else if (tx_wait_count >= TX_WAIT_TIMEOUT_CYCLES-1) begin
                        error_sticky[3] <= 1'b1;
                        state <= ST_WRITE_STOP;
                    end else tx_wait_count <= tx_wait_count + 1'b1;
                end
                // Reuse the tested command/R1b engine for stop. Keep original
                // sticky write errors while draining CMD12 and its DAT0 busy.
                if ((state == ST_WRITE_STOP) && !sd_clk) begin
                    auto_stop_active <= 1'b1;
                    cmd_index_latched <= 6'd12;
                    cmd_arg_latched <= 32'd0;
                    cmd_resp_latched <= RESP_R48B;
                    cmd_data_latched <= 1'b0;
                    cmd_write_latched <= 1'b0;
                    cmd_multi_latched <= 1'b0;
                    cmd_crc_payload <= {2'b01,6'd12,32'd0};
                    cmd_crc_count <= 6'd0; cmd_crc <= 7'd0;
                    state <= ST_CMD_CRC;
                end
                // CRC7 preparation runs on the system clock while SDCLK is
                // low.  This avoids a large combinational CRC chain.
                if ((state == ST_CMD_CRC) && !sd_clk) begin
                    cmd_crc <= command_crc_next;
                    cmd_crc_payload <= {cmd_crc_payload[38:0], 1'b0};
                    if (cmd_crc_count == 6'd39) begin
                        cmd_tx_shift <= {2'b01, cmd_index_latched,
                                         cmd_arg_latched,
                                         command_crc_next, 1'b1};
                        cmd_tx_count <= 6'd0;
                        cmd_tx_last_sampled <= 1'b0;
                        sd_cmd_out <= 1'b0;
                        sd_cmd_oe <= 1'b1;
                        divider_count <= 16'd0;
                        state <= ST_CMD_TX;
                    end else begin
                        cmd_crc_count <= cmd_crc_count + 1'b1;
                    end
                end

                if (clock_should_run) begin
                    if (divider_count >= divider) begin
                        divider_count <= 16'd0;
                        if (!sd_clk) begin
                            // Rising SD clock edge: sample card inputs.
                            sd_clk <= 1'b1;

                            // DAT has its own receiver because a read token
                            // may overlap the command response on CMD.  This
                            // case is deliberately separate from the command
                            // case below; both therefore sample the same edge.
                            case (data_state)
                                DATA_WAIT: begin
                                    if (bus4_latched ?
                                        (sd_dat_in == 4'b0000) :
                                        (sd_dat_in[0] == 1'b0)) begin
                                        if (!free_buffer) begin
                                            error_sticky[7] <= 1'b1;
                                            data_state <= DATA_FAIL;
                                        end else begin
                                            if (!buffer0_ready)
                                                data_buffer_select <= 1'b0;
                                            else
                                                data_buffer_select <= 1'b1;
                                            data_byte_count <= 10'd0;
                                            data_bit_count <= 3'd0;
                                            data_nibble_phase <= 1'b0;
                                            data_byte_shift <= 8'd0;
                                            data_word_build <= 32'd0;
                                            data_crc_count <= 5'd0;
                                            data_crc0 <= 16'd0;
                                            data_crc1 <= 16'd0;
                                            data_crc2 <= 16'd0;
                                            data_crc3 <= 16'd0;
                                            data_crc_bad <= 1'b0;
                                            data_timeout_count <= 32'd0;
                                            data_state <= DATA_BITS;
                                        end
                                    end else if (bus4_latched &&
                                                 (sd_dat_in[0] == 1'b0)) begin
                                        // DAT0 asserted without the required
                                        // four-lane start bit.
                                        error_sticky[5] <= 1'b1;
                                        data_state <= DATA_FAIL;
                                    end else if (DATA_TIMEOUT_CLOCKS <= 1) begin
                                        error_sticky[3] <= 1'b1;
                                        data_state <= DATA_FAIL;
                                    end else if (data_timeout_count >=
                                                 (DATA_TIMEOUT_CLOCKS - 1)) begin
                                        error_sticky[3] <= 1'b1;
                                        data_state <= DATA_FAIL;
                                    end else begin
                                        data_timeout_count <=
                                            data_timeout_count + 1'b1;
                                    end
                                end

                                DATA_BITS: begin
                                    data_crc0 <= data_crc0_next;
                                    if (bus4_latched) begin
                                        data_crc1 <= data_crc1_next;
                                        data_crc2 <= data_crc2_next;
                                        data_crc3 <= data_crc3_next;
                                    end

                                    if (bus4_latched &&
                                        !data_nibble_phase) begin
                                        data_byte_shift <= {sd_dat_in, 4'd0};
                                        data_nibble_phase <= 1'b1;
                                    end else if (bus4_latched ||
                                                 (data_bit_count == 3'd7)) begin
                                        // Fixed byte-lane cases avoid a
                                        // variable part-select in this path.
                                        case (data_byte_count[1:0])
                                            2'd0: data_word_build <=
                                                {24'd0, completed_data_byte};
                                            2'd1: data_word_build <=
                                                {16'd0, completed_data_byte,
                                                 data_word_build[7:0]};
                                            2'd2: data_word_build <=
                                                {8'd0, completed_data_byte,
                                                 data_word_build[15:0]};
                                            default: data_word_build <= 32'd0;
                                        endcase

                                        data_nibble_phase <= 1'b0;
                                        data_bit_count <= 3'd0;
                                        data_byte_shift <= 8'd0;
                                        if (data_byte_count ==
                                            (block_size_latched - 1'b1)) begin
                                            data_crc_count <= 5'd0;
                                            data_state <= DATA_CRC;
                                        end else begin
                                            data_byte_count <=
                                                data_byte_count + 1'b1;
                                        end
                                    end else begin
                                        data_byte_shift <=
                                            {data_byte_shift[6:0],
                                             sd_dat_in[0]};
                                        data_bit_count <=
                                            data_bit_count + 1'b1;
                                    end
                                end

                                DATA_CRC: begin
                                    if (sd_dat_in[0] != data_crc0[15])
                                        data_crc_bad <= 1'b1;
                                    if (bus4_latched &&
                                        ((sd_dat_in[1] != data_crc1[15]) ||
                                         (sd_dat_in[2] != data_crc2[15]) ||
                                         (sd_dat_in[3] != data_crc3[15])))
                                        data_crc_bad <= 1'b1;
                                    data_crc0 <= {data_crc0[14:0], 1'b0};
                                    data_crc1 <= {data_crc1[14:0], 1'b0};
                                    data_crc2 <= {data_crc2[14:0], 1'b0};
                                    data_crc3 <= {data_crc3[14:0], 1'b0};
                                    if (data_crc_count == 5'd15) begin
                                        data_state <= DATA_END;
                                    end else begin
                                        data_crc_count <=
                                            data_crc_count + 1'b1;
                                    end
                                end

                                DATA_END: begin
                                    if (data_crc_bad ||
                                        (bus4_latched ?
                                         (sd_dat_in != 4'b1111) :
                                         (sd_dat_in[0] != 1'b1))) begin
                                        if (data_crc_bad)
                                            error_sticky[4] <= 1'b1;
                                        if (bus4_latched ?
                                            (sd_dat_in != 4'b1111) :
                                            (sd_dat_in[0] != 1'b1))
                                            error_sticky[5] <= 1'b1;
                                        data_state <= DATA_FAIL;
                                    end else begin
                                        if (data_buffer_select) begin
                                            buffer1_ready <= 1'b1;
                                            buffer1_block_index <= blocks_done;
                                        end else begin
                                            buffer0_ready <= 1'b1;
                                            buffer0_block_index <= blocks_done;
                                        end
                                        blocks_done <= blocks_done + 1'b1;

                                        if (cmd_multi_latched &&
                                            ((blocks_done + 1'b1) <
                                             block_count_latched)) begin
                                            data_timeout_count <= 32'd0;
                                            data_state <= DATA_WAIT;
                                        end else begin
                                            data_state <= DATA_DONE;
                                        end
                                    end
                                end

                                default: begin
                                end
                            endcase

                            case (state)
                                ST_CMD_TX: begin
                                    if (cmd_tx_count == 6'd47)
                                        cmd_tx_last_sampled <= 1'b1;
                                    else
                                        cmd_tx_count <= cmd_tx_count + 1'b1;
                                end

                                ST_RESP_WAIT: begin
                                    if (sd_cmd_in == 1'b0) begin
                                        response_shift <= {135'd0,
                                                           sd_cmd_in};
                                        response_bit_count <= 8'd1;
                                        response_crc <= 7'd0;
                                        timeout_count <= 32'd0;
                                        state <= ST_RESP_RECV;
                                    end else if (CMD_TIMEOUT_CLOCKS <= 1) begin
                                        if (cmd_data_latched) begin
                                            pending_response_error[0] <= 1'b1;
                                            state <= ST_DATA_WAIT;
                                        end else if (cmd_resp_latched ==
                                                     RESP_R48B) begin
                                            pending_response_error[0] <= 1'b1;
                                            timeout_count <= 32'd0;
                                            state <= ST_BUSY_WAIT;
                                        end else begin
                                            error_sticky[0] <= 1'b1;
                                            data_state <= DATA_IDLE;
                                            trailing_count <= 4'd0;
                                            trailing_last_sampled <= 1'b0;
                                            state <= write_multi_active ? ST_WRITE_STOP : ST_TRAILING;
                                        end
                                    end else if (timeout_count >=
                                                 (CMD_TIMEOUT_CLOCKS - 1)) begin
                                        if (cmd_data_latched) begin
                                            pending_response_error[0] <= 1'b1;
                                            state <= ST_DATA_WAIT;
                                        end else if (cmd_resp_latched ==
                                                     RESP_R48B) begin
                                            pending_response_error[0] <= 1'b1;
                                            timeout_count <= 32'd0;
                                            state <= ST_BUSY_WAIT;
                                        end else begin
                                            error_sticky[0] <= 1'b1;
                                            data_state <= DATA_IDLE;
                                            trailing_count <= 4'd0;
                                            trailing_last_sampled <= 1'b0;
                                            state <= write_multi_active ? ST_WRITE_STOP : ST_TRAILING;
                                        end
                                    end else begin
                                        timeout_count <= timeout_count + 1'b1;
                                    end
                                end

                                ST_RESP_RECV: begin
                                    response_shift <= response136_next;
                                    if ((cmd_resp_latched == RESP_R136_CRC) &&
                                        (response_bit_count >= 8'd8) &&
                                        (response_bit_count < 8'd128))
                                        response_crc <= response_crc_next;
                                    else if ((cmd_resp_latched !=
                                              RESP_R136_CRC) &&
                                             (response_bit_count < 8'd40))
                                        response_crc <= response_crc_next;

                                    if ((cmd_resp_latched == RESP_R136_CRC) &&
                                        (response_bit_count == 8'd135)) begin
                                        response0 <= response136_next[31:0];
                                        response1 <= response136_next[63:32];
                                        response2 <= response136_next[95:64];
                                        response3 <= response136_next[127:96];
                                        if (response136_frame_bad)
                                            error_sticky[2] <= 1'b1;
                                        if (response136_crc_bad)
                                            error_sticky[1] <= 1'b1;
                                        data_state <= DATA_IDLE;
                                        trailing_count <= 4'd0;
                                        trailing_last_sampled <= 1'b0;
                                        state <= ST_TRAILING;
                                    end else if ((cmd_resp_latched !=
                                                 RESP_R136_CRC) &&
                                                (response_bit_count ==
                                                 8'd47)) begin
                                        response0 <= response48_next[31:0];
                                        response1 <= {16'd0,
                                                     response48_next[47:32]};
                                        response2 <= 32'd0;
                                        response3 <= 32'd0;
                                        if (response48_frame_bad ||
                                            response48_crc_bad) begin
                                            if (cmd_data_latched) begin
                                                if (response48_frame_bad)
                                                    pending_response_error[2]
                                                        <= 1'b1;
                                                if (response48_crc_bad)
                                                    pending_response_error[1]
                                                        <= 1'b1;
                                                state <= ST_DATA_WAIT;
                                            end else if (cmd_resp_latched ==
                                                         RESP_R48B) begin
                                                if (response48_frame_bad)
                                                    pending_response_error[2]
                                                        <= 1'b1;
                                                if (response48_crc_bad)
                                                    pending_response_error[1]
                                                        <= 1'b1;
                                                timeout_count <= 32'd0;
                                                state <= ST_BUSY_WAIT;
                                            end else begin
                                                if (response48_frame_bad)
                                                    error_sticky[2] <= 1'b1;
                                                if (response48_crc_bad)
                                                    error_sticky[1] <= 1'b1;
                                                data_state <= DATA_IDLE;
                                                trailing_count <= 4'd0;
                                                trailing_last_sampled <= 1'b0;
                                                state <= write_multi_active ? ST_WRITE_STOP : ST_TRAILING;
                                            end
                                        end else if (cmd_write_latched) begin
                                            // Never send data after an R1 card
                                            // error, even when its CRC is valid.
                                            if (|(response48_next[39:8] & 32'hfdff_e008)) begin
                                                error_sticky[7] <= 1'b1;
                                                trailing_count <= 4'd0;
                                                trailing_last_sampled <= 1'b0;
                                                state <= write_multi_active ? ST_WRITE_STOP : ST_TRAILING;
                                            end else begin
                                                timeout_count <= 32'd0;
                                                state <= write_multi_active ? ST_WRITE_WAIT : ST_WRITE_DELAY;
                                            end
                                        end else if (cmd_data_latched) begin
                                            timeout_count <= 32'd0;
                                            state <= ST_DATA_WAIT;
                                        end else if (cmd_resp_latched ==
                                                     RESP_R48B) begin
                                            // Write-stop R1 remains strict.
                                            // The reader separately permits
                                            // its documented final-LBA
                                            // OUT_OF_RANGE exception.
                                            if (write_multi_active && auto_stop_active &&
                                                |(response48_next[39:8] & 32'hfdff_e008))
                                                error_sticky[7] <= 1'b1;
                                            timeout_count <= 32'd0;
                                            state <= ST_BUSY_WAIT;
                                        end else begin
                                            trailing_count <= 4'd0;
                                            trailing_last_sampled <= 1'b0;
                                            state <= ST_TRAILING;
                                        end
                                    end else begin
                                        response_bit_count <=
                                            response_bit_count + 1'b1;
                                    end
                                end

                                ST_WRITE_DELAY: begin
                                    if (write_multi_active && write_stop_requested) begin
                                        state <= ST_WRITE_STOP;
                                    end else if (timeout_count == 32'd3) begin
                                        data_byte_count <= 10'd0;
                                        data_nibble_phase <= 1'b0;
                                        data_crc0 <= 16'd0; data_crc1 <= 16'd0;
                                        data_crc2 <= 16'd0; data_crc3 <= 16'd0;
                                        state <= ST_WRITE_START;
                                    end else timeout_count <= timeout_count + 1'b1;
                                end
                                ST_WRITE_START: state <= ST_WRITE_BITS;
                                ST_WRITE_BITS: begin
                                    data_crc0 <= data_crc0_next;
                                    data_crc1 <= data_crc1_next;
                                    data_crc2 <= data_crc2_next;
                                    data_crc3 <= data_crc3_next;
                                    if (!data_nibble_phase) data_nibble_phase <= 1'b1;
                                    else begin
                                        data_nibble_phase <= 1'b0;
                                        if (data_byte_count == 10'd511) begin
                                            data_crc_count <= 5'd0;
                                            // CRC shifts no longer access the
                                            // RAM, so the producer can reuse
                                            // this bank during card busy.
                                            if (write_multi_active) begin
                                                if (write_buffer_select) tx1_full <= 1'b0;
                                                else tx0_full <= 1'b0;
                                            end
                                            state <= ST_WRITE_CRC;
                                        end else data_byte_count <= data_byte_count + 1'b1;
                                    end
                                end
                                ST_WRITE_CRC: begin
                                    data_crc0 <= {data_crc0[14:0],1'b0};
                                    data_crc1 <= {data_crc1[14:0],1'b0};
                                    data_crc2 <= {data_crc2[14:0],1'b0};
                                    data_crc3 <= {data_crc3[14:0],1'b0};
                                    if (data_crc_count == 5'd15) state <= ST_WRITE_END;
                                    else data_crc_count <= data_crc_count + 1'b1;
                                end
                                ST_WRITE_END: begin
                                    timeout_count <= 32'd0;
                                    state <= ST_WRITE_RESP;
                                end
                                ST_WRITE_RESP: begin
                                    if (!sd_dat_in[0]) begin
                                        data_byte_shift <= 8'd0;
                                        data_crc_count <= 5'd0;
                                        state <= ST_WRITE_TOKEN;
                                    end else if (timeout_count >= CMD_TIMEOUT_CLOCKS-1) begin
                                        error_sticky[3] <= 1'b1;
                                        timeout_count <= 32'd0;
                                        state <= ST_WRITE_BUSY;
                                    end else timeout_count <= timeout_count + 1'b1;
                                end
                                ST_WRITE_TOKEN: begin
                                    data_byte_shift <= {data_byte_shift[6:0],sd_dat_in[0]};
                                    if (data_crc_count == 5'd3) begin
                                        if ({data_byte_shift[3:0],sd_dat_in[0]} != 5'b00101) begin
                                            if ({data_byte_shift[3:0],sd_dat_in[0]} == 5'b01011)
                                                error_sticky[4] <= 1'b1;
                                            else error_sticky[5] <= 1'b1;
                                        end
                                        timeout_count <= 32'd0;
                                        state <= ST_WRITE_BUSY;
                                    end else data_crc_count <= data_crc_count + 1'b1;
                                end
                                ST_WRITE_BUSY: begin
                                    // DONE is impossible while DAT0 is busy.
                                    // Software defers error handling until this
                                    // state also completes on a rejected token.
                                    if (sd_dat_in[0]) begin
                                        if (!(|error_sticky)) blocks_done <= blocks_done + 1'b1;
                                        if (write_multi_active) begin
                                            if ((|error_sticky) || write_stop_requested ||
                                                (blocks_done + 6'd1 >= block_count_latched))
                                                state <= ST_WRITE_STOP;
                                            else begin
                                                write_buffer_select <= ~write_buffer_select;
                                                tx_wait_count <= 32'd0;
                                                state <= ST_WRITE_WAIT;
                                            end
                                        end else begin
                                            trailing_count <= 4'd0;
                                            trailing_last_sampled <= 1'b0;
                                            state <= ST_TRAILING;
                                        end
                                    end else if (timeout_count >= WRITE_TIMEOUT_CLOCKS-1) begin
                                        error_sticky[3] <= 1'b1;
                                        trailing_count <= 4'd0;
                                        trailing_last_sampled <= 1'b0;
                                        state <= write_multi_active ? ST_WRITE_STOP : ST_TRAILING;
                                    end else timeout_count <= timeout_count + 1'b1;
                                end

                                ST_BUSY_WAIT: begin
                                    if (sd_dat_in[0] == 1'b1) begin
                                        trailing_count <= 4'd0;
                                        trailing_last_sampled <= 1'b0;
                                        timeout_count <= 32'd0;
                                        state <= ST_TRAILING;
                                    end else if ((write_multi_active ? WRITE_TIMEOUT_CLOCKS : BUSY_TIMEOUT_CLOCKS) <= 1) begin
                                        error_sticky[3] <= 1'b1;
                                        trailing_count <= 4'd0;
                                        trailing_last_sampled <= 1'b0;
                                        state <= ST_TRAILING;
                                    end else if (timeout_count >=
                                                 ((write_multi_active ? WRITE_TIMEOUT_CLOCKS : BUSY_TIMEOUT_CLOCKS) - 1)) begin
                                        error_sticky[3] <= 1'b1;
                                        trailing_count <= 4'd0;
                                        trailing_last_sampled <= 1'b0;
                                        state <= ST_TRAILING;
                                    end else begin
                                        timeout_count <= timeout_count + 1'b1;
                                    end
                                end

                                ST_DATA_WAIT: begin
                                    if (data_state == DATA_FAIL) begin
                                        data_state <= DATA_IDLE;
                                        trailing_count <= 4'd0;
                                        trailing_last_sampled <= 1'b0;
                                        state <= ST_TRAILING;
                                    end else if (data_state == DATA_DONE) begin
                                        data_state <= DATA_IDLE;
                                        if (cmd_multi_latched) begin
                                            auto_stop_active <= 1'b1;
                                            cmd_index_latched <= 6'd12;
                                            cmd_arg_latched <= 32'd0;
                                            cmd_resp_latched <= RESP_R48B;
                                            cmd_data_latched <= 1'b0;
                                            cmd_multi_latched <= 1'b0;
                                            cmd_crc_payload <=
                                                {2'b01, 6'd12, 32'd0};
                                            cmd_crc_count <= 6'd0;
                                            cmd_crc <= 7'd0;
                                            state <= ST_CMD_CRC;
                                        end else begin
                                            trailing_count <= 4'd0;
                                            trailing_last_sampled <= 1'b0;
                                            state <= ST_TRAILING;
                                        end
                                    end else if (data_state == DATA_IDLE) begin
                                        // A data command must remain armed
                                        // until it completes or fails.  Do
                                        // not leave the supervisor wedged if
                                        // an unexpected cancellation occurs.
                                        error_sticky[3] <= 1'b1;
                                        trailing_count <= 4'd0;
                                        trailing_last_sampled <= 1'b0;
                                        state <= ST_TRAILING;
                                    end
                                end

                                ST_TRAILING: begin
                                    if (trailing_count == 4'd7)
                                        trailing_last_sampled <= 1'b1;
                                    else
                                        trailing_count <=
                                            trailing_count + 1'b1;
                                end

                                ST_IDLE_CLOCK: begin
                                    if (idle_clocks_remaining <= 32'd1) begin
                                        idle_clocks_remaining <= 32'd0;
                                        idle_last_sampled <= 1'b1;
                                    end else begin
                                        idle_clocks_remaining <=
                                            idle_clocks_remaining - 1'b1;
                                    end
                                end

                                default: begin
                                end
                            endcase
                        end else begin
                            // Falling SD clock edge: change/release CMD and
                            // finish operations only after returning low.
                            sd_clk <= 1'b0;
                            case (state)
                                ST_CMD_TX: begin
                                    if (cmd_tx_last_sampled) begin
                                        sd_cmd_out <= 1'b1;
                                        sd_cmd_oe <= 1'b0;
                                        cmd_tx_last_sampled <= 1'b0;
                                        timeout_count <= 32'd0;
                                        response_bit_count <= 8'd0;
                                        response_crc <= 7'd0;
                                        if (cmd_resp_latched == RESP_NONE) begin
                                            trailing_count <= 4'd0;
                                            trailing_last_sampled <= 1'b0;
                                            state <= ST_TRAILING;
                                        end else begin
                                            if (cmd_data_latched) begin
                                                data_timeout_count <= 32'd0;
                                                data_state <= DATA_WAIT;
                                            end
                                            state <= ST_RESP_WAIT;
                                        end
                                    end else begin
                                        cmd_tx_shift <=
                                            {cmd_tx_shift[46:0], 1'b1};
                                        sd_cmd_out <= cmd_tx_shift[46];
                                    end
                                end

                                ST_WRITE_START: begin sd_dat_oe <= 1'b1; sd_dat_out <= 4'h0; end
                                ST_WRITE_BITS: begin sd_dat_oe <= 1'b1; sd_dat_out <= write_nibble; end
                                ST_WRITE_CRC: begin
                                    sd_dat_out <= {data_crc3[15],data_crc2[15],data_crc1[15],data_crc0[15]};
                                end
                                ST_WRITE_END: sd_dat_out <= 4'hf;
                                ST_WRITE_RESP: begin sd_dat_oe <= 1'b0; sd_dat_out <= 4'hf; end
                                ST_TRAILING: begin
                                    if (trailing_last_sampled) begin
                                        state <= ST_IDLE;
                                        busy <= 1'b0;
                                        done <= 1'b1;
                                        auto_stop_active <= 1'b0;
                                        tx0_full <= 1'b0; tx1_full <= 1'b0;
                                        write_multi_active <= 1'b0;
                                        data_state <= DATA_IDLE;
                                        error_sticky[2:0] <=
                                            error_sticky[2:0] |
                                            pending_response_error;
                                        pending_response_error <= 3'd0;
                                        trailing_last_sampled <= 1'b0;
                                    end
                                end

                                ST_IDLE_CLOCK: begin
                                    if (idle_last_sampled) begin
                                        state <= ST_IDLE;
                                        busy <= 1'b0;
                                        done <= 1'b1;
                                        idle_last_sampled <= 1'b0;
                                    end
                                end

                                default: begin
                                end
                            endcase
                        end
                    end else begin
                        divider_count <= divider_count + 1'b1;
                    end
                end else begin
                    divider_count <= 16'd0;
                end
            end
        end
    end
endmodule

// One byte lane has one synchronous writer and one asynchronous reader.
// A second mirror supplies a simultaneous independent TX read address.
// Neither array is reset, matching the original buffer; only ownership flags
// are reset. The same-address read port is steered aside during a write:
// MMIO never consumes rdata on its own write, and published TX is immutable.
module sd_native_sector_bank (
    input  wire        clk,
    input  wire [6:0]  write_addr,
    input  wire [31:0] write_data,
    input  wire [3:0]  write_strobe,
    input  wire [6:0]  cpu_read_addr,
    input  wire [6:0]  tx_read_addr,
    output wire [31:0] cpu_read_data,
    output wire [31:0] tx_read_data
);
    wire any_write = |write_strobe;
    wire [6:0] cpu_safe_addr = (any_write &&
                                (cpu_read_addr == write_addr)) ?
                               (write_addr ^ 7'd1) : cpu_read_addr;
    wire [6:0] tx_safe_addr = (any_write &&
                               (tx_read_addr == write_addr)) ?
                              (write_addr ^ 7'd1) : tx_read_addr;

    genvar lane;
    generate for (lane = 0; lane < 4; lane = lane + 1) begin : g_lane
        reg [7:0] cpu_mem [0:127] /* synthesis syn_ramstyle="distributed_ram" */;
        reg [7:0] tx_mem [0:127] /* synthesis syn_ramstyle="distributed_ram" */;
        always @(posedge clk) begin
            if (write_strobe[lane]) begin
                cpu_mem[write_addr] <= write_data[lane*8 +: 8];
                tx_mem[write_addr] <= write_data[lane*8 +: 8];
            end
        end
        assign cpu_read_data[lane*8 +: 8] = cpu_mem[cpu_safe_addr];
        assign tx_read_data[lane*8 +: 8] = tx_mem[tx_safe_addr];
    end endgenerate
endmodule
