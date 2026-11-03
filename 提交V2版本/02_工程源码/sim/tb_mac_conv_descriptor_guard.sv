`timescale 1ns / 1ps
module tb_mac_conv_descriptor_guard;
    reg [8:0] width=320, height=320;
    reg [15:0] channels=3, output_channels=16;
    reg [2:0] kernel=6, padding=2;
    reg [1:0] stride=2;
    reg [7:0] channel_tile=0;
    reg [5:0] weight_lines=27;
    reg [31:0] input_src=32'h1000_1000;
    reg [31:0] weight_src=32'h1010_0000;
    reg [31:0] output_dst=32'h1020_0000;
    wire valid;
    wire [3:0] error_code;
    wire [8:0] output_width, output_height;
    wire [31:0] input_tensor_bytes, weight_bytes, output_bytes;

    mac_conv_descriptor_guard #(
        .DDR_BASE(32'h1000_0000), .DDR_BYTES(8*1024*1024)
    ) dut (.*);

    task check;
        input condition;
        input [255:0] message;
        begin if (!condition) $fatal(1, "descriptor guard: %0s", message); end
    endtask

    initial begin
        #1;
        check(valid && error_code==0, "first layer rejected");
        check(output_width==160 && output_height==160,
              "first layer output shape wrong");
        check(input_tensor_bytes==409600 && weight_bytes==3456 &&
              output_bytes==409600, "first layer byte budget wrong");
        weight_lines=26; #1;
        check(!valid && error_code==3, "short weight tile accepted");
        weight_lines=27; channel_tile=1; #1;
        check(!valid && error_code==1, "nonexistent channel tile accepted");
        channel_tile=0; input_src=32'h1000_1001; #1;
        check(!valid && error_code==2, "misaligned input accepted");
        input_src=32'h1000_1000;
        output_dst=32'h107f_fffc; #1;
        check(!valid && error_code==2, "output over DDR end accepted");
        output_dst=32'h1020_0000;
        weight_src=input_src; #1;
        check(!valid && error_code==4, "overlapping input and weights accepted");
        weight_src=32'h1010_0000;
        width=1; height=1; channels=4; output_channels=16;
        kernel=1; stride=1; padding=0; weight_lines=1;
        input_src=32'h1000_0ffc;
        output_dst=32'h1020_0000;
        #1;
        check(valid && input_tensor_bytes==4 && weight_bytes==128 &&
              output_bytes==16 && output_width==1 && output_height==1,
              "legacy-shape 1x1 descriptor wrong");
        $display("MAC_CONV_DESCRIPTOR_GUARD_PASS first_input=409600 first_weight=3456 first_output=409600");
        $finish;
    end
endmodule
