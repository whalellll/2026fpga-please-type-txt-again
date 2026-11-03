`timescale 1ns/1ps

module tb_fp8_e4m3_q8_exhaustive;
    reg [7:0] encoded;
    wire [17:0] actual;
    reg [17:0] expected;
    integer code;
    integer exponent;
    integer fraction;
    integer magnitude;

    Fp8E4M3ToQ8 dut(.io_in(encoded), .io_out(actual));

    initial begin
        for (code = 0; code < 256; code = code + 1) begin
            encoded = code[7:0];
            exponent = (code >> 3) & 15;
            fraction = code & 7;
            if (exponent == 0)
                magnitude = (fraction + 1) >> 1;
            else if (exponent == 1)
                magnitude = (9 + fraction) >> 1;
            else if (exponent == 15 && fraction == 7)
                magnitude = 0;
            else
                magnitude = (8 + fraction) << (exponent - 2);
            expected = code[7] ? -magnitude : magnitude;
            #1;
            if (actual !== expected)
                $fatal(1, "FP8 decode mismatch code=%02x actual=%05x expected=%05x",
                       code[7:0], actual, expected);
        end
        $display("FP8_E4M3_Q8_EXHAUSTIVE_PASS cases=256");
        $finish;
    end
endmodule
