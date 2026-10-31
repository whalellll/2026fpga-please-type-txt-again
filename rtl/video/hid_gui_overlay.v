`timescale 1ns/1ps

// Pixel-domain CH9350 status bar, lightweight GUI and mouse pointer.
// The input stream is an already-rendered 1280x720 RGB stream.  Active-area
// coordinates are reconstructed from DE so the block can be shared by the
// CoreMark and Linux video pipelines without changing their text memories.
module hid_gui_overlay #(
    parameter integer LINUX_PROFILE = 0
)(
    input  wire        pix_clk,
    input  wire        resetn,
    input  wire        hs_in,
    input  wire        vs_in,
    input  wire        de_in,
    input  wire [7:0]  r_in,
    input  wire [7:0]  g_in,
    input  wire [7:0]  b_in,

    input  wire [10:0] mouse_x,
    input  wire [10:0]  mouse_y,
    input  wire [2:0]  mouse_buttons,
    input  wire [7:0]  mouse_wheel,
    input  wire [7:0]  last_usage,
    input  wire         keyboard_seen,
    input  wire         mouse_seen,
    input  wire [31:0] keyboard_count,
    input  wire [31:0] mouse_count,
    input  wire [31:0] error_count,
    input  wire         gui_help,
    input  wire         gui_stats,
    input  wire         gui_speed_2x,
    input  wire         gui_cursor_alt,
    input  wire         gui_term_focus,

    output reg         hs_out,
    output reg         vs_out,
    output reg         de_out,
    output reg  [7:0]  r_out,
    output reg  [7:0]  g_out,
    output reg  [7:0]  b_out
);
    reg de_prev;
    reg frame_active;
    reg [10:0] active_x;
    reg [10:0] active_y;
    wire line_start = de_in && !de_prev;
    wire [10:0] pixel_x = line_start ? 11'd0 : active_x;
    wire [10:0] pixel_y = line_start ?
                         (frame_active ? active_y + 1'b1 : 11'd0) : active_y;

    always @(posedge pix_clk) begin
        if (!resetn || vs_in) begin
            de_prev <= 1'b0;
            frame_active <= 1'b0;
            active_x <= 11'd0;
            active_y <= 11'd0;
        end else begin
            de_prev <= de_in;
            if (line_start) begin
                active_x <= 11'd1;
                if (frame_active)
                    active_y <= active_y + 1'b1;
                else begin
                    active_y <= 11'd0;
                    frame_active <= 1'b1;
                end
            end else if (de_in) begin
                active_x <= active_x + 1'b1;
            end
        end
    end

    wire [6:0] gui_col = pixel_x[10:4];
    wire [5:0] gui_row = pixel_y[10:5];
    wire [3:0] gui_font_row = pixel_y[4:1];
    wire [2:0] gui_font_x = pixel_x[3:1];

    wire [7:0] x2_ascii, x1_ascii, x0_ascii;
    wire [7:0] y2_ascii, y1_ascii, y0_ascii;
    wire [7:0] usage1_ascii, usage0_ascii, button_ascii;
    wire [7:0] wheel1_ascii, wheel0_ascii;
    wire [7:0] kbdcnt1_ascii, kbdcnt0_ascii;
    wire [7:0] mousecnt1_ascii, mousecnt0_ascii;
    wire [7:0] errcnt1_ascii, errcnt0_ascii;

    hid_hex_ascii u_x2(.nibble({1'b0, mouse_x[10:8]}), .ascii(x2_ascii));
    hid_hex_ascii u_x1(.nibble(mouse_x[7:4]), .ascii(x1_ascii));
    hid_hex_ascii u_x0(.nibble(mouse_x[3:0]), .ascii(x0_ascii));
    hid_hex_ascii u_y2(.nibble({1'b0, mouse_y[10:8]}), .ascii(y2_ascii));
    hid_hex_ascii u_y1(.nibble(mouse_y[7:4]), .ascii(y1_ascii));
    hid_hex_ascii u_y0(.nibble(mouse_y[3:0]), .ascii(y0_ascii));
    hid_hex_ascii u_u1(.nibble(last_usage[7:4]), .ascii(usage1_ascii));
    hid_hex_ascii u_u0(.nibble(last_usage[3:0]), .ascii(usage0_ascii));
    hid_hex_ascii u_bt(.nibble({1'b0, mouse_buttons}), .ascii(button_ascii));
    hid_hex_ascii u_w1(.nibble(mouse_wheel[7:4]), .ascii(wheel1_ascii));
    hid_hex_ascii u_w0(.nibble(mouse_wheel[3:0]), .ascii(wheel0_ascii));
    hid_hex_ascii u_kc1(.nibble(keyboard_count[7:4]), .ascii(kbdcnt1_ascii));
    hid_hex_ascii u_kc0(.nibble(keyboard_count[3:0]), .ascii(kbdcnt0_ascii));
    hid_hex_ascii u_mc1(.nibble(mouse_count[7:4]), .ascii(mousecnt1_ascii));
    hid_hex_ascii u_mc0(.nibble(mouse_count[3:0]), .ascii(mousecnt0_ascii));
    hid_hex_ascii u_ec1(.nibble(error_count[7:4]), .ascii(errcnt1_ascii));
    hid_hex_ascii u_ec0(.nibble(error_count[3:0]), .ascii(errcnt0_ascii));

    reg [7:0] gui_char;
    reg gui_region;
    reg gui_button;
    reg gui_button_hover;
    reg [7:0] gui_bg_r, gui_bg_g, gui_bg_b;

    always @* begin
        gui_char = 8'h20;
        gui_region = 1'b0;
        gui_button = 1'b0;
        gui_button_hover = 1'b0;
        gui_bg_r = 8'h10;
        gui_bg_g = 8'h1b;
        gui_bg_b = 8'h38;

        // The two-row status/toolbar belongs only to the CoreMark profile.
        // Linux passes the complete 1280x64 title area through, removing the
        // former blue HELP/STATS/SPEED/CURSOR information box.
        if ((LINUX_PROFILE == 0) && de_in && (pixel_y < 11'd64)) begin
            gui_region = 1'b1;
            if (gui_row == 0) begin
                if (LINUX_PROFILE == 0) begin
                    case (gui_col)
                        0:gui_char="C"; 1:gui_char="H"; 2:gui_char="9";
                        3:gui_char="3"; 4:gui_char="5"; 5:gui_char="0";
                        7:gui_char="H"; 8:gui_char="I"; 9:gui_char="D";
                        46:gui_char="H"; 47:gui_char="E"; 48:gui_char="L"; 49:gui_char="P";
                        53:gui_char="S"; 54:gui_char="T"; 55:gui_char="A";
                        56:gui_char="T"; 57:gui_char="S";
                        61:gui_char="S"; 62:gui_char="P"; 63:gui_char="E";
                        64:gui_char="E"; 65:gui_char="D";
                        69:gui_char="C"; 70:gui_char="U"; 71:gui_char="R";
                        72:gui_char="S"; 73:gui_char="O"; 74:gui_char="R";
                        default: gui_char=8'h20;
                    endcase
                    if ((pixel_x>=720 && pixel_x<=815) ||
                        (pixel_x>=832 && pixel_x<=943) ||
                        (pixel_x>=960 && pixel_x<=1071) ||
                        (pixel_x>=1088 && pixel_x<=1231)) begin
                        gui_button = 1'b1;
                        gui_button_hover = (mouse_y < 32) &&
                            (((mouse_x>=720)&&(mouse_x<=815)&&(pixel_x>=720)&&(pixel_x<=815)) ||
                             ((mouse_x>=832)&&(mouse_x<=943)&&(pixel_x>=832)&&(pixel_x<=943)) ||
                             ((mouse_x>=960)&&(mouse_x<=1071)&&(pixel_x>=960)&&(pixel_x<=1071)) ||
                             ((mouse_x>=1088)&&(mouse_x<=1231)&&(pixel_x>=1088)&&(pixel_x<=1231)));
                    end
                end else begin
                    case (gui_col)
                        25:gui_char="T"; 26:gui_char="E"; 27:gui_char="R"; 28:gui_char="M";
                        32:gui_char="C"; 33:gui_char="L"; 34:gui_char="E";
                        35:gui_char="A"; 36:gui_char="R";
                        39:gui_char="H"; 40:gui_char="E"; 41:gui_char="L"; 42:gui_char="P";
                        45:gui_char="S"; 46:gui_char="P"; 47:gui_char="E";
                        48:gui_char="E"; 49:gui_char="D";
                        52:gui_char="C"; 53:gui_char="U"; 54:gui_char="R";
                        55:gui_char="S"; 56:gui_char="O"; 57:gui_char="R";
                        61:gui_char="H"; 62:gui_char="I"; 63:gui_char="D";
                        default: gui_char=8'h20;
                    endcase
                    if ((pixel_x>=384 && pixel_x<=495) ||
                        (pixel_x>=496 && pixel_x<=607) ||
                        (pixel_x>=608 && pixel_x<=703) ||
                        (pixel_x>=704 && pixel_x<=815) ||
                        (pixel_x>=816 && pixel_x<=943)) begin
                        gui_button = 1'b1;
                        gui_button_hover = (mouse_y < 32) &&
                            (((mouse_x>=384)&&(mouse_x<=495)&&(pixel_x>=384)&&(pixel_x<=495)) ||
                             ((mouse_x>=496)&&(mouse_x<=607)&&(pixel_x>=496)&&(pixel_x<=607)) ||
                             ((mouse_x>=608)&&(mouse_x<=703)&&(pixel_x>=608)&&(pixel_x<=703)) ||
                             ((mouse_x>=704)&&(mouse_x<=815)&&(pixel_x>=704)&&(pixel_x<=815)) ||
                             ((mouse_x>=816)&&(mouse_x<=943)&&(pixel_x>=816)&&(pixel_x<=943)));
                    end
                end
            end else begin
                // Live status row: state, coordinates, buttons, wheel and key.
                if (LINUX_PROFILE == 0) begin
                    case (gui_col)
                        0:gui_char="S"; 1:gui_char="T"; 2:gui_char=":";
                        10:gui_char="X"; 11:gui_char=":"; 12:gui_char=x2_ascii;
                        13:gui_char=x1_ascii; 14:gui_char=x0_ascii;
                        16:gui_char="Y"; 17:gui_char=":"; 18:gui_char=y2_ascii;
                        19:gui_char=y1_ascii; 20:gui_char=y0_ascii;
                        22:gui_char="B"; 23:gui_char=":"; 24:gui_char=button_ascii;
                        26:gui_char="W"; 27:gui_char=":"; 28:gui_char=wheel1_ascii;
                        29:gui_char=wheel0_ascii;
                        31:gui_char="K"; 32:gui_char=":"; 33:gui_char=usage1_ascii;
                        34:gui_char=usage0_ascii;
                        37:gui_char="2"; 38:gui_char="X";
                        default: gui_char=8'h20;
                    endcase
                    if ((gui_col>=3)&&(gui_col<=7)) begin
                        if (keyboard_seen && mouse_seen) begin
                            case(gui_col) 3:gui_char="R";4:gui_char="E";5:gui_char="A";6:gui_char="D";7:gui_char="Y"; default:gui_char=8'h20;endcase
                        end else if (keyboard_seen) begin
                            case(gui_col) 3:gui_char="K";4:gui_char="B";5:gui_char="D"; default:gui_char=8'h20;endcase
                        end else if (mouse_seen) begin
                            case(gui_col) 3:gui_char="M";4:gui_char="O";5:gui_char="U";6:gui_char="S";7:gui_char="E"; default:gui_char=8'h20;endcase
                        end else begin
                            case(gui_col) 3:gui_char="W";4:gui_char="A";5:gui_char="I";6:gui_char="T"; default:gui_char=8'h20;endcase
                        end
                    end
                    if ((gui_col==37)||(gui_col==38))
                        gui_char = gui_speed_2x ? gui_char : 8'h20;
                end else begin
                    case (gui_col)
                        25:gui_char="S"; 26:gui_char="T"; 27:gui_char=":";
                        35:gui_char="X"; 36:gui_char=":"; 37:gui_char=x2_ascii;
                        38:gui_char=x1_ascii; 39:gui_char=x0_ascii;
                        41:gui_char="Y"; 42:gui_char=":"; 43:gui_char=y2_ascii;
                        44:gui_char=y1_ascii; 45:gui_char=y0_ascii;
                        47:gui_char="B"; 48:gui_char=":"; 49:gui_char=button_ascii;
                        51:gui_char="W"; 52:gui_char=":"; 53:gui_char=wheel1_ascii;
                        54:gui_char=wheel0_ascii;
                        56:gui_char="K"; 57:gui_char=":"; 58:gui_char=usage1_ascii;
                        59:gui_char=usage0_ascii;
                        62:gui_char="F"; 63:gui_char="O"; 64:gui_char="C";
                        65:gui_char="U"; 66:gui_char="S";
                        default: gui_char=8'h20;
                    endcase
                    if ((gui_col>=28)&&(gui_col<=32)) begin
                        if (keyboard_seen && mouse_seen) begin
                            case(gui_col) 28:gui_char="R";29:gui_char="E";30:gui_char="A";31:gui_char="D";32:gui_char="Y"; default:gui_char=8'h20;endcase
                        end else if (keyboard_seen) begin
                            case(gui_col) 28:gui_char="K";29:gui_char="B";30:gui_char="D"; default:gui_char=8'h20;endcase
                        end else if (mouse_seen) begin
                            case(gui_col) 28:gui_char="M";29:gui_char="O";30:gui_char="U";31:gui_char="S";32:gui_char="E"; default:gui_char=8'h20;endcase
                        end else begin
                            case(gui_col) 28:gui_char="W";29:gui_char="A";30:gui_char="I";31:gui_char="T"; default:gui_char=8'h20;endcase
                        end
                    end
                    if ((gui_col>=62)&&(gui_col<=66) && !gui_term_focus)
                        gui_char=8'h20;
                end
            end
        end

        // HELP panel.  It is intentionally graphical/ASCII-only so the same
        // proven font ROM works in both deliverables.
        if (gui_help && de_in && (pixel_x>=160)&&(pixel_x<1120) &&
            (pixel_y>=160)&&(pixel_y<512)) begin
            gui_region = 1'b1;
            gui_bg_r = 8'h18; gui_bg_g = 8'h24; gui_bg_b = 8'h48;
            case ({gui_row,gui_col})
                {5'd5,7'd16}:gui_char="C"; {5'd5,7'd17}:gui_char="H";
                {5'd5,7'd18}:gui_char="9"; {5'd5,7'd19}:gui_char="3";
                {5'd5,7'd20}:gui_char="5"; {5'd5,7'd21}:gui_char="0";
                {5'd5,7'd23}:gui_char="M"; {5'd5,7'd24}:gui_char="O";
                {5'd5,7'd25}:gui_char="D"; {5'd5,7'd26}:gui_char="E";
                {5'd5,7'd27}:gui_char="2"; {5'd5,7'd29}:gui_char="H";
                {5'd5,7'd30}:gui_char="E"; {5'd5,7'd31}:gui_char="L";
                {5'd5,7'd32}:gui_char="P";
                {5'd7,7'd13}:gui_char="K"; {5'd7,7'd14}:gui_char="E";
                {5'd7,7'd15}:gui_char="Y"; {5'd7,7'd16}:gui_char="B";
                {5'd7,7'd17}:gui_char="O"; {5'd7,7'd18}:gui_char="A";
                {5'd7,7'd19}:gui_char="R"; {5'd7,7'd20}:gui_char="D";
                {5'd7,7'd21}:gui_char=":"; {5'd7,7'd23}:gui_char="U";
                {5'd7,7'd24}:gui_char="S"; {5'd7,7'd26}:gui_char="A";
                {5'd7,7'd27}:gui_char="N"; {5'd7,7'd28}:gui_char="S";
                {5'd7,7'd29}:gui_char="I";
                {5'd8,7'd13}:gui_char="M"; {5'd8,7'd14}:gui_char="O";
                {5'd8,7'd15}:gui_char="U"; {5'd8,7'd16}:gui_char="S";
                {5'd8,7'd17}:gui_char="E"; {5'd8,7'd18}:gui_char=":";
                {5'd8,7'd20}:gui_char="M"; {5'd8,7'd21}:gui_char="O";
                {5'd8,7'd22}:gui_char="V"; {5'd8,7'd23}:gui_char="E";
                {5'd8,7'd25}:gui_char="A"; {5'd8,7'd26}:gui_char="N";
                {5'd8,7'd27}:gui_char="D"; {5'd8,7'd29}:gui_char="C";
                {5'd8,7'd30}:gui_char="L"; {5'd8,7'd31}:gui_char="I";
                {5'd8,7'd32}:gui_char="C"; {5'd8,7'd33}:gui_char="K";
                {5'd10,7'd13}:gui_char="F"; {5'd10,7'd14}:gui_char="1";
                {5'd10,7'd16}:gui_char="O"; {5'd10,7'd17}:gui_char="R";
                {5'd10,7'd19}:gui_char="H"; {5'd10,7'd20}:gui_char="E";
                {5'd10,7'd21}:gui_char="L"; {5'd10,7'd22}:gui_char="P";
                {5'd10,7'd24}:gui_char="C"; {5'd10,7'd25}:gui_char="L";
                {5'd10,7'd26}:gui_char="O"; {5'd10,7'd27}:gui_char="S";
                {5'd10,7'd28}:gui_char="E";
                default: gui_char=8'h20;
            endcase
        end

        // Optional compact statistics panel in the CoreMark profile.
        if ((LINUX_PROFILE == 0) && gui_stats && de_in &&
            (pixel_x>=32)&&(pixel_x<608)&&(pixel_y>=96)&&(pixel_y<224)) begin
            gui_region=1'b1;
            gui_bg_r=8'h12; gui_bg_g=8'h2c; gui_bg_b=8'h34;
            case ({gui_row,gui_col})
                {5'd3,7'd4}:gui_char="K"; {5'd3,7'd5}:gui_char="B";
                {5'd3,7'd6}:gui_char="D"; {5'd3,7'd7}:gui_char="=";
                {5'd3,7'd8}:gui_char=kbdcnt1_ascii; {5'd3,7'd9}:gui_char=kbdcnt0_ascii;
                {5'd4,7'd4}:gui_char="M"; {5'd4,7'd5}:gui_char="O";
                {5'd4,7'd6}:gui_char="U"; {5'd4,7'd7}:gui_char="S";
                {5'd4,7'd8}:gui_char="E"; {5'd4,7'd9}:gui_char="=";
                {5'd4,7'd10}:gui_char=mousecnt1_ascii; {5'd4,7'd11}:gui_char=mousecnt0_ascii;
                {5'd5,7'd4}:gui_char="E"; {5'd5,7'd5}:gui_char="R";
                {5'd5,7'd6}:gui_char="R"; {5'd5,7'd7}:gui_char="=";
                {5'd5,7'd8}:gui_char=errcnt1_ascii; {5'd5,7'd9}:gui_char=errcnt0_ascii;
                default: gui_char=8'h20;
            endcase
        end

        if (gui_button) begin
            if (gui_button_hover) begin
                gui_bg_r=8'h18; gui_bg_g=8'h78; gui_bg_b=8'h58;
            end else begin
                gui_bg_r=8'h24; gui_bg_g=8'h42; gui_bg_b=8'h70;
            end
        end
    end

    wire [7:0] gui_font_bits;
    font_rom u_hid_gui_font(
        .clk(pix_clk),
        .addr({gui_char[6:0], gui_font_row}),
        .bits(gui_font_bits)
    );

    reg [10:0] s1_x;
    reg [10:0] s1_y;
    reg [2:0] s1_font_x;
    reg s1_gui_region;
    reg [7:0] s1_bg_r, s1_bg_g, s1_bg_b;
    reg s1_hs, s1_vs, s1_de;
    reg [7:0] s1_r, s1_g, s1_b;

    wire [10:0] cursor_dx = s1_x - mouse_x;
    wire [10:0] cursor_dy = s1_y - mouse_y;
    wire cursor_box = mouse_seen && s1_de && (s1_x >= mouse_x) &&
                      (s1_y >= mouse_y) && (cursor_dx < 11'd16) &&
                      (cursor_dy < 11'd24);
    reg cursor_outer;
    reg cursor_inner;

    // Windows-style 16x22 arrow with a top-left hot spot, black one-pixel
    // outline, white body and slanted lower stem.  Explicit rows avoid a
    // variable-indexed bitmap on the pixel path in PDS 2022.2-SP6.4.
    always @* begin
        cursor_outer = 1'b0;
        cursor_inner = 1'b0;
        if (cursor_box) begin
            case (cursor_dy)
                11'd0:  cursor_outer = (cursor_dx == 11'd0);
                11'd1:  cursor_outer = (cursor_dx <= 11'd1);
                11'd2:  begin cursor_outer=(cursor_dx<=11'd2);  cursor_inner=(cursor_dx==11'd1); end
                11'd3:  begin cursor_outer=(cursor_dx<=11'd3);  cursor_inner=(cursor_dx>=11'd1)&&(cursor_dx<=11'd2); end
                11'd4:  begin cursor_outer=(cursor_dx<=11'd4);  cursor_inner=(cursor_dx>=11'd1)&&(cursor_dx<=11'd3); end
                11'd5:  begin cursor_outer=(cursor_dx<=11'd5);  cursor_inner=(cursor_dx>=11'd1)&&(cursor_dx<=11'd4); end
                11'd6:  begin cursor_outer=(cursor_dx<=11'd6);  cursor_inner=(cursor_dx>=11'd1)&&(cursor_dx<=11'd5); end
                11'd7:  begin cursor_outer=(cursor_dx<=11'd7);  cursor_inner=(cursor_dx>=11'd1)&&(cursor_dx<=11'd6); end
                11'd8:  begin cursor_outer=(cursor_dx<=11'd8);  cursor_inner=(cursor_dx>=11'd1)&&(cursor_dx<=11'd7); end
                11'd9:  begin cursor_outer=(cursor_dx<=11'd9);  cursor_inner=(cursor_dx>=11'd1)&&(cursor_dx<=11'd8); end
                11'd10: begin cursor_outer=(cursor_dx<=11'd10); cursor_inner=(cursor_dx>=11'd1)&&(cursor_dx<=11'd9); end
                11'd11: begin cursor_outer=(cursor_dx<=11'd11); cursor_inner=(cursor_dx>=11'd1)&&(cursor_dx<=11'd10); end
                11'd12: begin cursor_outer=(cursor_dx<=11'd12); cursor_inner=(cursor_dx>=11'd1)&&(cursor_dx<=11'd11); end
                11'd13: begin cursor_outer=(cursor_dx<=11'd13); cursor_inner=(cursor_dx>=11'd1)&&(cursor_dx<=11'd4); end
                11'd14: begin
                    cursor_outer=((cursor_dx<=11'd4)||((cursor_dx>=11'd6)&&(cursor_dx<=11'd9)));
                    cursor_inner=(((cursor_dx>=11'd1)&&(cursor_dx<=11'd3))||((cursor_dx>=11'd7)&&(cursor_dx<=11'd8)));
                end
                11'd15: begin
                    cursor_outer=((cursor_dx<=11'd3)||((cursor_dx>=11'd6)&&(cursor_dx<=11'd10)));
                    cursor_inner=(((cursor_dx>=11'd1)&&(cursor_dx<=11'd2))||((cursor_dx>=11'd7)&&(cursor_dx<=11'd9)));
                end
                11'd16: begin
                    cursor_outer=((cursor_dx<=11'd2)||((cursor_dx>=11'd7)&&(cursor_dx<=11'd10)));
                    cursor_inner=((cursor_dx==11'd1)||((cursor_dx>=11'd8)&&(cursor_dx<=11'd9)));
                end
                11'd17: begin
                    cursor_outer=((cursor_dx<=11'd1)||((cursor_dx>=11'd7)&&(cursor_dx<=11'd11)));
                    cursor_inner=((cursor_dx>=11'd8)&&(cursor_dx<=11'd10));
                end
                11'd18: begin
                    cursor_outer=((cursor_dx==11'd0)||((cursor_dx>=11'd8)&&(cursor_dx<=11'd11)));
                    cursor_inner=((cursor_dx>=11'd9)&&(cursor_dx<=11'd10));
                end
                11'd19: begin
                    cursor_outer=((cursor_dx>=11'd8)&&(cursor_dx<=11'd12));
                    cursor_inner=((cursor_dx>=11'd9)&&(cursor_dx<=11'd11));
                end
                11'd20: begin
                    cursor_outer=((cursor_dx>=11'd9)&&(cursor_dx<=11'd12));
                    cursor_inner=((cursor_dx>=11'd10)&&(cursor_dx<=11'd11));
                end
                11'd21: begin
                    cursor_outer=((cursor_dx>=11'd9)&&(cursor_dx<=11'd11));
                    cursor_inner=(cursor_dx==11'd10);
                end
                default: begin cursor_outer=1'b0; cursor_inner=1'b0; end
            endcase
        end
    end
    wire gui_font_pixel = gui_font_bits[7-s1_font_x];

    always @(posedge pix_clk) begin
        if (!resetn) begin
            s1_x<=0; s1_y<=0; s1_font_x<=0; s1_gui_region<=0;
            s1_bg_r<=0; s1_bg_g<=0; s1_bg_b<=0;
            s1_hs<=0; s1_vs<=0; s1_de<=0; s1_r<=0; s1_g<=0; s1_b<=0;
            hs_out<=0; vs_out<=0; de_out<=0; r_out<=0; g_out<=0; b_out<=0;
        end else begin
            s1_x <= pixel_x;
            s1_y <= pixel_y;
            s1_font_x <= gui_font_x;
            s1_gui_region <= gui_region;
            s1_bg_r <= gui_bg_r; s1_bg_g <= gui_bg_g; s1_bg_b <= gui_bg_b;
            s1_hs<=hs_in; s1_vs<=vs_in; s1_de<=de_in;
            s1_r<=r_in; s1_g<=g_in; s1_b<=b_in;

            hs_out<=s1_hs; vs_out<=s1_vs; de_out<=s1_de;
            if (!s1_de) begin
                r_out<=0; g_out<=0; b_out<=0;
            end else if (cursor_outer) begin
                if (!cursor_inner) begin
                    r_out<=0; g_out<=0; b_out<=0;
                end else if (LINUX_PROFILE != 0) begin
                    // A Windows-style pointer stays white while clicking.
                    r_out<=8'hf8; g_out<=8'hf8; b_out<=8'hf8;
                end else if (mouse_buttons[0]) begin
                    r_out<=8'h30; g_out<=8'hff; b_out<=8'h70;
                end else if (mouse_buttons[1]) begin
                    r_out<=8'hff; g_out<=8'h50; b_out<=8'h40;
                end else if (mouse_buttons[2]) begin
                    r_out<=8'h40; g_out<=8'h90; b_out<=8'hff;
                end else if (gui_cursor_alt) begin
                    r_out<=8'hff; g_out<=8'hd0; b_out<=8'h30;
                end else begin
                    r_out<=8'hf8; g_out<=8'hf8; b_out<=8'hf8;
                end
            end else if (s1_gui_region && gui_font_pixel) begin
                r_out<=8'hf4; g_out<=8'hf7; b_out<=8'hff;
            end else if (s1_gui_region) begin
                r_out<=s1_bg_r; g_out<=s1_bg_g; b_out<=s1_bg_b;
            end else begin
                r_out<=s1_r; g_out<=s1_g; b_out<=s1_b;
            end
        end
    end
endmodule

module hid_hex_ascii(
    input wire [3:0] nibble,
    output reg [7:0] ascii
);
    always @* begin
        case (nibble)
            4'h0:ascii="0"; 4'h1:ascii="1"; 4'h2:ascii="2"; 4'h3:ascii="3";
            4'h4:ascii="4"; 4'h5:ascii="5"; 4'h6:ascii="6"; 4'h7:ascii="7";
            4'h8:ascii="8"; 4'h9:ascii="9"; 4'ha:ascii="A"; 4'hb:ascii="B";
            4'hc:ascii="C"; 4'hd:ascii="D"; 4'he:ascii="E"; default:ascii="F";
        endcase
    end
endmodule
