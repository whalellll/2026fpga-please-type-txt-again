`timescale 1ns / 1ps

// 8x16 bitmap font ROM for the text plane.
//
// The memory is organised as 2048 bytes addressed by {ascii[6:0], row[3:0]}:
// one 16-byte glyph per ASCII code, bit 7 = leftmost pixel.  Glyphs for
// ASCII 0x20..0x7F come from font8x16.hex (generated from Consolas by
// scripts/gen_font.ps1); codes below 0x20 and 0x7F are blank so control
// characters and high-ANSI bytes never draw garbage.
module font_rom (
    input  wire        clk,
    input  wire [10:0] addr,   // {ascii[6:0], row[3:0]}
    output reg  [7:0]  bits    // registered ROM output, 1 cycle latency
);

    reg [7:0] rom [0:2047];

    initial $readmemh("font8x16.hex", rom);

    always @(posedge clk) begin
        bits <= rom[addr];
    end

endmodule
