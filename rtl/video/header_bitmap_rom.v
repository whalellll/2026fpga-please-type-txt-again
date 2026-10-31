`timescale 1ns/1ps

// Packed 384x64 monochrome header bitmap, eight horizontal pixels per byte.
// The generated asset contains the fixed CONSOLE/Chinese HDMI title.
// The colour terminal icon has a separate ROM.
module header_bitmap_rom (
    input  wire        clk,
    input  wire [11:0] addr,
    output reg  [7:0]  bits
);
    reg [7:0] rom [0:3071];
    initial $readmemh("header_bitmap.hex", rom);
    always @(posedge clk)
        bits <= rom[addr];
endmodule
