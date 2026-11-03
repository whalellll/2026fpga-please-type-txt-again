`timescale 1ns / 1ps
// Isolated, volatile-CRAM acceptance harness for the stage-2 window only.
// It does not connect DDR, Linux, or the production SoC register map.
module mac_conv_window_board_top (
    input wire free_clk,
    input wire rst_board,
    output wire uart_txd
);
    localparam [2:0] S_CFG = 0, S_RUN = 1, S_REPORT = 2,
                     S_PAUSE = 3;
    reg [7:0] por_count = 0;
    wire resetn = rst_board && (&por_count);
    always @(posedge free_clk)
        if (!(&por_count)) por_count <= por_count + 1'b1;

    reg [2:0] state;
    reg [1:0] job;
    reg failed;
    reg [15:0] source_index, output_index, run_cycles;
    reg [15:0] job_cycles [0:3];
    reg [15:0] job_stalls [0:3];
    reg [8:0] expected_x, expected_y;
    reg [2:0] expected_kx, expected_ky;
    reg [7:0] ready_pattern;
    reg [31:0] source_rom [0:100];
    reg [31:0] expected_rom [0:443];
    initial begin
        $readmemh("sim/vectors/yolo_window_board_source.hex", source_rom);
        $readmemh("sim/vectors/yolo_window_board_expected.hex", expected_rom);
    end

    wire [8:0] width = job == 0 ? 9'd4 : job == 3 ? 9'd7 : 9'd5;
    wire [8:0] height = job == 0 ? 9'd3 : job == 3 ? 9'd7 : 9'd4;
    wire [2:0] kernel = job == 0 ? 3'd1 : job == 3 ? 3'd6 : 3'd3;
    wire [1:0] stride = job == 0 ? 2'd1 : 2'd2;
    wire [2:0] padding = job == 0 ? 3'd0 : job == 3 ? 3'd2 : 3'd1;
    wire [7:0] tile = job == 2 ? 8'd1 : 8'd0;
    wire [8:0] output_width = job == 0 ? 9'd4 : 9'd3;
    wire [15:0] source_base = job == 0 ? 0 : job == 1 ? 12 :
                              job == 2 ? 32 : 52;
    wire [15:0] expected_base = job == 0 ? 0 : job == 1 ? 12 :
                                job == 2 ? 66 : 120;
    wire [15:0] source_count = job == 0 ? 12 : job == 3 ? 49 : 20;
    wire [15:0] expected_count = job == 0 ? 12 : job == 3 ? 324 : 54;
    wire cfg_ready, in_ready, out_valid, done, error;
    wire [31:0] out_data, input_beats, output_beats, stall_cycles;
    wire [8:0] out_x, out_y;
    wire [2:0] out_kx, out_ky;
    wire [7:0] out_tile_id;
    wire in_valid = state == S_RUN && source_index < source_count;
    wire out_ready = state == S_RUN &&
                     ready_pattern[2:0] != 3 && ready_pattern[2:0] != 4;
    wire [31:0] in_data = source_rom[source_base + source_index];
    wire output_fire = out_valid && out_ready;
    wire mismatch = output_fire &&
        (out_data !== expected_rom[expected_base + output_index] ||
         out_x != expected_x || out_y != expected_y ||
         out_kx != expected_kx || out_ky != expected_ky ||
         out_tile_id != tile || output_index >= expected_count);

    mac_conv_window #(.MAX_WIDTH(16)) u_window (
        .clk(free_clk), .resetn(resetn), .flush(1'b0),
        .cfg_valid(state == S_CFG), .cfg_ready(cfg_ready),
        .cfg_width(width), .cfg_height(height), .cfg_kernel(kernel),
        .cfg_stride(stride), .cfg_padding(padding), .cfg_tile_id(tile),
        .in_valid(in_valid), .in_ready(in_ready), .in_data(in_data),
        .out_valid(out_valid), .out_ready(out_ready), .out_data(out_data),
        .out_x(out_x), .out_y(out_y), .out_kx(out_kx), .out_ky(out_ky),
        .out_tile_id(out_tile_id), .done(done), .error(error),
        .input_beats(input_beats), .output_beats(output_beats),
        .stall_cycles(stall_cycles)
    );

    reg [6:0] message_index;
    reg [24:0] pause_cycles;
    reg [9:0] tx_shift;
    reg [7:0] tx_div;
    reg [3:0] tx_bits;
    wire tx_busy = tx_bits != 0;
    wire [6:0] message_length = failed ? 7'd19 : 7'd71;
    wire tx_send = state == S_REPORT && !tx_busy &&
                   message_index < message_length;
    assign uart_txd = tx_busy ? tx_shift[0] : 1'b1;

    // Former hex_digit/message_byte functions as one combinational block.
    reg [7:0] tx_data;
    reg [1:0] which;
    reg [4:0] field;
    reg [15:0] cycles, stalls;
    always @* begin
        tx_data = "?";
        if (message_index < 7'd13) begin
            case (message_index)
                 0: tx_data = "W";  1: tx_data = "I";
                 2: tx_data = "N";  3: tx_data = "D";
                 4: tx_data = "O";  5: tx_data = "W";
                 6: tx_data = "_";  7: tx_data = "B";
                 8: tx_data = "O";  9: tx_data = "A";
                10: tx_data = "R"; 11: tx_data = "D";
                12: tx_data = "_";
            endcase
        end else if (message_index < 7'd17) begin
            case (message_index)
                13: tx_data = failed ? "F" : "P";
                14: tx_data = "A";
                15: tx_data = failed ? "I" : "S";
                16: tx_data = failed ? "L" : "S";
            endcase
        end else if (failed) begin
            tx_data = message_index == 7'd17 ? 8'd13 : 8'd10;
        end else if (message_index == 7'd17) begin
            tx_data = " ";
        end else if (message_index == 7'd69) begin
            tx_data = 8'd13;
        end else if (message_index == 7'd70) begin
            tx_data = 8'd10;
        end else begin
            if (message_index < 7'd31) begin
                which = 0; field = message_index - 7'd18;
            end else if (message_index < 7'd44) begin
                which = 1; field = message_index - 7'd31;
            end else if (message_index < 7'd57) begin
                which = 2; field = message_index - 7'd44;
            end else begin
                which = 3; field = message_index - 7'd57;
            end
            cycles = which == 0 ? job_cycles[0] : which == 1 ? job_cycles[1] :
                     which == 2 ? job_cycles[2] : job_cycles[3];
            stalls = which == 0 ? job_stalls[0] : which == 1 ? job_stalls[1] :
                     which == 2 ? job_stalls[2] : job_stalls[3];
            case (field)
                 0: tx_data = "C";
                 1: tx_data = 8'd48 + which;
                 2: tx_data = "=";
                 3: tx_data = cycles[15:12] < 10 ? (8'd48 + cycles[15:12]) :
                               (8'd55 + cycles[15:12]);
                 4: tx_data = cycles[11:8] < 10 ? (8'd48 + cycles[11:8]) :
                               (8'd55 + cycles[11:8]);
                 5: tx_data = cycles[7:4] < 10 ? (8'd48 + cycles[7:4]) :
                               (8'd55 + cycles[7:4]);
                 6: tx_data = cycles[3:0] < 10 ? (8'd48 + cycles[3:0]) :
                               (8'd55 + cycles[3:0]);
                 7: tx_data = "/";
                 8: tx_data = stalls[15:12] < 10 ? (8'd48 + stalls[15:12]) :
                               (8'd55 + stalls[15:12]);
                 9: tx_data = stalls[11:8] < 10 ? (8'd48 + stalls[11:8]) :
                               (8'd55 + stalls[11:8]);
                10: tx_data = stalls[7:4] < 10 ? (8'd48 + stalls[7:4]) :
                               (8'd55 + stalls[7:4]);
                11: tx_data = stalls[3:0] < 10 ? (8'd48 + stalls[3:0]) :
                               (8'd55 + stalls[3:0]);
                12: tx_data = " ";
            endcase
        end
    end



    always @(posedge free_clk) begin
        if (!resetn) begin
            state <= S_CFG;
            job <= 0;
            failed <= 0;
            source_index <= 0;
            output_index <= 0;
            run_cycles <= 0;
            expected_x <= 0; expected_y <= 0;
            expected_kx <= 0; expected_ky <= 0;
            ready_pattern <= 0;
            message_index <= 0;
            pause_cycles <= 0;
            tx_shift <= 10'h3ff;
            tx_div <= 0;
            tx_bits <= 0;
            job_cycles[0] <= 0; job_cycles[1] <= 0;
            job_cycles[2] <= 0; job_cycles[3] <= 0;
            job_stalls[0] <= 0; job_stalls[1] <= 0;
            job_stalls[2] <= 0; job_stalls[3] <= 0;
        end else begin
            if (tx_send) begin
                tx_shift <= {1'b1, tx_data, 1'b0};
                tx_bits <= 10;
                tx_div <= 0;
            end else if (tx_busy) begin
                if (tx_div == 8'd233) begin
                    tx_div <= 0;
                    tx_shift <= {1'b1, tx_shift[9:1]};
                    tx_bits <= tx_bits - 1'b1;
                end else tx_div <= tx_div + 1'b1;
            end

            if (mismatch || error) begin
                failed <= 1;
                message_index <= 0;
                state <= S_REPORT;
            end else case (state)
                S_CFG: if (cfg_ready) begin
                    source_index <= 0;
                    output_index <= 0;
                    run_cycles <= 0;
                    ready_pattern <= 0;
                    expected_x <= 0; expected_y <= 0;
                    expected_kx <= 0; expected_ky <= 0;
                    state <= S_RUN;
                end
                S_RUN: begin
                    run_cycles <= run_cycles + 1'b1;
                    ready_pattern <= ready_pattern + 1'b1;
                    if (in_valid && in_ready)
                        source_index <= source_index + 1'b1;
                    if (output_fire) begin
                        output_index <= output_index + 1'b1;
                        if (expected_kx + 1 < kernel)
                            expected_kx <= expected_kx + 1'b1;
                        else begin
                            expected_kx <= 0;
                            if (expected_ky + 1 < kernel)
                                expected_ky <= expected_ky + 1'b1;
                            else begin
                                expected_ky <= 0;
                                if (expected_x + 1 < output_width)
                                    expected_x <= expected_x + 1'b1;
                                else begin
                                    expected_x <= 0;
                                    expected_y <= expected_y + 1'b1;
                                end
                            end
                        end
                    end
                    if (done) begin
                        if (source_index != source_count ||
                            output_index != expected_count ||
                            input_beats != source_count ||
                            output_beats != expected_count) begin
                            failed <= 1;
                            message_index <= 0;
                            state <= S_REPORT;
                        end else begin
                            job_cycles[job] <= run_cycles;
                            job_stalls[job] <= stall_cycles[15:0];
                            if (job == 3) begin
                                message_index <= 0;
                                state <= S_REPORT;
                            end else begin
                                job <= job + 1'b1;
                                state <= S_CFG;
                            end
                        end
                    end else if (run_cycles == 16'd10000) begin
                        failed <= 1;
                        message_index <= 0;
                        state <= S_REPORT;
                    end
                end
                S_REPORT: if (tx_send) begin
                    message_index <= message_index + 1'b1;
                end else if (message_index == message_length && !tx_busy) begin
                    pause_cycles <= 0;
                    state <= S_PAUSE;
                end
                S_PAUSE: if (pause_cycles == 25'd27000000) begin
                    message_index <= 0;
                    state <= S_REPORT;
                end else pause_cycles <= pause_cycles + 1'b1;
                default: state <= S_CFG;
            endcase
        end
    end
endmodule
