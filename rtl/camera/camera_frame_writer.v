`timescale 1ns/1ps

// CMOS2 RGB565 capture to the Pango 256-bit native DDR write port.
//
// A frame is admitted only on a rising VSYNC while enable and
// frame_accept_enable are asserted and stop_request is clear.  The selected
// write buffer is then locked until that frame is either published or dropped.
// Only exact 1280-pixel lines and exact 720-line frames are publishable.
//
// The line RAM has the same asymmetric organization and byte/lane ordering as
// wr_fram_buf in the working HDMI_DDR3_OV5640_100H reference design:
// pixel 0 occupies bits 15:0 of the first 256-bit DDR word, pixel 15 occupies
// bits 255:240.  Two line slots and stable-payload toggle handshakes isolate
// the unrelated camera and DDR clocks.
module camera_frame_writer #(
    parameter [27:0] FB0_NATIVE = 28'h6c80000,
    parameter [27:0] FB1_NATIVE = 28'h6d00000,
    parameter [3:0]  CAMERA_ID  = 4'hc,
    parameter [9:0]  FRAME_LINES = 10'd720,
    parameter [15:0] STOP_QUIET_CYCLES = 16'd32767
) (
    input  wire         pixel_clk,
    input  wire         pixel_resetn,
    input  wire         pixel_vsync,
    input  wire         pixel_line_active,
    input  wire         pixel_valid,
    input  wire [15:0]  pixel_rgb565,

    input  wire         ddr_clk,
    input  wire         ddr_resetn,
    input  wire         enable,
    input  wire         frame_accept_enable,
    input  wire         write_buffer,
    input  wire         stop_request,

    output wire [27:0]  cam_awaddr,
    output wire [3:0]   cam_awid,
    output wire [3:0]   cam_awlen,
    output wire         cam_awvalid,
    input  wire         cam_awready,
    output wire [255:0] cam_wdata,
    output wire [31:0]  cam_wstrb,
    input  wire         cam_wready,
    input  wire [3:0]   cam_wid,
    input  wire         cam_wlast,
    output wire         cam_urgent,

    output reg          frame_started,
    output reg          frame_complete,
    output reg          completed_buffer,
    output reg          busy,
    output wire         idle,
    output reg  [31:0]  bad_line_count,
    output reg  [31:0]  drop_frame_count,
    output reg          ddr_error
);
    localparam [2:0] D_IDLE     = 3'd0;
    localparam [2:0] D_PREFETCH = 3'd1;
    localparam [2:0] D_AW       = 3'd2;
    localparam [2:0] D_WRITE    = 3'd3;

    // ------------------------------------------------------------------
    // Pixel-domain capture and validation.
    // ------------------------------------------------------------------
    reg enable_p1, enable_p2;
    reg accept_p1, accept_p2, accept_p3;
    reg buffer_p1, buffer_p2;
    reg stop_p1, stop_p2;
    reg vsync_d;
    reg line_active_d;

    reg ack0_p1, ack0_p2;
    reg ack1_p1, ack1_p2;
    reg release_p1, release_p2, release_seen_pix;
    reg ack0_ddr, ack1_ddr;
    reg frame_release_toggle_ddr;

    reg frame_slot_busy_pix;
    reg capture_active_pix;
    reg frame_bad_pix;
    reg [9:0] frame_line_count_pix;

    reg line_active_pix;
    reg [10:0] pixel_count_pix;
    reg line_overflow_pix;
    reg line_buffer_ok_pix;
    reg line_bank_pix;
    reg [15:0] first_pixel_pix;

    reg frame_start_toggle_pix;
    reg frame_start_buffer_pix;
    reg frame_end_toggle_pix;
    reg frame_end_valid_pix;
    reg bad_line_toggle_pix;
    reg stop_ack_toggle_pix;
    reg stop_seen_pix;

    reg req0_toggle_pix;
    reg req1_toggle_pix;
    reg [9:0] req0_line_pix;
    reg [9:0] req1_line_pix;

    wire vsync_rise_pix = pixel_vsync && !vsync_d;
    wire line_rise_pix = pixel_line_active && !line_active_d;
    wire line_fall_pix = !pixel_line_active && line_active_d;
    wire pair_write_pix = capture_active_pix && pixel_line_active &&
                          pixel_valid &&
                          line_active_pix && line_buffer_ok_pix &&
                          (pixel_count_pix < 11'd1280) &&
                          pixel_count_pix[0];
    wire [11:0] pair_word_pix = {1'b0, pixel_count_pix[10:1]};
    wire [11:0] ram_wr_addr = line_bank_pix
        ? (12'd640 + pair_word_pix) : pair_word_pix;
    wire [31:0] ram_wr_data = {pixel_rgb565, first_pixel_pix};

    always @(posedge pixel_clk or negedge pixel_resetn) begin
        if (!pixel_resetn) begin
            enable_p1              <= 1'b0;
            enable_p2              <= 1'b0;
            accept_p1              <= 1'b0;
            accept_p2              <= 1'b0;
            accept_p3              <= 1'b0;
            buffer_p1              <= 1'b0;
            buffer_p2              <= 1'b0;
            stop_p1                <= 1'b0;
            stop_p2                <= 1'b0;
            vsync_d                <= 1'b0;
            line_active_d          <= 1'b0;
            ack0_p1                <= 1'b0;
            ack0_p2                <= 1'b0;
            ack1_p1                <= 1'b0;
            ack1_p2                <= 1'b0;
            release_p1             <= 1'b0;
            release_p2             <= 1'b0;
            release_seen_pix       <= 1'b0;
            frame_slot_busy_pix    <= 1'b0;
            capture_active_pix     <= 1'b0;
            frame_bad_pix          <= 1'b0;
            frame_line_count_pix   <= 10'd0;
            line_active_pix        <= 1'b0;
            pixel_count_pix        <= 11'd0;
            line_overflow_pix      <= 1'b0;
            line_buffer_ok_pix     <= 1'b0;
            line_bank_pix          <= 1'b0;
            first_pixel_pix        <= 16'd0;
            frame_start_toggle_pix <= 1'b0;
            frame_start_buffer_pix <= 1'b0;
            frame_end_toggle_pix   <= 1'b0;
            frame_end_valid_pix    <= 1'b0;
            bad_line_toggle_pix    <= 1'b0;
            stop_ack_toggle_pix    <= 1'b0;
            stop_seen_pix          <= 1'b0;
            req0_toggle_pix        <= 1'b0;
            req1_toggle_pix        <= 1'b0;
            req0_line_pix          <= 10'd0;
            req1_line_pix          <= 10'd0;
        end else begin
            enable_p1  <= enable;
            enable_p2  <= enable_p1;
            accept_p1  <= frame_accept_enable;
            accept_p2  <= accept_p1;
            accept_p3  <= accept_p2;
            buffer_p1  <= write_buffer;
            buffer_p2  <= buffer_p1;
            stop_p1    <= stop_request;
            stop_p2    <= stop_p1;
            vsync_d    <= pixel_vsync;
            line_active_d <= pixel_line_active;
            ack0_p1    <= ack0_ddr;
            ack0_p2    <= ack0_p1;
            ack1_p1    <= ack1_ddr;
            ack1_p2    <= ack1_p1;
            release_p1 <= frame_release_toggle_ddr;
            release_p2 <= release_p1;

            if (!stop_p2)
                stop_seen_pix <= 1'b0;

            // Stop is acknowledged in the pixel domain before the DDR domain
            // releases this frame slot.  Abort immediately even if HREF is
            // stuck high: the partial line is not submitted and a later HREF
            // falling edge cannot create a stale request for the next session.
            if (stop_p2 && !stop_seen_pix) begin
                stop_seen_pix          <= 1'b1;
                stop_ack_toggle_pix    <= ~stop_ack_toggle_pix;
                line_active_pix        <= 1'b0;
                pixel_count_pix        <= 11'd0;
                line_overflow_pix      <= 1'b0;
                line_buffer_ok_pix     <= 1'b0;
                if (capture_active_pix) begin
                    frame_end_valid_pix  <= 1'b0;
                    frame_end_toggle_pix <= ~frame_end_toggle_pix;
                    capture_active_pix   <= 1'b0;
                end
            end else if (release_p2 != release_seen_pix) begin
                release_seen_pix    <= release_p2;
                frame_slot_busy_pix <= 1'b0;
                capture_active_pix  <= 1'b0;
                line_active_pix     <= 1'b0;
            end else if (vsync_rise_pix) begin
                line_active_pix    <= 1'b0;
                pixel_count_pix    <= 11'd0;
                line_overflow_pix  <= 1'b0;
                line_buffer_ok_pix <= 1'b0;

                if (frame_slot_busy_pix && capture_active_pix) begin
                    frame_end_valid_pix  <= !frame_bad_pix && !stop_p2 &&
                                            enable_p2 &&
                                            !line_active_pix &&
                                            (frame_line_count_pix == FRAME_LINES);
                    frame_end_toggle_pix <= ~frame_end_toggle_pix;
                    capture_active_pix   <= 1'b0;
                end else if (!frame_slot_busy_pix && enable_p2 && accept_p3 &&
                             !stop_p2) begin
                    frame_slot_busy_pix    <= 1'b1;
                    capture_active_pix     <= 1'b1;
                    frame_bad_pix          <= 1'b0;
                    frame_line_count_pix   <= 10'd0;
                    frame_start_buffer_pix <= buffer_p2;
                    frame_start_toggle_pix <= ~frame_start_toggle_pix;
                end
            end else if (capture_active_pix) begin
                if (line_rise_pix) begin
                    line_active_pix    <= 1'b1;
                    pixel_count_pix    <= pixel_valid ? 11'd1 : 11'd0;
                    line_overflow_pix  <= 1'b0;
                    line_bank_pix      <= frame_line_count_pix[0];
                    if (pixel_valid)
                        first_pixel_pix <= pixel_rgb565;
                    if (frame_line_count_pix[0]) begin
                        line_buffer_ok_pix <=
                            (req1_toggle_pix == ack1_p2);
                        if (req1_toggle_pix != ack1_p2)
                            frame_bad_pix <= 1'b1;
                    end else begin
                        line_buffer_ok_pix <=
                            (req0_toggle_pix == ack0_p2);
                        if (req0_toggle_pix != ack0_p2)
                            frame_bad_pix <= 1'b1;
                    end
                end else if (pixel_line_active && line_active_pix &&
                             pixel_valid) begin
                    if (pixel_count_pix < 11'd1280) begin
                        if (!pixel_count_pix[0])
                            first_pixel_pix <= pixel_rgb565;
                        pixel_count_pix <= pixel_count_pix + 11'd1;
                    end else begin
                        pixel_count_pix   <= 11'd1281;
                        line_overflow_pix <= 1'b1;
                    end
                end else if (line_fall_pix && line_active_pix) begin
                    if ((pixel_count_pix == 11'd1280) &&
                        !line_overflow_pix && line_buffer_ok_pix &&
                        (frame_line_count_pix < FRAME_LINES)) begin
                        if (line_bank_pix) begin
                            req1_line_pix   <= frame_line_count_pix;
                            req1_toggle_pix <= ~req1_toggle_pix;
                        end else begin
                            req0_line_pix   <= frame_line_count_pix;
                            req0_toggle_pix <= ~req0_toggle_pix;
                        end
                    end else begin
                        frame_bad_pix       <= 1'b1;
                        bad_line_toggle_pix <= ~bad_line_toggle_pix;
                    end

                    if (frame_line_count_pix != 10'h3ff)
                        frame_line_count_pix <= frame_line_count_pix + 10'd1;
                    line_active_pix    <= 1'b0;
                    pixel_count_pix    <= 11'd0;
                    line_overflow_pix  <= 1'b0;
                    line_buffer_ok_pix <= 1'b0;
                end
            end
        end
    end

    // ------------------------------------------------------------------
    // Shared asymmetric line RAM.  Slot 0 uses narrow addresses 0..639
    // (wide 0..79); slot 1 uses 640..1279 (wide 80..159).
    // ------------------------------------------------------------------
    reg [8:0] ram_rd_addr;
    wire [255:0] ram_rd_data;

    camera_line_buffer u_camera_line_buffer (
        .wr_data(ram_wr_data),
        .wr_addr(ram_wr_addr),
        .wr_en(pair_write_pix),
        .wr_clk(pixel_clk),
        .wr_rst(!pixel_resetn),
        .rd_data(ram_rd_data),
        .rd_addr(ram_rd_addr),
        .rd_clk(ddr_clk),
        .rd_rst(!ddr_resetn)
    );

    // ------------------------------------------------------------------
    // DDR-domain mailbox synchronization and native burst writer.
    // ------------------------------------------------------------------
    reg start_d1, start_d2, start_seen_ddr;
    reg end_d1, end_d2, end_seen_ddr;
    reg req0_d1, req0_d2;
    reg req1_d1, req1_d2;
    reg bad_d1, bad_d2, bad_seen_ddr;
    reg stop_ack_d1, stop_ack_d2, stop_ack_seen_ddr;

    reg [2:0] d_state;
    reg frame_buffer_ddr;
    reg frame_end_received;
    reg frame_end_valid_ddr;
    reg frame_write_error;
    reg [9:0] expected_line_ddr;
    reg [9:0] written_line_count;

    reg active_line_bank;
    reg active_req_value;
    reg [2:0] burst_index;
    reg [3:0] beat_index;
    reg [27:0] native_addr;

    // Two-entry DDR-clock prefetch FIFO hides the synchronous block-RAM read
    // latency and still supplies one 256-bit word on every asserted WREADY.
    reg [255:0] fifo_word0;
    reg [255:0] fifo_word1;
    reg [1:0] fifo_count;
    reg [4:0] issue_count;
    reg read_pending;
    reg [15:0] stop_quiet_count;
    reg stop_confirmed_ddr;
    reg enable_d;

    wire pending0_ddr = (req0_d2 != ack0_ddr);
    wire pending1_ddr = (req1_d2 != ack1_ddr);
    wire start_event_ddr = (start_d2 != start_seen_ddr);
    wire end_event_ddr = (end_d2 != end_seen_ddr);
    wire bad_event_ddr = (bad_d2 != bad_seen_ddr);
    wire stop_ack_event_ddr = (stop_ack_d2 != stop_ack_seen_ddr);
    wire write_pop = (d_state == D_WRITE) && cam_wready &&
                     (fifo_count != 2'd0);
    wire prefetch_state = (d_state == D_PREFETCH) ||
                          (d_state == D_AW) ||
                          (d_state == D_WRITE);
    wire [2:0] occupied_after_pop = {1'b0, fifo_count} +
                                     {2'd0, read_pending} -
                                     {2'd0, write_pop};
    wire issue_read = prefetch_state && (issue_count < 5'd16) &&
                      (occupied_after_pop < 3'd2);

    assign cam_awaddr  = native_addr;
    assign cam_awid    = CAMERA_ID;
    assign cam_awlen   = 4'd15;
    assign cam_awvalid = (d_state == D_AW);
    assign cam_wdata   = fifo_word0;
    assign cam_wstrb   = 32'hffff_ffff;
    assign cam_urgent  = busy;
    assign idle        = !busy && (d_state == D_IDLE);

    always @(posedge ddr_clk or negedge ddr_resetn) begin
        if (!ddr_resetn) begin
            start_d1                <= 1'b0;
            start_d2                <= 1'b0;
            start_seen_ddr          <= 1'b0;
            end_d1                  <= 1'b0;
            end_d2                  <= 1'b0;
            end_seen_ddr            <= 1'b0;
            req0_d1                 <= 1'b0;
            req0_d2                 <= 1'b0;
            req1_d1                 <= 1'b0;
            req1_d2                 <= 1'b0;
            bad_d1                  <= 1'b0;
            bad_d2                  <= 1'b0;
            bad_seen_ddr            <= 1'b0;
            stop_ack_d1             <= 1'b0;
            stop_ack_d2             <= 1'b0;
            stop_ack_seen_ddr       <= 1'b0;
            ack0_ddr                <= 1'b0;
            ack1_ddr                <= 1'b0;
            frame_release_toggle_ddr<= 1'b0;
            d_state                 <= D_IDLE;
            frame_buffer_ddr        <= 1'b0;
            frame_end_received      <= 1'b0;
            frame_end_valid_ddr     <= 1'b0;
            frame_write_error       <= 1'b0;
            expected_line_ddr       <= 10'd0;
            written_line_count      <= 10'd0;
            active_line_bank        <= 1'b0;
            active_req_value        <= 1'b0;
            burst_index             <= 3'd0;
            beat_index              <= 4'd0;
            native_addr             <= 28'd0;
            ram_rd_addr             <= 9'd0;
            fifo_word0              <= 256'd0;
            fifo_word1              <= 256'd0;
            fifo_count              <= 2'd0;
            issue_count             <= 5'd0;
            read_pending            <= 1'b0;
            stop_quiet_count         <= 16'd0;
            stop_confirmed_ddr       <= 1'b0;
            enable_d                 <= 1'b0;
            frame_started           <= 1'b0;
            frame_complete          <= 1'b0;
            completed_buffer        <= 1'b0;
            busy                    <= 1'b0;
            bad_line_count          <= 32'd0;
            drop_frame_count        <= 32'd0;
            ddr_error               <= 1'b0;
        end else begin
            start_d1 <= frame_start_toggle_pix;
            start_d2 <= start_d1;
            end_d1   <= frame_end_toggle_pix;
            end_d2   <= end_d1;
            req0_d1  <= req0_toggle_pix;
            req0_d2  <= req0_d1;
            req1_d1  <= req1_toggle_pix;
            req1_d2  <= req1_d1;
            bad_d1   <= bad_line_toggle_pix;
            bad_d2   <= bad_d1;
            stop_ack_d1 <= stop_ack_toggle_pix;
            stop_ack_d2 <= stop_ack_d1;
            enable_d <= enable;

            frame_started  <= 1'b0;
            frame_complete <= 1'b0;

            if (enable && !enable_d && !busy && (d_state == D_IDLE)) begin
                bad_line_count   <= 32'd0;
                drop_frame_count <= 32'd0;
                ddr_error        <= 1'b0;
            end

            if (bad_event_ddr) begin
                bad_seen_ddr   <= bad_d2;
                bad_line_count <= bad_line_count + 32'd1;
            end

            if (stop_ack_event_ddr) begin
                stop_ack_seen_ddr <= stop_ack_d2;
                if (busy && stop_request) begin
                    stop_confirmed_ddr <= 1'b1;
                    stop_quiet_count   <= 16'd0;
                end
            end

            if (end_event_ddr) begin
                end_seen_ddr        <= end_d2;
                if (busy) begin
                    frame_end_received  <= 1'b1;
                    frame_end_valid_ddr <= frame_end_valid_pix;
                end
            end

            // Capture one completed synchronous RAM read and optionally pop
            // one native write word in the same cycle.
            case ({read_pending, write_pop})
                2'b01: begin
                    if (fifo_count == 2'd2) begin
                        fifo_word0 <= fifo_word1;
                        fifo_count <= 2'd1;
                    end else begin
                        fifo_count <= 2'd0;
                    end
                end
                2'b10: begin
                    if (fifo_count == 2'd0) begin
                        fifo_word0 <= ram_rd_data;
                        fifo_count <= 2'd1;
                    end else begin
                        fifo_word1 <= ram_rd_data;
                        fifo_count <= 2'd2;
                    end
                end
                2'b11: begin
                    if (fifo_count == 2'd2) begin
                        fifo_word0 <= fifo_word1;
                        fifo_word1 <= ram_rd_data;
                        fifo_count <= 2'd2;
                    end else begin
                        fifo_word0 <= ram_rd_data;
                        fifo_count <= 2'd1;
                    end
                end
                default: begin
                    fifo_count <= fifo_count;
                end
            endcase

            read_pending <= issue_read;
            if (issue_read) begin
                issue_count <= issue_count + 5'd1;
                ram_rd_addr <= ram_rd_addr + 9'd1;
            end

            if (start_event_ddr) begin
                start_seen_ddr       <= start_d2;
                if (!busy && (d_state == D_IDLE) && enable &&
                    !stop_request) begin
                    frame_buffer_ddr    <= frame_start_buffer_pix;
                    frame_end_received  <= 1'b0;
                    frame_end_valid_ddr <= 1'b0;
                    frame_write_error   <= 1'b0;
                    expected_line_ddr   <= 10'd0;
                    written_line_count  <= 10'd0;
                    busy                <= 1'b1;
                    frame_started       <= 1'b1;
                    stop_quiet_count     <= 16'd0;
                    stop_confirmed_ddr   <= 1'b0;
                end else if (!busy) begin
                    drop_frame_count         <= drop_frame_count + 32'd1;
                    frame_release_toggle_ddr <= ~frame_release_toggle_ddr;
                    end_seen_ddr              <= end_d2;
                end else begin
                    ddr_error <= 1'b1;
                end
            end

            case (d_state)
                D_IDLE: begin
                    fifo_count   <= 2'd0;
                    issue_count  <= 5'd0;
                    read_pending <= 1'b0;

                    if (busy && frame_end_received && !stop_request &&
                        (!frame_end_valid_ddr || frame_write_error)) begin
                        if (pending0_ddr) begin
                            ack0_ddr <= req0_d2;
                        end else if (pending1_ddr) begin
                            ack1_ddr <= req1_d2;
                        end else begin
                            drop_frame_count         <= drop_frame_count + 32'd1;
                            busy                     <= 1'b0;
                            frame_end_received       <= 1'b0;
                            frame_release_toggle_ddr <= ~frame_release_toggle_ddr;
                        end
                    end else if (busy && stop_request) begin
                        if (pending0_ddr) begin
                            ack0_ddr        <= req0_d2;
                            stop_quiet_count<= 16'd0;
                        end else if (pending1_ddr) begin
                            ack1_ddr        <= req1_d2;
                            stop_quiet_count<= 16'd0;
                        end else if ((req0_d1 != req0_d2) ||
                                     (req1_d1 != req1_d2) ||
                                     (end_d1 != end_d2)) begin
                            stop_quiet_count <= 16'd0;
                        end else if ((stop_confirmed_ddr &&
                                      frame_end_received &&
                                      (stop_quiet_count >= 16'd4)) ||
                                     (!stop_confirmed_ddr &&
                                      (stop_quiet_count >=
                                       STOP_QUIET_CYCLES))) begin
                            drop_frame_count         <= drop_frame_count + 32'd1;
                            busy                     <= 1'b0;
                            frame_end_received       <= 1'b0;
                            frame_write_error        <= 1'b1;
                            end_seen_ddr              <= end_d2;
                            ack0_ddr                  <= req0_d2;
                            ack1_ddr                  <= req1_d2;
                            stop_quiet_count          <= 16'd0;
                            stop_confirmed_ddr        <= 1'b0;
                            frame_release_toggle_ddr <= ~frame_release_toggle_ddr;
                        end else begin
                            stop_quiet_count <= stop_quiet_count + 16'd1;
                        end
                    end else if (busy && frame_end_received &&
                                 frame_end_valid_ddr &&
                                 (written_line_count == FRAME_LINES) &&
                                 !pending0_ddr && !pending1_ddr) begin
                        frame_complete          <= 1'b1;
                        completed_buffer        <= frame_buffer_ddr;
                        busy                    <= 1'b0;
                        frame_end_received      <= 1'b0;
                        frame_release_toggle_ddr<= ~frame_release_toggle_ddr;
                    end else if (busy && frame_end_received &&
                                 frame_end_valid_ddr &&
                                 (written_line_count < FRAME_LINES) &&
                                 !pending0_ddr && !pending1_ddr) begin
                        frame_write_error <= 1'b1;
                    end else if (busy && pending0_ddr) begin
                        stop_quiet_count <= 16'd0;
                        if (req0_line_pix != expected_line_ddr) begin
                            ack0_ddr          <= req0_d2;
                            frame_write_error <= 1'b1;
                        end else begin
                            active_line_bank <= 1'b0;
                            active_req_value <= req0_d2;
                            burst_index      <= 3'd0;
                            beat_index       <= 4'd0;
                            native_addr      <= (frame_buffer_ddr
                                ? FB1_NATIVE : FB0_NATIVE) +
                                ({18'd0, req0_line_pix} << 9) +
                                ({18'd0, req0_line_pix} << 7);
                            ram_rd_addr <= 9'd0;
                            d_state     <= D_PREFETCH;
                        end
                    end else if (busy && pending1_ddr) begin
                        stop_quiet_count <= 16'd0;
                        if (req1_line_pix != expected_line_ddr) begin
                            ack1_ddr          <= req1_d2;
                            frame_write_error <= 1'b1;
                        end else begin
                            active_line_bank <= 1'b1;
                            active_req_value <= req1_d2;
                            burst_index      <= 3'd0;
                            beat_index       <= 4'd0;
                            native_addr      <= (frame_buffer_ddr
                                ? FB1_NATIVE : FB0_NATIVE) +
                                ({18'd0, req1_line_pix} << 9) +
                                ({18'd0, req1_line_pix} << 7);
                            ram_rd_addr <= 9'd80;
                            d_state     <= D_PREFETCH;
                        end
                    end else begin
                        stop_quiet_count <= 16'd0;
                    end
                end

                D_PREFETCH: begin
                    if (stop_request || (frame_end_received &&
                        (!frame_end_valid_ddr || frame_write_error))) begin
                        if (active_line_bank)
                            ack1_ddr <= active_req_value;
                        else
                            ack0_ddr <= active_req_value;
                        fifo_count   <= 2'd0;
                        issue_count  <= 5'd0;
                        read_pending <= 1'b0;
                        if (stop_request)
                            frame_write_error <= 1'b1;
                        d_state      <= D_IDLE;
                    end else if (fifo_count == 2'd2) begin
                        d_state <= D_AW;
                    end
                end

                D_AW: begin
                    // Once AWVALID is presented, the native write request is
                    // irrevocable: hold both AWVALID and native_addr until
                    // AWREADY accepts it.  A stop may cancel only the earlier
                    // D_PREFETCH state.  After this handshake D_WRITE drains
                    // the accepted burst through WLAST before stopping.
                    if (cam_awvalid && cam_awready) begin
                        beat_index <= 4'd0;
                        d_state    <= D_WRITE;
                    end
                end

                D_WRITE: begin
                    if (write_pop) begin
                        if (cam_wlast != (beat_index == 4'd15)) begin
                            ddr_error         <= 1'b1;
                            frame_write_error <= 1'b1;
                        end
                        if (cam_wlast && (cam_wid != CAMERA_ID)) begin
                            ddr_error         <= 1'b1;
                            frame_write_error <= 1'b1;
                        end

                        if (cam_wlast) begin
                            if ((burst_index == 3'd4) || stop_request ||
                                (frame_end_received &&
                                 (!frame_end_valid_ddr ||
                                  frame_write_error))) begin
                                if (active_line_bank)
                                    ack1_ddr <= active_req_value;
                                else
                                    ack0_ddr <= active_req_value;

                                if ((burst_index == 3'd4) && !stop_request &&
                                    !frame_write_error &&
                                    (beat_index == 4'd15) &&
                                    (cam_wid == CAMERA_ID)) begin
                                    written_line_count <=
                                        written_line_count + 10'd1;
                                    expected_line_ddr <=
                                        expected_line_ddr + 10'd1;
                                end else begin
                                    frame_write_error <= 1'b1;
                                end
                                fifo_count   <= 2'd0;
                                issue_count  <= 5'd0;
                                read_pending <= 1'b0;
                                d_state      <= D_IDLE;
                            end else begin
                                burst_index <= burst_index + 3'd1;
                                native_addr <= native_addr + 28'd128;
                                beat_index  <= 4'd0;
                                fifo_count   <= 2'd0;
                                issue_count  <= 5'd0;
                                read_pending <= 1'b0;
                                d_state      <= D_PREFETCH;
                            end
                        end else if (beat_index != 4'd15) begin
                            beat_index <= beat_index + 4'd1;
                        end
                    end
                end

                default: begin
                    d_state <= D_IDLE;
                end
            endcase
        end
    end
endmodule
