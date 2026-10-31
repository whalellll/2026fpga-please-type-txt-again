`timescale 1ns/1ps

// Self-drawn terminal >_ icon for the 80x64 header slot, encoded as one
// RGB332 byte per pixel by scripts/gen_hdmi_header.ps1.
module header_logo_rom (
    input  wire [12:0] addr,
    input  wire        clk,
    output reg  [7:0]  rgb332
);
    reg [7:0] rom [0:5119];
    initial $readmemh("header_logo_rgb332.hex", rom);
    always @(posedge clk)
        rgb332 <= rom[addr];
endmodule
