// One NHWC4 channel tile per descriptor. The upstream DMA supplies one
// four-byte pixel word per beat in raster order. Padding taps are zero.
// Output order is (y, x, ky, kx) for the configured channel tile.
module mac_conv_window #(
    parameter MAX_WIDTH = 320
) (
    input wire clk,
    input wire resetn,
    input wire flush,
    input wire cfg_valid,
    output wire cfg_ready,
    input wire [8:0] cfg_width,
    input wire [8:0] cfg_height,
    input wire [2:0] cfg_kernel,
    input wire [1:0] cfg_stride,
    input wire [2:0] cfg_padding,
    input wire [7:0] cfg_tile_id,
    input wire in_valid,
    output wire in_ready,
    input wire [31:0] in_data,
    output wire out_valid,
    input wire out_ready,
    output wire [31:0] out_data,
    output wire [8:0] out_x,
    output wire [8:0] out_y,
    output wire [2:0] out_kx,
    output wire [2:0] out_ky,
    output wire [7:0] out_tile_id,
    output reg done,
    output reg error,
    output reg [31:0] input_beats,
    output reg [31:0] output_beats,
    output reg [31:0] stall_cycles
);
    localparam IDLE = 3'd0, BYPASS = 3'd1, FILL = 3'd2,
               EMIT = 3'd3, DRAIN = 3'd4, DISCARD = 3'd5;
    reg [2:0] state;
    reg [8:0] width_r, height_r, out_width_r, out_height_r;
    reg [2:0] kernel_r, padding_r;
    reg [1:0] stride_r;
    reg [7:0] tile_r;
    reg [8:0] in_x, in_y, emit_x, emit_y;
    reg [2:0] tap_x, tap_y;
    reg [8:0] held_x, held_y;
    reg [2:0] held_kx, held_ky;
    reg [31:0] held_data;
    reg held_valid;
    reg [31:0] line_ram [0:6*MAX_WIDTH-1];

    // Nine-bit row indices need a bounded constant-modulus circuit. PDS
    // cannot map the generic signed remainder operator into this fabric.
    reg [2:0] row_mod6_in_y;
    reg [2:0] even_count_in;
    reg [2:0] odd_count_in;
    reg [4:0] value_in;
    always @* begin
        even_count_in = {2'b0, in_y[2]} + {2'b0, in_y[4]} +
                     {2'b0, in_y[6]} + {2'b0, in_y[8]};
        odd_count_in = {2'b0, in_y[1]} + {2'b0, in_y[3]} +
                    {2'b0, in_y[5]} + {2'b0, in_y[7]};
        value_in = {even_count_in, 2'b0} + {1'b0, odd_count_in, 1'b0} +
                {4'b0, in_y[0]};
        if (value_in >= 5'd24) value_in = value_in - 5'd24;
        if (value_in >= 5'd12) value_in = value_in - 5'd12;
        if (value_in >= 5'd6) value_in = value_in - 5'd6;
        row_mod6_in_y = value_in[2:0];
    end
    reg [2:0] even_count_src;
    reg [2:0] odd_count_src;
    reg [4:0] value_src;
    // The source-row fold is computed inline in the sequential block where
    // it is used: source_y is blocking-assigned there, so a separate
    // always @* could observe a stale value within the same time step (the
    // original function call evaluated immediately).


    wire [10:0] cfg_w_padded = {2'b0, cfg_width} +
                                ({2'b0, cfg_padding} << 1);
    wire [10:0] cfg_h_padded = {2'b0, cfg_height} +
                                ({2'b0, cfg_padding} << 1);
    wire cfg_ok = cfg_width != 0 && cfg_height != 0 &&
                  cfg_width <= MAX_WIDTH && cfg_height <= 320 &&
                  (cfg_kernel == 1 || cfg_kernel == 3 || cfg_kernel == 6) &&
                  (cfg_stride == 1 || cfg_stride == 2) &&
                  cfg_padding < cfg_kernel &&
                  cfg_w_padded >= cfg_kernel && cfg_h_padded >= cfg_kernel &&
                  (cfg_kernel != 1 || cfg_padding == 0);
    wire bypass_selected = ((stride_r == 1) ||
                             (!in_x[0] && !in_y[0]));
    wire input_last = (in_x == width_r - 1 && in_y == height_r - 1);
    wire held_handshake = held_valid && out_ready;
    wire [10:0] last_needed_unclipped = emit_y * stride_r +
                                        kernel_r - 1 - padding_r;
    wire [8:0] last_needed_row = last_needed_unclipped >= height_r ?
                                 height_r - 1 : last_needed_unclipped[8:0];
    // in_y is the next row to finish, so this comparison avoids a
    // width*row multiply on the ready/valid path.
    wire fill_needed = in_y <= last_needed_row;
    // Accepted dimensions are at most 320, with kernels up to six taps.
    // Padded source coordinates stay in -5..324; retain a sign bit without
    // inferring 32-bit arithmetic for each tap.
    reg signed [9:0] source_y;
    reg signed [$clog2(MAX_WIDTH + 8):0] source_x;
    reg [$clog2(6*MAX_WIDTH)-1:0] ram_address;

    assign cfg_ready = resetn && !flush && state == IDLE;
    assign in_ready = resetn && !flush &&
                      (state == BYPASS ?
                       (bypass_selected ? out_ready : 1'b1) :
                       ((state == FILL && fill_needed) || state == DISCARD));
    assign out_valid = resetn && !flush &&
                       (state == BYPASS ?
                        (in_valid && bypass_selected) : held_valid);
    assign out_data = state == BYPASS ? in_data : held_data;
    assign out_x = state == BYPASS ?
                   (stride_r == 1 ? in_x : {1'b0, in_x[8:1]}) : held_x;
    assign out_y = state == BYPASS ?
                   (stride_r == 1 ? in_y : {1'b0, in_y[8:1]}) : held_y;
    assign out_kx = state == BYPASS ? 3'b0 : held_kx;
    assign out_ky = state == BYPASS ? 3'b0 : held_ky;
    assign out_tile_id = tile_r;

    always @(posedge clk) begin
        if (!resetn || flush) begin
            state <= IDLE;
            done <= 0;
            error <= 0;
            held_valid <= 0;
            input_beats <= 0;
            output_beats <= 0;
            stall_cycles <= 0;
            in_x <= 0;
            in_y <= 0;
            emit_x <= 0;
            emit_y <= 0;
            tap_x <= 0;
            tap_y <= 0;
        end else begin
            done <= 0;
            error <= 0;
            if (out_valid && !out_ready)
                stall_cycles <= stall_cycles + 1;
            if (state != BYPASS && held_handshake) begin
                output_beats <= output_beats + 1;
                held_valid <= 0;
            end
            case (state)
                IDLE: if (cfg_valid) begin
                    if (!cfg_ok) begin
                        error <= 1;
                    end else begin
                        width_r <= cfg_width;
                        height_r <= cfg_height;
                        kernel_r <= cfg_kernel;
                        stride_r <= cfg_stride;
                        padding_r <= cfg_padding;
                        tile_r <= cfg_tile_id;
                        out_width_r <= (cfg_stride == 2 ?
                                        ((cfg_w_padded - cfg_kernel) >> 1) :
                                        (cfg_w_padded - cfg_kernel)) + 1;
                        out_height_r <= (cfg_stride == 2 ?
                                         ((cfg_h_padded - cfg_kernel) >> 1) :
                                         (cfg_h_padded - cfg_kernel)) + 1;
                        input_beats <= 0;
                        output_beats <= 0;
                        stall_cycles <= 0;
                        in_x <= 0;
                        in_y <= 0;
                        emit_x <= 0;
                        emit_y <= 0;
                        tap_x <= 0;
                        tap_y <= 0;
                        held_valid <= 0;
                        state <= cfg_kernel == 1 ? BYPASS : FILL;
                    end
                end
                BYPASS: if (in_valid && in_ready) begin
                    input_beats <= input_beats + 1;
                    if (bypass_selected)
                        output_beats <= output_beats + 1;
                    if (input_last) begin
                        state <= IDLE;
                        done <= 1;
                    end else if (in_x == width_r - 1) begin
                        in_x <= 0;
                        in_y <= in_y + 1;
                    end else
                        in_x <= in_x + 1;
                end
                FILL: begin
                    if (!fill_needed)
                        state <= EMIT;
                    else if (in_valid && in_ready) begin
                        line_ram[row_mod6_in_y * MAX_WIDTH + in_x] <= in_data;
                        input_beats <= input_beats + 1;
                        if (in_x == width_r - 1) begin
                            in_x <= 0;
                            in_y <= in_y + 1;
                        end else
                            in_x <= in_x + 1;
                    end
                end
                EMIT: if (!held_valid || out_ready) begin
                    source_y = emit_y * stride_r + tap_y - padding_r;
                    source_x = emit_x * stride_r + tap_x - padding_r;
                    held_data <= 0;
                    if (source_y >= 0 && source_y < height_r &&
                        source_x >= 0 && source_x < width_r) begin
                        even_count_src = {2'b0, source_y[2]} +
                            {2'b0, source_y[4]} + {2'b0, source_y[6]} +
                            {2'b0, source_y[8]};
                        odd_count_src = {2'b0, source_y[1]} +
                            {2'b0, source_y[3]} + {2'b0, source_y[5]} +
                            {2'b0, source_y[7]};
                        value_src = {even_count_src, 2'b0} +
                            {1'b0, odd_count_src, 1'b0} +
                            {4'b0, source_y[0]};
                        if (value_src >= 5'd24) value_src = value_src - 5'd24;
                        if (value_src >= 5'd12) value_src = value_src - 5'd12;
                        if (value_src >= 5'd6) value_src = value_src - 5'd6;
                        ram_address = value_src[2:0] * MAX_WIDTH + source_x;
                        held_data <= line_ram[ram_address];
                    end
                    held_x <= emit_x;
                    held_y <= emit_y;
                    held_kx <= tap_x;
                    held_ky <= tap_y;
                    held_valid <= 1;
                    if (tap_x + 1 < kernel_r)
                        tap_x <= tap_x + 1;
                    else begin
                        tap_x <= 0;
                        if (tap_y + 1 < kernel_r)
                            tap_y <= tap_y + 1;
                        else begin
                            tap_y <= 0;
                            if (emit_x + 1 < out_width_r)
                                emit_x <= emit_x + 1;
                            else begin
                                emit_x <= 0;
                                state <= DRAIN;
                            end
                        end
                    end
                end
                DRAIN: if (held_handshake) begin
                    if (emit_y + 1 < out_height_r) begin
                        emit_y <= emit_y + 1;
                        state <= FILL;
                    end else if (in_y == height_r) begin
                        done <= 1;
                        state <= IDLE;
                    end else
                        state <= DISCARD;
                end
                DISCARD: if (in_valid && in_ready) begin
                    input_beats <= input_beats + 1;
                    if (input_last) begin
                        done <= 1;
                        state <= IDLE;
                    end else if (in_x == width_r - 1) begin
                        in_x <= 0;
                        in_y <= in_y + 1;
                    end else
                        in_x <= in_x + 1;
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
