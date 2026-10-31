`timescale 1ns/1ps

// Hardware terminal fed from accepted LiteUART TX writes.
//
// The system-clock side receives exactly the bytes sent to the physical
// serial port.  A small gray-pointer FIFO crosses those bytes into the HDMI
// pixel domain.  The pixel side implements the terminal controls needed by
// the bootloader, OpenSBI, Linux printk and a BusyBox shell: CR/LF, tab,
// non-destructive backspace and the common ANSI CSI cursor controls.
//
// Twenty 80-column logical rows are stored as a ring of 32 physical rows.
// Scrolling therefore changes one row pointer and clears only the new bottom
// line; Linux output can never stall on a full-screen memory copy.
module uart_console_text (
    input  wire       sys_clk,
    input  wire       sys_resetn,
    input  wire       char_valid,
    input  wire [7:0] char_data,

    input  wire       pix_clk,
    input  wire       pix_resetn,
    input  wire [4:0] rd_row,
    input  wire [6:0] rd_col,
    output reg  [7:0] rd_data,
    output wire [11:0] cursor_cell,
    output reg        fifo_overflow
);
    localparam integer FIFO_AW = 5;
    localparam integer FIFO_PW = FIFO_AW + 1;
    localparam integer FIFO_DEPTH = 1 << FIFO_AW;
    localparam [1:0] PARSE_NORMAL = 2'd0;
    localparam [1:0] PARSE_ESC    = 2'd1;
    localparam [1:0] PARSE_CSI    = 2'd2;

    reg [7:0] fifo_mem [0:FIFO_DEPTH-1];
    reg [FIFO_PW-1:0] wbin, wgray, rbin, rgray;
    reg [FIFO_PW-1:0] rgray_s1, rgray_s2;
    reg [FIFO_PW-1:0] wgray_s1, wgray_s2;

    wire [FIFO_PW-1:0] wbin_next = wbin + {{(FIFO_PW-1){1'b0}}, 1'b1};
    wire [FIFO_PW-1:0] wgray_next = (wbin_next >> 1) ^ wbin_next;
    wire [FIFO_PW-1:0] rbin_next = rbin + {{(FIFO_PW-1){1'b0}}, 1'b1};
    wire [FIFO_PW-1:0] rgray_next = (rbin_next >> 1) ^ rbin_next;
    wire fifo_full = wgray_next ==
                     {~rgray_s2[FIFO_PW-1:FIFO_PW-2],
                       rgray_s2[FIFO_PW-3:0]};
    wire fifo_empty = (rgray == wgray_s2);
    wire [7:0] fifo_byte = fifo_mem[rbin[FIFO_AW-1:0]];

    always @(posedge sys_clk) begin
        if (!sys_resetn) begin
            wbin          <= {FIFO_PW{1'b0}};
            wgray         <= {FIFO_PW{1'b0}};
            rgray_s1      <= {FIFO_PW{1'b0}};
            rgray_s2      <= {FIFO_PW{1'b0}};
            fifo_overflow <= 1'b0;
        end else begin
            rgray_s1 <= rgray;
            rgray_s2 <= rgray_s1;
            if (char_valid) begin
                if (!fifo_full) begin
                    fifo_mem[wbin[FIFO_AW-1:0]] <= char_data;
                    wbin  <= wbin_next;
                    wgray <= wgray_next;
                end else begin
                    fifo_overflow <= 1'b1;
                end
            end
        end
    end

    // 32 physical rows x 128 bytes.  Only columns 0..79 and rows 0..19 are
    // displayed; power-of-two strides make the ring mapping inexpensive.
    reg [7:0] text_ram [0:4095] /* synthesis syn_ramstyle="block_ram" */;
    reg [4:0] top_row;
    reg [4:0] cursor_row;
    reg [6:0] cursor_col;
    reg [1:0] parse_state;
    reg [7:0] csi_param;
    reg       csi_seen;

    reg       clear_all_active;
    reg [11:0] clear_addr;
    reg       clear_line_active;
    reg [4:0] clear_phys_row;
    reg [6:0] clear_col;
    reg [6:0] clear_last_col;

    wire [5:0] read_row_sum = {1'b0, top_row} + {1'b0, rd_row};
    wire [4:0] read_phys_row = (read_row_sum >= 6'd20)
                             ? read_row_sum - 6'd20 : read_row_sum[4:0];
    wire [11:0] read_addr = {read_phys_row, 7'b0} + {5'b0, rd_col};

    wire [5:0] write_row_sum = {1'b0, top_row} + {1'b0, cursor_row};
    wire [4:0] write_phys_row = (write_row_sum >= 6'd20)
                              ? write_row_sum - 6'd20 : write_row_sum[4:0];
    wire [11:0] write_addr = {write_phys_row, 7'b0} + {5'b0, cursor_col};
    wire [11:0] line_clear_addr = {clear_phys_row, 7'b0} + {5'b0, clear_col};

    assign cursor_cell = {cursor_row, cursor_col};

    always @(posedge pix_clk) begin
        if (!pix_resetn) begin
            rbin              <= {FIFO_PW{1'b0}};
            rgray             <= {FIFO_PW{1'b0}};
            wgray_s1          <= {FIFO_PW{1'b0}};
            wgray_s2          <= {FIFO_PW{1'b0}};
            rd_data           <= 8'h20;
            top_row           <= 5'd0;
            cursor_row        <= 5'd0;
            cursor_col        <= 7'd0;
            parse_state       <= PARSE_NORMAL;
            csi_param         <= 8'd0;
            csi_seen          <= 1'b0;
            clear_all_active  <= 1'b1;
            clear_addr        <= 12'd0;
            clear_line_active <= 1'b0;
            clear_phys_row    <= 5'd0;
            clear_col         <= 7'd0;
            clear_last_col    <= 7'd79;
        end else begin
            wgray_s1 <= wgray;
            wgray_s2 <= wgray_s1;
            rd_data  <= text_ram[read_addr];

            if (clear_all_active) begin
                text_ram[clear_addr] <= 8'h20;
                if (clear_addr == 12'hfff) begin
                    clear_all_active <= 1'b0;
                    clear_addr       <= 12'd0;
                end else begin
                    clear_addr <= clear_addr + 12'd1;
                end
            end else if (clear_line_active) begin
                text_ram[line_clear_addr] <= 8'h20;
                if (clear_col == clear_last_col) begin
                    clear_line_active <= 1'b0;
                    clear_col         <= 7'd0;
                end else begin
                    clear_col <= clear_col + 7'd1;
                end
            end else if (!fifo_empty) begin
                rbin  <= rbin_next;
                rgray <= rgray_next;

                case (parse_state)
                    PARSE_NORMAL: begin
                        if (fifo_byte == 8'h1b) begin
                            parse_state <= PARSE_ESC;
                        end else if (fifo_byte == 8'h0d) begin
                            cursor_col <= 7'd0;
                        end else if (fifo_byte == 8'h0a) begin
                            cursor_col <= 7'd0;
                            if (cursor_row == 5'd19) begin
                                top_row <= (top_row == 5'd19)
                                         ? 5'd0 : top_row + 5'd1;
                                clear_phys_row    <= top_row;
                                clear_col         <= 7'd0;
                                clear_last_col    <= 7'd79;
                                clear_line_active <= 1'b1;
                            end else begin
                                cursor_row <= cursor_row + 5'd1;
                            end
                        end else if (fifo_byte == 8'h08) begin
                            // Linux line editors use BS for cursor motion.
                            // Deletion is emitted explicitly as "BS SP BS".
                            if (cursor_col != 7'd0)
                                cursor_col <= cursor_col - 7'd1;
                        end else if (fifo_byte == 8'h7f) begin
                            // DEL has no display effect on terminal output.
                        end else if (fifo_byte == 8'h09) begin
                            if (cursor_col < 7'd72)
                                cursor_col <= (cursor_col + 7'd8) & 7'h78;
                            else
                                cursor_col <= 7'd79;
                        end else if ((fifo_byte >= 8'h20) &&
                                     (fifo_byte <= 8'h7e)) begin
                            text_ram[write_addr] <= fifo_byte;
                            if (cursor_col == 7'd79) begin
                                cursor_col <= 7'd0;
                                if (cursor_row == 5'd19) begin
                                    top_row <= (top_row == 5'd19)
                                             ? 5'd0 : top_row + 5'd1;
                                    clear_phys_row    <= top_row;
                                    clear_col         <= 7'd0;
                                    clear_last_col    <= 7'd79;
                                    clear_line_active <= 1'b1;
                                end else begin
                                    cursor_row <= cursor_row + 5'd1;
                                end
                            end else begin
                                cursor_col <= cursor_col + 7'd1;
                            end
                        end
                    end

                    PARSE_ESC: begin
                        if (fifo_byte == "[") begin
                            parse_state <= PARSE_CSI;
                            csi_param   <= 8'd0;
                            csi_seen    <= 1'b0;
                        end else begin
                            parse_state <= PARSE_NORMAL;
                        end
                    end

                    default: begin // PARSE_CSI
                        if ((fifo_byte >= "0") && (fifo_byte <= "9")) begin
                            csi_param <= (csi_param * 8'd10) +
                                         (fifo_byte - "0");
                            csi_seen  <= 1'b1;
                        end else if ((fifo_byte >= 8'h40) &&
                                     (fifo_byte <= 8'h7e)) begin
                            // Missing or zero relative-motion parameters mean
                            // one cell.  Clamp motion to the 80x20 viewport.
                            if (fifo_byte == "A") begin
                                if ((!csi_seen) || (csi_param == 8'd0)) begin
                                    if (cursor_row != 5'd0)
                                        cursor_row <= cursor_row - 5'd1;
                                end else if (csi_param >= {3'd0, cursor_row}) begin
                                    cursor_row <= 5'd0;
                                end else begin
                                    cursor_row <= cursor_row - csi_param[4:0];
                                end
                            end else if (fifo_byte == "B") begin
                                if ((!csi_seen) || (csi_param == 8'd0)) begin
                                    if (cursor_row != 5'd19)
                                        cursor_row <= cursor_row + 5'd1;
                                end else if (csi_param >=
                                             (8'd19 - {3'd0, cursor_row})) begin
                                    cursor_row <= 5'd19;
                                end else begin
                                    cursor_row <= cursor_row + csi_param[4:0];
                                end
                            end else if (fifo_byte == "C") begin
                                if ((!csi_seen) || (csi_param == 8'd0)) begin
                                    if (cursor_col != 7'd79)
                                        cursor_col <= cursor_col + 7'd1;
                                end else if (csi_param >=
                                             (8'd79 - {1'b0, cursor_col})) begin
                                    cursor_col <= 7'd79;
                                end else begin
                                    cursor_col <= cursor_col + csi_param[6:0];
                                end
                            end else if (fifo_byte == "D") begin
                                if ((!csi_seen) || (csi_param == 8'd0)) begin
                                    if (cursor_col != 7'd0)
                                        cursor_col <= cursor_col - 7'd1;
                                end else if (csi_param >= {1'b0, cursor_col}) begin
                                    cursor_col <= 7'd0;
                                end else begin
                                    cursor_col <= cursor_col - csi_param[6:0];
                                end
                            end else if ((fifo_byte == "H") || (fifo_byte == "f")) begin
                                cursor_row <= 5'd0;
                                cursor_col <= 7'd0;
                            end else if ((fifo_byte == "J") &&
                                         ((csi_seen &&
                                           (csi_param == 8'd2)) ||
                                          (((!csi_seen) ||
                                            (csi_param == 8'd0)) &&
                                           (cursor_row == 5'd0) &&
                                           (cursor_col == 7'd0)))) begin
                                top_row          <= 5'd0;
                                cursor_row       <= 5'd0;
                                cursor_col       <= 7'd0;
                                clear_addr       <= 12'd0;
                                clear_all_active <= 1'b1;
                            end else if (fifo_byte == "K") begin
                                clear_phys_row    <= write_phys_row;
                                if ((!csi_seen) || (csi_param == 8'd0)) begin
                                    clear_col         <= cursor_col;
                                    clear_last_col    <= 7'd79;
                                    clear_line_active <= 1'b1;
                                end else if (csi_param == 8'd1) begin
                                    clear_col         <= 7'd0;
                                    clear_last_col    <= cursor_col;
                                    clear_line_active <= 1'b1;
                                end else if (csi_param == 8'd2) begin
                                    clear_col         <= 7'd0;
                                    clear_last_col    <= 7'd79;
                                    clear_line_active <= 1'b1;
                                end
                            end
                            parse_state <= PARSE_NORMAL;
                            csi_param   <= 8'd0;
                            csi_seen    <= 1'b0;
                        end
                    end
                endcase
            end
        end
    end
endmodule

