`timescale 1ns/1ps

// Owns the two framebuffer banks while a bootloader camera session is active.
// A completed bank is published only after its final native DDR write.  The
// opposite bank is not granted again until HDMI has acknowledged the published
// bank at its own frame boundary.
module camera_buffer_control (
    input  wire        clk,
    input  wire        resetn,
    input  wire        control_enable,
    input  wire        stop_request,
    input  wire        snapshot_hold,

    input  wire        writer_started,
    input  wire        writer_complete,
    input  wire        writer_completed_buffer,
    input  wire        writer_idle,

    input  wire        display_enable,
    input  wire        display_buffer,

    output reg         sensor_enable,
    output reg         frame_accept_enable,
    output reg         write_buffer,
    output reg         frame_valid,
    output reg         published_buffer,
    output wire        idle,
    output wire        stopping,
    output wire        snapshot_ready,
    output reg         snapshot_buffer,
    output reg  [31:0] snapshot_frame_count,
    output reg  [31:0] frame_count
);
    localparam [2:0] S_IDLE         = 3'd0;
    localparam [2:0] S_READY        = 3'd1;
    localparam [2:0] S_WRITING      = 3'd2;
    localparam [2:0] S_WAIT_DISPLAY = 3'd3;
    localparam [2:0] S_STOPPING     = 3'd4;
    localparam [2:0] S_PAUSE_DRAIN  = 3'd5;
    localparam [2:0] S_HELD         = 3'd6;

    reg [2:0] state;
    reg [9:0] pause_quiet;
    reg hold_seen, snapshot_valid;

    assign idle = (state == S_IDLE) && !sensor_enable;
    assign stopping = (state == S_STOPPING) ||
                      (control_enable && stop_request);
    assign snapshot_ready = (state == S_HELD) && snapshot_valid && writer_idle;

    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            state               <= S_IDLE;
            sensor_enable       <= 1'b0;
            frame_accept_enable <= 1'b0;
            write_buffer        <= 1'b0;
            frame_valid         <= 1'b0;
            published_buffer    <= 1'b0;
            frame_count         <= 32'd0;
            pause_quiet         <= 10'd0;
            hold_seen           <= 1'b0;
            snapshot_valid      <= 1'b0;
            snapshot_buffer     <= 1'b0;
            snapshot_frame_count<= 32'd0;
        end else begin
            // Freeze the bank that HDMI was actually scanning when the
            // request arrived.  A writer already in progress targets the
            // other bank and may finish, but cannot change this snapshot.
            if (!snapshot_hold) begin
                hold_seen <= 1'b0;
                snapshot_valid <= 1'b0;
            end else if (!hold_seen) begin
                hold_seen <= 1'b1;
                snapshot_buffer <= display_buffer;
                snapshot_frame_count <= (display_buffer == published_buffer)
                    ? frame_count : frame_count - 32'd1;
                snapshot_valid <= display_enable && frame_valid &&
                    ((display_buffer == published_buffer) ||
                     (frame_count != 32'd1));
            end
            case (state)
                S_IDLE: begin
                    sensor_enable       <= 1'b0;
                    frame_accept_enable <= 1'b0;
                    if (!control_enable)
                        frame_valid <= 1'b0;
                    if (control_enable && !stop_request) begin
                        sensor_enable       <= 1'b1;
                        frame_accept_enable <= 1'b1;
                        write_buffer        <= ~display_buffer;
                        frame_valid         <= 1'b0;
                        published_buffer    <= 1'b0;
                        frame_count         <= 32'd0;
                        state               <= S_READY;
                    end
                end

                S_READY: begin
                    if (!control_enable || stop_request) begin
                        frame_accept_enable <= 1'b0;
                        state               <= S_STOPPING;
                    end else if (writer_started) begin
                        frame_accept_enable <= 1'b0;
                        state               <= S_WRITING;
                    end else if (snapshot_hold) begin
                        // The pixel CDC may still have seen the old grant.
                        // Drain any late frame_start before declaring the
                        // published bank immutable to software.
                        frame_accept_enable <= 1'b0;
                        pause_quiet <= 10'd0;
                        state <= S_PAUSE_DRAIN;
                    end
                end

                S_WRITING: begin
                    if (writer_complete) begin
                        if (control_enable && !stop_request) begin
                            published_buffer <= writer_completed_buffer;
                            frame_valid      <= 1'b1;
                            frame_count      <= frame_count + 32'd1;
                            state            <= S_WAIT_DISPLAY;
                        end else begin
                            state <= S_STOPPING;
                        end
                    end else if (writer_idle) begin
                        // An invalid/aborted frame was drained without being
                        // published.  Retry only while the session remains live.
                        if (control_enable && !stop_request) begin
                            frame_accept_enable <= 1'b1;
                            state               <= S_READY;
                        end else begin
                            state <= S_STOPPING;
                        end
                    end
                end

                S_WAIT_DISPLAY: begin
                    if (!control_enable || stop_request) begin
                        state <= S_STOPPING;
                    end else if (snapshot_hold) begin
                        state <= S_HELD;
                    end else if (display_enable &&
                                 (display_buffer == published_buffer)) begin
                        write_buffer        <= ~published_buffer;
                        frame_accept_enable <= 1'b1;
                        state               <= S_READY;
                    end
                end

                S_PAUSE_DRAIN: begin
                    if (!control_enable || stop_request) begin
                        state <= S_STOPPING;
                    end else if (writer_started || !writer_idle) begin
                        state <= S_WRITING;
                    end else if (!snapshot_hold) begin
                        state <= S_WAIT_DISPLAY;
                    end else if (pause_quiet == 10'd1023) begin
                        state <= S_HELD;
                    end else begin
                        pause_quiet <= pause_quiet + 10'd1;
                    end
                end

                S_HELD: begin
                    if (!control_enable || stop_request)
                        state <= S_STOPPING;
                    else if (!snapshot_hold)
                        state <= S_WAIT_DISPLAY;
                end

                S_STOPPING: begin
                    frame_accept_enable <= 1'b0;
                    if (writer_idle) begin
                        sensor_enable <= 1'b0;
                        state         <= S_IDLE;
                    end
                end

                default: begin
                    state               <= S_IDLE;
                    sensor_enable       <= 1'b0;
                    frame_accept_enable <= 1'b0;
                    frame_valid         <= 1'b0;
                end
            endcase
        end
    end
endmodule
