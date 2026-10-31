`timescale 1ns/1ps

// Simulation model for the Pango 32-bit-write/256-bit-read dual-clock RAM.
// Eight adjacent 32-bit words form one native DDR word.  This lane ordering
// matches the wr_fram_buf IP used by the working dual-camera reference design.
module camera_line_buffer (
    input  wire [31:0]  wr_data,
    input  wire [11:0]  wr_addr,
    input  wire         wr_en,
    input  wire         wr_clk,
    input  wire         wr_rst,
    output reg  [255:0] rd_data,
    input  wire [8:0]   rd_addr,
    input  wire         rd_clk,
    input  wire         rd_rst
);
    reg [31:0] memory [0:4095];

    always @(posedge wr_clk) begin
        if (wr_en)
            memory[wr_addr] <= wr_data;
    end

    always @(posedge rd_clk or posedge rd_rst) begin
        if (rd_rst) begin
            rd_data <= 256'd0;
        end else begin
            rd_data <= {
                memory[{rd_addr, 3'b111}],
                memory[{rd_addr, 3'b110}],
                memory[{rd_addr, 3'b101}],
                memory[{rd_addr, 3'b100}],
                memory[{rd_addr, 3'b011}],
                memory[{rd_addr, 3'b010}],
                memory[{rd_addr, 3'b001}],
                memory[{rd_addr, 3'b000}]
            };
        end
    end
endmodule
