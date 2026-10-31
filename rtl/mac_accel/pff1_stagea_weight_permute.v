`timescale 1ns/1ps

// Reuse the dense MAC's 1024-bit weight assembly register. Its 32 incoming
// DDR words are four consecutive 32-byte PFF1 rows. The pCi=4, pCo=32 core
// wants two adjacent lanes from each of the four rows, repeated 16 times.
// Every output byte is a constant-index wire alias; this module needs no
// registers, muxes, or arithmetic.
module pff1_stagea_weight_permute (
    input wire [1023:0] row_major,
    output wire [1023:0] packed_weights
);
    genvar pair, row, parity;
    generate
        for (pair = 0; pair < 16; pair = pair + 1) begin : g_pair
            for (row = 0; row < 4; row = row + 1) begin : g_row
                for (parity = 0; parity < 2; parity = parity + 1) begin : g_parity
                    assign packed_weights[(pair * 8 + row * 2 + parity) * 8 +: 8] =
                        row_major[(row * 32 + pair * 2 + parity) * 8 +: 8];
                end
            end
        end
    endgenerate
endmodule
