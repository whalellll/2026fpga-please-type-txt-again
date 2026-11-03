`timescale 1ns/1ps

// 1280x720p60 HDMI text console.  The fixed 64-pixel header is followed by
// an 80x20 terminal using an 8x16 font scaled to 16x32 pixels.
module video_linux_console #(
    parameter H_ACT  = 1280,
    parameter H_FP   = 110,
    parameter H_SYNC = 40,
    parameter H_BP   = 220,
    parameter V_ACT  = 720,
    parameter V_FP   = 5,
    parameter V_SYNC = 5,
    parameter V_BP   = 20
)(
    input  wire        pix_clk,
    input  wire        rstn,
    output reg  [4:0]  text_rd_row,
    output reg  [6:0]  text_rd_col,
    input  wire [7:0]  text_rd_data,
    input  wire [11:0] cursor_cell,
    output wire        vs_out,
    output wire        hs_out,
    output wire        de_out,
    output wire [7:0]  r_out,
    output wire [7:0]  g_out,
    output wire [7:0]  b_out
);
    localparam H_TOTAL = H_SYNC + H_BP + H_ACT + H_FP;
    localparam V_TOTAL = V_SYNC + V_BP + V_ACT + V_FP;
    localparam H_START = H_SYNC + H_BP;
    localparam V_START = V_SYNC + V_BP;

    reg [11:0] h_count;
    reg [10:0] v_count;
    wire hs_c = h_count < H_SYNC;
    wire vs_c = v_count < V_SYNC;
    wire de_c = (h_count >= H_START) && (h_count < H_START + H_ACT) &&
                (v_count >= V_START) && (v_count < V_START + V_ACT);
    wire [10:0] x_act = h_count - H_START;
    wire [10:0] y_act = v_count - V_START;

    wire header_c = de_c && (y_act < 10'd64);
    wire text_c = de_c && (y_act >= 10'd64) && (y_act < 10'd704);
    wire [10:0] text_y = y_act - 10'd64;
    wire [10:0] text_x = x_act - (H_ACT - 1280) / 2;
    wire [6:0] cell_col_c = text_x[10:4];
    wire [4:0] cell_row_c = text_y[9:5];
    wire [3:0] font_row_c = text_y[4:1];
    wire [2:0] font_x_c = text_x[3:1];
    wire cell_ok_c = text_c && (x_act >= (H_ACT - 1280) / 2) &&
                     (x_act < (H_ACT + 1280) / 2) && (cell_col_c < 7'd80) &&
                     (cell_row_c < 5'd20);

    // Header ROM covers x=0..383.  48 bytes per line = 32 + 16.
    wire header_bitmap_c = header_c && (x_act < 11'd384);
    wire [11:0] header_addr_c = {y_act[5:0], 5'b0} +
                                {y_act[5:0], 4'b0} +
                                {7'b0, x_act[8:3]};
    wire [7:0] header_bits;
    header_bitmap_rom u_header (
        .clk  (pix_clk),
        .addr (header_bitmap_c ? header_addr_c : 12'd0),
        .bits (header_bits)
    );
    wire header_logo_c = header_c && (x_act < 11'd80);
    wire [12:0] logo_addr_c = {y_act[5:0], 6'b0} +
                              {y_act[5:0], 4'b0} +
                              {6'b0, x_act[6:0]};
    wire [7:0] logo_rgb332;
    header_logo_rom u_logo (
        .clk    (pix_clk),
        .addr   (header_logo_c ? logo_addr_c : 13'd0),
        .rgb332 (logo_rgb332)
    );

    // Cursor blink: approximately 0.53 seconds per phase at 60 Hz.
    reg [5:0] blink_cnt;
    wire cursor_c = blink_cnt[5] && cell_ok_c &&
                    (cursor_cell == {cell_row_c, cell_col_c});

    // Metadata pipeline aligned with the registered text RAM and font ROM.
    reg [3:0] s1_fr;
    reg [2:0] s1_fx;
    reg       s1_cur, s1_hs, s1_vs, s1_de, s1_text;
    reg       s1_header, s1_header_bitmap, s1_header_logo;
    reg [2:0] s1_header_bit;

    reg [3:0] s2_fr;
    reg [2:0] s2_fx;
    reg       s2_cur, s2_hs, s2_vs, s2_de, s2_text;
    reg       s2_header, s2_header_logo, s2_header_pixel;
    reg [7:0] s2_logo_rgb;

    reg [7:0] s3_char;
    reg [3:0] s3_fr;
    reg [2:0] s3_fx;
    reg       s3_cur, s3_hs, s3_vs, s3_de, s3_text;
    reg       s3_header, s3_header_logo, s3_header_pixel;
    reg [7:0] s3_logo_rgb;

    reg [2:0] s4_fx;
    reg       s4_cur, s4_hs, s4_vs, s4_de, s4_text;
    reg       s4_header, s4_header_logo, s4_header_pixel;
    reg [7:0] s4_logo_rgb;

    reg [7:0] s5_r, s5_g, s5_b;
    reg       s5_hs, s5_vs, s5_de;

    wire [7:0] font_bits;
    font_rom u_font (
        .clk  (pix_clk),
        .addr ({s3_char[6:0], s3_fr}),
        .bits (font_bits)
    );
    wire font_pixel = font_bits[7 - s4_fx];

    localparam [7:0] BODY_R = 8'h0d, BODY_G = 8'h12, BODY_B = 8'h24;
    localparam [7:0] HEAD_R = 8'h00, HEAD_G = 8'h00, HEAD_B = 8'h00;
    localparam [7:0] RULE_R = 8'h25, RULE_G = 8'h9d, RULE_B = 8'hd8;
    localparam [7:0] TEXT_R = 8'hee, TEXT_G = 8'hf3, TEXT_B = 8'hff;
    localparam [7:0] CUR_R  = 8'h21, CUR_G  = 8'h9a, CUR_B  = 8'h55;
    wire [7:0] logo_r8 = {s4_logo_rgb[7:5], s4_logo_rgb[7:5],
                          s4_logo_rgb[7:6]};
    wire [7:0] logo_g8 = {s4_logo_rgb[4:2], s4_logo_rgb[4:2],
                          s4_logo_rgb[4:3]};
    wire [7:0] logo_b8 = {s4_logo_rgb[1:0], s4_logo_rgb[1:0],
                          s4_logo_rgb[1:0], s4_logo_rgb[1:0]};

    always @(posedge pix_clk) begin
        if (!rstn) begin
            h_count <= 12'd0;
            v_count <= 11'd0;
            blink_cnt <= 6'd0;
            text_rd_row <= 5'd0;
            text_rd_col <= 7'd0;
            s1_fr <= 4'd0; s1_fx <= 3'd0;
            s1_cur <= 1'b0; s1_hs <= 1'b0; s1_vs <= 1'b0;
            s1_de <= 1'b0; s1_text <= 1'b0; s1_header <= 1'b0;
            s1_header_bitmap <= 1'b0; s1_header_logo <= 1'b0;
            s1_header_bit <= 3'd0;
            s2_fr <= 4'd0; s2_fx <= 3'd0;
            s2_cur <= 1'b0; s2_hs <= 1'b0; s2_vs <= 1'b0;
            s2_de <= 1'b0; s2_text <= 1'b0; s2_header <= 1'b0;
            s2_header_logo <= 1'b0; s2_header_pixel <= 1'b0;
            s2_logo_rgb <= 8'd0;
            s3_char <= 8'h20; s3_fr <= 4'd0; s3_fx <= 3'd0;
            s3_cur <= 1'b0; s3_hs <= 1'b0; s3_vs <= 1'b0;
            s3_de <= 1'b0; s3_text <= 1'b0; s3_header <= 1'b0;
            s3_header_logo <= 1'b0; s3_header_pixel <= 1'b0;
            s3_logo_rgb <= 8'd0;
            s4_fx <= 3'd0; s4_cur <= 1'b0; s4_hs <= 1'b0;
            s4_vs <= 1'b0; s4_de <= 1'b0; s4_text <= 1'b0;
            s4_header <= 1'b0; s4_header_logo <= 1'b0;
            s4_header_pixel <= 1'b0;
            s4_logo_rgb <= 8'd0;
            s5_r <= 8'd0; s5_g <= 8'd0; s5_b <= 8'd0;
            s5_hs <= 1'b0; s5_vs <= 1'b0; s5_de <= 1'b0;
        end else begin
            if (h_count == H_TOTAL - 1) begin
                h_count <= 12'd0;
                if (v_count == V_TOTAL - 1) begin
                    v_count <= 11'd0;
                    blink_cnt <= blink_cnt + 6'd1;
                end else begin
                    v_count <= v_count + 11'd1;
                end
            end else begin
                h_count <= h_count + 12'd1;
            end

            text_rd_row <= cell_ok_c ? cell_row_c : 5'd0;
            text_rd_col <= cell_ok_c ? cell_col_c : 7'd0;
            s1_fr <= font_row_c;
            s1_fx <= font_x_c;
            s1_cur <= cursor_c;
            s1_hs <= hs_c; s1_vs <= vs_c; s1_de <= de_c;
            s1_text <= cell_ok_c;
            s1_header <= header_c;
            s1_header_bitmap <= header_bitmap_c;
            s1_header_logo <= header_logo_c;
            s1_header_bit <= x_act[2:0];

            s2_fr <= s1_fr; s2_fx <= s1_fx;
            s2_cur <= s1_cur; s2_hs <= s1_hs; s2_vs <= s1_vs;
            s2_de <= s1_de; s2_text <= s1_text;
            s2_header <= s1_header;
            s2_header_logo <= s1_header_logo;
            s2_header_pixel <= s1_header_bitmap &&
                               header_bits[7 - s1_header_bit];
            s2_logo_rgb <= logo_rgb332;

            s3_char <= s2_text ? text_rd_data : 8'h20;
            s3_fr <= s2_fr; s3_fx <= s2_fx;
            s3_cur <= s2_cur; s3_hs <= s2_hs; s3_vs <= s2_vs;
            s3_de <= s2_de; s3_text <= s2_text;
            s3_header <= s2_header;
            s3_header_logo <= s2_header_logo;
            s3_header_pixel <= s2_header_pixel;
            s3_logo_rgb <= s2_logo_rgb;

            s4_fx <= s3_fx;
            s4_cur <= s3_cur; s4_hs <= s3_hs; s4_vs <= s3_vs;
            s4_de <= s3_de; s4_text <= s3_text;
            s4_header <= s3_header;
            s4_header_logo <= s3_header_logo;
            s4_header_pixel <= s3_header_pixel;
            s4_logo_rgb <= s3_logo_rgb;

            if (!s4_de) begin
                s5_r <= 8'd0; s5_g <= 8'd0; s5_b <= 8'd0;
            end else if (s4_header) begin
                if (s4_header_logo) begin
                    s5_r <= logo_r8;
                    s5_g <= logo_g8;
                    s5_b <= logo_b8;
                end else if (s4_header_pixel) begin
                    s5_r <= TEXT_R;
                    s5_g <= TEXT_G;
                    s5_b <= TEXT_B;
                end else begin
                    s5_r <= HEAD_R; s5_g <= HEAD_G; s5_b <= HEAD_B;
                end
            end else if (s4_text && font_pixel) begin
                s5_r <= TEXT_R; s5_g <= TEXT_G; s5_b <= TEXT_B;
            end else if (s4_cur) begin
                s5_r <= CUR_R; s5_g <= CUR_G; s5_b <= CUR_B;
            end else if (s4_de) begin
                // A blue separator at the bottom of the fixed header makes
                // the permanent title visually distinct from terminal rows.
                s5_r <= BODY_R; s5_g <= BODY_G; s5_b <= BODY_B;
            end
            s5_hs <= s4_hs; s5_vs <= s4_vs; s5_de <= s4_de;
        end
    end

    assign hs_out = s5_hs;
    assign vs_out = s5_vs;
    assign de_out = s5_de;
    assign r_out = s5_r;
    assign g_out = s5_g;
    assign b_out = s5_b;
endmodule
