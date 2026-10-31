// Combinational validation for a single NHWC4 convolution layer descriptor.
// Byte counts include all channel tiles. The DMA may execute one tile at a
// time, but each descriptor must describe ranges valid for the whole tensor.
module mac_conv_descriptor_guard #(
    parameter [31:0] DDR_BASE = 32'h0000_0000,
    parameter integer DDR_BYTES = 256 * 1024 * 1024
) (
    input wire [8:0] width,
    input wire [8:0] height,
    input wire [15:0] channels,
    input wire [15:0] output_channels,
    input wire [2:0] kernel,
    input wire [1:0] stride,
    input wire [2:0] padding,
    input wire [7:0] channel_tile,
    input wire [5:0] weight_lines,
    input wire [31:0] input_src,
    input wire [31:0] weight_src,
    input wire [31:0] output_dst,
    output wire valid,
    output reg [3:0] error_code,
    output wire [8:0] output_width,
    output wire [8:0] output_height,
    output wire [31:0] input_tensor_bytes,
    output wire [31:0] weight_bytes,
    output wire [31:0] output_bytes
);
    localparam [32:0] DDR_LIMIT = {1'b0, DDR_BASE} + DDR_BYTES;
    wire [15:0] channel_tiles = (channels + 16'd3) >> 2;
    wire [10:0] padded_width = {2'b0, width} + ({8'b0, padding} << 1);
    wire [10:0] padded_height = {2'b0, height} + ({8'b0, padding} << 1);
    wire [10:0] width_span = padded_width - kernel;
    wire [10:0] height_span = padded_height - kernel;
    assign output_width = padded_width < kernel ? 9'd0 :
                          (stride == 2 ? (width_span >> 1) : width_span) + 11'd1;
    assign output_height = padded_height < kernel ? 9'd0 :
                           (stride == 2 ? (height_span >> 1) : height_span) + 11'd1;
    wire [31:0] flattened_k = channels * kernel * kernel;
    wire [31:0] needed_weight_lines = (flattened_k + 32'd3) >> 2;
    assign input_tensor_bytes = width * height * channel_tiles * 32'd4;
    assign weight_bytes = {26'b0, weight_lines} << 7;
    assign output_bytes = output_width * output_height * output_channels;
    wire [32:0] input_end = {1'b0, input_src} + {1'b0, input_tensor_bytes};
    wire [32:0] weight_end = {1'b0, weight_src} + {1'b0, weight_bytes};
    wire [32:0] output_end = {1'b0, output_dst} + {1'b0, output_bytes};
    wire input_weight_overlap = {1'b0, input_src} < weight_end &&
                                {1'b0, weight_src} < input_end;
    wire input_output_overlap = {1'b0, input_src} < output_end &&
                                {1'b0, output_dst} < input_end;
    wire weight_output_overlap = {1'b0, weight_src} < output_end &&
                                 {1'b0, output_dst} < weight_end;
    assign valid = error_code == 0;

    always @* begin
        error_code = 0;
        if (width == 0 || width > 320 || height == 0 || height > 320 ||
            channels == 0 || channels > 1024 ||
            output_channels == 0 || output_channels > 256 ||
            (kernel != 1 && kernel != 3 && kernel != 6) ||
            (stride != 1 && stride != 2) || padding >= kernel ||
            (kernel == 1 && padding != 0) ||
            padded_width < kernel || padded_height < kernel ||
            {8'b0, channel_tile} >= channel_tiles)
            error_code = 1;
        else if (weight_lines == 0 || weight_lines > 32 ||
                 needed_weight_lines != weight_lines)
            error_code = 3;
        else if (input_src[1:0] != 0 || weight_src[1:0] != 0 ||
                 output_dst[1:0] != 0 ||
                 {1'b0, input_src} < {1'b0, DDR_BASE} ||
                 {1'b0, weight_src} < {1'b0, DDR_BASE} ||
                 {1'b0, output_dst} < {1'b0, DDR_BASE} ||
                 input_end > DDR_LIMIT || weight_end > DDR_LIMIT ||
                 output_end > DDR_LIMIT)
            error_code = 2;
        else if (input_weight_overlap || input_output_overlap ||
                 weight_output_overlap)
            error_code = 4;
    end
endmodule
