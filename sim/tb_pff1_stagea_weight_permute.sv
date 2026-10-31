`timescale 1ns/1ps

module tb_pff1_stagea_weight_permute;
    reg [1023:0] row_major;
    wire [1023:0] packed_weights;
    pff1_stagea_weight_permute dut(.row_major(row_major), .packed_weights(packed_weights));
    integer row, lane, pair, parity, value;
    initial begin
        row_major = 0;
        for (row = 0; row < 4; row = row + 1)
            for (lane = 0; lane < 32; lane = lane + 1)
                row_major[(row * 32 + lane) * 8 +: 8] =
                    (row * 31 + lane * 7 + 13) & 255;
        #1;
        for (pair = 0; pair < 16; pair = pair + 1)
            for (row = 0; row < 4; row = row + 1)
                for (parity = 0; parity < 2; parity = parity + 1) begin
                    value = (row * 31 + (pair * 2 + parity) * 7 + 13) & 255;
                    if (packed_weights[(pair * 8 + row * 2 + parity) * 8 +: 8] !== value[7:0])
                        $fatal(1, "pair=%d row=%d parity=%d", pair, row, parity);
                end
        $display("PFF1_STAGEA_WEIGHT_PERMUTE_PASS bytes=128");
        $finish;
    end
endmodule
