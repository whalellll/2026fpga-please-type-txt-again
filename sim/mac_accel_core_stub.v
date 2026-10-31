`timescale 1ns / 1ps

module MacAccelCore #(
    parameter COMPACT_S16_OUTPUT = 0,
    parameter integer WEIGHT_BANK_LINES = 1024,
    parameter ENABLE_FP8 = 1,
    parameter BIAS_WORD_WRITE = 0,
    parameter WEIGHT_WORD_WRITE = 0
) (
    input  wire         io_clk,
    input  wire         io_rstN,
    input  wire         io_start,
    output reg          io_busy,
    output reg          io_done,
    input  wire         io_doneClear,
    input  wire [15:0]  io_cfgPixels,
    input  wire [15:0]  io_cfgCin,
    input  wire [15:0]  io_cfgCout,
    input  wire [1:0]   io_cfgComputeMode,
    input  wire [1:0]   io_cfgActivation,
    input  wire [1:0]   io_cfgOutputFormat,
    input  wire [7:0]   io_cfgOutShift,
    input  wire         io_hostInWe,
    input  wire [31:0]  io_hostInWaddr,
    input  wire [63:0]  io_hostInWdata,
    input  wire         io_hostWtWe,
    input  wire [31:0]  io_hostWtWaddr,
    input  wire [1023:0] io_hostWtWdata,
    input  wire         io_hostWtWordWe,
    input  wire [4:0]   io_hostWtWordIndex,
    input  wire [31:0]  io_hostWtWordData,
    input  wire         io_hostBiasWe,
    input  wire [31:0]  io_hostBiasWaddr,
    input  wire [1535:0] io_hostBiasWdata,
    input  wire         io_hostBiasWordWe,
    input  wire         io_hostBiasZeroWe,
    input  wire [5:0]   io_hostBiasWordIndex,
    input  wire [31:0]  io_hostBiasWordData,
    input  wire         io_hostOutRe,
    input  wire [31:0]  io_hostOutRaddr,
    output reg  [31:0]  io_hostOutRdata
);

    reg [2:0] run_count;
    reg [63:0] captured_input;
    reg [1023:0] captured_weight;
    reg [1535:0] captured_bias;
    reg [31:0] captured_input_addr;
    reg [31:0] captured_weight_addr;
    reg [31:0] captured_bias_addr;

    wire unused_cfg = &{1'b0, io_cfgPixels, io_cfgCin, io_cfgCout,
                        io_cfgComputeMode, io_cfgActivation,
                        io_cfgOutputFormat, io_cfgOutShift};

    always @(posedge io_clk) begin
        if (!io_rstN) begin
            io_busy <= 1'b0;
            io_done <= 1'b0;
            io_hostOutRdata <= 32'b0;
            run_count <= 3'b0;
            captured_input <= 64'b0;
            captured_weight <= 1024'b0;
            captured_bias <= 1536'b0;
            captured_input_addr <= 32'b0;
            captured_weight_addr <= 32'b0;
            captured_bias_addr <= 32'b0;
        end else begin
            if (io_doneClear)
                io_done <= 1'b0;

            if (io_hostInWe) begin
                captured_input <= io_hostInWdata;
                captured_input_addr <= io_hostInWaddr;
            end
            if (io_hostWtWe) begin
                captured_weight <= io_hostWtWdata;
                captured_weight_addr <= io_hostWtWaddr;
            end
            if (WEIGHT_WORD_WRITE && io_hostWtWordWe) begin
                captured_weight[io_hostWtWordIndex*32 +: 32] <= io_hostWtWordData;
                captured_weight_addr <= io_hostWtWaddr;
            end
            if (io_hostBiasWe) begin
                captured_bias <= io_hostBiasWdata;
                captured_bias_addr <= io_hostBiasWaddr;
            end
            if (BIAS_WORD_WRITE && io_hostBiasZeroWe) begin
                captured_bias <= 1536'b0;
                captured_bias_addr <= io_hostBiasWaddr;
            end
            if (BIAS_WORD_WRITE && io_hostBiasWordWe && io_hostBiasWordIndex < 6'd48) begin
                captured_bias[io_hostBiasWordIndex*32 +: 32] <= io_hostBiasWordData;
                captured_bias_addr <= io_hostBiasWaddr;
            end
            if (io_hostOutRe)
                io_hostOutRdata <= 32'ha500_0000 | io_hostOutRaddr;

            if (io_start && !io_busy) begin
                io_busy <= 1'b1;
                io_done <= 1'b0;
                run_count <= 3'd4;
            end else if (io_busy) begin
                if (run_count == 3'd1) begin
                    io_busy <= 1'b0;
                    io_done <= 1'b1;
                    run_count <= 3'b0;
                end else begin
                    run_count <= run_count - 3'd1;
                end
            end
        end
    end

endmodule
