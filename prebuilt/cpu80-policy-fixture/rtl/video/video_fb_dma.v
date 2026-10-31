`timescale 1ns/1ps

// 1280x720p60 RGB565 framebuffer scanout.
//
// Two fixed 2 MiB DDR slots hold the front/back frames.  The DDR side reads
// five 16-beat (512-byte) native bursts per line.  A complete native burst is
// first absorbed into a DDR-clock buffer because the Pango DDR port has no
// RREADY.  Stable-payload toggle handshakes then move 256-bit words into two
// pixel-clock line buffers, avoiding a dual-clock block RAM.
module video_fb_dma #(
    parameter [31:0] FB0_BASE = 32'h1b20_0000,
    parameter [31:0] FB1_BASE = 32'h1b40_0000,
    parameter integer H_ACT   = 1280,
    parameter integer H_FP    = 110,
    parameter integer H_SYNC  = 40,
    parameter integer H_BP    = 220,
    parameter integer V_ACT   = 720,
    parameter integer V_FP    = 5,
    parameter integer V_SYNC  = 5,
    parameter integer V_BP    = 20
) (
    input  wire         sys_enable,
    input  wire         sys_requested_buffer,
    input  wire         sys_clear_underflow_toggle,

    input  wire         ddr_clk,
    input  wire         ddr_resetn,
    input  wire         ddr_init_done,
    output wire [27:0]  fb_araddr,
    output wire [3:0]   fb_arid,
    output wire [3:0]   fb_arlen,
    output wire         fb_arvalid,
    output wire         fb_urgent,
    input  wire         fb_arready,
    input  wire [255:0] fb_rdata,
    input  wire [3:0]   fb_rid,
    input  wire         fb_rlast,
    input  wire         fb_rvalid,
    output wire         dma_busy_ddr,
    output reg          dma_error_ddr,

    input  wire         pix_clk,
    input  wire         pix_resetn,
    output reg          active_enable_pix,
    output reg          active_buffer_pix,
    output reg          underflow_pix,
    output reg  [31:0]  frame_count_pix,
    output reg  [31:0]  underflow_count_pix,
    output wire         vs_out,
    output wire         hs_out,
    output wire         de_out,
    output wire [7:0]   r_out,
    output wire [7:0]   g_out,
    output wire [7:0]   b_out
);
    localparam integer H_TOTAL = H_SYNC + H_BP + H_ACT + H_FP;
    localparam integer V_TOTAL = V_SYNC + V_BP + V_ACT + V_FP;
    localparam integer H_START = H_SYNC + H_BP;
    localparam integer V_START = V_SYNC + V_BP;
    localparam [3:0] FB_ID = 4'he;

    // ------------------------------------------------------------------
    // Pixel-domain timing and fixed-size line buffers.
    // One line is 80 x 256-bit words (1280 RGB565 pixels).
    // ------------------------------------------------------------------
    reg [255:0] line_mem0 [0:79] /* synthesis syn_ramstyle="block_ram" */;
    reg [255:0] line_mem1 [0:79] /* synthesis syn_ramstyle="block_ram" */;
    reg line_ready0, line_ready1;
    reg [9:0] line_number0, line_number1;

    reg [10:0] h_count;
    reg [9:0]  v_count;
    wire hs_c = h_count < H_SYNC;
    wire vs_c = v_count < V_SYNC;
    wire de_c = (h_count >= H_START) && (h_count < H_START + H_ACT) &&
                (v_count >= V_START) && (v_count < V_START + V_ACT);
    wire [10:0] x_act = h_count - H_START;
    wire [9:0]  y_act = v_count - V_START;
    wire frame_wrap_c = (h_count == H_TOTAL - 1) &&
                        (v_count == V_TOTAL - 1);
    wire current_line_ready = y_act[0]
        ? (line_ready1 && (line_number1 == y_act))
        : (line_ready0 && (line_number0 == y_act));

    // System control synchronizers.  Changes become visible only at a frame
    // boundary, so page flips cannot tear.
    reg enable_p1, enable_p2;
    reg front_p1, front_p2;
    reg clear_p1, clear_p2, clear_seen;

    // Pixel -> DDR line-request mailbox.
    reg req_toggle_pix;
    reg req_pending_pix;
    reg [9:0] req_line_pix;
    reg req_bank_pix;
    reg req_front_pix;
    reg req_epoch_pix;
    reg frame_epoch_pix;
    reg [9:0] next_fetch_line_pix;

    // DDR -> pixel data mailbox.
    reg data_toggle_p1, data_toggle_p2, data_seen_pix;
    reg data_ack_pix;
    reg done_toggle_p1, done_toggle_p2, done_seen_pix;

    // These payload registers are written only in the DDR domain and remain
    // stable until their corresponding toggle is acknowledged/sampled.
    reg [255:0] data_payload_ddr;
    reg [6:0]   data_word_ddr;
    reg         data_bank_ddr;
    reg         data_toggle_ddr;
    reg         done_toggle_ddr;
    reg [9:0]   done_line_ddr;
    reg         done_bank_ddr;
    reg         done_epoch_ddr;

    // Five-stage output pipeline, aligned with video_linux_console.
    reg [255:0] s1_word;
    reg [3:0] s1_lane;
    reg s1_valid, s1_hs, s1_vs, s1_de;
    reg [15:0] s2_pixel;
    reg s2_valid, s2_hs, s2_vs, s2_de;
    reg [15:0] s3_pixel;
    reg s3_valid, s3_hs, s3_vs, s3_de;
    reg [15:0] s4_pixel;
    reg s4_valid, s4_hs, s4_vs, s4_de;
    reg [7:0] s5_r, s5_g, s5_b;
    reg s5_hs, s5_vs, s5_de;

    wire [7:0] rgb_r = {s4_pixel[15:11], s4_pixel[15:13]};
    wire [7:0] rgb_g = {s4_pixel[10:5],  s4_pixel[10:9]};
    wire [7:0] rgb_b = {s4_pixel[4:0],   s4_pixel[4:2]};

    always @(posedge pix_clk or negedge pix_resetn) begin
        if (!pix_resetn) begin
            h_count                 <= 11'd0;
            v_count                 <= 10'd0;
            enable_p1               <= 1'b0;
            enable_p2               <= 1'b0;
            front_p1                <= 1'b0;
            front_p2                <= 1'b0;
            clear_p1                <= 1'b0;
            clear_p2                <= 1'b0;
            clear_seen              <= 1'b0;
            active_enable_pix       <= 1'b0;
            active_buffer_pix       <= 1'b0;
            underflow_pix           <= 1'b0;
            frame_count_pix         <= 32'd0;
            underflow_count_pix     <= 32'd0;
            line_ready0             <= 1'b0;
            line_ready1             <= 1'b0;
            line_number0            <= 10'd0;
            line_number1            <= 10'd0;
            req_toggle_pix          <= 1'b0;
            req_pending_pix         <= 1'b0;
            req_line_pix            <= 10'd0;
            req_bank_pix            <= 1'b0;
            req_front_pix           <= 1'b0;
            req_epoch_pix           <= 1'b0;
            frame_epoch_pix         <= 1'b0;
            next_fetch_line_pix     <= 10'd0;
            data_toggle_p1          <= 1'b0;
            data_toggle_p2          <= 1'b0;
            data_seen_pix           <= 1'b0;
            data_ack_pix            <= 1'b0;
            done_toggle_p1          <= 1'b0;
            done_toggle_p2          <= 1'b0;
            done_seen_pix           <= 1'b0;
            s1_word                 <= 256'd0;
            s1_lane                 <= 4'd0;
            s1_valid                <= 1'b0;
            s1_hs                   <= 1'b0;
            s1_vs                   <= 1'b0;
            s1_de                   <= 1'b0;
            s2_pixel                <= 16'd0;
            s2_valid                <= 1'b0;
            s2_hs                   <= 1'b0;
            s2_vs                   <= 1'b0;
            s2_de                   <= 1'b0;
            s3_pixel                <= 16'd0;
            s3_valid                <= 1'b0;
            s3_hs                   <= 1'b0;
            s3_vs                   <= 1'b0;
            s3_de                   <= 1'b0;
            s4_pixel                <= 16'd0;
            s4_valid                <= 1'b0;
            s4_hs                   <= 1'b0;
            s4_vs                   <= 1'b0;
            s4_de                   <= 1'b0;
            s5_r                    <= 8'd0;
            s5_g                    <= 8'd0;
            s5_b                    <= 8'd0;
            s5_hs                   <= 1'b0;
            s5_vs                   <= 1'b0;
            s5_de                   <= 1'b0;
        end else begin
            enable_p1 <= sys_enable;
            enable_p2 <= enable_p1;
            front_p1  <= sys_requested_buffer;
            front_p2  <= front_p1;
            clear_p1  <= sys_clear_underflow_toggle;
            clear_p2  <= clear_p1;

            data_toggle_p1 <= data_toggle_ddr;
            data_toggle_p2 <= data_toggle_p1;
            done_toggle_p1 <= done_toggle_ddr;
            done_toggle_p2 <= done_toggle_p1;

            if (clear_p2 != clear_seen) begin
                clear_seen          <= clear_p2;
                underflow_pix       <= 1'b0;
                underflow_count_pix <= 32'd0;
            end

            // Consume one stable 256-bit mailbox word and write it using only
            // pix_clk.  This deliberately avoids a dual-clock line RAM.
            if (data_toggle_p2 != data_seen_pix) begin
                if (data_bank_ddr)
                    line_mem1[data_word_ddr] <= data_payload_ddr;
                else
                    line_mem0[data_word_ddr] <= data_payload_ddr;
                data_seen_pix <= data_toggle_p2;
                data_ack_pix  <= data_toggle_p2;
            end

            if (done_toggle_p2 != done_seen_pix) begin
                done_seen_pix   <= done_toggle_p2;
                req_pending_pix <= 1'b0;
                if (done_epoch_ddr == frame_epoch_pix) begin
                    if (done_bank_ddr) begin
                        line_ready1  <= 1'b1;
                        line_number1 <= done_line_ddr;
                    end else begin
                        line_ready0  <= 1'b1;
                        line_number0 <= done_line_ddr;
                    end
                end
            end

            // Raster timing.
            if (h_count == H_TOTAL - 1) begin
                h_count <= 11'd0;
                if (v_count == V_TOTAL - 1) begin
                    v_count             <= 10'd0;
                    frame_count_pix     <= frame_count_pix + 32'd1;
                    active_enable_pix   <= enable_p2;
                    active_buffer_pix   <= front_p2;
                    frame_epoch_pix     <= ~frame_epoch_pix;
                    next_fetch_line_pix <= 10'd0;
                    line_ready0         <= 1'b0;
                    line_ready1         <= 1'b0;
                end else begin
                    v_count <= v_count + 10'd1;
                end
            end else begin
                h_count <= h_count + 11'd1;
            end

            // Count at most one underflow for each visible line.
            if (active_enable_pix && (h_count == H_START) &&
                (v_count >= V_START) && (v_count < V_START + V_ACT) &&
                !current_line_ready) begin
                underflow_pix       <= 1'b1;
                underflow_count_pix <= underflow_count_pix + 32'd1;
            end

            // The just-displayed parity bank becomes available for line+2.
            if (active_enable_pix &&
                (h_count == H_START + H_ACT - 1) &&
                (v_count >= V_START) && (v_count < V_START + V_ACT)) begin
                if (y_act[0])
                    line_ready1 <= 1'b0;
                else
                    line_ready0 <= 1'b0;
            end

            // Sequential prefetch: lines 0 and 1 are loaded in vertical
            // blanking; each displayed line then frees its parity bank.
            if (active_enable_pix && !frame_wrap_c && !req_pending_pix &&
                (next_fetch_line_pix < V_ACT) &&
                (next_fetch_line_pix[0] ? !line_ready1 : !line_ready0)) begin
                req_line_pix        <= next_fetch_line_pix;
                req_bank_pix        <= next_fetch_line_pix[0];
                req_front_pix       <= active_buffer_pix;
                req_epoch_pix       <= frame_epoch_pix;
                req_toggle_pix      <= ~req_toggle_pix;
                req_pending_pix     <= 1'b1;
                next_fetch_line_pix <= next_fetch_line_pix + 10'd1;
            end

            // S1: synchronous wide line read and timing metadata.
            if (de_c && active_enable_pix) begin
                if (y_act[0])
                    s1_word <= line_mem1[x_act[10:4]];
                else
                    s1_word <= line_mem0[x_act[10:4]];
            end else begin
                s1_word <= 256'd0;
            end
            s1_lane  <= x_act[3:0];
            s1_valid <= de_c && active_enable_pix && current_line_ready;
            s1_hs    <= hs_c;
            s1_vs    <= vs_c;
            s1_de    <= de_c;

            // S2..S5: lane select, delay and RGB expansion.
            s2_pixel <= s1_word[s1_lane * 16 +: 16];
            s2_valid <= s1_valid;
            s2_hs <= s1_hs; s2_vs <= s1_vs; s2_de <= s1_de;
            s3_pixel <= s2_pixel;
            s3_valid <= s2_valid;
            s3_hs <= s2_hs; s3_vs <= s2_vs; s3_de <= s2_de;
            s4_pixel <= s3_pixel;
            s4_valid <= s3_valid;
            s4_hs <= s3_hs; s4_vs <= s3_vs; s4_de <= s3_de;
            s5_r <= (s4_de && s4_valid) ? rgb_r : 8'd0;
            s5_g <= (s4_de && s4_valid) ? rgb_g : 8'd0;
            s5_b <= (s4_de && s4_valid) ? rgb_b : 8'd0;
            s5_hs <= s4_hs; s5_vs <= s4_vs; s5_de <= s4_de;
        end
    end

    assign hs_out = s5_hs;
    assign vs_out = s5_vs;
    assign de_out = s5_de;
    assign r_out  = s5_r;
    assign g_out  = s5_g;
    assign b_out  = s5_b;

    // ------------------------------------------------------------------
    // DDR-domain fetch engine.
    // ------------------------------------------------------------------
    localparam [2:0] D_IDLE  = 3'd0;
    localparam [2:0] D_AR    = 3'd1;
    localparam [2:0] D_RECV  = 3'd2;
    localparam [2:0] D_SEND  = 3'd3;
    localparam [2:0] D_ACK   = 3'd4;

    reg [2:0] d_state;
    reg req_toggle_d1, req_toggle_d2, req_seen_ddr;
    reg data_ack_d1, data_ack_d2;
    reg [255:0] burst_mem [0:15];
    reg [3:0] rx_index;
    reg [3:0] drain_index;
    reg [2:0] burst_index;
    reg [27:0] native_addr;
    reg [9:0] request_line_ddr;
    reg request_bank_ddr;
    reg request_epoch_ddr;

    wire [31:0] requested_base = req_front_pix ? FB1_BASE : FB0_BASE;
    assign fb_araddr  = native_addr;
    assign fb_arid    = FB_ID;
    assign fb_arlen   = 4'd15;
    assign fb_arvalid = (d_state == D_AR) && ddr_init_done;
    assign fb_urgent  = (d_state != D_IDLE);
    assign dma_busy_ddr = (d_state != D_IDLE) ||
                          (req_toggle_d2 != req_seen_ddr);

    always @(posedge ddr_clk or negedge ddr_resetn) begin
        if (!ddr_resetn) begin
            d_state          <= D_IDLE;
            req_toggle_d1    <= 1'b0;
            req_toggle_d2    <= 1'b0;
            req_seen_ddr     <= 1'b0;
            data_ack_d1      <= 1'b0;
            data_ack_d2      <= 1'b0;
            data_toggle_ddr  <= 1'b0;
            data_payload_ddr <= 256'd0;
            data_word_ddr    <= 7'd0;
            data_bank_ddr    <= 1'b0;
            done_toggle_ddr  <= 1'b0;
            done_line_ddr    <= 10'd0;
            done_bank_ddr    <= 1'b0;
            done_epoch_ddr   <= 1'b0;
            rx_index         <= 4'd0;
            drain_index      <= 4'd0;
            burst_index      <= 3'd0;
            native_addr      <= 28'd0;
            request_line_ddr <= 10'd0;
            request_bank_ddr <= 1'b0;
            request_epoch_ddr<= 1'b0;
            dma_error_ddr    <= 1'b0;
        end else begin
            req_toggle_d1 <= req_toggle_pix;
            req_toggle_d2 <= req_toggle_d1;
            data_ack_d1   <= data_ack_pix;
            data_ack_d2   <= data_ack_d1;

            case (d_state)
                D_IDLE: begin
                    if (ddr_init_done && (req_toggle_d2 != req_seen_ddr)) begin
                        req_seen_ddr      <= req_toggle_d2;
                        request_line_ddr  <= req_line_pix;
                        request_bank_ddr  <= req_bank_pix;
                        request_epoch_ddr <= req_epoch_pix;
                        native_addr       <= {requested_base[29:5], 3'b000} +
                                             ({18'd0, req_line_pix} << 9) +
                                             ({18'd0, req_line_pix} << 7);
                        burst_index <= 3'd0;
                        d_state     <= D_AR;
                    end
                end

                D_AR: begin
                    if (fb_arvalid && fb_arready) begin
                        rx_index <= 4'd0;
                        d_state  <= D_RECV;
                    end
                end

                D_RECV: begin
                    if (fb_rvalid) begin
                        burst_mem[rx_index] <= fb_rdata;
                        if (fb_rid != FB_ID)
                            dma_error_ddr <= 1'b1;
                        if (fb_rlast) begin
                            if (rx_index != 4'd15)
                                dma_error_ddr <= 1'b1;
                            drain_index <= 4'd0;
                            d_state     <= D_SEND;
                        end else if (rx_index == 4'd15) begin
                            dma_error_ddr <= 1'b1;
                        end else begin
                            rx_index <= rx_index + 4'd1;
                        end
                    end
                end

                D_SEND: begin
                    if (data_ack_d2 == data_toggle_ddr) begin
                        data_payload_ddr <= burst_mem[drain_index];
                        data_word_ddr    <= {burst_index, 4'b0000} +
                                            drain_index;
                        data_bank_ddr    <= request_bank_ddr;
                        data_toggle_ddr  <= ~data_toggle_ddr;
                        d_state          <= D_ACK;
                    end
                end

                D_ACK: begin
                    if (data_ack_d2 == data_toggle_ddr) begin
                        if (drain_index == 4'd15) begin
                            if (burst_index == 3'd4) begin
                                done_line_ddr   <= request_line_ddr;
                                done_bank_ddr   <= request_bank_ddr;
                                done_epoch_ddr  <= request_epoch_ddr;
                                done_toggle_ddr <= ~done_toggle_ddr;
                                d_state         <= D_IDLE;
                            end else begin
                                burst_index <= burst_index + 3'd1;
                                native_addr <= native_addr + 28'd128;
                                d_state     <= D_AR;
                            end
                        end else begin
                            drain_index <= drain_index + 4'd1;
                            d_state     <= D_SEND;
                        end
                    end
                end

                default: d_state <= D_IDLE;
            endcase
        end
    end
endmodule
