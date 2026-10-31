`timescale 1ns/1ps

// CH9350L state-2 HID receiver.
//
// The CH9350L is the USB host.  This block only receives its 115200-8-N-1
// UART reports, parses the fixed state-2 keyboard/mouse frames, translates
// ordinary USB boot-keyboard usages to a console byte stream and maintains
// mouse/GUI state.  No USB signalling is implemented in the FPGA.
//
// State-2 frames:
//   keyboard: 57 AB 01 + modifier,reserved,key0..key5
//   mouse:    57 AB 02 + buttons,dx,dy,wheel
module ch9350_hid_core #(
    parameter integer UART_BAUD_DIV = 234,
    parameter integer GUI_PROFILE = 0,
    parameter integer REPEAT_DELAY_CYCLES = 13_500_000,
    parameter integer REPEAT_PERIOD_CYCLES = 1_080_000
)(
    input  wire        clk,
    input  wire        resetn,
    input  wire        ch9350_uart_rx,
    output wire        ch9350_uart_tx,

    output wire        key_valid,
    output wire [7:0]  key_data,
    input  wire        key_ready,

    output reg  [10:0] mouse_x,
    output reg  [9:0]  mouse_y,
    output reg  [2:0]  mouse_buttons,
    output reg  [7:0]  mouse_last_dx,
    output reg  [7:0]  mouse_last_dy,
    output reg  [7:0]  mouse_last_wheel,
    output reg  [7:0]  keyboard_modifier,
    output reg  [7:0]  keyboard_last_usage,
    output reg  [7:0]  keyboard_last_ascii,
    output reg         caps_lock,
    output reg         keyboard_seen,
    output reg         mouse_seen,
    output reg  [31:0] keyboard_frame_count,
    output reg  [31:0] mouse_frame_count,
    output reg  [15:0] mouse_left_press_count,
    output reg  [15:0] mouse_right_press_count,
    output reg  [31:0] parse_error_count,
    output reg  [31:0] dropped_key_count,

    output reg         gui_help,
    output reg         gui_stats,
    output reg         gui_speed_2x,
    output reg         gui_cursor_alt,
    output reg         gui_term_focus,
    output reg         state_toggle
);
    // CH9350 state 2 does not require polling commands.  Keep the return UART
    // in its safe idle state; the pin is still routed for future LED/control
    // commands and for a complete four-wire module connection.
    assign ch9350_uart_tx = 1'b1;

    // ------------------------------------------------------------------
    // UART receive
    // ------------------------------------------------------------------
    localparam [1:0] RX_IDLE  = 2'd0;
    localparam [1:0] RX_START = 2'd1;
    localparam [1:0] RX_DATA  = 2'd2;
    localparam [1:0] RX_STOP  = 2'd3;

    reg rx_meta, rx_sync;
    reg [1:0] rx_state;
    reg [15:0] rx_baud_count;
    reg [2:0] rx_bit_index;
    reg [7:0] rx_shift;
    reg [7:0] rx_byte;
    reg rx_byte_strobe;
    reg rx_frame_error;

    always @(posedge clk) begin
        if (!resetn) begin
            rx_meta        <= 1'b1;
            rx_sync        <= 1'b1;
            rx_state       <= RX_IDLE;
            rx_baud_count  <= 16'd0;
            rx_bit_index   <= 3'd0;
            rx_shift       <= 8'd0;
            rx_byte        <= 8'd0;
            rx_byte_strobe <= 1'b0;
            rx_frame_error <= 1'b0;
        end else begin
            rx_meta        <= ch9350_uart_rx;
            rx_sync        <= rx_meta;
            rx_byte_strobe <= 1'b0;
            rx_frame_error <= 1'b0;

            case (rx_state)
                RX_IDLE: begin
                    if (!rx_sync) begin
                        rx_baud_count <= UART_BAUD_DIV / 2;
                        rx_state      <= RX_START;
                    end
                end

                RX_START: begin
                    if (rx_baud_count != 16'd0) begin
                        rx_baud_count <= rx_baud_count - 16'd1;
                    end else if (!rx_sync) begin
                        rx_baud_count <= UART_BAUD_DIV - 1;
                        rx_bit_index  <= 3'd0;
                        rx_state      <= RX_DATA;
                    end else begin
                        rx_state <= RX_IDLE;
                    end
                end

                RX_DATA: begin
                    if (rx_baud_count != 16'd0) begin
                        rx_baud_count <= rx_baud_count - 16'd1;
                    end else begin
                        rx_shift[rx_bit_index] <= rx_sync;
                        rx_baud_count <= UART_BAUD_DIV - 1;
                        if (rx_bit_index == 3'd7) begin
                            rx_state <= RX_STOP;
                        end else begin
                            rx_bit_index <= rx_bit_index + 3'd1;
                        end
                    end
                end

                default: begin // RX_STOP
                    if (rx_baud_count != 16'd0) begin
                        rx_baud_count <= rx_baud_count - 16'd1;
                    end else begin
                        if (rx_sync) begin
                            rx_byte        <= rx_shift;
                            rx_byte_strobe <= 1'b1;
                        end else begin
                            rx_frame_error <= 1'b1;
                        end
                        rx_state <= RX_IDLE;
                    end
                end
            endcase
        end
    end

    // ------------------------------------------------------------------
    // State-2 frame parser with byte-boundary resynchronisation
    // ------------------------------------------------------------------
    localparam [2:0] PARSE_57    = 3'd0;
    localparam [2:0] PARSE_AB    = 3'd1;
    localparam [2:0] PARSE_TYPE  = 3'd2;
    localparam [2:0] PARSE_KBD   = 3'd3;
    localparam [2:0] PARSE_MOUSE = 3'd4;
    localparam integer FRAME_TIMEOUT_CYCLES = UART_BAUD_DIV * 20;

    reg [2:0] parser_state;
    reg [3:0] payload_index;
    reg [15:0] frame_timeout;
    reg parser_error_pulse;
    reg keyboard_report_pulse;
    reg mouse_report_pulse;

    reg [7:0] report_modifier;
    reg [7:0] report_reserved;
    reg [7:0] report_key0, report_key1, report_key2;
    reg [7:0] report_key3, report_key4, report_key5;
    reg [7:0] report_mouse_buttons;
    reg [7:0] report_mouse_dx, report_mouse_dy, report_mouse_wheel;

    always @(posedge clk) begin
        if (!resetn) begin
            parser_state          <= PARSE_57;
            payload_index         <= 4'd0;
            frame_timeout         <= 16'd0;
            parser_error_pulse    <= 1'b0;
            keyboard_report_pulse <= 1'b0;
            mouse_report_pulse    <= 1'b0;
            report_modifier       <= 8'd0;
            report_reserved       <= 8'd0;
            report_key0           <= 8'd0;
            report_key1           <= 8'd0;
            report_key2           <= 8'd0;
            report_key3           <= 8'd0;
            report_key4           <= 8'd0;
            report_key5           <= 8'd0;
            report_mouse_buttons  <= 8'd0;
            report_mouse_dx       <= 8'd0;
            report_mouse_dy       <= 8'd0;
            report_mouse_wheel    <= 8'd0;
        end else begin
            parser_error_pulse    <= 1'b0;
            keyboard_report_pulse <= 1'b0;
            mouse_report_pulse    <= 1'b0;

            if (rx_frame_error) begin
                parser_state       <= PARSE_57;
                payload_index      <= 4'd0;
                frame_timeout      <= 16'd0;
                parser_error_pulse <= 1'b1;
            end else begin
                if (parser_state != PARSE_57) begin
                    if (rx_byte_strobe) begin
                        frame_timeout <= FRAME_TIMEOUT_CYCLES;
                    end else if (frame_timeout != 16'd0) begin
                        frame_timeout <= frame_timeout - 16'd1;
                    end else begin
                        parser_state       <= PARSE_57;
                        payload_index      <= 4'd0;
                        parser_error_pulse <= 1'b1;
                    end
                end else begin
                    frame_timeout <= 16'd0;
                end

                if (rx_byte_strobe) begin
                    case (parser_state)
                        PARSE_57: begin
                            if (rx_byte == 8'h57) begin
                                parser_state  <= PARSE_AB;
                                frame_timeout <= FRAME_TIMEOUT_CYCLES;
                            end
                        end

                        PARSE_AB: begin
                            if (rx_byte == 8'hab) begin
                                parser_state <= PARSE_TYPE;
                            end else if (rx_byte != 8'h57) begin
                                parser_state       <= PARSE_57;
                                parser_error_pulse <= 1'b1;
                            end
                        end

                        PARSE_TYPE: begin
                            payload_index <= 4'd0;
                            if (rx_byte == 8'h01) begin
                                parser_state <= PARSE_KBD;
                            end else if (rx_byte == 8'h02) begin
                                parser_state <= PARSE_MOUSE;
                            end else if (rx_byte == 8'h57) begin
                                parser_state <= PARSE_AB;
                                parser_error_pulse <= 1'b1;
                            end else begin
                                parser_state <= PARSE_57;
                                parser_error_pulse <= 1'b1;
                            end
                        end

                        PARSE_KBD: begin
                            case (payload_index)
                                4'd0: report_modifier <= rx_byte;
                                4'd1: report_reserved <= rx_byte;
                                4'd2: report_key0 <= rx_byte;
                                4'd3: report_key1 <= rx_byte;
                                4'd4: report_key2 <= rx_byte;
                                4'd5: report_key3 <= rx_byte;
                                4'd6: report_key4 <= rx_byte;
                                default: report_key5 <= rx_byte;
                            endcase
                            if (payload_index == 4'd7) begin
                                keyboard_report_pulse <= 1'b1;
                                parser_state <= PARSE_57;
                                payload_index <= 4'd0;
                                frame_timeout <= 16'd0;
                            end else begin
                                payload_index <= payload_index + 4'd1;
                            end
                        end

                        default: begin // PARSE_MOUSE
                            case (payload_index)
                                4'd0: report_mouse_buttons <= rx_byte;
                                4'd1: report_mouse_dx <= rx_byte;
                                4'd2: report_mouse_dy <= rx_byte;
                                default: report_mouse_wheel <= rx_byte;
                            endcase
                            if (payload_index == 4'd3) begin
                                mouse_report_pulse <= 1'b1;
                                parser_state <= PARSE_57;
                                payload_index <= 4'd0;
                                frame_timeout <= 16'd0;
                            end else begin
                                payload_index <= payload_index + 4'd1;
                            end
                        end
                    endcase
                end
            end
        end
    end

    // ------------------------------------------------------------------
    // New-key detection and US-ANSI translation
    // ------------------------------------------------------------------
    reg [7:0] prev_key0, prev_key1, prev_key2;
    reg [7:0] prev_key3, prev_key4, prev_key5;

    wire report_rollover = (report_key0 == 8'h01) ||
                           (report_key1 == 8'h01) ||
                           (report_key2 == 8'h01) ||
                           (report_key3 == 8'h01) ||
                           (report_key4 == 8'h01) ||
                           (report_key5 == 8'h01);

    wire key0_new = (report_key0 != 8'd0) &&
                    (report_key0 != prev_key0) && (report_key0 != prev_key1) &&
                    (report_key0 != prev_key2) && (report_key0 != prev_key3) &&
                    (report_key0 != prev_key4) && (report_key0 != prev_key5);
    wire key1_new = (report_key1 != 8'd0) &&
                    (report_key1 != prev_key0) && (report_key1 != prev_key1) &&
                    (report_key1 != prev_key2) && (report_key1 != prev_key3) &&
                    (report_key1 != prev_key4) && (report_key1 != prev_key5);
    wire key2_new = (report_key2 != 8'd0) &&
                    (report_key2 != prev_key0) && (report_key2 != prev_key1) &&
                    (report_key2 != prev_key2) && (report_key2 != prev_key3) &&
                    (report_key2 != prev_key4) && (report_key2 != prev_key5);
    wire key3_new = (report_key3 != 8'd0) &&
                    (report_key3 != prev_key0) && (report_key3 != prev_key1) &&
                    (report_key3 != prev_key2) && (report_key3 != prev_key3) &&
                    (report_key3 != prev_key4) && (report_key3 != prev_key5);
    wire key4_new = (report_key4 != 8'd0) &&
                    (report_key4 != prev_key0) && (report_key4 != prev_key1) &&
                    (report_key4 != prev_key2) && (report_key4 != prev_key3) &&
                    (report_key4 != prev_key4) && (report_key4 != prev_key5);
    wire key5_new = (report_key5 != 8'd0) &&
                    (report_key5 != prev_key0) && (report_key5 != prev_key1) &&
                    (report_key5 != prev_key2) && (report_key5 != prev_key3) &&
                    (report_key5 != prev_key4) && (report_key5 != prev_key5);

    wire [7:0] new_usage = report_rollover ? 8'd0 :
                           key0_new ? report_key0 :
                           key1_new ? report_key1 :
                           key2_new ? report_key2 :
                           key3_new ? report_key3 :
                           key4_new ? report_key4 :
                           key5_new ? report_key5 : 8'd0;

    reg [7:0] repeat_usage;
    wire repeat_usage_down = (repeat_usage != 8'd0) &&
                             ((repeat_usage == report_key0) ||
                              (repeat_usage == report_key1) ||
                              (repeat_usage == report_key2) ||
                              (repeat_usage == report_key3) ||
                              (repeat_usage == report_key4) ||
                              (repeat_usage == report_key5));
    wire shift_active = report_modifier[1] || report_modifier[5];
    wire ctrl_active  = report_modifier[0] || report_modifier[4];
    wire alt_active   = report_modifier[2] || report_modifier[6];

    reg [2:0] map_len;
    reg [7:0] map0, map1, map2, map3, map4;
    reg [7:0] map_last_ascii;
    reg map_repeatable;

    always @* begin
        map_len = 3'd0;
        map0 = 8'd0;
        map1 = 8'd0;
        map2 = 8'd0;
        map3 = 8'd0;
        map4 = 8'd0;
        map_last_ascii = 8'd0;
        map_repeatable = 1'b0;

        if ((new_usage >= 8'h04) && (new_usage <= 8'h1d)) begin
            map_len = 3'd1;
            map_repeatable = 1'b1;
            if (ctrl_active) begin
                map0 = new_usage - 8'h03;
            end else if (shift_active ^ caps_lock) begin
                map0 = 8'h41 + (new_usage - 8'h04);
            end else begin
                map0 = 8'h61 + (new_usage - 8'h04);
            end
        end else begin
            case (new_usage)
                8'h1e: begin map_len=1; map0=shift_active ? "!" : "1"; map_repeatable=1; end
                8'h1f: begin map_len=1; map0=shift_active ? "@" : "2"; map_repeatable=1; end
                8'h20: begin map_len=1; map0=shift_active ? "#" : "3"; map_repeatable=1; end
                8'h21: begin map_len=1; map0=shift_active ? "$" : "4"; map_repeatable=1; end
                8'h22: begin map_len=1; map0=shift_active ? "%" : "5"; map_repeatable=1; end
                8'h23: begin map_len=1; map0=shift_active ? "^" : "6"; map_repeatable=1; end
                8'h24: begin map_len=1; map0=shift_active ? "&" : "7"; map_repeatable=1; end
                8'h25: begin map_len=1; map0=shift_active ? "*" : "8"; map_repeatable=1; end
                8'h26: begin map_len=1; map0=shift_active ? "(" : "9"; map_repeatable=1; end
                8'h27: begin map_len=1; map0=shift_active ? ")" : "0"; map_repeatable=1; end
                8'h28: begin map_len=1; map0=8'h0d; end
                8'h29: begin map_len=1; map0=8'h1b; end
                8'h2a: begin map_len=1; map0=8'h7f; map_repeatable=1; end
                8'h2b: begin map_len=1; map0=8'h09; end
                8'h2c: begin map_len=1; map0=8'h20; map_repeatable=1; end
                8'h2d: begin map_len=1; map0=shift_active ? "_" : "-"; map_repeatable=1; end
                8'h2e: begin map_len=1; map0=shift_active ? "+" : "="; map_repeatable=1; end
                8'h2f: begin map_len=1; map0=shift_active ? "{" : "["; map_repeatable=1; end
                8'h30: begin map_len=1; map0=shift_active ? "}" : "]"; map_repeatable=1; end
                8'h31: begin map_len=1; map0=shift_active ? "|" : 8'h5c; map_repeatable=1; end
                8'h33: begin map_len=1; map0=shift_active ? ":" : ";"; map_repeatable=1; end
                8'h34: begin map_len=1; map0=shift_active ? 8'h22 : 8'h27; map_repeatable=1; end
                8'h35: begin map_len=1; map0=shift_active ? "~" : "`"; map_repeatable=1; end
                8'h36: begin map_len=1; map0=shift_active ? "<" : ","; map_repeatable=1; end
                8'h37: begin map_len=1; map0=shift_active ? ">" : "."; map_repeatable=1; end
                8'h38: begin map_len=1; map0=shift_active ? "?" : "/"; map_repeatable=1; end
                8'h49: begin map_len=4; map0=8'h1b; map1="["; map2="3"; map3="~"; map_repeatable=1; end
                8'h4a: begin map_len=3; map0=8'h1b; map1="["; map2="H"; map_repeatable=1; end
                8'h4d: begin map_len=3; map0=8'h1b; map1="["; map2="F"; map_repeatable=1; end
                8'h4f: begin map_len=3; map0=8'h1b; map1="["; map2="C"; map_repeatable=1; end
                8'h50: begin map_len=3; map0=8'h1b; map1="["; map2="D"; map_repeatable=1; end
                8'h51: begin map_len=3; map0=8'h1b; map1="["; map2="B"; map_repeatable=1; end
                8'h52: begin map_len=3; map0=8'h1b; map1="["; map2="A"; map_repeatable=1; end
                default: begin map_len=0; map_repeatable=0; end
            endcase
        end

        map_last_ascii = map0;
        if (alt_active && (map_len != 0) && (map_len < 5)) begin
            map4 = map3;
            map3 = map2;
            map2 = map1;
            map1 = map0;
            map0 = 8'h1b;
            map_len = map_len + 1'b1;
        end
    end

    // ------------------------------------------------------------------
    // Mouse coordinate arithmetic (signed delta, saturating screen bounds)
    // ------------------------------------------------------------------
    reg signed [12:0] mouse_x_sum;
    reg signed [11:0] mouse_y_sum;
    reg [10:0] mouse_x_next;
    reg [9:0] mouse_y_next;
    always @* begin
        if (gui_speed_2x) begin
            mouse_x_sum = $signed({1'b0, mouse_x}) +
                          ($signed({{5{report_mouse_dx[7]}}, report_mouse_dx}) <<< 1);
            mouse_y_sum = $signed({1'b0, mouse_y}) +
                          ($signed({{4{report_mouse_dy[7]}}, report_mouse_dy}) <<< 1);
        end else begin
            mouse_x_sum = $signed({1'b0, mouse_x}) +
                          $signed({{5{report_mouse_dx[7]}}, report_mouse_dx});
            mouse_y_sum = $signed({1'b0, mouse_y}) +
                          $signed({{4{report_mouse_dy[7]}}, report_mouse_dy});
        end

        if (mouse_x_sum < 0)
            mouse_x_next = 11'd0;
        else if (mouse_x_sum > 13'sd1279)
            mouse_x_next = 11'd1279;
        else
            mouse_x_next = mouse_x_sum[10:0];

        if (mouse_y_sum < 0)
            mouse_y_next = 10'd0;
        else if (mouse_y_sum > 12'sd719)
            mouse_y_next = 10'd719;
        else
            mouse_y_next = mouse_y_sum[9:0];
    end

    // ------------------------------------------------------------------
    // Console-byte queue and state/control updates
    // ------------------------------------------------------------------
    reg [25:0] repeat_countdown;
    reg [2:0] repeat_len;
    reg [7:0] repeat0, repeat1, repeat2, repeat3, repeat4;
    reg clear_pending;

    reg seq_active;
    reg [2:0] seq_len;
    reg [2:0] seq_index;
    reg [7:0] seq0, seq1, seq2, seq3, seq4;
    reg [7:0] fifo_push_data;
    wire fifo_push_ready;
    wire fifo_push_valid = seq_active;

    always @* begin
        case (seq_index)
            3'd0: fifo_push_data = seq0;
            3'd1: fifo_push_data = seq1;
            3'd2: fifo_push_data = seq2;
            3'd3: fifo_push_data = seq3;
            default: fifo_push_data = seq4;
        endcase
    end

    wire fifo_overflow;
    ch9350_byte_fifo #(
        .DEPTH(32),
        .PTR_W(5)
    ) u_key_fifo (
        .clk         (clk),
        .resetn      (resetn),
        .push_valid  (fifo_push_valid),
        .push_data   (fifo_push_data),
        .push_ready  (fifo_push_ready),
        .pop_ready   (key_ready),
        .pop_valid   (key_valid),
        .pop_data    (key_data),
        .overflow    (fifo_overflow)
    );

    always @(posedge clk) begin
        if (!resetn) begin
            prev_key0 <= 0; prev_key1 <= 0; prev_key2 <= 0;
            prev_key3 <= 0; prev_key4 <= 0; prev_key5 <= 0;
            mouse_x <= 11'd640;
            mouse_y <= 10'd360;
            mouse_buttons <= 3'd0;
            mouse_last_dx <= 0; mouse_last_dy <= 0; mouse_last_wheel <= 0;
            keyboard_modifier <= 0;
            keyboard_last_usage <= 0;
            keyboard_last_ascii <= 0;
            caps_lock <= 0;
            keyboard_seen <= 0;
            mouse_seen <= 0;
            keyboard_frame_count <= 0;
            mouse_frame_count <= 0;
            mouse_left_press_count <= 0;
            mouse_right_press_count <= 0;
            parse_error_count <= 0;
            dropped_key_count <= 0;
            gui_help <= 0;
            gui_stats <= 0;
            gui_speed_2x <= 0;
            gui_cursor_alt <= 0;
            gui_term_focus <= 1;
            state_toggle <= 0;
            repeat_usage <= 0;
            repeat_countdown <= 0;
            repeat_len <= 0;
            repeat0 <= 0; repeat1 <= 0; repeat2 <= 0; repeat3 <= 0; repeat4 <= 0;
            clear_pending <= 0;
            seq_active <= 0;
            seq_len <= 0;
            seq_index <= 0;
            seq0 <= 0; seq1 <= 0; seq2 <= 0; seq3 <= 0; seq4 <= 0;
        end else begin
            if (parser_error_pulse || fifo_overflow)
                parse_error_count <= parse_error_count + 1'b1;

            if (seq_active && fifo_push_ready) begin
                if (seq_index + 1'b1 >= seq_len) begin
                    seq_active <= 1'b0;
                    seq_index <= 3'd0;
                end else begin
                    seq_index <= seq_index + 1'b1;
                end
            end

            if (keyboard_report_pulse) begin
                keyboard_seen <= 1'b1;
                keyboard_frame_count <= keyboard_frame_count + 1'b1;
                keyboard_modifier <= report_modifier;
                state_toggle <= ~state_toggle;

                if (!report_rollover) begin
                    prev_key0 <= report_key0;
                    prev_key1 <= report_key1;
                    prev_key2 <= report_key2;
                    prev_key3 <= report_key3;
                    prev_key4 <= report_key4;
                    prev_key5 <= report_key5;
                end

                if (!repeat_usage_down) begin
                    repeat_usage <= 8'd0;
                    repeat_countdown <= 0;
                end

                if (new_usage != 8'd0) begin
                    keyboard_last_usage <= new_usage;
                    keyboard_last_ascii <= map_last_ascii;

                    if (new_usage == 8'h39) begin
                        caps_lock <= ~caps_lock;
                        repeat_usage <= 8'd0;
                    end else if (new_usage == 8'h3a) begin
                        gui_help <= ~gui_help;
                        repeat_usage <= 8'd0;
                    end else begin
                        if (new_usage == 8'h29)
                            gui_help <= 1'b0;
                        if (map_repeatable) begin
                            repeat_usage <= new_usage;
                            repeat_countdown <= REPEAT_DELAY_CYCLES;
                            repeat_len <= map_len;
                            repeat0 <= map0; repeat1 <= map1; repeat2 <= map2;
                            repeat3 <= map3; repeat4 <= map4;
                        end else begin
                            repeat_usage <= 8'd0;
                            repeat_countdown <= 0;
                        end
                    end

                    if ((map_len != 0) && !seq_active && (new_usage != 8'h39) &&
                        (new_usage != 8'h3a)) begin
                        seq_active <= 1'b1;
                        seq_len <= map_len;
                        seq_index <= 0;
                        seq0 <= map0; seq1 <= map1; seq2 <= map2;
                        seq3 <= map3; seq4 <= map4;
                    end else if ((map_len != 0) && seq_active) begin
                        dropped_key_count <= dropped_key_count + 1'b1;
                    end
                end
            end else if (repeat_usage != 8'd0) begin
                if (!repeat_usage_down) begin
                    repeat_usage <= 8'd0;
                    repeat_countdown <= 0;
                end else if (repeat_countdown != 0) begin
                    repeat_countdown <= repeat_countdown - 1'b1;
                end else if (!seq_active) begin
                    seq_active <= 1'b1;
                    seq_len <= repeat_len;
                    seq_index <= 0;
                    seq0 <= repeat0; seq1 <= repeat1; seq2 <= repeat2;
                    seq3 <= repeat3; seq4 <= repeat4;
                    repeat_countdown <= REPEAT_PERIOD_CYCLES;
                end
            end

            if (mouse_report_pulse) begin
                mouse_seen <= 1'b1;
                mouse_frame_count <= mouse_frame_count + 1'b1;
                if (report_mouse_buttons[0] && !mouse_buttons[0])
                    mouse_left_press_count <= mouse_left_press_count + 1'b1;
                if (report_mouse_buttons[1] && !mouse_buttons[1])
                    mouse_right_press_count <= mouse_right_press_count + 1'b1;
                mouse_x <= mouse_x_next;
                mouse_y <= mouse_y_next;
                mouse_buttons <= report_mouse_buttons[2:0];
                mouse_last_dx <= report_mouse_dx;
                mouse_last_dy <= report_mouse_dy;
                mouse_last_wheel <= report_mouse_wheel;
                state_toggle <= ~state_toggle;

                // The clickable toolbar exists only in the CoreMark GUI.
                // Linux has no hidden click targets after its blue toolbar
                // was removed.
                if ((GUI_PROFILE == 0) && report_mouse_buttons[0] &&
                    !mouse_buttons[0] && (mouse_y_next < 10'd32)) begin
                        if ((mouse_x_next >= 11'd720) && (mouse_x_next <= 11'd815))
                            gui_help <= ~gui_help;
                        else if ((mouse_x_next >= 11'd832) && (mouse_x_next <= 11'd943))
                            gui_stats <= ~gui_stats;
                        else if ((mouse_x_next >= 11'd960) && (mouse_x_next <= 11'd1071))
                            gui_speed_2x <= ~gui_speed_2x;
                        else if ((mouse_x_next >= 11'd1088) && (mouse_x_next <= 11'd1231))
                            gui_cursor_alt <= ~gui_cursor_alt;
                end
            end

            if (clear_pending && !seq_active && !keyboard_report_pulse) begin
                seq_active <= 1'b1;
                seq_len <= 3'd1;
                seq_index <= 0;
                seq0 <= 8'h0c; // Ctrl-L; BusyBox ash owns the terminal clear.
                seq1 <= 0; seq2 <= 0; seq3 <= 0; seq4 <= 0;
                clear_pending <= 1'b0;
            end
        end
    end
endmodule

// Small ready/valid byte FIFO used between HID translation and the existing
// LiteUART receive register.  The consumer gives the physical UART priority;
// this FIFO simply holds its byte until selected.
module ch9350_byte_fifo #(
    parameter integer DEPTH = 32,
    parameter integer PTR_W = 5
)(
    input  wire       clk,
    input  wire       resetn,
    input  wire       push_valid,
    input  wire [7:0] push_data,
    output wire       push_ready,
    input  wire       pop_ready,
    output wire       pop_valid,
    output wire [7:0] pop_data,
    output reg        overflow
);
    reg [7:0] mem [0:DEPTH-1];
    reg [PTR_W-1:0] wr_ptr, rd_ptr;
    reg [PTR_W:0] count;
    wire do_push = push_valid && push_ready;
    wire do_pop = pop_ready && pop_valid;

    assign push_ready = count < DEPTH;
    assign pop_valid = count != 0;
    assign pop_data = mem[rd_ptr];

    always @(posedge clk) begin
        if (!resetn) begin
            wr_ptr <= 0;
            rd_ptr <= 0;
            count <= 0;
            overflow <= 0;
        end else begin
            overflow <= push_valid && !push_ready;
            if (do_push) begin
                mem[wr_ptr] <= push_data;
                wr_ptr <= wr_ptr + 1'b1;
            end
            if (do_pop)
                rd_ptr <= rd_ptr + 1'b1;
            case ({do_push, do_pop})
                2'b10: count <= count + 1'b1;
                2'b01: count <= count - 1'b1;
                default: count <= count;
            endcase
        end
    end
endmodule
