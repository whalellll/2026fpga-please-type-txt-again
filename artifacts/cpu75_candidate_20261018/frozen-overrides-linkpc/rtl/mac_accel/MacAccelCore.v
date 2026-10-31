module Bank1R1W(
  input         io_clk, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  input         io_rstN, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  input         io_we, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  input  [31:0] io_waddr, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  input  [63:0] io_wdata, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  input         io_re, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  input  [31:0] io_raddr, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  output [63:0] io_rdata // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
);
  reg [63:0] memory [0:1023]; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire  memory_readData_MPORT_en; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire [9:0] memory_readData_MPORT_addr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire [63:0] memory_readData_MPORT_data; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire [63:0] memory_MPORT_data; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire [9:0] memory_MPORT_addr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire  memory_MPORT_mask; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire  memory_MPORT_en; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire  _T_1 = ~io_rstN; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 31:40]
  reg [63:0] readData; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 36:27]
  wire  _T_2 = io_waddr < 32'h400; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 38:28]
  assign memory_readData_MPORT_en = io_re;
  assign memory_readData_MPORT_addr = io_raddr[9:0];
  assign memory_readData_MPORT_data = memory[memory_readData_MPORT_addr]; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  assign memory_MPORT_data = io_wdata;
  assign memory_MPORT_addr = io_waddr[9:0];
  assign memory_MPORT_mask = 1'h1;
  assign memory_MPORT_en = io_we & _T_2;
  assign io_rdata = readData; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 52:14]
  always @(posedge io_clk) begin
    if (memory_MPORT_en & memory_MPORT_mask) begin
      memory[memory_MPORT_addr] <= memory_MPORT_data; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 41:17]
      readData <= 64'h0; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 46:18]
    end else if (io_re) begin // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 36:27]
      readData <= memory_readData_MPORT_data;
    end
  end
endmodule
module Bank1R1W_1(
  input           io_clk, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  input           io_rstN, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  input           io_we, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  input  [31:0]   io_waddr, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  input  [1023:0] io_wdata, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  input           io_re, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  input  [31:0]   io_raddr, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  output [1023:0] io_rdata // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
);
  reg [1023:0] memory [0:1023]; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire  memory_readData_MPORT_en; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire [9:0] memory_readData_MPORT_addr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire [1023:0] memory_readData_MPORT_data; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire [1023:0] memory_MPORT_data; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire [9:0] memory_MPORT_addr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire  memory_MPORT_mask; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire  memory_MPORT_en; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire  _T_1 = ~io_rstN; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 31:40]
  reg [1023:0] readData; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 36:27]
  wire  _T_2 = io_waddr < 32'h400; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 38:28]
  assign memory_readData_MPORT_en = io_re;
  assign memory_readData_MPORT_addr = io_raddr[9:0];
  assign memory_readData_MPORT_data = memory[memory_readData_MPORT_addr]; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  assign memory_MPORT_data = io_wdata;
  assign memory_MPORT_addr = io_waddr[9:0];
  assign memory_MPORT_mask = 1'h1;
  assign memory_MPORT_en = io_we & _T_2;
  assign io_rdata = readData; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 52:14]
  always @(posedge io_clk) begin
    if (memory_MPORT_en & memory_MPORT_mask) begin
      memory[memory_MPORT_addr] <= memory_MPORT_data; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 41:17]
      readData <= 1024'h0; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 46:18]
    end else if (io_re) begin // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 36:27]
      readData <= memory_readData_MPORT_data;
    end
  end
endmodule
// Pikafish boot profile: FC0 is 256 x 32 U8S8, exactly 64 weight lines.
// Keep the original 1024-line block-RAM bank for the generic profile.
module Bank1R1W_1_compact #(parameter WORD_WRITE = 0)(
  input io_clk, io_rstN, io_we, io_re,
  input [31:0] io_waddr, io_raddr,
  input [1023:0] io_wdata,
  input io_wordWe,
  input [4:0] io_wordIndex,
  input [31:0] io_wordData,
  output reg [1023:0] io_rdata
);
  wire [1023:0] write_data;
  wire [1023:0] memory_read_data;
  // Optional DMA word stores preserve the original enabled read latency.
  // The default host interface still writes a complete weight line.
  wire [1023:0] source_data = WORD_WRITE ? {32{io_wordData}} : io_wdata;
  // These two write pairs were the direct register-to-LUTRAM hold paths in
  // consecutive post-route reports. Identity LUTs add no cycle or weight
  // transformation and leave the generic bank untouched.
  assign write_data[1023:930] = source_data[1023:930];
  assign write_data[927:68] = source_data[927:68];
  assign write_data[65:0] = source_data[65:0];
`ifdef SYNTHESIS
  (* PAP_DONT_TOUCH *) GTP_LUT6D #(.INIT(64'hCCCCCCCC_AAAAAAAA)) u_weight_hold_lut_66 (
    .I0(source_data[66]), .I1(source_data[67]),
    .I2(1'b0), .I3(1'b0), .I4(1'b0), .I5(1'b1),
    .Z5(write_data[66]), .Z(write_data[67])
  );
  (* PAP_DONT_TOUCH *) GTP_LUT6D #(.INIT(64'hCCCCCCCC_AAAAAAAA)) u_weight_hold_lut_928 (
    .I0(source_data[928]), .I1(source_data[929]),
    .I2(1'b0), .I3(1'b0), .I4(1'b0), .I5(1'b1),
    .Z5(write_data[928]), .Z(write_data[929])
  );
`else
  assign write_data[67:66] = source_data[67:66];
  assign write_data[929:928] = source_data[929:928];
`endif
  genvar weight_word;
  generate if (WORD_WRITE) begin : g_words
    for (weight_word=0;weight_word<32;weight_word=weight_word+1) begin : g_word
      reg [31:0] memory [0:63] /* synthesis syn_ramstyle="lut_ram" */;
      wire selected = io_wordWe && io_waddr < 32'd64 && io_wordIndex == weight_word;
      always @(posedge io_clk)
        if (selected) memory[io_waddr[5:0]] <= write_data[weight_word*32+:32];
      assign memory_read_data[weight_word*32+:32] = memory[io_raddr[5:0]];
    end
  end else begin : g_wide
    reg [1023:0] memory [0:63] /* synthesis syn_ramstyle="lut_ram" */;
    always @(posedge io_clk)
      if (io_we && io_waddr < 32'd64) memory[io_waddr[5:0]] <= write_data;
    assign memory_read_data = memory[io_raddr[5:0]];
  end endgenerate
  always @(posedge io_clk or negedge io_rstN) begin
    if (!io_rstN) io_rdata <= 1024'b0;
    else if (io_re) io_rdata <= memory_read_data;
  end
endmodule
module Bank1R1W_2(
  input           io_clk, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  input           io_rstN, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  input           io_we, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  input  [31:0]   io_waddr, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  input  [1535:0] io_wdata, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  input           io_re, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  input  [31:0]   io_raddr, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  output [1535:0] io_rdata // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
);
  reg [1535:0] memory [0:15] /* synthesis syn_ramstyle="lut_ram" */; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire  memory_readData_MPORT_en; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire [3:0] memory_readData_MPORT_addr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire [1535:0] memory_readData_MPORT_data; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire [1535:0] memory_MPORT_data; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire [3:0] memory_MPORT_addr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire  memory_MPORT_mask; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire  memory_MPORT_en; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire  _T_1 = ~io_rstN; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 31:40]
  reg [1535:0] readData; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 36:27]
  wire  _T_2 = io_waddr < 32'h10; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 38:28]
  assign memory_readData_MPORT_en = io_re;
  assign memory_readData_MPORT_addr = io_raddr[3:0];
  assign memory_readData_MPORT_data = memory[memory_readData_MPORT_addr]; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
`ifdef SYNTHESIS
  // Preserve two independent identity paths in one dual-output LUT for hold repair.
  genvar pad_pair;
  generate
    for (pad_pair = 0; pad_pair < 768; pad_pair = pad_pair + 1) begin : write_data_pad
      (* PAP_DONT_TOUCH *) GTP_LUT6D #(.INIT(64'hCCCCCCCC_AAAAAAAA)) u_hold_dual_lut (
        .I0(io_wdata[2*pad_pair]), .I1(io_wdata[2*pad_pair+1]),
        .I2(1'b0), .I3(1'b0), .I4(1'b0), .I5(1'b1),
        .Z5(memory_MPORT_data[2*pad_pair]), .Z(memory_MPORT_data[2*pad_pair+1])
      );
    end
  endgenerate
`else
  assign memory_MPORT_data = io_wdata;
`endif
  assign memory_MPORT_addr = io_waddr[3:0];
  assign memory_MPORT_mask = 1'h1;
  assign memory_MPORT_en = io_we & _T_2;
  assign io_rdata = readData; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 52:14]
  always @(posedge io_clk) begin
    if (memory_MPORT_en & memory_MPORT_mask) begin
      memory[memory_MPORT_addr] <= memory_MPORT_data; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 41:17]
      readData <= 1536'h0; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 46:18]
    end else if (io_re) begin // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 36:27]
      readData <= memory_readData_MPORT_data;
    end
  end
endmodule
// DMA-only bias store: accept each DDR word at its final lane position.
// A zero-bias tile still clears all 48 words on one clock edge.
module MacBiasWordBank(
  input           io_clk,
  input           io_rstN,
  input           io_wordWe,
  input           io_zeroWe,
  input  [31:0]   io_waddr,
  input  [5:0]    io_wordIndex,
  input  [31:0]   io_wordData,
  input           io_re,
  input  [31:0]   io_raddr,
  output [1535:0] io_rdata
);
  genvar bias_word;
  generate for (bias_word = 0; bias_word < 48; bias_word = bias_word + 1) begin : g_word
    reg [31:0] memory [0:15] /* synthesis syn_ramstyle="lut_ram" */;
    reg [31:0] read_data;
    wire word_selected = io_wordWe && (io_wordIndex == bias_word);
    always @(posedge io_clk) begin
      if (io_waddr < 32'd16) begin
        if (io_zeroWe)
          memory[io_waddr[3:0]] <= 32'b0;
        else if (word_selected)
          memory[io_waddr[3:0]] <= io_wordData;
      end
    end
    always @(posedge io_clk or negedge io_rstN) begin
      if (!io_rstN)
        read_data <= 32'b0;
      else if (io_re)
        read_data <= memory[io_raddr[3:0]];
    end
    assign io_rdata[bias_word*32 +: 32] = read_data;
  end endgenerate
endmodule
module Bank1R1W_3 #(
  parameter DEPTH = 8192,
  parameter ADDR_BITS = $clog2(DEPTH)
)(
  input         io_clk, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  input         io_rstN, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  input         io_we, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  input  [31:0] io_waddr, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  input  [31:0] io_wdata, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  input         io_re, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  input  [31:0] io_raddr, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
  output [31:0] io_rdata // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 18:14]
);
  reg [31:0] memory [0:DEPTH-1];
  wire  memory_readData_MPORT_en; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire [ADDR_BITS-1:0] memory_readData_MPORT_addr;
  wire [31:0] memory_readData_MPORT_data; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire [31:0] memory_MPORT_data; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire [ADDR_BITS-1:0] memory_MPORT_addr;
  wire  memory_MPORT_mask; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire  memory_MPORT_en; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  wire  _T_1 = ~io_rstN; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 31:40]
  reg [31:0] readData; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 36:27]
  wire  _T_2 = io_waddr < DEPTH;
  assign memory_readData_MPORT_en = io_re;
  assign memory_readData_MPORT_addr = io_raddr[ADDR_BITS-1:0];
  assign memory_readData_MPORT_data = memory[memory_readData_MPORT_addr]; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
  assign memory_MPORT_data = io_wdata;
  assign memory_MPORT_addr = io_waddr[ADDR_BITS-1:0];
  assign memory_MPORT_mask = 1'h1;
  assign memory_MPORT_en = io_we & _T_2;
  assign io_rdata = readData; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 52:14]
  always @(posedge io_clk) begin
    if (memory_MPORT_en & memory_MPORT_mask) begin
      memory[memory_MPORT_addr] <= memory_MPORT_data; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 35:21]
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 41:17]
      readData <= 32'h0; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 46:18]
    end else if (io_re) begin // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 36:27]
      readData <= memory_readData_MPORT_data;
    end
  end
endmodule
module Fp8E4M3ToQ8(
  input  [7:0]  io_in, // @[\\src\\main\\scala\\macaccel\\Fp8E4M3.scala 16:14]
  output [17:0] io_out // @[\\src\\main\\scala\\macaccel\\Fp8E4M3.scala 16:14]
);
  wire  sign = io_in[7]; // @[\\src\\main\\scala\\macaccel\\Fp8E4M3.scala 21:19]
  wire [3:0] exponent = io_in[6:3]; // @[\\src\\main\\scala\\macaccel\\Fp8E4M3.scala 22:23]
  wire [2:0] fraction = io_in[2:0]; // @[\\src\\main\\scala\\macaccel\\Fp8E4M3.scala 23:23]
  wire [3:0] significand = {1'h1,fraction}; // @[\\src\\main\\scala\\macaccel\\Fp8E4M3.scala 24:24]
  // Apply the sign while the rounded significand is only five bits wide.
  // The original 18-bit conditional negator is then unnecessary.
  wire [3:0] subnormal0 = ({1'b0, fraction} + 4'd1) >> 1;
  wire [3:0] subnormal1 = ({1'b0, 1'b1, fraction} + 5'd1) >> 1;
  wire [3:0] base_magnitude = exponent == 4'd0 ? subnormal0 :
                              exponent == 4'd1 ? subnormal1 :
                              (exponent == 4'd15 && fraction == 3'd7) ? 4'd0 : significand;
  wire signed [4:0] signed_base = sign ? -$signed({1'b0, base_magnitude}) :
                                           $signed({1'b0, base_magnitude});
  wire [3:0] shift = exponent < 4'd2 ? 4'd0 : exponent - 4'd2;
  wire signed [17:0] widened = {{13{signed_base[4]}}, signed_base};
  assign io_out = widened <<< shift;
endmodule
module ApmProduct(
  input         io_clk, // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 106:14]
  input         io_rstN, // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 106:14]
  input  [17:0] io_x0, // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 106:14]
  input  [17:0] io_w0, // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 106:14]
  output [47:0] io_result // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 106:14]
);
  wire [47:0] apm_P; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [47:0] apm_CPO; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_COUT; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [29:0] apm_CXO; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [24:0] apm_CXBO; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [29:0] apm_X; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [29:0] apm_CXI; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [24:0] apm_CXBI; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [24:0] apm_XB; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [17:0] apm_Y; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [47:0] apm_Z; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [47:0] apm_CPI; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CIN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [2:0] apm_MODEY; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [3:0] apm_MODEZ; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [4:0] apm_MODEIN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CLK; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEX1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEX2; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEX3; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEXB; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEY1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEY2; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEZ; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEPRE; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEM; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEP; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEMODEY; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEMODEZ; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEMODEIN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTX; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTXB; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTY; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTZ; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTPRE; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTM; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTP; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTMODEY; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTMODEZ; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTMODEIN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [11:0] _x18_T_1 = io_x0[17] ? 12'hfff : 12'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 142:23]
  GTP_APM_E2
    #(.ASYNC_RST(0), .CIN_SEL(0), .CPO_REG(0), .CXO_REG(0), .GRS_EN("FALSE"), .MODEIN_REG(0), .MODEY_REG(0), .MODEZ_REG(0), .MULT_REG(0), .PREADD_REG(0), .P_INIT0(0), .P_INIT1(0), .P_REG(0), .ROUNDMODE_SEL(0), .USE_ACCLOW(0), .USE_MULT(1), .USE_POSTADD(1), .USE_PREADD(0), .USE_SIMD(0), .XB_REG(0), .XB_SEL(0), .X_REG(1), .X_SEL(0), .Y_REG(1), .Z_REG(0))
    apm ( // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
    .P(apm_P),
    .CPO(apm_CPO),
    .COUT(apm_COUT),
    .CXO(apm_CXO),
    .CXBO(apm_CXBO),
    .X(apm_X),
    .CXI(apm_CXI),
    .CXBI(apm_CXBI),
    .XB(apm_XB),
    .Y(apm_Y),
    .Z(apm_Z),
    .CPI(apm_CPI),
    .CIN(apm_CIN),
    .MODEY(apm_MODEY),
    .MODEZ(apm_MODEZ),
    .MODEIN(apm_MODEIN),
    .CLK(apm_CLK),
    .CEX1(apm_CEX1),
    .CEX2(apm_CEX2),
    .CEX3(apm_CEX3),
    .CEXB(apm_CEXB),
    .CEY1(apm_CEY1),
    .CEY2(apm_CEY2),
    .CEZ(apm_CEZ),
    .CEPRE(apm_CEPRE),
    .CEM(apm_CEM),
    .CEP(apm_CEP),
    .CEMODEY(apm_CEMODEY),
    .CEMODEZ(apm_CEMODEZ),
    .CEMODEIN(apm_CEMODEIN),
    .RSTX(apm_RSTX),
    .RSTXB(apm_RSTXB),
    .RSTY(apm_RSTY),
    .RSTZ(apm_RSTZ),
    .RSTPRE(apm_RSTPRE),
    .RSTM(apm_RSTM),
    .RSTP(apm_RSTP),
    .RSTMODEY(apm_RSTMODEY),
    .RSTMODEZ(apm_RSTMODEZ),
    .RSTMODEIN(apm_RSTMODEIN)
  );
  assign io_result = apm_CPO; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 185:15]
  assign apm_X = {_x18_T_1,io_x0}; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 142:18]
  assign apm_CXI = 30'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 146:16]
  assign apm_CXBI = 25'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 147:17]
  assign apm_XB = 25'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 148:15]
  assign apm_Y = io_w0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 145:14]
  assign apm_Z = 48'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 149:14]
  assign apm_CPI = 48'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 150:16]
  assign apm_CIN = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 151:16]
  assign apm_MODEY = 3'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 154:18]
  assign apm_MODEZ = 4'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 155:18]
  assign apm_MODEIN = 5'h2; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 156:19]
  assign apm_CLK = io_clk; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 157:16]
  assign apm_CEX1 = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 158:17]
  assign apm_CEX2 = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 159:17]
  assign apm_CEX3 = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 160:17]
  assign apm_CEXB = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 161:17]
  assign apm_CEY1 = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 162:17]
  assign apm_CEY2 = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 163:17]
  assign apm_CEZ = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 164:16]
  assign apm_CEPRE = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 165:18]
  assign apm_CEM = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 166:16]
  assign apm_CEP = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 167:16]
  assign apm_CEMODEY = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 168:20]
  assign apm_CEMODEZ = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 169:20]
  assign apm_CEMODEIN = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 170:21]
  assign apm_RSTX = ~io_rstN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 173:20]
  assign apm_RSTXB = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 174:18]
  assign apm_RSTY = ~io_rstN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 175:20]
  assign apm_RSTZ = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 176:17]
  assign apm_RSTPRE = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 177:19]
  assign apm_RSTM = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 178:17]
  assign apm_RSTP = ~io_rstN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 179:20]
  assign apm_RSTMODEY = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 180:21]
  assign apm_RSTMODEZ = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 181:21]
  assign apm_RSTMODEIN = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 182:22]
endmodule
module ApmProduct_2(
  input         io_clk, // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 106:14]
  input         io_rstN, // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 106:14]
  input  [17:0] io_x0, // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 106:14]
  input  [17:0] io_w0, // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 106:14]
  input  [47:0] io_cpi, // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 106:14]
  output [47:0] io_result // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 106:14]
);
  wire [47:0] apm_P; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [47:0] apm_CPO; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_COUT; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [29:0] apm_CXO; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [24:0] apm_CXBO; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [29:0] apm_X; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [29:0] apm_CXI; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [24:0] apm_CXBI; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [24:0] apm_XB; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [17:0] apm_Y; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [47:0] apm_Z; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [47:0] apm_CPI; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CIN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [2:0] apm_MODEY; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [3:0] apm_MODEZ; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [4:0] apm_MODEIN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CLK; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEX1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEX2; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEX3; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEXB; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEY1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEY2; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEZ; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEPRE; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEM; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEP; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEMODEY; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEMODEZ; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEMODEIN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTX; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTXB; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTY; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTZ; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTPRE; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTM; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTP; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTMODEY; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTMODEZ; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTMODEIN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [11:0] _x18_T_1 = io_x0[17] ? 12'hfff : 12'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 142:23]
  GTP_APM_E2
    #(.ASYNC_RST(0), .CIN_SEL(0), .CPO_REG(0), .CXO_REG(0), .GRS_EN("FALSE"), .MODEIN_REG(0), .MODEY_REG(0), .MODEZ_REG(0), .MULT_REG(0), .PREADD_REG(0), .P_INIT0(0), .P_INIT1(0), .P_REG(0), .ROUNDMODE_SEL(0), .USE_ACCLOW(0), .USE_MULT(1), .USE_POSTADD(1), .USE_PREADD(0), .USE_SIMD(0), .XB_REG(0), .XB_SEL(0), .X_REG(1), .X_SEL(0), .Y_REG(1), .Z_REG(0))
    apm ( // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
    .P(apm_P),
    .CPO(apm_CPO),
    .COUT(apm_COUT),
    .CXO(apm_CXO),
    .CXBO(apm_CXBO),
    .X(apm_X),
    .CXI(apm_CXI),
    .CXBI(apm_CXBI),
    .XB(apm_XB),
    .Y(apm_Y),
    .Z(apm_Z),
    .CPI(apm_CPI),
    .CIN(apm_CIN),
    .MODEY(apm_MODEY),
    .MODEZ(apm_MODEZ),
    .MODEIN(apm_MODEIN),
    .CLK(apm_CLK),
    .CEX1(apm_CEX1),
    .CEX2(apm_CEX2),
    .CEX3(apm_CEX3),
    .CEXB(apm_CEXB),
    .CEY1(apm_CEY1),
    .CEY2(apm_CEY2),
    .CEZ(apm_CEZ),
    .CEPRE(apm_CEPRE),
    .CEM(apm_CEM),
    .CEP(apm_CEP),
    .CEMODEY(apm_CEMODEY),
    .CEMODEZ(apm_CEMODEZ),
    .CEMODEIN(apm_CEMODEIN),
    .RSTX(apm_RSTX),
    .RSTXB(apm_RSTXB),
    .RSTY(apm_RSTY),
    .RSTZ(apm_RSTZ),
    .RSTPRE(apm_RSTPRE),
    .RSTM(apm_RSTM),
    .RSTP(apm_RSTP),
    .RSTMODEY(apm_RSTMODEY),
    .RSTMODEZ(apm_RSTMODEZ),
    .RSTMODEIN(apm_RSTMODEIN)
  );
  assign io_result = apm_CPO; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 185:15]
  assign apm_X = {_x18_T_1,io_x0}; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 142:18]
  assign apm_CXI = 30'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 146:16]
  assign apm_CXBI = 25'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 147:17]
  assign apm_XB = 25'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 148:15]
  assign apm_Y = io_w0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 145:14]
  assign apm_Z = 48'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 149:14]
  assign apm_CPI = io_cpi; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 150:16]
  assign apm_CIN = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 151:16]
  assign apm_MODEY = 3'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 154:18]
  assign apm_MODEZ = 4'h3; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 155:18]
  assign apm_MODEIN = 5'h2; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 156:19]
  assign apm_CLK = io_clk; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 157:16]
  assign apm_CEX1 = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 158:17]
  assign apm_CEX2 = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 159:17]
  assign apm_CEX3 = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 160:17]
  assign apm_CEXB = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 161:17]
  assign apm_CEY1 = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 162:17]
  assign apm_CEY2 = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 163:17]
  assign apm_CEZ = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 164:16]
  assign apm_CEPRE = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 165:18]
  assign apm_CEM = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 166:16]
  assign apm_CEP = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 167:16]
  assign apm_CEMODEY = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 168:20]
  assign apm_CEMODEZ = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 169:20]
  assign apm_CEMODEIN = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 170:21]
  assign apm_RSTX = ~io_rstN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 173:20]
  assign apm_RSTXB = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 174:18]
  assign apm_RSTY = ~io_rstN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 175:20]
  assign apm_RSTZ = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 176:17]
  assign apm_RSTPRE = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 177:19]
  assign apm_RSTM = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 178:17]
  assign apm_RSTP = ~io_rstN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 179:20]
  assign apm_RSTMODEY = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 180:21]
  assign apm_RSTMODEZ = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 181:21]
  assign apm_RSTMODEIN = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 182:22]
endmodule
module ApmProduct_6(
  input         io_clk, // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 106:14]
  input         io_rstN, // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 106:14]
  input  [17:0] io_x0, // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 106:14]
  input  [17:0] io_w0, // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 106:14]
  input  [47:0] io_cpi, // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 106:14]
  output [47:0] io_result // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 106:14]
);
  wire [47:0] apm_P; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [47:0] apm_CPO; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_COUT; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [29:0] apm_CXO; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [24:0] apm_CXBO; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [29:0] apm_X; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [29:0] apm_CXI; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [24:0] apm_CXBI; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [24:0] apm_XB; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [17:0] apm_Y; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [47:0] apm_Z; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [47:0] apm_CPI; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CIN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [2:0] apm_MODEY; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [3:0] apm_MODEZ; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [4:0] apm_MODEIN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CLK; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEX1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEX2; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEX3; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEXB; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEY1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEY2; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEZ; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEPRE; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEM; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEP; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEMODEY; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEMODEZ; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_CEMODEIN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTX; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTXB; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTY; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTZ; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTPRE; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTM; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTP; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTMODEY; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTMODEZ; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire  apm_RSTMODEIN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
  wire [11:0] _x18_T_1 = io_x0[17] ? 12'hfff : 12'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 142:23]
  GTP_APM_E2
    #(.ASYNC_RST(0), .CIN_SEL(0), .CPO_REG(0), .CXO_REG(0), .GRS_EN("FALSE"), .MODEIN_REG(0), .MODEY_REG(0), .MODEZ_REG(0), .MULT_REG(0), .PREADD_REG(0), .P_INIT0(0), .P_INIT1(0), .P_REG(1), .ROUNDMODE_SEL(0), .USE_ACCLOW(0), .USE_MULT(1), .USE_POSTADD(1), .USE_PREADD(0), .USE_SIMD(0), .XB_REG(0), .XB_SEL(0), .X_REG(1), .X_SEL(0), .Y_REG(1), .Z_REG(0))
    apm ( // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 139:21]
    .P(apm_P),
    .CPO(apm_CPO),
    .COUT(apm_COUT),
    .CXO(apm_CXO),
    .CXBO(apm_CXBO),
    .X(apm_X),
    .CXI(apm_CXI),
    .CXBI(apm_CXBI),
    .XB(apm_XB),
    .Y(apm_Y),
    .Z(apm_Z),
    .CPI(apm_CPI),
    .CIN(apm_CIN),
    .MODEY(apm_MODEY),
    .MODEZ(apm_MODEZ),
    .MODEIN(apm_MODEIN),
    .CLK(apm_CLK),
    .CEX1(apm_CEX1),
    .CEX2(apm_CEX2),
    .CEX3(apm_CEX3),
    .CEXB(apm_CEXB),
    .CEY1(apm_CEY1),
    .CEY2(apm_CEY2),
    .CEZ(apm_CEZ),
    .CEPRE(apm_CEPRE),
    .CEM(apm_CEM),
    .CEP(apm_CEP),
    .CEMODEY(apm_CEMODEY),
    .CEMODEZ(apm_CEMODEZ),
    .CEMODEIN(apm_CEMODEIN),
    .RSTX(apm_RSTX),
    .RSTXB(apm_RSTXB),
    .RSTY(apm_RSTY),
    .RSTZ(apm_RSTZ),
    .RSTPRE(apm_RSTPRE),
    .RSTM(apm_RSTM),
    .RSTP(apm_RSTP),
    .RSTMODEY(apm_RSTMODEY),
    .RSTMODEZ(apm_RSTMODEZ),
    .RSTMODEIN(apm_RSTMODEIN)
  );
  assign io_result = apm_P; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 185:15]
  assign apm_X = {_x18_T_1,io_x0}; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 142:18]
  assign apm_CXI = 30'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 146:16]
  assign apm_CXBI = 25'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 147:17]
  assign apm_XB = 25'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 148:15]
  assign apm_Y = io_w0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 145:14]
  assign apm_Z = 48'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 149:14]
  assign apm_CPI = io_cpi; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 150:16]
  assign apm_CIN = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 151:16]
  assign apm_MODEY = 3'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 154:18]
  assign apm_MODEZ = 4'h3; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 155:18]
  assign apm_MODEIN = 5'h2; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 156:19]
  assign apm_CLK = io_clk; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 157:16]
  assign apm_CEX1 = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 158:17]
  assign apm_CEX2 = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 159:17]
  assign apm_CEX3 = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 160:17]
  assign apm_CEXB = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 161:17]
  assign apm_CEY1 = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 162:17]
  assign apm_CEY2 = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 163:17]
  assign apm_CEZ = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 164:16]
  assign apm_CEPRE = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 165:18]
  assign apm_CEM = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 166:16]
  assign apm_CEP = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 167:16]
  assign apm_CEMODEY = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 168:20]
  assign apm_CEMODEZ = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 169:20]
  assign apm_CEMODEIN = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 170:21]
  assign apm_RSTX = ~io_rstN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 173:20]
  assign apm_RSTXB = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 174:18]
  assign apm_RSTY = ~io_rstN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 175:20]
  assign apm_RSTZ = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 176:17]
  assign apm_RSTPRE = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 177:19]
  assign apm_RSTM = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 178:17]
  assign apm_RSTP = ~io_rstN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 179:20]
  assign apm_RSTMODEY = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 180:21]
  assign apm_RSTMODEZ = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 181:21]
  assign apm_RSTMODEIN = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 182:22]
endmodule
module ApmAccumulator(
  input         io_clk, // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 198:14]
  input         io_rstN, // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 198:14]
  input         io_enable, // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 198:14]
  input         io_clear, // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 198:14]
  input  [47:0] io_addend, // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 198:14]
  output [47:0] io_result // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 198:14]
);
  wire [47:0] apm_P; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire [47:0] apm_CPO; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_COUT; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire [29:0] apm_CXO; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire [24:0] apm_CXBO; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire [29:0] apm_X; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire [29:0] apm_CXI; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire [24:0] apm_CXBI; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire [24:0] apm_XB; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire [17:0] apm_Y; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire [47:0] apm_Z; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire [47:0] apm_CPI; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_CIN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire [2:0] apm_MODEY; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire [3:0] apm_MODEZ; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire [4:0] apm_MODEIN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_CLK; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_CEX1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_CEX2; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_CEX3; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_CEXB; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_CEY1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_CEY2; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_CEZ; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_CEPRE; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_CEM; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_CEP; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_CEMODEY; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_CEMODEZ; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_CEMODEIN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_RSTX; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_RSTXB; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_RSTY; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_RSTZ; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_RSTPRE; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_RSTM; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_RSTP; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_RSTMODEY; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_RSTMODEZ; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire  apm_RSTMODEIN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
  wire [1:0] _apm_io_MODEY_T = io_clear ? 2'h0 : 2'h2; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 229:24]
  GTP_APM_E2
    #(.ASYNC_RST(0), .CIN_SEL(0), .CPO_REG(0), .CXO_REG(0), .GRS_EN("FALSE"), .MODEIN_REG(0), .MODEY_REG(0), .MODEZ_REG(0), .MULT_REG(0), .PREADD_REG(0), .P_INIT0(0), .P_INIT1(0), .P_REG(1), .ROUNDMODE_SEL(0), .USE_ACCLOW(0), .USE_MULT(0), .USE_POSTADD(1), .USE_PREADD(0), .USE_SIMD(0), .XB_REG(0), .XB_SEL(0), .X_REG(0), .X_SEL(0), .Y_REG(0), .Z_REG(0))
    apm ( // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 220:21]
    .P(apm_P),
    .CPO(apm_CPO),
    .COUT(apm_COUT),
    .CXO(apm_CXO),
    .CXBO(apm_CXBO),
    .X(apm_X),
    .CXI(apm_CXI),
    .CXBI(apm_CXBI),
    .XB(apm_XB),
    .Y(apm_Y),
    .Z(apm_Z),
    .CPI(apm_CPI),
    .CIN(apm_CIN),
    .MODEY(apm_MODEY),
    .MODEZ(apm_MODEZ),
    .MODEIN(apm_MODEIN),
    .CLK(apm_CLK),
    .CEX1(apm_CEX1),
    .CEX2(apm_CEX2),
    .CEX3(apm_CEX3),
    .CEXB(apm_CEXB),
    .CEY1(apm_CEY1),
    .CEY2(apm_CEY2),
    .CEZ(apm_CEZ),
    .CEPRE(apm_CEPRE),
    .CEM(apm_CEM),
    .CEP(apm_CEP),
    .CEMODEY(apm_CEMODEY),
    .CEMODEZ(apm_CEMODEZ),
    .CEMODEIN(apm_CEMODEIN),
    .RSTX(apm_RSTX),
    .RSTXB(apm_RSTXB),
    .RSTY(apm_RSTY),
    .RSTZ(apm_RSTZ),
    .RSTPRE(apm_RSTPRE),
    .RSTM(apm_RSTM),
    .RSTP(apm_RSTP),
    .RSTMODEY(apm_RSTMODEY),
    .RSTMODEZ(apm_RSTMODEZ),
    .RSTMODEIN(apm_RSTMODEIN)
  );
  assign io_result = apm_P; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 256:15]
  assign apm_X = 30'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 221:14]
  assign apm_CXI = 30'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 222:16]
  assign apm_CXBI = 25'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 223:17]
  assign apm_XB = 25'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 224:15]
  assign apm_Y = 18'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 225:14]
  assign apm_Z = io_addend; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 226:14]
  assign apm_CPI = 48'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 227:16]
  assign apm_CIN = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 228:16]
  assign apm_MODEY = {{1'd0}, _apm_io_MODEY_T}; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 229:18]
  assign apm_MODEZ = 4'h2; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 230:18]
  assign apm_MODEIN = 5'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 231:19]
  assign apm_CLK = io_clk; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 232:16]
  assign apm_CEX1 = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 233:17]
  assign apm_CEX2 = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 234:17]
  assign apm_CEX3 = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 235:17]
  assign apm_CEXB = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 236:17]
  assign apm_CEY1 = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 237:17]
  assign apm_CEY2 = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 238:17]
  assign apm_CEZ = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 239:16]
  assign apm_CEPRE = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 240:18]
  assign apm_CEM = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 241:16]
  assign apm_CEP = io_enable; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 242:16]
  assign apm_CEMODEY = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 243:20]
  assign apm_CEMODEZ = 1'h1; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 244:20]
  assign apm_CEMODEIN = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 245:21]
  assign apm_RSTX = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 246:17]
  assign apm_RSTXB = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 247:18]
  assign apm_RSTY = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 248:17]
  assign apm_RSTZ = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 249:17]
  assign apm_RSTPRE = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 250:19]
  assign apm_RSTM = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 251:17]
  assign apm_RSTP = ~io_rstN; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 252:20]
  assign apm_RSTMODEY = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 253:21]
  assign apm_RSTMODEZ = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 254:21]
  assign apm_RSTMODEIN = 1'h0; // @[\\src\\main\\scala\\macaccel\\GtpApmE2.scala 255:22]
endmodule
module MacPeArray #(parameter ENABLE_FP8 = 1)(
  input           io_clk, // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 23:14]
  input           io_rstN, // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 23:14]
  input           io_validI, // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 23:14]
  input           io_accClear, // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 23:14]
  input  [1:0]    io_computeMode, // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 23:14]
  input           io_postMode, // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 23:14]
  input  [31:0]   io_laneMask, // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 23:14]
  input  [63:0]   io_x, // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 23:14]
  input  [1023:0] io_w, // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 23:14]
  input  [575:0]  io_postData, // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 23:14]
  output          io_validO, // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 23:14]
  output [1535:0] io_acc, // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 23:14]
  output [1535:0] io_postResult // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 23:14]
);
  wire [7:0] fp8Lo_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_1_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_1_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_1_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_1_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_1_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_1_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_1_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_1_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_1_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_1_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_1_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_1_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_1_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_1_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_1_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_1_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_2_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_2_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_2_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_2_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_2_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_2_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_2_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_2_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_2_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_2_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_2_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_2_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_2_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_2_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_2_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_2_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_3_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_3_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_3_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_3_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_3_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_3_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_3_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_3_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_3_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_3_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_3_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_3_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_3_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_3_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_3_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_3_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_4_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_4_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_4_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_4_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_4_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_4_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_4_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_4_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_4_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_4_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_4_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_4_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_4_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_4_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_5_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_5_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_5_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_5_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_5_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_5_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_5_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_5_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_5_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_5_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_5_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_5_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_5_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_5_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_5_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_5_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_6_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_6_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_6_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_6_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_6_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_6_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_6_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_6_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_6_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_6_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_6_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_6_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_6_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_6_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_6_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_6_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_7_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_7_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_7_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_7_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_7_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_7_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_7_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_7_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_7_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_7_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_7_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_7_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_7_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_7_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_7_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_7_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_8_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_8_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_8_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_8_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_8_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_8_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_8_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_8_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_8_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_8_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_8_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_8_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_8_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_8_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_9_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_9_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_9_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_9_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_9_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_9_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_9_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_9_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_9_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_9_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_9_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_9_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_9_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_9_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_9_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_9_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_10_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_10_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_10_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_10_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_10_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_10_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_10_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_10_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_10_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_10_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_10_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_10_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_10_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_10_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_10_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_10_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_11_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_11_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_11_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_11_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_11_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_11_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_11_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_11_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_11_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_11_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_11_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_11_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_11_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_11_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_11_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_11_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_12_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_12_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_12_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_12_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_12_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_12_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_12_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_12_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_12_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_12_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_12_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_12_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_12_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_12_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_13_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_13_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_13_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_13_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_13_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_13_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_13_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_13_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_13_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_13_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_13_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_13_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_13_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_13_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_13_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_13_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_14_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_14_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_14_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_14_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_14_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_14_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_14_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_14_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_14_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_14_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_14_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_14_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_14_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_14_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_14_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_14_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_15_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_15_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_15_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_15_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_15_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_15_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_15_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_15_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_15_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_15_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_15_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_15_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_15_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_15_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_15_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_15_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_16_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_16_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_16_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_16_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_16_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_16_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_16_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_16_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_16_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_16_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_16_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_16_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_16_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_16_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_17_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_17_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_17_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_17_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_17_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_17_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_17_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_17_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_17_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_17_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_17_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_17_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_17_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_17_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_17_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_17_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_18_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_18_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_18_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_18_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_18_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_18_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_18_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_18_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_18_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_18_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_18_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_18_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_18_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_18_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_18_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_18_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_19_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_19_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_19_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_19_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_19_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_19_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_19_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_19_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_19_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_19_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_19_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_19_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_19_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_19_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_19_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_19_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_20_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_20_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_20_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_20_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_20_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_20_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_20_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_20_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_20_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_20_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_20_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_20_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_20_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_20_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_21_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_21_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_21_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_21_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_21_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_21_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_21_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_21_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_21_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_21_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_21_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_21_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_21_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_21_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_21_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_21_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_22_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_22_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_22_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_22_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_22_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_22_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_22_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_22_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_22_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_22_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_22_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_22_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_22_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_22_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_22_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_22_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_23_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_23_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_23_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_23_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_23_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_23_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_23_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_23_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_23_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_23_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_23_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_23_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_23_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_23_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_23_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_23_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_24_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_24_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_24_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_24_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_24_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_24_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_24_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_24_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_24_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_24_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_24_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_24_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_24_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_24_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_25_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_25_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_25_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_25_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_25_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_25_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_25_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_25_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_25_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_25_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_25_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_25_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_25_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_25_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_25_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_25_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_26_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_26_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_26_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_26_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_26_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_26_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_26_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_26_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_26_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_26_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_26_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_26_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_26_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_26_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_26_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_26_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_27_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_27_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_27_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_27_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_27_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_27_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_27_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_27_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_27_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_27_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_27_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_27_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_27_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_27_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_27_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_27_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_28_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_28_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_28_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_28_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_28_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_28_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_28_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_28_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_28_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_28_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_28_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_28_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_28_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_28_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_29_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_29_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_29_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_29_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_29_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_29_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_29_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_29_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_29_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_29_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_29_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_29_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_29_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_29_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_29_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_29_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_30_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_30_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_30_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_30_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_30_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_30_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_30_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_30_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_30_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_30_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_30_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_30_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_30_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_30_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_30_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_30_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_31_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_31_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_31_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_31_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_31_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_31_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_31_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_31_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_31_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_31_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_31_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_31_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_31_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_31_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_31_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_31_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_32_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_32_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_32_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_32_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_32_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_32_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_32_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_32_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_32_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_32_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_32_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_32_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_32_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_32_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_33_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_33_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_33_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_33_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_33_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_33_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_33_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_33_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_33_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_33_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_33_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_33_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_33_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_33_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_33_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_33_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_34_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_34_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_34_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_34_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_34_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_34_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_34_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_34_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_34_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_34_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_34_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_34_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_34_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_34_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_34_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_34_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_35_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_35_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_35_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_35_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_35_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_35_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_35_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_35_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_35_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_35_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_35_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_35_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_35_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_35_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_35_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_35_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_36_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_36_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_36_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_36_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_36_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_36_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_36_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_36_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_36_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_36_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_36_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_36_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_36_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_36_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_37_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_37_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_37_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_37_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_37_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_37_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_37_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_37_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_37_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_37_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_37_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_37_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_37_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_37_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_37_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_37_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_38_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_38_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_38_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_38_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_38_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_38_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_38_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_38_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_38_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_38_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_38_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_38_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_38_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_38_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_38_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_38_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_39_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_39_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_39_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_39_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_39_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_39_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_39_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_39_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_39_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_39_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_39_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_39_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_39_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_39_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_39_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_39_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_40_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_40_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_40_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_40_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_40_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_40_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_40_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_40_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_40_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_40_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_40_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_40_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_40_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_40_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_41_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_41_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_41_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_41_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_41_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_41_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_41_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_41_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_41_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_41_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_41_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_41_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_41_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_41_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_41_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_41_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_42_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_42_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_42_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_42_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_42_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_42_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_42_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_42_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_42_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_42_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_42_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_42_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_42_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_42_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_42_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_42_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_43_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_43_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_43_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_43_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_43_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_43_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_43_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_43_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_43_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_43_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_43_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_43_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_43_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_43_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_43_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_43_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_44_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_44_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_44_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_44_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_44_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_44_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_44_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_44_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_44_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_44_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_44_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_44_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_44_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_44_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_45_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_45_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_45_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_45_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_45_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_45_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_45_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_45_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_45_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_45_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_45_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_45_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_45_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_45_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_45_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_45_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_46_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_46_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_46_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_46_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_46_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_46_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_46_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_46_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_46_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_46_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_46_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_46_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_46_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_46_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_46_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_46_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_47_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_47_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_47_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_47_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_47_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_47_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_47_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_47_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_47_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_47_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_47_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_47_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_47_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_47_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_47_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_47_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_48_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_48_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_48_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_48_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_48_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_48_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_48_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_48_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_48_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_48_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_48_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_48_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_48_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_48_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_49_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_49_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_49_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_49_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_49_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_49_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_49_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_49_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_49_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_49_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_49_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_49_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_49_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_49_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_49_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_49_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_50_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_50_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_50_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_50_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_50_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_50_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_50_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_50_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_50_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_50_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_50_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_50_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_50_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_50_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_50_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_50_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_51_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_51_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_51_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_51_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_51_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_51_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_51_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_51_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_51_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_51_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_51_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_51_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_51_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_51_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_51_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_51_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_52_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_52_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_52_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_52_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_52_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_52_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_52_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_52_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_52_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_52_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_52_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_52_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_52_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_52_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_53_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_53_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_53_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_53_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_53_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_53_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_53_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_53_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_53_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_53_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_53_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_53_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_53_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_53_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_53_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_53_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_54_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_54_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_54_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_54_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_54_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_54_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_54_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_54_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_54_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_54_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_54_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_54_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_54_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_54_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_54_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_54_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_55_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_55_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_55_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_55_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_55_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_55_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_55_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_55_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_55_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_55_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_55_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_55_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_55_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_55_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_55_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_55_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_56_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_56_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_56_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_56_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_56_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_56_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_56_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_56_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_56_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_56_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_56_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_56_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_56_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_56_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_57_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_57_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_57_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_57_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_57_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_57_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_57_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_57_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_57_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_57_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_57_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_57_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_57_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_57_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_57_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_57_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_58_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_58_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_58_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_58_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_58_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_58_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_58_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_58_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_58_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_58_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_58_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_58_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_58_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_58_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_58_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_58_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_59_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_59_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_59_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_59_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_59_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_59_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_59_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_59_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_59_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_59_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_59_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_59_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_59_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_59_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_59_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_59_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_60_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_60_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_60_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_60_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_60_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_60_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_60_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_60_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_60_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_60_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_60_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_60_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_60_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_60_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_61_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_61_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_61_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_61_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_61_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_61_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_61_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_61_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_61_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_61_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_61_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_61_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_61_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_61_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_61_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_61_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_62_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_62_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_62_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_62_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_62_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_62_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_62_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_62_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_62_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_62_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_62_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_62_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_62_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_62_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_62_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_62_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [7:0] fp8Lo_63_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [17:0] fp8Lo_63_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
  wire [7:0] fp8Hi_63_io_in; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire [17:0] fp8Hi_63_io_out; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
  wire  mLo_63_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mLo_63_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_63_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [17:0] mLo_63_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_63_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire [47:0] mLo_63_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
  wire  mHi_63_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  mHi_63_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_63_io_x0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [17:0] mHi_63_io_w0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_63_io_cpi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire [47:0] mHi_63_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
  wire  accumApmLo_0_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_0_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_0_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_0_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_0_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_0_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_1_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_1_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_1_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_1_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_1_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_1_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_2_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_2_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_2_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_2_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_2_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_2_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_3_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_3_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_3_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_3_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_3_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_3_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_4_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_4_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_4_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_4_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_4_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_4_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_5_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_5_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_5_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_5_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_5_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_5_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_6_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_6_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_6_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_6_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_6_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_6_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_7_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_7_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_7_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_7_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_7_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_7_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_8_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_8_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_8_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_8_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_8_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_8_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_9_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_9_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_9_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_9_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_9_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_9_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_10_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_10_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_10_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_10_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_10_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_10_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_11_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_11_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_11_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_11_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_11_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_11_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_12_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_12_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_12_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_12_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_12_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_12_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_13_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_13_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_13_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_13_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_13_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_13_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_14_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_14_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_14_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_14_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_14_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_14_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_15_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_15_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_15_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmLo_15_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_15_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire [47:0] accumApmLo_15_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
  wire  accumApmHi_0_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_0_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_0_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_0_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_0_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_0_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_1_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_1_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_1_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_1_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_1_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_1_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_2_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_2_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_2_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_2_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_2_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_2_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_3_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_3_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_3_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_3_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_3_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_3_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_4_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_4_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_4_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_4_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_4_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_4_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_5_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_5_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_5_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_5_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_5_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_5_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_6_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_6_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_6_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_6_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_6_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_6_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_7_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_7_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_7_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_7_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_7_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_7_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_8_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_8_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_8_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_8_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_8_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_8_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_9_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_9_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_9_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_9_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_9_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_9_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_10_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_10_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_10_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_10_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_10_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_10_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_11_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_11_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_11_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_11_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_11_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_11_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_12_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_12_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_12_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_12_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_12_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_12_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_13_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_13_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_13_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_13_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_13_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_13_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_14_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_14_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_14_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_14_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_14_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_14_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_15_io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_15_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_15_io_enable; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  accumApmHi_15_io_clear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_15_io_addend; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire [47:0] accumApmHi_15_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
  wire  s16Mode = io_computeMode == 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 57:32]
  wire  signed8Mode = io_computeMode == 2'h1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 58:36]
  wire  fp8Mode = ENABLE_FP8 && io_computeMode == 2'h3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 59:32]
  wire [15:0] xWord = io_x[15:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 62:21]
  wire [1:0] _x16Signed_T_1 = xWord[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 63:29]
  wire [17:0] x16Signed = {_x16Signed_T_1,xWord}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 63:24]
  wire [9:0] _x8Signed_T_1 = xWord[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 64:28]
  wire [17:0] x8Signed = {_x8Signed_T_1,xWord[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 64:23]
  wire [17:0] x8Unsigned = {10'h0,xWord[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 65:25]
  wire [17:0] _regularX_0_T = signed8Mode ? x8Signed : x8Unsigned; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 67:10]
  wire [17:0] regularX_0 = s16Mode ? x16Signed : _regularX_0_T; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 66:24]
  wire [15:0] xWord_1 = io_x[31:16]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 62:21]
  wire [1:0] _x16Signed_T_3 = xWord_1[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 63:29]
  wire [17:0] x16Signed_1 = {_x16Signed_T_3,xWord_1}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 63:24]
  wire [9:0] _x8Signed_T_4 = xWord_1[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 64:28]
  wire [17:0] x8Signed_1 = {_x8Signed_T_4,xWord_1[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 64:23]
  wire [17:0] x8Unsigned_1 = {10'h0,xWord_1[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 65:25]
  wire [17:0] _regularX_1_T = signed8Mode ? x8Signed_1 : x8Unsigned_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 67:10]
  wire [17:0] regularX_1 = s16Mode ? x16Signed_1 : _regularX_1_T; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 66:24]
  wire [15:0] xWord_2 = io_x[47:32]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 62:21]
  wire [1:0] _x16Signed_T_5 = xWord_2[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 63:29]
  wire [17:0] x16Signed_2 = {_x16Signed_T_5,xWord_2}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 63:24]
  wire [9:0] _x8Signed_T_7 = xWord_2[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 64:28]
  wire [17:0] x8Signed_2 = {_x8Signed_T_7,xWord_2[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 64:23]
  wire [17:0] x8Unsigned_2 = {10'h0,xWord_2[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 65:25]
  wire [17:0] _regularX_2_T = signed8Mode ? x8Signed_2 : x8Unsigned_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 67:10]
  wire [17:0] regularX_2 = s16Mode ? x16Signed_2 : _regularX_2_T; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 66:24]
  wire [15:0] xWord_3 = io_x[63:48]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 62:21]
  wire [1:0] _x16Signed_T_7 = xWord_3[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 63:29]
  wire [17:0] x16Signed_3 = {_x16Signed_T_7,xWord_3}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 63:24]
  wire [9:0] _x8Signed_T_10 = xWord_3[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 64:28]
  wire [17:0] x8Signed_3 = {_x8Signed_T_10,xWord_3[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 64:23]
  wire [17:0] x8Unsigned_3 = {10'h0,xWord_3[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 65:25]
  wire [17:0] _regularX_3_T = signed8Mode ? x8Signed_3 : x8Unsigned_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 67:10]
  wire [17:0] regularX_3 = s16Mode ? x16Signed_3 : _regularX_3_T; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 66:24]
  wire [15:0] wWord = io_w[15:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_1 = wWord[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed = {_w16Signed_T_1,wWord}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_1 = wWord[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned = {_w8LoSigned_T_1,wWord[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_1 = wWord[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned = {_w8HiSigned_T_1,wWord[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T = fp8Mode ? fp8Lo_io_out : w8LoSigned; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo = s16Mode ? w16Signed : _regularWLo_T; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T = fp8Mode ? fp8Hi_io_out : w8HiSigned; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi = s16Mode ? 18'h0 : _regularWHi_T; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [17:0] postLo = io_postData[17:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 105:31]
  wire [17:0] postHi = io_postData[35:18]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 107:31]
  wire [15:0] wWord_1 = io_w[31:16]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_3 = wWord_1[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_1 = {_w16Signed_T_3,wWord_1}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_4 = wWord_1[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_1 = {_w8LoSigned_T_4,wWord_1[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_4 = wWord_1[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_1 = {_w8HiSigned_T_4,wWord_1[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_1 = fp8Mode ? fp8Lo_1_io_out : w8LoSigned_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_1 = s16Mode ? w16Signed_1 : _regularWLo_T_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_1 = fp8Mode ? fp8Hi_1_io_out : w8HiSigned_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_1 = s16Mode ? 18'h0 : _regularWHi_T_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_2 = io_w[47:32]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_5 = wWord_2[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_2 = {_w16Signed_T_5,wWord_2}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_7 = wWord_2[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_2 = {_w8LoSigned_T_7,wWord_2[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_7 = wWord_2[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_2 = {_w8HiSigned_T_7,wWord_2[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_2 = fp8Mode ? fp8Lo_2_io_out : w8LoSigned_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_2 = s16Mode ? w16Signed_2 : _regularWLo_T_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_2 = fp8Mode ? fp8Hi_2_io_out : w8HiSigned_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_2 = s16Mode ? 18'h0 : _regularWHi_T_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_3 = io_w[63:48]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_7 = wWord_3[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_3 = {_w16Signed_T_7,wWord_3}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_10 = wWord_3[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_3 = {_w8LoSigned_T_10,wWord_3[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_10 = wWord_3[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_3 = {_w8HiSigned_T_10,wWord_3[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_3 = fp8Mode ? fp8Lo_3_io_out : w8LoSigned_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_3 = s16Mode ? w16Signed_3 : _regularWLo_T_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_3 = fp8Mode ? fp8Hi_3_io_out : w8HiSigned_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_3 = s16Mode ? 18'h0 : _regularWHi_T_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_4 = io_w[79:64]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_9 = wWord_4[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_4 = {_w16Signed_T_9,wWord_4}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_13 = wWord_4[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_4 = {_w8LoSigned_T_13,wWord_4[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_13 = wWord_4[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_4 = {_w8HiSigned_T_13,wWord_4[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_4 = fp8Mode ? fp8Lo_4_io_out : w8LoSigned_4; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_4 = s16Mode ? w16Signed_4 : _regularWLo_T_4; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_4 = fp8Mode ? fp8Hi_4_io_out : w8HiSigned_4; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_4 = s16Mode ? 18'h0 : _regularWHi_T_4; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [17:0] postLo_4 = io_postData[53:36]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 105:31]
  wire [17:0] postHi_4 = io_postData[71:54]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 107:31]
  wire [15:0] wWord_5 = io_w[95:80]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_11 = wWord_5[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_5 = {_w16Signed_T_11,wWord_5}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_16 = wWord_5[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_5 = {_w8LoSigned_T_16,wWord_5[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_16 = wWord_5[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_5 = {_w8HiSigned_T_16,wWord_5[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_5 = fp8Mode ? fp8Lo_5_io_out : w8LoSigned_5; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_5 = s16Mode ? w16Signed_5 : _regularWLo_T_5; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_5 = fp8Mode ? fp8Hi_5_io_out : w8HiSigned_5; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_5 = s16Mode ? 18'h0 : _regularWHi_T_5; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_6 = io_w[111:96]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_13 = wWord_6[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_6 = {_w16Signed_T_13,wWord_6}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_19 = wWord_6[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_6 = {_w8LoSigned_T_19,wWord_6[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_19 = wWord_6[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_6 = {_w8HiSigned_T_19,wWord_6[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_6 = fp8Mode ? fp8Lo_6_io_out : w8LoSigned_6; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_6 = s16Mode ? w16Signed_6 : _regularWLo_T_6; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_6 = fp8Mode ? fp8Hi_6_io_out : w8HiSigned_6; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_6 = s16Mode ? 18'h0 : _regularWHi_T_6; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_7 = io_w[127:112]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_15 = wWord_7[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_7 = {_w16Signed_T_15,wWord_7}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_22 = wWord_7[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_7 = {_w8LoSigned_T_22,wWord_7[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_22 = wWord_7[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_7 = {_w8HiSigned_T_22,wWord_7[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_7 = fp8Mode ? fp8Lo_7_io_out : w8LoSigned_7; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_7 = s16Mode ? w16Signed_7 : _regularWLo_T_7; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_7 = fp8Mode ? fp8Hi_7_io_out : w8HiSigned_7; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_7 = s16Mode ? 18'h0 : _regularWHi_T_7; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_8 = io_w[143:128]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_17 = wWord_8[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_8 = {_w16Signed_T_17,wWord_8}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_25 = wWord_8[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_8 = {_w8LoSigned_T_25,wWord_8[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_25 = wWord_8[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_8 = {_w8HiSigned_T_25,wWord_8[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_8 = fp8Mode ? fp8Lo_8_io_out : w8LoSigned_8; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_8 = s16Mode ? w16Signed_8 : _regularWLo_T_8; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_8 = fp8Mode ? fp8Hi_8_io_out : w8HiSigned_8; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_8 = s16Mode ? 18'h0 : _regularWHi_T_8; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [17:0] postLo_8 = io_postData[89:72]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 105:31]
  wire [17:0] postHi_8 = io_postData[107:90]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 107:31]
  wire [15:0] wWord_9 = io_w[159:144]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_19 = wWord_9[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_9 = {_w16Signed_T_19,wWord_9}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_28 = wWord_9[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_9 = {_w8LoSigned_T_28,wWord_9[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_28 = wWord_9[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_9 = {_w8HiSigned_T_28,wWord_9[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_9 = fp8Mode ? fp8Lo_9_io_out : w8LoSigned_9; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_9 = s16Mode ? w16Signed_9 : _regularWLo_T_9; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_9 = fp8Mode ? fp8Hi_9_io_out : w8HiSigned_9; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_9 = s16Mode ? 18'h0 : _regularWHi_T_9; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_10 = io_w[175:160]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_21 = wWord_10[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_10 = {_w16Signed_T_21,wWord_10}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_31 = wWord_10[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_10 = {_w8LoSigned_T_31,wWord_10[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_31 = wWord_10[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_10 = {_w8HiSigned_T_31,wWord_10[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_10 = fp8Mode ? fp8Lo_10_io_out : w8LoSigned_10; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_10 = s16Mode ? w16Signed_10 : _regularWLo_T_10; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_10 = fp8Mode ? fp8Hi_10_io_out : w8HiSigned_10; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_10 = s16Mode ? 18'h0 : _regularWHi_T_10; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_11 = io_w[191:176]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_23 = wWord_11[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_11 = {_w16Signed_T_23,wWord_11}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_34 = wWord_11[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_11 = {_w8LoSigned_T_34,wWord_11[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_34 = wWord_11[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_11 = {_w8HiSigned_T_34,wWord_11[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_11 = fp8Mode ? fp8Lo_11_io_out : w8LoSigned_11; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_11 = s16Mode ? w16Signed_11 : _regularWLo_T_11; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_11 = fp8Mode ? fp8Hi_11_io_out : w8HiSigned_11; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_11 = s16Mode ? 18'h0 : _regularWHi_T_11; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_12 = io_w[207:192]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_25 = wWord_12[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_12 = {_w16Signed_T_25,wWord_12}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_37 = wWord_12[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_12 = {_w8LoSigned_T_37,wWord_12[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_37 = wWord_12[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_12 = {_w8HiSigned_T_37,wWord_12[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_12 = fp8Mode ? fp8Lo_12_io_out : w8LoSigned_12; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_12 = s16Mode ? w16Signed_12 : _regularWLo_T_12; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_12 = fp8Mode ? fp8Hi_12_io_out : w8HiSigned_12; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_12 = s16Mode ? 18'h0 : _regularWHi_T_12; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [17:0] postLo_12 = io_postData[125:108]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 105:31]
  wire [17:0] postHi_12 = io_postData[143:126]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 107:31]
  wire [15:0] wWord_13 = io_w[223:208]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_27 = wWord_13[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_13 = {_w16Signed_T_27,wWord_13}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_40 = wWord_13[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_13 = {_w8LoSigned_T_40,wWord_13[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_40 = wWord_13[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_13 = {_w8HiSigned_T_40,wWord_13[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_13 = fp8Mode ? fp8Lo_13_io_out : w8LoSigned_13; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_13 = s16Mode ? w16Signed_13 : _regularWLo_T_13; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_13 = fp8Mode ? fp8Hi_13_io_out : w8HiSigned_13; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_13 = s16Mode ? 18'h0 : _regularWHi_T_13; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_14 = io_w[239:224]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_29 = wWord_14[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_14 = {_w16Signed_T_29,wWord_14}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_43 = wWord_14[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_14 = {_w8LoSigned_T_43,wWord_14[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_43 = wWord_14[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_14 = {_w8HiSigned_T_43,wWord_14[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_14 = fp8Mode ? fp8Lo_14_io_out : w8LoSigned_14; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_14 = s16Mode ? w16Signed_14 : _regularWLo_T_14; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_14 = fp8Mode ? fp8Hi_14_io_out : w8HiSigned_14; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_14 = s16Mode ? 18'h0 : _regularWHi_T_14; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_15 = io_w[255:240]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_31 = wWord_15[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_15 = {_w16Signed_T_31,wWord_15}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_46 = wWord_15[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_15 = {_w8LoSigned_T_46,wWord_15[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_46 = wWord_15[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_15 = {_w8HiSigned_T_46,wWord_15[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_15 = fp8Mode ? fp8Lo_15_io_out : w8LoSigned_15; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_15 = s16Mode ? w16Signed_15 : _regularWLo_T_15; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_15 = fp8Mode ? fp8Hi_15_io_out : w8HiSigned_15; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_15 = s16Mode ? 18'h0 : _regularWHi_T_15; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_16 = io_w[271:256]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_33 = wWord_16[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_16 = {_w16Signed_T_33,wWord_16}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_49 = wWord_16[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_16 = {_w8LoSigned_T_49,wWord_16[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_49 = wWord_16[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_16 = {_w8HiSigned_T_49,wWord_16[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_16 = fp8Mode ? fp8Lo_16_io_out : w8LoSigned_16; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_16 = s16Mode ? w16Signed_16 : _regularWLo_T_16; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_16 = fp8Mode ? fp8Hi_16_io_out : w8HiSigned_16; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_16 = s16Mode ? 18'h0 : _regularWHi_T_16; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [17:0] postLo_16 = io_postData[161:144]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 105:31]
  wire [17:0] postHi_16 = io_postData[179:162]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 107:31]
  wire [15:0] wWord_17 = io_w[287:272]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_35 = wWord_17[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_17 = {_w16Signed_T_35,wWord_17}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_52 = wWord_17[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_17 = {_w8LoSigned_T_52,wWord_17[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_52 = wWord_17[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_17 = {_w8HiSigned_T_52,wWord_17[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_17 = fp8Mode ? fp8Lo_17_io_out : w8LoSigned_17; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_17 = s16Mode ? w16Signed_17 : _regularWLo_T_17; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_17 = fp8Mode ? fp8Hi_17_io_out : w8HiSigned_17; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_17 = s16Mode ? 18'h0 : _regularWHi_T_17; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_18 = io_w[303:288]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_37 = wWord_18[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_18 = {_w16Signed_T_37,wWord_18}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_55 = wWord_18[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_18 = {_w8LoSigned_T_55,wWord_18[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_55 = wWord_18[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_18 = {_w8HiSigned_T_55,wWord_18[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_18 = fp8Mode ? fp8Lo_18_io_out : w8LoSigned_18; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_18 = s16Mode ? w16Signed_18 : _regularWLo_T_18; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_18 = fp8Mode ? fp8Hi_18_io_out : w8HiSigned_18; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_18 = s16Mode ? 18'h0 : _regularWHi_T_18; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_19 = io_w[319:304]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_39 = wWord_19[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_19 = {_w16Signed_T_39,wWord_19}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_58 = wWord_19[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_19 = {_w8LoSigned_T_58,wWord_19[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_58 = wWord_19[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_19 = {_w8HiSigned_T_58,wWord_19[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_19 = fp8Mode ? fp8Lo_19_io_out : w8LoSigned_19; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_19 = s16Mode ? w16Signed_19 : _regularWLo_T_19; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_19 = fp8Mode ? fp8Hi_19_io_out : w8HiSigned_19; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_19 = s16Mode ? 18'h0 : _regularWHi_T_19; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_20 = io_w[335:320]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_41 = wWord_20[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_20 = {_w16Signed_T_41,wWord_20}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_61 = wWord_20[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_20 = {_w8LoSigned_T_61,wWord_20[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_61 = wWord_20[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_20 = {_w8HiSigned_T_61,wWord_20[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_20 = fp8Mode ? fp8Lo_20_io_out : w8LoSigned_20; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_20 = s16Mode ? w16Signed_20 : _regularWLo_T_20; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_20 = fp8Mode ? fp8Hi_20_io_out : w8HiSigned_20; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_20 = s16Mode ? 18'h0 : _regularWHi_T_20; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [17:0] postLo_20 = io_postData[197:180]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 105:31]
  wire [17:0] postHi_20 = io_postData[215:198]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 107:31]
  wire [15:0] wWord_21 = io_w[351:336]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_43 = wWord_21[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_21 = {_w16Signed_T_43,wWord_21}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_64 = wWord_21[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_21 = {_w8LoSigned_T_64,wWord_21[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_64 = wWord_21[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_21 = {_w8HiSigned_T_64,wWord_21[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_21 = fp8Mode ? fp8Lo_21_io_out : w8LoSigned_21; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_21 = s16Mode ? w16Signed_21 : _regularWLo_T_21; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_21 = fp8Mode ? fp8Hi_21_io_out : w8HiSigned_21; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_21 = s16Mode ? 18'h0 : _regularWHi_T_21; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_22 = io_w[367:352]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_45 = wWord_22[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_22 = {_w16Signed_T_45,wWord_22}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_67 = wWord_22[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_22 = {_w8LoSigned_T_67,wWord_22[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_67 = wWord_22[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_22 = {_w8HiSigned_T_67,wWord_22[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_22 = fp8Mode ? fp8Lo_22_io_out : w8LoSigned_22; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_22 = s16Mode ? w16Signed_22 : _regularWLo_T_22; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_22 = fp8Mode ? fp8Hi_22_io_out : w8HiSigned_22; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_22 = s16Mode ? 18'h0 : _regularWHi_T_22; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_23 = io_w[383:368]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_47 = wWord_23[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_23 = {_w16Signed_T_47,wWord_23}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_70 = wWord_23[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_23 = {_w8LoSigned_T_70,wWord_23[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_70 = wWord_23[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_23 = {_w8HiSigned_T_70,wWord_23[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_23 = fp8Mode ? fp8Lo_23_io_out : w8LoSigned_23; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_23 = s16Mode ? w16Signed_23 : _regularWLo_T_23; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_23 = fp8Mode ? fp8Hi_23_io_out : w8HiSigned_23; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_23 = s16Mode ? 18'h0 : _regularWHi_T_23; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_24 = io_w[399:384]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_49 = wWord_24[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_24 = {_w16Signed_T_49,wWord_24}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_73 = wWord_24[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_24 = {_w8LoSigned_T_73,wWord_24[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_73 = wWord_24[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_24 = {_w8HiSigned_T_73,wWord_24[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_24 = fp8Mode ? fp8Lo_24_io_out : w8LoSigned_24; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_24 = s16Mode ? w16Signed_24 : _regularWLo_T_24; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_24 = fp8Mode ? fp8Hi_24_io_out : w8HiSigned_24; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_24 = s16Mode ? 18'h0 : _regularWHi_T_24; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [17:0] postLo_24 = io_postData[233:216]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 105:31]
  wire [17:0] postHi_24 = io_postData[251:234]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 107:31]
  wire [15:0] wWord_25 = io_w[415:400]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_51 = wWord_25[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_25 = {_w16Signed_T_51,wWord_25}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_76 = wWord_25[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_25 = {_w8LoSigned_T_76,wWord_25[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_76 = wWord_25[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_25 = {_w8HiSigned_T_76,wWord_25[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_25 = fp8Mode ? fp8Lo_25_io_out : w8LoSigned_25; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_25 = s16Mode ? w16Signed_25 : _regularWLo_T_25; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_25 = fp8Mode ? fp8Hi_25_io_out : w8HiSigned_25; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_25 = s16Mode ? 18'h0 : _regularWHi_T_25; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_26 = io_w[431:416]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_53 = wWord_26[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_26 = {_w16Signed_T_53,wWord_26}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_79 = wWord_26[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_26 = {_w8LoSigned_T_79,wWord_26[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_79 = wWord_26[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_26 = {_w8HiSigned_T_79,wWord_26[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_26 = fp8Mode ? fp8Lo_26_io_out : w8LoSigned_26; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_26 = s16Mode ? w16Signed_26 : _regularWLo_T_26; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_26 = fp8Mode ? fp8Hi_26_io_out : w8HiSigned_26; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_26 = s16Mode ? 18'h0 : _regularWHi_T_26; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_27 = io_w[447:432]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_55 = wWord_27[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_27 = {_w16Signed_T_55,wWord_27}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_82 = wWord_27[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_27 = {_w8LoSigned_T_82,wWord_27[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_82 = wWord_27[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_27 = {_w8HiSigned_T_82,wWord_27[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_27 = fp8Mode ? fp8Lo_27_io_out : w8LoSigned_27; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_27 = s16Mode ? w16Signed_27 : _regularWLo_T_27; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_27 = fp8Mode ? fp8Hi_27_io_out : w8HiSigned_27; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_27 = s16Mode ? 18'h0 : _regularWHi_T_27; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_28 = io_w[463:448]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_57 = wWord_28[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_28 = {_w16Signed_T_57,wWord_28}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_85 = wWord_28[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_28 = {_w8LoSigned_T_85,wWord_28[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_85 = wWord_28[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_28 = {_w8HiSigned_T_85,wWord_28[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_28 = fp8Mode ? fp8Lo_28_io_out : w8LoSigned_28; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_28 = s16Mode ? w16Signed_28 : _regularWLo_T_28; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_28 = fp8Mode ? fp8Hi_28_io_out : w8HiSigned_28; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_28 = s16Mode ? 18'h0 : _regularWHi_T_28; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [17:0] postLo_28 = io_postData[269:252]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 105:31]
  wire [17:0] postHi_28 = io_postData[287:270]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 107:31]
  wire [15:0] wWord_29 = io_w[479:464]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_59 = wWord_29[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_29 = {_w16Signed_T_59,wWord_29}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_88 = wWord_29[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_29 = {_w8LoSigned_T_88,wWord_29[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_88 = wWord_29[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_29 = {_w8HiSigned_T_88,wWord_29[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_29 = fp8Mode ? fp8Lo_29_io_out : w8LoSigned_29; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_29 = s16Mode ? w16Signed_29 : _regularWLo_T_29; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_29 = fp8Mode ? fp8Hi_29_io_out : w8HiSigned_29; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_29 = s16Mode ? 18'h0 : _regularWHi_T_29; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_30 = io_w[495:480]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_61 = wWord_30[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_30 = {_w16Signed_T_61,wWord_30}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_91 = wWord_30[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_30 = {_w8LoSigned_T_91,wWord_30[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_91 = wWord_30[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_30 = {_w8HiSigned_T_91,wWord_30[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_30 = fp8Mode ? fp8Lo_30_io_out : w8LoSigned_30; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_30 = s16Mode ? w16Signed_30 : _regularWLo_T_30; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_30 = fp8Mode ? fp8Hi_30_io_out : w8HiSigned_30; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_30 = s16Mode ? 18'h0 : _regularWHi_T_30; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_31 = io_w[511:496]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_63 = wWord_31[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_31 = {_w16Signed_T_63,wWord_31}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_94 = wWord_31[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_31 = {_w8LoSigned_T_94,wWord_31[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_94 = wWord_31[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_31 = {_w8HiSigned_T_94,wWord_31[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_31 = fp8Mode ? fp8Lo_31_io_out : w8LoSigned_31; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_31 = s16Mode ? w16Signed_31 : _regularWLo_T_31; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_31 = fp8Mode ? fp8Hi_31_io_out : w8HiSigned_31; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_31 = s16Mode ? 18'h0 : _regularWHi_T_31; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_32 = io_w[527:512]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_65 = wWord_32[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_32 = {_w16Signed_T_65,wWord_32}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_97 = wWord_32[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_32 = {_w8LoSigned_T_97,wWord_32[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_97 = wWord_32[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_32 = {_w8HiSigned_T_97,wWord_32[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_32 = fp8Mode ? fp8Lo_32_io_out : w8LoSigned_32; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_32 = s16Mode ? w16Signed_32 : _regularWLo_T_32; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_32 = fp8Mode ? fp8Hi_32_io_out : w8HiSigned_32; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_32 = s16Mode ? 18'h0 : _regularWHi_T_32; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [17:0] postLo_32 = io_postData[305:288]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 105:31]
  wire [17:0] postHi_32 = io_postData[323:306]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 107:31]
  wire [15:0] wWord_33 = io_w[543:528]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_67 = wWord_33[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_33 = {_w16Signed_T_67,wWord_33}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_100 = wWord_33[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_33 = {_w8LoSigned_T_100,wWord_33[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_100 = wWord_33[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_33 = {_w8HiSigned_T_100,wWord_33[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_33 = fp8Mode ? fp8Lo_33_io_out : w8LoSigned_33; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_33 = s16Mode ? w16Signed_33 : _regularWLo_T_33; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_33 = fp8Mode ? fp8Hi_33_io_out : w8HiSigned_33; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_33 = s16Mode ? 18'h0 : _regularWHi_T_33; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_34 = io_w[559:544]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_69 = wWord_34[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_34 = {_w16Signed_T_69,wWord_34}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_103 = wWord_34[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_34 = {_w8LoSigned_T_103,wWord_34[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_103 = wWord_34[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_34 = {_w8HiSigned_T_103,wWord_34[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_34 = fp8Mode ? fp8Lo_34_io_out : w8LoSigned_34; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_34 = s16Mode ? w16Signed_34 : _regularWLo_T_34; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_34 = fp8Mode ? fp8Hi_34_io_out : w8HiSigned_34; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_34 = s16Mode ? 18'h0 : _regularWHi_T_34; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_35 = io_w[575:560]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_71 = wWord_35[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_35 = {_w16Signed_T_71,wWord_35}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_106 = wWord_35[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_35 = {_w8LoSigned_T_106,wWord_35[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_106 = wWord_35[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_35 = {_w8HiSigned_T_106,wWord_35[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_35 = fp8Mode ? fp8Lo_35_io_out : w8LoSigned_35; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_35 = s16Mode ? w16Signed_35 : _regularWLo_T_35; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_35 = fp8Mode ? fp8Hi_35_io_out : w8HiSigned_35; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_35 = s16Mode ? 18'h0 : _regularWHi_T_35; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_36 = io_w[591:576]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_73 = wWord_36[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_36 = {_w16Signed_T_73,wWord_36}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_109 = wWord_36[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_36 = {_w8LoSigned_T_109,wWord_36[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_109 = wWord_36[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_36 = {_w8HiSigned_T_109,wWord_36[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_36 = fp8Mode ? fp8Lo_36_io_out : w8LoSigned_36; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_36 = s16Mode ? w16Signed_36 : _regularWLo_T_36; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_36 = fp8Mode ? fp8Hi_36_io_out : w8HiSigned_36; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_36 = s16Mode ? 18'h0 : _regularWHi_T_36; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [17:0] postLo_36 = io_postData[341:324]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 105:31]
  wire [17:0] postHi_36 = io_postData[359:342]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 107:31]
  wire [15:0] wWord_37 = io_w[607:592]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_75 = wWord_37[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_37 = {_w16Signed_T_75,wWord_37}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_112 = wWord_37[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_37 = {_w8LoSigned_T_112,wWord_37[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_112 = wWord_37[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_37 = {_w8HiSigned_T_112,wWord_37[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_37 = fp8Mode ? fp8Lo_37_io_out : w8LoSigned_37; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_37 = s16Mode ? w16Signed_37 : _regularWLo_T_37; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_37 = fp8Mode ? fp8Hi_37_io_out : w8HiSigned_37; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_37 = s16Mode ? 18'h0 : _regularWHi_T_37; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_38 = io_w[623:608]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_77 = wWord_38[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_38 = {_w16Signed_T_77,wWord_38}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_115 = wWord_38[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_38 = {_w8LoSigned_T_115,wWord_38[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_115 = wWord_38[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_38 = {_w8HiSigned_T_115,wWord_38[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_38 = fp8Mode ? fp8Lo_38_io_out : w8LoSigned_38; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_38 = s16Mode ? w16Signed_38 : _regularWLo_T_38; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_38 = fp8Mode ? fp8Hi_38_io_out : w8HiSigned_38; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_38 = s16Mode ? 18'h0 : _regularWHi_T_38; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_39 = io_w[639:624]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_79 = wWord_39[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_39 = {_w16Signed_T_79,wWord_39}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_118 = wWord_39[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_39 = {_w8LoSigned_T_118,wWord_39[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_118 = wWord_39[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_39 = {_w8HiSigned_T_118,wWord_39[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_39 = fp8Mode ? fp8Lo_39_io_out : w8LoSigned_39; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_39 = s16Mode ? w16Signed_39 : _regularWLo_T_39; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_39 = fp8Mode ? fp8Hi_39_io_out : w8HiSigned_39; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_39 = s16Mode ? 18'h0 : _regularWHi_T_39; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_40 = io_w[655:640]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_81 = wWord_40[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_40 = {_w16Signed_T_81,wWord_40}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_121 = wWord_40[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_40 = {_w8LoSigned_T_121,wWord_40[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_121 = wWord_40[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_40 = {_w8HiSigned_T_121,wWord_40[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_40 = fp8Mode ? fp8Lo_40_io_out : w8LoSigned_40; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_40 = s16Mode ? w16Signed_40 : _regularWLo_T_40; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_40 = fp8Mode ? fp8Hi_40_io_out : w8HiSigned_40; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_40 = s16Mode ? 18'h0 : _regularWHi_T_40; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [17:0] postLo_40 = io_postData[377:360]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 105:31]
  wire [17:0] postHi_40 = io_postData[395:378]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 107:31]
  wire [15:0] wWord_41 = io_w[671:656]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_83 = wWord_41[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_41 = {_w16Signed_T_83,wWord_41}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_124 = wWord_41[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_41 = {_w8LoSigned_T_124,wWord_41[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_124 = wWord_41[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_41 = {_w8HiSigned_T_124,wWord_41[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_41 = fp8Mode ? fp8Lo_41_io_out : w8LoSigned_41; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_41 = s16Mode ? w16Signed_41 : _regularWLo_T_41; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_41 = fp8Mode ? fp8Hi_41_io_out : w8HiSigned_41; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_41 = s16Mode ? 18'h0 : _regularWHi_T_41; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_42 = io_w[687:672]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_85 = wWord_42[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_42 = {_w16Signed_T_85,wWord_42}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_127 = wWord_42[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_42 = {_w8LoSigned_T_127,wWord_42[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_127 = wWord_42[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_42 = {_w8HiSigned_T_127,wWord_42[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_42 = fp8Mode ? fp8Lo_42_io_out : w8LoSigned_42; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_42 = s16Mode ? w16Signed_42 : _regularWLo_T_42; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_42 = fp8Mode ? fp8Hi_42_io_out : w8HiSigned_42; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_42 = s16Mode ? 18'h0 : _regularWHi_T_42; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_43 = io_w[703:688]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_87 = wWord_43[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_43 = {_w16Signed_T_87,wWord_43}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_130 = wWord_43[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_43 = {_w8LoSigned_T_130,wWord_43[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_130 = wWord_43[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_43 = {_w8HiSigned_T_130,wWord_43[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_43 = fp8Mode ? fp8Lo_43_io_out : w8LoSigned_43; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_43 = s16Mode ? w16Signed_43 : _regularWLo_T_43; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_43 = fp8Mode ? fp8Hi_43_io_out : w8HiSigned_43; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_43 = s16Mode ? 18'h0 : _regularWHi_T_43; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_44 = io_w[719:704]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_89 = wWord_44[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_44 = {_w16Signed_T_89,wWord_44}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_133 = wWord_44[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_44 = {_w8LoSigned_T_133,wWord_44[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_133 = wWord_44[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_44 = {_w8HiSigned_T_133,wWord_44[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_44 = fp8Mode ? fp8Lo_44_io_out : w8LoSigned_44; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_44 = s16Mode ? w16Signed_44 : _regularWLo_T_44; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_44 = fp8Mode ? fp8Hi_44_io_out : w8HiSigned_44; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_44 = s16Mode ? 18'h0 : _regularWHi_T_44; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [17:0] postLo_44 = io_postData[413:396]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 105:31]
  wire [17:0] postHi_44 = io_postData[431:414]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 107:31]
  wire [15:0] wWord_45 = io_w[735:720]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_91 = wWord_45[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_45 = {_w16Signed_T_91,wWord_45}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_136 = wWord_45[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_45 = {_w8LoSigned_T_136,wWord_45[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_136 = wWord_45[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_45 = {_w8HiSigned_T_136,wWord_45[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_45 = fp8Mode ? fp8Lo_45_io_out : w8LoSigned_45; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_45 = s16Mode ? w16Signed_45 : _regularWLo_T_45; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_45 = fp8Mode ? fp8Hi_45_io_out : w8HiSigned_45; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_45 = s16Mode ? 18'h0 : _regularWHi_T_45; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_46 = io_w[751:736]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_93 = wWord_46[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_46 = {_w16Signed_T_93,wWord_46}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_139 = wWord_46[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_46 = {_w8LoSigned_T_139,wWord_46[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_139 = wWord_46[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_46 = {_w8HiSigned_T_139,wWord_46[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_46 = fp8Mode ? fp8Lo_46_io_out : w8LoSigned_46; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_46 = s16Mode ? w16Signed_46 : _regularWLo_T_46; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_46 = fp8Mode ? fp8Hi_46_io_out : w8HiSigned_46; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_46 = s16Mode ? 18'h0 : _regularWHi_T_46; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_47 = io_w[767:752]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_95 = wWord_47[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_47 = {_w16Signed_T_95,wWord_47}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_142 = wWord_47[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_47 = {_w8LoSigned_T_142,wWord_47[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_142 = wWord_47[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_47 = {_w8HiSigned_T_142,wWord_47[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_47 = fp8Mode ? fp8Lo_47_io_out : w8LoSigned_47; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_47 = s16Mode ? w16Signed_47 : _regularWLo_T_47; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_47 = fp8Mode ? fp8Hi_47_io_out : w8HiSigned_47; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_47 = s16Mode ? 18'h0 : _regularWHi_T_47; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_48 = io_w[783:768]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_97 = wWord_48[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_48 = {_w16Signed_T_97,wWord_48}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_145 = wWord_48[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_48 = {_w8LoSigned_T_145,wWord_48[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_145 = wWord_48[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_48 = {_w8HiSigned_T_145,wWord_48[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_48 = fp8Mode ? fp8Lo_48_io_out : w8LoSigned_48; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_48 = s16Mode ? w16Signed_48 : _regularWLo_T_48; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_48 = fp8Mode ? fp8Hi_48_io_out : w8HiSigned_48; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_48 = s16Mode ? 18'h0 : _regularWHi_T_48; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [17:0] postLo_48 = io_postData[449:432]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 105:31]
  wire [17:0] postHi_48 = io_postData[467:450]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 107:31]
  wire [15:0] wWord_49 = io_w[799:784]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_99 = wWord_49[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_49 = {_w16Signed_T_99,wWord_49}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_148 = wWord_49[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_49 = {_w8LoSigned_T_148,wWord_49[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_148 = wWord_49[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_49 = {_w8HiSigned_T_148,wWord_49[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_49 = fp8Mode ? fp8Lo_49_io_out : w8LoSigned_49; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_49 = s16Mode ? w16Signed_49 : _regularWLo_T_49; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_49 = fp8Mode ? fp8Hi_49_io_out : w8HiSigned_49; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_49 = s16Mode ? 18'h0 : _regularWHi_T_49; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_50 = io_w[815:800]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_101 = wWord_50[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_50 = {_w16Signed_T_101,wWord_50}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_151 = wWord_50[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_50 = {_w8LoSigned_T_151,wWord_50[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_151 = wWord_50[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_50 = {_w8HiSigned_T_151,wWord_50[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_50 = fp8Mode ? fp8Lo_50_io_out : w8LoSigned_50; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_50 = s16Mode ? w16Signed_50 : _regularWLo_T_50; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_50 = fp8Mode ? fp8Hi_50_io_out : w8HiSigned_50; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_50 = s16Mode ? 18'h0 : _regularWHi_T_50; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_51 = io_w[831:816]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_103 = wWord_51[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_51 = {_w16Signed_T_103,wWord_51}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_154 = wWord_51[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_51 = {_w8LoSigned_T_154,wWord_51[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_154 = wWord_51[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_51 = {_w8HiSigned_T_154,wWord_51[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_51 = fp8Mode ? fp8Lo_51_io_out : w8LoSigned_51; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_51 = s16Mode ? w16Signed_51 : _regularWLo_T_51; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_51 = fp8Mode ? fp8Hi_51_io_out : w8HiSigned_51; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_51 = s16Mode ? 18'h0 : _regularWHi_T_51; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_52 = io_w[847:832]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_105 = wWord_52[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_52 = {_w16Signed_T_105,wWord_52}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_157 = wWord_52[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_52 = {_w8LoSigned_T_157,wWord_52[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_157 = wWord_52[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_52 = {_w8HiSigned_T_157,wWord_52[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_52 = fp8Mode ? fp8Lo_52_io_out : w8LoSigned_52; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_52 = s16Mode ? w16Signed_52 : _regularWLo_T_52; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_52 = fp8Mode ? fp8Hi_52_io_out : w8HiSigned_52; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_52 = s16Mode ? 18'h0 : _regularWHi_T_52; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [17:0] postLo_52 = io_postData[485:468]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 105:31]
  wire [17:0] postHi_52 = io_postData[503:486]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 107:31]
  wire [15:0] wWord_53 = io_w[863:848]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_107 = wWord_53[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_53 = {_w16Signed_T_107,wWord_53}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_160 = wWord_53[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_53 = {_w8LoSigned_T_160,wWord_53[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_160 = wWord_53[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_53 = {_w8HiSigned_T_160,wWord_53[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_53 = fp8Mode ? fp8Lo_53_io_out : w8LoSigned_53; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_53 = s16Mode ? w16Signed_53 : _regularWLo_T_53; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_53 = fp8Mode ? fp8Hi_53_io_out : w8HiSigned_53; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_53 = s16Mode ? 18'h0 : _regularWHi_T_53; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_54 = io_w[879:864]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_109 = wWord_54[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_54 = {_w16Signed_T_109,wWord_54}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_163 = wWord_54[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_54 = {_w8LoSigned_T_163,wWord_54[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_163 = wWord_54[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_54 = {_w8HiSigned_T_163,wWord_54[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_54 = fp8Mode ? fp8Lo_54_io_out : w8LoSigned_54; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_54 = s16Mode ? w16Signed_54 : _regularWLo_T_54; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_54 = fp8Mode ? fp8Hi_54_io_out : w8HiSigned_54; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_54 = s16Mode ? 18'h0 : _regularWHi_T_54; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_55 = io_w[895:880]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_111 = wWord_55[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_55 = {_w16Signed_T_111,wWord_55}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_166 = wWord_55[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_55 = {_w8LoSigned_T_166,wWord_55[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_166 = wWord_55[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_55 = {_w8HiSigned_T_166,wWord_55[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_55 = fp8Mode ? fp8Lo_55_io_out : w8LoSigned_55; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_55 = s16Mode ? w16Signed_55 : _regularWLo_T_55; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_55 = fp8Mode ? fp8Hi_55_io_out : w8HiSigned_55; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_55 = s16Mode ? 18'h0 : _regularWHi_T_55; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_56 = io_w[911:896]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_113 = wWord_56[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_56 = {_w16Signed_T_113,wWord_56}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_169 = wWord_56[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_56 = {_w8LoSigned_T_169,wWord_56[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_169 = wWord_56[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_56 = {_w8HiSigned_T_169,wWord_56[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_56 = fp8Mode ? fp8Lo_56_io_out : w8LoSigned_56; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_56 = s16Mode ? w16Signed_56 : _regularWLo_T_56; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_56 = fp8Mode ? fp8Hi_56_io_out : w8HiSigned_56; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_56 = s16Mode ? 18'h0 : _regularWHi_T_56; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [17:0] postLo_56 = io_postData[521:504]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 105:31]
  wire [17:0] postHi_56 = io_postData[539:522]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 107:31]
  wire [15:0] wWord_57 = io_w[927:912]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_115 = wWord_57[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_57 = {_w16Signed_T_115,wWord_57}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_172 = wWord_57[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_57 = {_w8LoSigned_T_172,wWord_57[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_172 = wWord_57[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_57 = {_w8HiSigned_T_172,wWord_57[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_57 = fp8Mode ? fp8Lo_57_io_out : w8LoSigned_57; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_57 = s16Mode ? w16Signed_57 : _regularWLo_T_57; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_57 = fp8Mode ? fp8Hi_57_io_out : w8HiSigned_57; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_57 = s16Mode ? 18'h0 : _regularWHi_T_57; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_58 = io_w[943:928]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_117 = wWord_58[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_58 = {_w16Signed_T_117,wWord_58}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_175 = wWord_58[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_58 = {_w8LoSigned_T_175,wWord_58[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_175 = wWord_58[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_58 = {_w8HiSigned_T_175,wWord_58[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_58 = fp8Mode ? fp8Lo_58_io_out : w8LoSigned_58; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_58 = s16Mode ? w16Signed_58 : _regularWLo_T_58; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_58 = fp8Mode ? fp8Hi_58_io_out : w8HiSigned_58; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_58 = s16Mode ? 18'h0 : _regularWHi_T_58; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_59 = io_w[959:944]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_119 = wWord_59[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_59 = {_w16Signed_T_119,wWord_59}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_178 = wWord_59[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_59 = {_w8LoSigned_T_178,wWord_59[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_178 = wWord_59[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_59 = {_w8HiSigned_T_178,wWord_59[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_59 = fp8Mode ? fp8Lo_59_io_out : w8LoSigned_59; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_59 = s16Mode ? w16Signed_59 : _regularWLo_T_59; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_59 = fp8Mode ? fp8Hi_59_io_out : w8HiSigned_59; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_59 = s16Mode ? 18'h0 : _regularWHi_T_59; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_60 = io_w[975:960]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_121 = wWord_60[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_60 = {_w16Signed_T_121,wWord_60}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_181 = wWord_60[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_60 = {_w8LoSigned_T_181,wWord_60[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_181 = wWord_60[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_60 = {_w8HiSigned_T_181,wWord_60[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_60 = fp8Mode ? fp8Lo_60_io_out : w8LoSigned_60; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_60 = s16Mode ? w16Signed_60 : _regularWLo_T_60; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_60 = fp8Mode ? fp8Hi_60_io_out : w8HiSigned_60; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_60 = s16Mode ? 18'h0 : _regularWHi_T_60; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [17:0] postLo_60 = io_postData[557:540]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 105:31]
  wire [17:0] postHi_60 = io_postData[575:558]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 107:31]
  wire [15:0] wWord_61 = io_w[991:976]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_123 = wWord_61[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_61 = {_w16Signed_T_123,wWord_61}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_184 = wWord_61[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_61 = {_w8LoSigned_T_184,wWord_61[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_184 = wWord_61[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_61 = {_w8HiSigned_T_184,wWord_61[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_61 = fp8Mode ? fp8Lo_61_io_out : w8LoSigned_61; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_61 = s16Mode ? w16Signed_61 : _regularWLo_T_61; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_61 = fp8Mode ? fp8Hi_61_io_out : w8HiSigned_61; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_61 = s16Mode ? 18'h0 : _regularWHi_T_61; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_62 = io_w[1007:992]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_125 = wWord_62[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_62 = {_w16Signed_T_125,wWord_62}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_187 = wWord_62[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_62 = {_w8LoSigned_T_187,wWord_62[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_187 = wWord_62[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_62 = {_w8HiSigned_T_187,wWord_62[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_62 = fp8Mode ? fp8Lo_62_io_out : w8LoSigned_62; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_62 = s16Mode ? w16Signed_62 : _regularWLo_T_62; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_62 = fp8Mode ? fp8Hi_62_io_out : w8HiSigned_62; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_62 = s16Mode ? 18'h0 : _regularWHi_T_62; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire [15:0] wWord_63 = io_w[1023:1008]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 78:23]
  wire [1:0] _w16Signed_T_127 = wWord_63[15] ? 2'h3 : 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:31]
  wire [17:0] w16Signed_63 = {_w16Signed_T_127,wWord_63}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 83:26]
  wire [9:0] _w8LoSigned_T_190 = wWord_63[7] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:32]
  wire [17:0] w8LoSigned_63 = {_w8LoSigned_T_190,wWord_63[7:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 84:27]
  wire [9:0] _w8HiSigned_T_190 = wWord_63[15] ? 10'h3ff : 10'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:32]
  wire [17:0] w8HiSigned_63 = {_w8HiSigned_T_190,wWord_63[15:8]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 85:27]
  wire [17:0] _regularWLo_T_63 = fp8Mode ? fp8Lo_63_io_out : w8LoSigned_63; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 99:12]
  wire [17:0] regularWLo_63 = s16Mode ? w16Signed_63 : _regularWLo_T_63; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 98:27]
  wire [17:0] _regularWHi_T_63 = fp8Mode ? fp8Hi_63_io_out : w8HiSigned_63; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 101:12]
  wire [17:0] regularWHi_63 = s16Mode ? 18'h0 : _regularWHi_T_63; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 100:27]
  wire  _T_1 = ~io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 136:40]
  reg  validD1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 139:26]
  reg  validD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 140:26]
  reg  validR; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 141:25]
  reg  clearD1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 142:26]
  reg  clearD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 143:26]
  reg  postD1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 144:25]
  reg  postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 145:25]
  reg [1:0] modeD1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 146:25]
  reg [1:0] modeD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 147:25]
  reg [31:0] maskD1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 148:25]
  reg [31:0] maskD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 149:25]
  wire  lowLaneEnable = modeD2 == 2'h0 ? maskD2[0] : maskD2[0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 172:30]
  wire  highLaneEnable = modeD2 != 2'h0 & maskD2[1]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 174:60]
  wire  lowLaneEnable_1 = modeD2 == 2'h0 ? maskD2[1] : maskD2[2]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 172:30]
  wire  highLaneEnable_1 = modeD2 != 2'h0 & maskD2[3]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 174:60]
  wire  lowLaneEnable_2 = modeD2 == 2'h0 ? maskD2[2] : maskD2[4]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 172:30]
  wire  highLaneEnable_2 = modeD2 != 2'h0 & maskD2[5]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 174:60]
  wire  lowLaneEnable_3 = modeD2 == 2'h0 ? maskD2[3] : maskD2[6]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 172:30]
  wire  highLaneEnable_3 = modeD2 != 2'h0 & maskD2[7]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 174:60]
  wire  lowLaneEnable_4 = modeD2 == 2'h0 ? maskD2[4] : maskD2[8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 172:30]
  wire  highLaneEnable_4 = modeD2 != 2'h0 & maskD2[9]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 174:60]
  wire  lowLaneEnable_5 = modeD2 == 2'h0 ? maskD2[5] : maskD2[10]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 172:30]
  wire  highLaneEnable_5 = modeD2 != 2'h0 & maskD2[11]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 174:60]
  wire  lowLaneEnable_6 = modeD2 == 2'h0 ? maskD2[6] : maskD2[12]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 172:30]
  wire  highLaneEnable_6 = modeD2 != 2'h0 & maskD2[13]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 174:60]
  wire  lowLaneEnable_7 = modeD2 == 2'h0 ? maskD2[7] : maskD2[14]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 172:30]
  wire  highLaneEnable_7 = modeD2 != 2'h0 & maskD2[15]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 174:60]
  wire  lowLaneEnable_8 = modeD2 == 2'h0 ? maskD2[8] : maskD2[16]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 172:30]
  wire  highLaneEnable_8 = modeD2 != 2'h0 & maskD2[17]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 174:60]
  wire  lowLaneEnable_9 = modeD2 == 2'h0 ? maskD2[9] : maskD2[18]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 172:30]
  wire  highLaneEnable_9 = modeD2 != 2'h0 & maskD2[19]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 174:60]
  wire  lowLaneEnable_10 = modeD2 == 2'h0 ? maskD2[10] : maskD2[20]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 172:30]
  wire  highLaneEnable_10 = modeD2 != 2'h0 & maskD2[21]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 174:60]
  wire  lowLaneEnable_11 = modeD2 == 2'h0 ? maskD2[11] : maskD2[22]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 172:30]
  wire  highLaneEnable_11 = modeD2 != 2'h0 & maskD2[23]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 174:60]
  wire  lowLaneEnable_12 = modeD2 == 2'h0 ? maskD2[12] : maskD2[24]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 172:30]
  wire  highLaneEnable_12 = modeD2 != 2'h0 & maskD2[25]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 174:60]
  wire  lowLaneEnable_13 = modeD2 == 2'h0 ? maskD2[13] : maskD2[26]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 172:30]
  wire  highLaneEnable_13 = modeD2 != 2'h0 & maskD2[27]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 174:60]
  wire  lowLaneEnable_14 = modeD2 == 2'h0 ? maskD2[14] : maskD2[28]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 172:30]
  wire  highLaneEnable_14 = modeD2 != 2'h0 & maskD2[29]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 174:60]
  wire  lowLaneEnable_15 = modeD2 == 2'h0 ? maskD2[15] : maskD2[30]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 172:30]
  wire  highLaneEnable_15 = modeD2 != 2'h0 & maskD2[31]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 174:60]
  wire  _narrowResult_T_1 = modeD2 == 2'h2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 194:14]
  wire  narrowResult = modeD2 == 2'h1 | _narrowResult_T_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 193:54]
  wire [15:0] _accumPhysical_0_T_1 = accumApmLo_0_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:17]
  wire [47:0] _accumPhysical_0_T_3 = {_accumPhysical_0_T_1,accumApmLo_0_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:12]
  wire [47:0] accumPhysical_0 = narrowResult ? _accumPhysical_0_T_3 : accumApmLo_0_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 201:31]
  wire [15:0] _accumPhysical_16_T_1 = accumApmHi_0_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:17]
  wire [47:0] _accumPhysical_16_T_3 = {_accumPhysical_16_T_1,accumApmHi_0_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:12]
  wire [47:0] accumPhysical_16 = narrowResult ? _accumPhysical_16_T_3 : accumApmHi_0_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 203:39]
  wire [15:0] _accumPhysical_1_T_1 = accumApmLo_1_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:17]
  wire [47:0] _accumPhysical_1_T_3 = {_accumPhysical_1_T_1,accumApmLo_1_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:12]
  wire [47:0] accumPhysical_1 = narrowResult ? _accumPhysical_1_T_3 : accumApmLo_1_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 201:31]
  wire [15:0] _accumPhysical_17_T_1 = accumApmHi_1_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:17]
  wire [47:0] _accumPhysical_17_T_3 = {_accumPhysical_17_T_1,accumApmHi_1_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:12]
  wire [47:0] accumPhysical_17 = narrowResult ? _accumPhysical_17_T_3 : accumApmHi_1_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 203:39]
  wire [15:0] _accumPhysical_2_T_1 = accumApmLo_2_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:17]
  wire [47:0] _accumPhysical_2_T_3 = {_accumPhysical_2_T_1,accumApmLo_2_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:12]
  wire [47:0] accumPhysical_2 = narrowResult ? _accumPhysical_2_T_3 : accumApmLo_2_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 201:31]
  wire [15:0] _accumPhysical_18_T_1 = accumApmHi_2_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:17]
  wire [47:0] _accumPhysical_18_T_3 = {_accumPhysical_18_T_1,accumApmHi_2_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:12]
  wire [47:0] accumPhysical_18 = narrowResult ? _accumPhysical_18_T_3 : accumApmHi_2_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 203:39]
  wire [15:0] _accumPhysical_3_T_1 = accumApmLo_3_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:17]
  wire [47:0] _accumPhysical_3_T_3 = {_accumPhysical_3_T_1,accumApmLo_3_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:12]
  wire [47:0] accumPhysical_3 = narrowResult ? _accumPhysical_3_T_3 : accumApmLo_3_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 201:31]
  wire [15:0] _accumPhysical_19_T_1 = accumApmHi_3_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:17]
  wire [47:0] _accumPhysical_19_T_3 = {_accumPhysical_19_T_1,accumApmHi_3_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:12]
  wire [47:0] accumPhysical_19 = narrowResult ? _accumPhysical_19_T_3 : accumApmHi_3_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 203:39]
  wire [15:0] _accumPhysical_4_T_1 = accumApmLo_4_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:17]
  wire [47:0] _accumPhysical_4_T_3 = {_accumPhysical_4_T_1,accumApmLo_4_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:12]
  wire [47:0] accumPhysical_4 = narrowResult ? _accumPhysical_4_T_3 : accumApmLo_4_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 201:31]
  wire [15:0] _accumPhysical_20_T_1 = accumApmHi_4_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:17]
  wire [47:0] _accumPhysical_20_T_3 = {_accumPhysical_20_T_1,accumApmHi_4_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:12]
  wire [47:0] accumPhysical_20 = narrowResult ? _accumPhysical_20_T_3 : accumApmHi_4_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 203:39]
  wire [15:0] _accumPhysical_5_T_1 = accumApmLo_5_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:17]
  wire [47:0] _accumPhysical_5_T_3 = {_accumPhysical_5_T_1,accumApmLo_5_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:12]
  wire [47:0] accumPhysical_5 = narrowResult ? _accumPhysical_5_T_3 : accumApmLo_5_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 201:31]
  wire [15:0] _accumPhysical_21_T_1 = accumApmHi_5_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:17]
  wire [47:0] _accumPhysical_21_T_3 = {_accumPhysical_21_T_1,accumApmHi_5_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:12]
  wire [47:0] accumPhysical_21 = narrowResult ? _accumPhysical_21_T_3 : accumApmHi_5_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 203:39]
  wire [15:0] _accumPhysical_6_T_1 = accumApmLo_6_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:17]
  wire [47:0] _accumPhysical_6_T_3 = {_accumPhysical_6_T_1,accumApmLo_6_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:12]
  wire [47:0] accumPhysical_6 = narrowResult ? _accumPhysical_6_T_3 : accumApmLo_6_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 201:31]
  wire [15:0] _accumPhysical_22_T_1 = accumApmHi_6_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:17]
  wire [47:0] _accumPhysical_22_T_3 = {_accumPhysical_22_T_1,accumApmHi_6_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:12]
  wire [47:0] accumPhysical_22 = narrowResult ? _accumPhysical_22_T_3 : accumApmHi_6_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 203:39]
  wire [15:0] _accumPhysical_7_T_1 = accumApmLo_7_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:17]
  wire [47:0] _accumPhysical_7_T_3 = {_accumPhysical_7_T_1,accumApmLo_7_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:12]
  wire [47:0] accumPhysical_7 = narrowResult ? _accumPhysical_7_T_3 : accumApmLo_7_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 201:31]
  wire [15:0] _accumPhysical_23_T_1 = accumApmHi_7_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:17]
  wire [47:0] _accumPhysical_23_T_3 = {_accumPhysical_23_T_1,accumApmHi_7_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:12]
  wire [47:0] accumPhysical_23 = narrowResult ? _accumPhysical_23_T_3 : accumApmHi_7_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 203:39]
  wire [15:0] _accumPhysical_8_T_1 = accumApmLo_8_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:17]
  wire [47:0] _accumPhysical_8_T_3 = {_accumPhysical_8_T_1,accumApmLo_8_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:12]
  wire [47:0] accumPhysical_8 = narrowResult ? _accumPhysical_8_T_3 : accumApmLo_8_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 201:31]
  wire [15:0] _accumPhysical_24_T_1 = accumApmHi_8_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:17]
  wire [47:0] _accumPhysical_24_T_3 = {_accumPhysical_24_T_1,accumApmHi_8_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:12]
  wire [47:0] accumPhysical_24 = narrowResult ? _accumPhysical_24_T_3 : accumApmHi_8_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 203:39]
  wire [15:0] _accumPhysical_9_T_1 = accumApmLo_9_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:17]
  wire [47:0] _accumPhysical_9_T_3 = {_accumPhysical_9_T_1,accumApmLo_9_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:12]
  wire [47:0] accumPhysical_9 = narrowResult ? _accumPhysical_9_T_3 : accumApmLo_9_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 201:31]
  wire [15:0] _accumPhysical_25_T_1 = accumApmHi_9_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:17]
  wire [47:0] _accumPhysical_25_T_3 = {_accumPhysical_25_T_1,accumApmHi_9_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:12]
  wire [47:0] accumPhysical_25 = narrowResult ? _accumPhysical_25_T_3 : accumApmHi_9_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 203:39]
  wire [15:0] _accumPhysical_10_T_1 = accumApmLo_10_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:17]
  wire [47:0] _accumPhysical_10_T_3 = {_accumPhysical_10_T_1,accumApmLo_10_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:12]
  wire [47:0] accumPhysical_10 = narrowResult ? _accumPhysical_10_T_3 : accumApmLo_10_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 201:31]
  wire [15:0] _accumPhysical_26_T_1 = accumApmHi_10_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:17]
  wire [47:0] _accumPhysical_26_T_3 = {_accumPhysical_26_T_1,accumApmHi_10_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:12]
  wire [47:0] accumPhysical_26 = narrowResult ? _accumPhysical_26_T_3 : accumApmHi_10_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 203:39]
  wire [15:0] _accumPhysical_11_T_1 = accumApmLo_11_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:17]
  wire [47:0] _accumPhysical_11_T_3 = {_accumPhysical_11_T_1,accumApmLo_11_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:12]
  wire [47:0] accumPhysical_11 = narrowResult ? _accumPhysical_11_T_3 : accumApmLo_11_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 201:31]
  wire [15:0] _accumPhysical_27_T_1 = accumApmHi_11_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:17]
  wire [47:0] _accumPhysical_27_T_3 = {_accumPhysical_27_T_1,accumApmHi_11_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:12]
  wire [47:0] accumPhysical_27 = narrowResult ? _accumPhysical_27_T_3 : accumApmHi_11_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 203:39]
  wire [15:0] _accumPhysical_12_T_1 = accumApmLo_12_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:17]
  wire [47:0] _accumPhysical_12_T_3 = {_accumPhysical_12_T_1,accumApmLo_12_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:12]
  wire [47:0] accumPhysical_12 = narrowResult ? _accumPhysical_12_T_3 : accumApmLo_12_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 201:31]
  wire [15:0] _accumPhysical_28_T_1 = accumApmHi_12_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:17]
  wire [47:0] _accumPhysical_28_T_3 = {_accumPhysical_28_T_1,accumApmHi_12_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:12]
  wire [47:0] accumPhysical_28 = narrowResult ? _accumPhysical_28_T_3 : accumApmHi_12_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 203:39]
  wire [15:0] _accumPhysical_13_T_1 = accumApmLo_13_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:17]
  wire [47:0] _accumPhysical_13_T_3 = {_accumPhysical_13_T_1,accumApmLo_13_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:12]
  wire [47:0] accumPhysical_13 = narrowResult ? _accumPhysical_13_T_3 : accumApmLo_13_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 201:31]
  wire [15:0] _accumPhysical_29_T_1 = accumApmHi_13_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:17]
  wire [47:0] _accumPhysical_29_T_3 = {_accumPhysical_29_T_1,accumApmHi_13_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:12]
  wire [47:0] accumPhysical_29 = narrowResult ? _accumPhysical_29_T_3 : accumApmHi_13_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 203:39]
  wire [15:0] _accumPhysical_14_T_1 = accumApmLo_14_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:17]
  wire [47:0] _accumPhysical_14_T_3 = {_accumPhysical_14_T_1,accumApmLo_14_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:12]
  wire [47:0] accumPhysical_14 = narrowResult ? _accumPhysical_14_T_3 : accumApmLo_14_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 201:31]
  wire [15:0] _accumPhysical_30_T_1 = accumApmHi_14_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:17]
  wire [47:0] _accumPhysical_30_T_3 = {_accumPhysical_30_T_1,accumApmHi_14_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:12]
  wire [47:0] accumPhysical_30 = narrowResult ? _accumPhysical_30_T_3 : accumApmHi_14_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 203:39]
  wire [15:0] _accumPhysical_15_T_1 = accumApmLo_15_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:17]
  wire [47:0] _accumPhysical_15_T_3 = {_accumPhysical_15_T_1,accumApmLo_15_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 202:12]
  wire [47:0] accumPhysical_15 = narrowResult ? _accumPhysical_15_T_3 : accumApmLo_15_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 201:31]
  wire [15:0] _accumPhysical_31_T_1 = accumApmHi_15_io_result[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:17]
  wire [47:0] _accumPhysical_31_T_3 = {_accumPhysical_31_T_1,accumApmHi_15_io_result[31:0]}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 204:12]
  wire [47:0] accumPhysical_31 = narrowResult ? _accumPhysical_31_T_3 : accumApmHi_15_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 203:39]
  wire [383:0] io_acc_lo_lo = {accumPhysical_7,accumPhysical_6,accumPhysical_5,accumPhysical_4,accumPhysical_3,
    accumPhysical_2,accumPhysical_1,accumPhysical_0}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 209:29]
  wire [767:0] io_acc_lo = {accumPhysical_15,accumPhysical_14,accumPhysical_13,accumPhysical_12,accumPhysical_11,
    accumPhysical_10,accumPhysical_9,accumPhysical_8,io_acc_lo_lo}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 209:29]
  wire [383:0] io_acc_hi_lo = {accumPhysical_23,accumPhysical_22,accumPhysical_21,accumPhysical_20,accumPhysical_19,
    accumPhysical_18,accumPhysical_17,accumPhysical_16}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 209:29]
  wire [767:0] io_acc_hi = {accumPhysical_31,accumPhysical_30,accumPhysical_29,accumPhysical_28,accumPhysical_27,
    accumPhysical_26,accumPhysical_25,accumPhysical_24,io_acc_hi_lo}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 209:29]
  Fp8E4M3ToQ8 fp8Lo ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_io_in),
    .io_out(fp8Lo_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_io_in),
    .io_out(fp8Hi_io_out)
  );
  ApmProduct mLo ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_io_clk),
    .io_rstN(mLo_io_rstN),
    .io_x0(mLo_io_x0),
    .io_w0(mLo_io_w0),
    .io_result(mLo_io_result)
  );
  ApmProduct mHi ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_io_clk),
    .io_rstN(mHi_io_rstN),
    .io_x0(mHi_io_x0),
    .io_w0(mHi_io_w0),
    .io_result(mHi_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_1 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_1_io_in),
    .io_out(fp8Lo_1_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_1 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_1_io_in),
    .io_out(fp8Hi_1_io_out)
  );
  ApmProduct_2 mLo_1 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_1_io_clk),
    .io_rstN(mLo_1_io_rstN),
    .io_x0(mLo_1_io_x0),
    .io_w0(mLo_1_io_w0),
    .io_cpi(mLo_1_io_cpi),
    .io_result(mLo_1_io_result)
  );
  ApmProduct_2 mHi_1 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_1_io_clk),
    .io_rstN(mHi_1_io_rstN),
    .io_x0(mHi_1_io_x0),
    .io_w0(mHi_1_io_w0),
    .io_cpi(mHi_1_io_cpi),
    .io_result(mHi_1_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_2 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_2_io_in),
    .io_out(fp8Lo_2_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_2 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_2_io_in),
    .io_out(fp8Hi_2_io_out)
  );
  ApmProduct_2 mLo_2 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_2_io_clk),
    .io_rstN(mLo_2_io_rstN),
    .io_x0(mLo_2_io_x0),
    .io_w0(mLo_2_io_w0),
    .io_cpi(mLo_2_io_cpi),
    .io_result(mLo_2_io_result)
  );
  ApmProduct_2 mHi_2 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_2_io_clk),
    .io_rstN(mHi_2_io_rstN),
    .io_x0(mHi_2_io_x0),
    .io_w0(mHi_2_io_w0),
    .io_cpi(mHi_2_io_cpi),
    .io_result(mHi_2_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_3 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_3_io_in),
    .io_out(fp8Lo_3_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_3 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_3_io_in),
    .io_out(fp8Hi_3_io_out)
  );
  ApmProduct_6 mLo_3 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_3_io_clk),
    .io_rstN(mLo_3_io_rstN),
    .io_x0(mLo_3_io_x0),
    .io_w0(mLo_3_io_w0),
    .io_cpi(mLo_3_io_cpi),
    .io_result(mLo_3_io_result)
  );
  ApmProduct_6 mHi_3 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_3_io_clk),
    .io_rstN(mHi_3_io_rstN),
    .io_x0(mHi_3_io_x0),
    .io_w0(mHi_3_io_w0),
    .io_cpi(mHi_3_io_cpi),
    .io_result(mHi_3_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_4 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_4_io_in),
    .io_out(fp8Lo_4_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_4 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_4_io_in),
    .io_out(fp8Hi_4_io_out)
  );
  ApmProduct mLo_4 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_4_io_clk),
    .io_rstN(mLo_4_io_rstN),
    .io_x0(mLo_4_io_x0),
    .io_w0(mLo_4_io_w0),
    .io_result(mLo_4_io_result)
  );
  ApmProduct mHi_4 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_4_io_clk),
    .io_rstN(mHi_4_io_rstN),
    .io_x0(mHi_4_io_x0),
    .io_w0(mHi_4_io_w0),
    .io_result(mHi_4_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_5 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_5_io_in),
    .io_out(fp8Lo_5_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_5 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_5_io_in),
    .io_out(fp8Hi_5_io_out)
  );
  ApmProduct_2 mLo_5 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_5_io_clk),
    .io_rstN(mLo_5_io_rstN),
    .io_x0(mLo_5_io_x0),
    .io_w0(mLo_5_io_w0),
    .io_cpi(mLo_5_io_cpi),
    .io_result(mLo_5_io_result)
  );
  ApmProduct_2 mHi_5 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_5_io_clk),
    .io_rstN(mHi_5_io_rstN),
    .io_x0(mHi_5_io_x0),
    .io_w0(mHi_5_io_w0),
    .io_cpi(mHi_5_io_cpi),
    .io_result(mHi_5_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_6 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_6_io_in),
    .io_out(fp8Lo_6_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_6 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_6_io_in),
    .io_out(fp8Hi_6_io_out)
  );
  ApmProduct_2 mLo_6 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_6_io_clk),
    .io_rstN(mLo_6_io_rstN),
    .io_x0(mLo_6_io_x0),
    .io_w0(mLo_6_io_w0),
    .io_cpi(mLo_6_io_cpi),
    .io_result(mLo_6_io_result)
  );
  ApmProduct_2 mHi_6 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_6_io_clk),
    .io_rstN(mHi_6_io_rstN),
    .io_x0(mHi_6_io_x0),
    .io_w0(mHi_6_io_w0),
    .io_cpi(mHi_6_io_cpi),
    .io_result(mHi_6_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_7 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_7_io_in),
    .io_out(fp8Lo_7_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_7 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_7_io_in),
    .io_out(fp8Hi_7_io_out)
  );
  ApmProduct_6 mLo_7 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_7_io_clk),
    .io_rstN(mLo_7_io_rstN),
    .io_x0(mLo_7_io_x0),
    .io_w0(mLo_7_io_w0),
    .io_cpi(mLo_7_io_cpi),
    .io_result(mLo_7_io_result)
  );
  ApmProduct_6 mHi_7 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_7_io_clk),
    .io_rstN(mHi_7_io_rstN),
    .io_x0(mHi_7_io_x0),
    .io_w0(mHi_7_io_w0),
    .io_cpi(mHi_7_io_cpi),
    .io_result(mHi_7_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_8 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_8_io_in),
    .io_out(fp8Lo_8_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_8 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_8_io_in),
    .io_out(fp8Hi_8_io_out)
  );
  ApmProduct mLo_8 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_8_io_clk),
    .io_rstN(mLo_8_io_rstN),
    .io_x0(mLo_8_io_x0),
    .io_w0(mLo_8_io_w0),
    .io_result(mLo_8_io_result)
  );
  ApmProduct mHi_8 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_8_io_clk),
    .io_rstN(mHi_8_io_rstN),
    .io_x0(mHi_8_io_x0),
    .io_w0(mHi_8_io_w0),
    .io_result(mHi_8_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_9 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_9_io_in),
    .io_out(fp8Lo_9_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_9 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_9_io_in),
    .io_out(fp8Hi_9_io_out)
  );
  ApmProduct_2 mLo_9 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_9_io_clk),
    .io_rstN(mLo_9_io_rstN),
    .io_x0(mLo_9_io_x0),
    .io_w0(mLo_9_io_w0),
    .io_cpi(mLo_9_io_cpi),
    .io_result(mLo_9_io_result)
  );
  ApmProduct_2 mHi_9 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_9_io_clk),
    .io_rstN(mHi_9_io_rstN),
    .io_x0(mHi_9_io_x0),
    .io_w0(mHi_9_io_w0),
    .io_cpi(mHi_9_io_cpi),
    .io_result(mHi_9_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_10 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_10_io_in),
    .io_out(fp8Lo_10_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_10 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_10_io_in),
    .io_out(fp8Hi_10_io_out)
  );
  ApmProduct_2 mLo_10 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_10_io_clk),
    .io_rstN(mLo_10_io_rstN),
    .io_x0(mLo_10_io_x0),
    .io_w0(mLo_10_io_w0),
    .io_cpi(mLo_10_io_cpi),
    .io_result(mLo_10_io_result)
  );
  ApmProduct_2 mHi_10 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_10_io_clk),
    .io_rstN(mHi_10_io_rstN),
    .io_x0(mHi_10_io_x0),
    .io_w0(mHi_10_io_w0),
    .io_cpi(mHi_10_io_cpi),
    .io_result(mHi_10_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_11 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_11_io_in),
    .io_out(fp8Lo_11_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_11 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_11_io_in),
    .io_out(fp8Hi_11_io_out)
  );
  ApmProduct_6 mLo_11 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_11_io_clk),
    .io_rstN(mLo_11_io_rstN),
    .io_x0(mLo_11_io_x0),
    .io_w0(mLo_11_io_w0),
    .io_cpi(mLo_11_io_cpi),
    .io_result(mLo_11_io_result)
  );
  ApmProduct_6 mHi_11 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_11_io_clk),
    .io_rstN(mHi_11_io_rstN),
    .io_x0(mHi_11_io_x0),
    .io_w0(mHi_11_io_w0),
    .io_cpi(mHi_11_io_cpi),
    .io_result(mHi_11_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_12 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_12_io_in),
    .io_out(fp8Lo_12_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_12 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_12_io_in),
    .io_out(fp8Hi_12_io_out)
  );
  ApmProduct mLo_12 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_12_io_clk),
    .io_rstN(mLo_12_io_rstN),
    .io_x0(mLo_12_io_x0),
    .io_w0(mLo_12_io_w0),
    .io_result(mLo_12_io_result)
  );
  ApmProduct mHi_12 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_12_io_clk),
    .io_rstN(mHi_12_io_rstN),
    .io_x0(mHi_12_io_x0),
    .io_w0(mHi_12_io_w0),
    .io_result(mHi_12_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_13 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_13_io_in),
    .io_out(fp8Lo_13_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_13 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_13_io_in),
    .io_out(fp8Hi_13_io_out)
  );
  ApmProduct_2 mLo_13 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_13_io_clk),
    .io_rstN(mLo_13_io_rstN),
    .io_x0(mLo_13_io_x0),
    .io_w0(mLo_13_io_w0),
    .io_cpi(mLo_13_io_cpi),
    .io_result(mLo_13_io_result)
  );
  ApmProduct_2 mHi_13 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_13_io_clk),
    .io_rstN(mHi_13_io_rstN),
    .io_x0(mHi_13_io_x0),
    .io_w0(mHi_13_io_w0),
    .io_cpi(mHi_13_io_cpi),
    .io_result(mHi_13_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_14 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_14_io_in),
    .io_out(fp8Lo_14_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_14 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_14_io_in),
    .io_out(fp8Hi_14_io_out)
  );
  ApmProduct_2 mLo_14 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_14_io_clk),
    .io_rstN(mLo_14_io_rstN),
    .io_x0(mLo_14_io_x0),
    .io_w0(mLo_14_io_w0),
    .io_cpi(mLo_14_io_cpi),
    .io_result(mLo_14_io_result)
  );
  ApmProduct_2 mHi_14 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_14_io_clk),
    .io_rstN(mHi_14_io_rstN),
    .io_x0(mHi_14_io_x0),
    .io_w0(mHi_14_io_w0),
    .io_cpi(mHi_14_io_cpi),
    .io_result(mHi_14_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_15 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_15_io_in),
    .io_out(fp8Lo_15_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_15 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_15_io_in),
    .io_out(fp8Hi_15_io_out)
  );
  ApmProduct_6 mLo_15 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_15_io_clk),
    .io_rstN(mLo_15_io_rstN),
    .io_x0(mLo_15_io_x0),
    .io_w0(mLo_15_io_w0),
    .io_cpi(mLo_15_io_cpi),
    .io_result(mLo_15_io_result)
  );
  ApmProduct_6 mHi_15 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_15_io_clk),
    .io_rstN(mHi_15_io_rstN),
    .io_x0(mHi_15_io_x0),
    .io_w0(mHi_15_io_w0),
    .io_cpi(mHi_15_io_cpi),
    .io_result(mHi_15_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_16 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_16_io_in),
    .io_out(fp8Lo_16_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_16 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_16_io_in),
    .io_out(fp8Hi_16_io_out)
  );
  ApmProduct mLo_16 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_16_io_clk),
    .io_rstN(mLo_16_io_rstN),
    .io_x0(mLo_16_io_x0),
    .io_w0(mLo_16_io_w0),
    .io_result(mLo_16_io_result)
  );
  ApmProduct mHi_16 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_16_io_clk),
    .io_rstN(mHi_16_io_rstN),
    .io_x0(mHi_16_io_x0),
    .io_w0(mHi_16_io_w0),
    .io_result(mHi_16_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_17 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_17_io_in),
    .io_out(fp8Lo_17_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_17 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_17_io_in),
    .io_out(fp8Hi_17_io_out)
  );
  ApmProduct_2 mLo_17 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_17_io_clk),
    .io_rstN(mLo_17_io_rstN),
    .io_x0(mLo_17_io_x0),
    .io_w0(mLo_17_io_w0),
    .io_cpi(mLo_17_io_cpi),
    .io_result(mLo_17_io_result)
  );
  ApmProduct_2 mHi_17 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_17_io_clk),
    .io_rstN(mHi_17_io_rstN),
    .io_x0(mHi_17_io_x0),
    .io_w0(mHi_17_io_w0),
    .io_cpi(mHi_17_io_cpi),
    .io_result(mHi_17_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_18 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_18_io_in),
    .io_out(fp8Lo_18_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_18 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_18_io_in),
    .io_out(fp8Hi_18_io_out)
  );
  ApmProduct_2 mLo_18 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_18_io_clk),
    .io_rstN(mLo_18_io_rstN),
    .io_x0(mLo_18_io_x0),
    .io_w0(mLo_18_io_w0),
    .io_cpi(mLo_18_io_cpi),
    .io_result(mLo_18_io_result)
  );
  ApmProduct_2 mHi_18 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_18_io_clk),
    .io_rstN(mHi_18_io_rstN),
    .io_x0(mHi_18_io_x0),
    .io_w0(mHi_18_io_w0),
    .io_cpi(mHi_18_io_cpi),
    .io_result(mHi_18_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_19 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_19_io_in),
    .io_out(fp8Lo_19_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_19 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_19_io_in),
    .io_out(fp8Hi_19_io_out)
  );
  ApmProduct_6 mLo_19 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_19_io_clk),
    .io_rstN(mLo_19_io_rstN),
    .io_x0(mLo_19_io_x0),
    .io_w0(mLo_19_io_w0),
    .io_cpi(mLo_19_io_cpi),
    .io_result(mLo_19_io_result)
  );
  ApmProduct_6 mHi_19 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_19_io_clk),
    .io_rstN(mHi_19_io_rstN),
    .io_x0(mHi_19_io_x0),
    .io_w0(mHi_19_io_w0),
    .io_cpi(mHi_19_io_cpi),
    .io_result(mHi_19_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_20 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_20_io_in),
    .io_out(fp8Lo_20_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_20 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_20_io_in),
    .io_out(fp8Hi_20_io_out)
  );
  ApmProduct mLo_20 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_20_io_clk),
    .io_rstN(mLo_20_io_rstN),
    .io_x0(mLo_20_io_x0),
    .io_w0(mLo_20_io_w0),
    .io_result(mLo_20_io_result)
  );
  ApmProduct mHi_20 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_20_io_clk),
    .io_rstN(mHi_20_io_rstN),
    .io_x0(mHi_20_io_x0),
    .io_w0(mHi_20_io_w0),
    .io_result(mHi_20_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_21 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_21_io_in),
    .io_out(fp8Lo_21_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_21 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_21_io_in),
    .io_out(fp8Hi_21_io_out)
  );
  ApmProduct_2 mLo_21 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_21_io_clk),
    .io_rstN(mLo_21_io_rstN),
    .io_x0(mLo_21_io_x0),
    .io_w0(mLo_21_io_w0),
    .io_cpi(mLo_21_io_cpi),
    .io_result(mLo_21_io_result)
  );
  ApmProduct_2 mHi_21 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_21_io_clk),
    .io_rstN(mHi_21_io_rstN),
    .io_x0(mHi_21_io_x0),
    .io_w0(mHi_21_io_w0),
    .io_cpi(mHi_21_io_cpi),
    .io_result(mHi_21_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_22 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_22_io_in),
    .io_out(fp8Lo_22_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_22 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_22_io_in),
    .io_out(fp8Hi_22_io_out)
  );
  ApmProduct_2 mLo_22 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_22_io_clk),
    .io_rstN(mLo_22_io_rstN),
    .io_x0(mLo_22_io_x0),
    .io_w0(mLo_22_io_w0),
    .io_cpi(mLo_22_io_cpi),
    .io_result(mLo_22_io_result)
  );
  ApmProduct_2 mHi_22 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_22_io_clk),
    .io_rstN(mHi_22_io_rstN),
    .io_x0(mHi_22_io_x0),
    .io_w0(mHi_22_io_w0),
    .io_cpi(mHi_22_io_cpi),
    .io_result(mHi_22_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_23 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_23_io_in),
    .io_out(fp8Lo_23_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_23 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_23_io_in),
    .io_out(fp8Hi_23_io_out)
  );
  ApmProduct_6 mLo_23 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_23_io_clk),
    .io_rstN(mLo_23_io_rstN),
    .io_x0(mLo_23_io_x0),
    .io_w0(mLo_23_io_w0),
    .io_cpi(mLo_23_io_cpi),
    .io_result(mLo_23_io_result)
  );
  ApmProduct_6 mHi_23 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_23_io_clk),
    .io_rstN(mHi_23_io_rstN),
    .io_x0(mHi_23_io_x0),
    .io_w0(mHi_23_io_w0),
    .io_cpi(mHi_23_io_cpi),
    .io_result(mHi_23_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_24 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_24_io_in),
    .io_out(fp8Lo_24_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_24 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_24_io_in),
    .io_out(fp8Hi_24_io_out)
  );
  ApmProduct mLo_24 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_24_io_clk),
    .io_rstN(mLo_24_io_rstN),
    .io_x0(mLo_24_io_x0),
    .io_w0(mLo_24_io_w0),
    .io_result(mLo_24_io_result)
  );
  ApmProduct mHi_24 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_24_io_clk),
    .io_rstN(mHi_24_io_rstN),
    .io_x0(mHi_24_io_x0),
    .io_w0(mHi_24_io_w0),
    .io_result(mHi_24_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_25 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_25_io_in),
    .io_out(fp8Lo_25_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_25 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_25_io_in),
    .io_out(fp8Hi_25_io_out)
  );
  ApmProduct_2 mLo_25 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_25_io_clk),
    .io_rstN(mLo_25_io_rstN),
    .io_x0(mLo_25_io_x0),
    .io_w0(mLo_25_io_w0),
    .io_cpi(mLo_25_io_cpi),
    .io_result(mLo_25_io_result)
  );
  ApmProduct_2 mHi_25 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_25_io_clk),
    .io_rstN(mHi_25_io_rstN),
    .io_x0(mHi_25_io_x0),
    .io_w0(mHi_25_io_w0),
    .io_cpi(mHi_25_io_cpi),
    .io_result(mHi_25_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_26 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_26_io_in),
    .io_out(fp8Lo_26_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_26 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_26_io_in),
    .io_out(fp8Hi_26_io_out)
  );
  ApmProduct_2 mLo_26 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_26_io_clk),
    .io_rstN(mLo_26_io_rstN),
    .io_x0(mLo_26_io_x0),
    .io_w0(mLo_26_io_w0),
    .io_cpi(mLo_26_io_cpi),
    .io_result(mLo_26_io_result)
  );
  ApmProduct_2 mHi_26 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_26_io_clk),
    .io_rstN(mHi_26_io_rstN),
    .io_x0(mHi_26_io_x0),
    .io_w0(mHi_26_io_w0),
    .io_cpi(mHi_26_io_cpi),
    .io_result(mHi_26_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_27 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_27_io_in),
    .io_out(fp8Lo_27_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_27 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_27_io_in),
    .io_out(fp8Hi_27_io_out)
  );
  ApmProduct_6 mLo_27 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_27_io_clk),
    .io_rstN(mLo_27_io_rstN),
    .io_x0(mLo_27_io_x0),
    .io_w0(mLo_27_io_w0),
    .io_cpi(mLo_27_io_cpi),
    .io_result(mLo_27_io_result)
  );
  ApmProduct_6 mHi_27 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_27_io_clk),
    .io_rstN(mHi_27_io_rstN),
    .io_x0(mHi_27_io_x0),
    .io_w0(mHi_27_io_w0),
    .io_cpi(mHi_27_io_cpi),
    .io_result(mHi_27_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_28 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_28_io_in),
    .io_out(fp8Lo_28_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_28 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_28_io_in),
    .io_out(fp8Hi_28_io_out)
  );
  ApmProduct mLo_28 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_28_io_clk),
    .io_rstN(mLo_28_io_rstN),
    .io_x0(mLo_28_io_x0),
    .io_w0(mLo_28_io_w0),
    .io_result(mLo_28_io_result)
  );
  ApmProduct mHi_28 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_28_io_clk),
    .io_rstN(mHi_28_io_rstN),
    .io_x0(mHi_28_io_x0),
    .io_w0(mHi_28_io_w0),
    .io_result(mHi_28_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_29 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_29_io_in),
    .io_out(fp8Lo_29_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_29 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_29_io_in),
    .io_out(fp8Hi_29_io_out)
  );
  ApmProduct_2 mLo_29 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_29_io_clk),
    .io_rstN(mLo_29_io_rstN),
    .io_x0(mLo_29_io_x0),
    .io_w0(mLo_29_io_w0),
    .io_cpi(mLo_29_io_cpi),
    .io_result(mLo_29_io_result)
  );
  ApmProduct_2 mHi_29 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_29_io_clk),
    .io_rstN(mHi_29_io_rstN),
    .io_x0(mHi_29_io_x0),
    .io_w0(mHi_29_io_w0),
    .io_cpi(mHi_29_io_cpi),
    .io_result(mHi_29_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_30 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_30_io_in),
    .io_out(fp8Lo_30_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_30 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_30_io_in),
    .io_out(fp8Hi_30_io_out)
  );
  ApmProduct_2 mLo_30 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_30_io_clk),
    .io_rstN(mLo_30_io_rstN),
    .io_x0(mLo_30_io_x0),
    .io_w0(mLo_30_io_w0),
    .io_cpi(mLo_30_io_cpi),
    .io_result(mLo_30_io_result)
  );
  ApmProduct_2 mHi_30 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_30_io_clk),
    .io_rstN(mHi_30_io_rstN),
    .io_x0(mHi_30_io_x0),
    .io_w0(mHi_30_io_w0),
    .io_cpi(mHi_30_io_cpi),
    .io_result(mHi_30_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_31 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_31_io_in),
    .io_out(fp8Lo_31_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_31 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_31_io_in),
    .io_out(fp8Hi_31_io_out)
  );
  ApmProduct_6 mLo_31 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_31_io_clk),
    .io_rstN(mLo_31_io_rstN),
    .io_x0(mLo_31_io_x0),
    .io_w0(mLo_31_io_w0),
    .io_cpi(mLo_31_io_cpi),
    .io_result(mLo_31_io_result)
  );
  ApmProduct_6 mHi_31 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_31_io_clk),
    .io_rstN(mHi_31_io_rstN),
    .io_x0(mHi_31_io_x0),
    .io_w0(mHi_31_io_w0),
    .io_cpi(mHi_31_io_cpi),
    .io_result(mHi_31_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_32 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_32_io_in),
    .io_out(fp8Lo_32_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_32 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_32_io_in),
    .io_out(fp8Hi_32_io_out)
  );
  ApmProduct mLo_32 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_32_io_clk),
    .io_rstN(mLo_32_io_rstN),
    .io_x0(mLo_32_io_x0),
    .io_w0(mLo_32_io_w0),
    .io_result(mLo_32_io_result)
  );
  ApmProduct mHi_32 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_32_io_clk),
    .io_rstN(mHi_32_io_rstN),
    .io_x0(mHi_32_io_x0),
    .io_w0(mHi_32_io_w0),
    .io_result(mHi_32_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_33 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_33_io_in),
    .io_out(fp8Lo_33_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_33 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_33_io_in),
    .io_out(fp8Hi_33_io_out)
  );
  ApmProduct_2 mLo_33 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_33_io_clk),
    .io_rstN(mLo_33_io_rstN),
    .io_x0(mLo_33_io_x0),
    .io_w0(mLo_33_io_w0),
    .io_cpi(mLo_33_io_cpi),
    .io_result(mLo_33_io_result)
  );
  ApmProduct_2 mHi_33 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_33_io_clk),
    .io_rstN(mHi_33_io_rstN),
    .io_x0(mHi_33_io_x0),
    .io_w0(mHi_33_io_w0),
    .io_cpi(mHi_33_io_cpi),
    .io_result(mHi_33_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_34 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_34_io_in),
    .io_out(fp8Lo_34_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_34 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_34_io_in),
    .io_out(fp8Hi_34_io_out)
  );
  ApmProduct_2 mLo_34 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_34_io_clk),
    .io_rstN(mLo_34_io_rstN),
    .io_x0(mLo_34_io_x0),
    .io_w0(mLo_34_io_w0),
    .io_cpi(mLo_34_io_cpi),
    .io_result(mLo_34_io_result)
  );
  ApmProduct_2 mHi_34 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_34_io_clk),
    .io_rstN(mHi_34_io_rstN),
    .io_x0(mHi_34_io_x0),
    .io_w0(mHi_34_io_w0),
    .io_cpi(mHi_34_io_cpi),
    .io_result(mHi_34_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_35 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_35_io_in),
    .io_out(fp8Lo_35_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_35 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_35_io_in),
    .io_out(fp8Hi_35_io_out)
  );
  ApmProduct_6 mLo_35 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_35_io_clk),
    .io_rstN(mLo_35_io_rstN),
    .io_x0(mLo_35_io_x0),
    .io_w0(mLo_35_io_w0),
    .io_cpi(mLo_35_io_cpi),
    .io_result(mLo_35_io_result)
  );
  ApmProduct_6 mHi_35 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_35_io_clk),
    .io_rstN(mHi_35_io_rstN),
    .io_x0(mHi_35_io_x0),
    .io_w0(mHi_35_io_w0),
    .io_cpi(mHi_35_io_cpi),
    .io_result(mHi_35_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_36 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_36_io_in),
    .io_out(fp8Lo_36_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_36 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_36_io_in),
    .io_out(fp8Hi_36_io_out)
  );
  ApmProduct mLo_36 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_36_io_clk),
    .io_rstN(mLo_36_io_rstN),
    .io_x0(mLo_36_io_x0),
    .io_w0(mLo_36_io_w0),
    .io_result(mLo_36_io_result)
  );
  ApmProduct mHi_36 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_36_io_clk),
    .io_rstN(mHi_36_io_rstN),
    .io_x0(mHi_36_io_x0),
    .io_w0(mHi_36_io_w0),
    .io_result(mHi_36_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_37 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_37_io_in),
    .io_out(fp8Lo_37_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_37 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_37_io_in),
    .io_out(fp8Hi_37_io_out)
  );
  ApmProduct_2 mLo_37 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_37_io_clk),
    .io_rstN(mLo_37_io_rstN),
    .io_x0(mLo_37_io_x0),
    .io_w0(mLo_37_io_w0),
    .io_cpi(mLo_37_io_cpi),
    .io_result(mLo_37_io_result)
  );
  ApmProduct_2 mHi_37 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_37_io_clk),
    .io_rstN(mHi_37_io_rstN),
    .io_x0(mHi_37_io_x0),
    .io_w0(mHi_37_io_w0),
    .io_cpi(mHi_37_io_cpi),
    .io_result(mHi_37_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_38 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_38_io_in),
    .io_out(fp8Lo_38_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_38 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_38_io_in),
    .io_out(fp8Hi_38_io_out)
  );
  ApmProduct_2 mLo_38 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_38_io_clk),
    .io_rstN(mLo_38_io_rstN),
    .io_x0(mLo_38_io_x0),
    .io_w0(mLo_38_io_w0),
    .io_cpi(mLo_38_io_cpi),
    .io_result(mLo_38_io_result)
  );
  ApmProduct_2 mHi_38 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_38_io_clk),
    .io_rstN(mHi_38_io_rstN),
    .io_x0(mHi_38_io_x0),
    .io_w0(mHi_38_io_w0),
    .io_cpi(mHi_38_io_cpi),
    .io_result(mHi_38_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_39 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_39_io_in),
    .io_out(fp8Lo_39_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_39 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_39_io_in),
    .io_out(fp8Hi_39_io_out)
  );
  ApmProduct_6 mLo_39 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_39_io_clk),
    .io_rstN(mLo_39_io_rstN),
    .io_x0(mLo_39_io_x0),
    .io_w0(mLo_39_io_w0),
    .io_cpi(mLo_39_io_cpi),
    .io_result(mLo_39_io_result)
  );
  ApmProduct_6 mHi_39 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_39_io_clk),
    .io_rstN(mHi_39_io_rstN),
    .io_x0(mHi_39_io_x0),
    .io_w0(mHi_39_io_w0),
    .io_cpi(mHi_39_io_cpi),
    .io_result(mHi_39_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_40 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_40_io_in),
    .io_out(fp8Lo_40_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_40 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_40_io_in),
    .io_out(fp8Hi_40_io_out)
  );
  ApmProduct mLo_40 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_40_io_clk),
    .io_rstN(mLo_40_io_rstN),
    .io_x0(mLo_40_io_x0),
    .io_w0(mLo_40_io_w0),
    .io_result(mLo_40_io_result)
  );
  ApmProduct mHi_40 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_40_io_clk),
    .io_rstN(mHi_40_io_rstN),
    .io_x0(mHi_40_io_x0),
    .io_w0(mHi_40_io_w0),
    .io_result(mHi_40_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_41 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_41_io_in),
    .io_out(fp8Lo_41_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_41 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_41_io_in),
    .io_out(fp8Hi_41_io_out)
  );
  ApmProduct_2 mLo_41 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_41_io_clk),
    .io_rstN(mLo_41_io_rstN),
    .io_x0(mLo_41_io_x0),
    .io_w0(mLo_41_io_w0),
    .io_cpi(mLo_41_io_cpi),
    .io_result(mLo_41_io_result)
  );
  ApmProduct_2 mHi_41 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_41_io_clk),
    .io_rstN(mHi_41_io_rstN),
    .io_x0(mHi_41_io_x0),
    .io_w0(mHi_41_io_w0),
    .io_cpi(mHi_41_io_cpi),
    .io_result(mHi_41_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_42 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_42_io_in),
    .io_out(fp8Lo_42_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_42 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_42_io_in),
    .io_out(fp8Hi_42_io_out)
  );
  ApmProduct_2 mLo_42 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_42_io_clk),
    .io_rstN(mLo_42_io_rstN),
    .io_x0(mLo_42_io_x0),
    .io_w0(mLo_42_io_w0),
    .io_cpi(mLo_42_io_cpi),
    .io_result(mLo_42_io_result)
  );
  ApmProduct_2 mHi_42 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_42_io_clk),
    .io_rstN(mHi_42_io_rstN),
    .io_x0(mHi_42_io_x0),
    .io_w0(mHi_42_io_w0),
    .io_cpi(mHi_42_io_cpi),
    .io_result(mHi_42_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_43 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_43_io_in),
    .io_out(fp8Lo_43_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_43 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_43_io_in),
    .io_out(fp8Hi_43_io_out)
  );
  ApmProduct_6 mLo_43 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_43_io_clk),
    .io_rstN(mLo_43_io_rstN),
    .io_x0(mLo_43_io_x0),
    .io_w0(mLo_43_io_w0),
    .io_cpi(mLo_43_io_cpi),
    .io_result(mLo_43_io_result)
  );
  ApmProduct_6 mHi_43 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_43_io_clk),
    .io_rstN(mHi_43_io_rstN),
    .io_x0(mHi_43_io_x0),
    .io_w0(mHi_43_io_w0),
    .io_cpi(mHi_43_io_cpi),
    .io_result(mHi_43_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_44 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_44_io_in),
    .io_out(fp8Lo_44_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_44 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_44_io_in),
    .io_out(fp8Hi_44_io_out)
  );
  ApmProduct mLo_44 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_44_io_clk),
    .io_rstN(mLo_44_io_rstN),
    .io_x0(mLo_44_io_x0),
    .io_w0(mLo_44_io_w0),
    .io_result(mLo_44_io_result)
  );
  ApmProduct mHi_44 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_44_io_clk),
    .io_rstN(mHi_44_io_rstN),
    .io_x0(mHi_44_io_x0),
    .io_w0(mHi_44_io_w0),
    .io_result(mHi_44_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_45 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_45_io_in),
    .io_out(fp8Lo_45_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_45 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_45_io_in),
    .io_out(fp8Hi_45_io_out)
  );
  ApmProduct_2 mLo_45 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_45_io_clk),
    .io_rstN(mLo_45_io_rstN),
    .io_x0(mLo_45_io_x0),
    .io_w0(mLo_45_io_w0),
    .io_cpi(mLo_45_io_cpi),
    .io_result(mLo_45_io_result)
  );
  ApmProduct_2 mHi_45 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_45_io_clk),
    .io_rstN(mHi_45_io_rstN),
    .io_x0(mHi_45_io_x0),
    .io_w0(mHi_45_io_w0),
    .io_cpi(mHi_45_io_cpi),
    .io_result(mHi_45_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_46 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_46_io_in),
    .io_out(fp8Lo_46_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_46 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_46_io_in),
    .io_out(fp8Hi_46_io_out)
  );
  ApmProduct_2 mLo_46 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_46_io_clk),
    .io_rstN(mLo_46_io_rstN),
    .io_x0(mLo_46_io_x0),
    .io_w0(mLo_46_io_w0),
    .io_cpi(mLo_46_io_cpi),
    .io_result(mLo_46_io_result)
  );
  ApmProduct_2 mHi_46 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_46_io_clk),
    .io_rstN(mHi_46_io_rstN),
    .io_x0(mHi_46_io_x0),
    .io_w0(mHi_46_io_w0),
    .io_cpi(mHi_46_io_cpi),
    .io_result(mHi_46_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_47 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_47_io_in),
    .io_out(fp8Lo_47_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_47 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_47_io_in),
    .io_out(fp8Hi_47_io_out)
  );
  ApmProduct_6 mLo_47 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_47_io_clk),
    .io_rstN(mLo_47_io_rstN),
    .io_x0(mLo_47_io_x0),
    .io_w0(mLo_47_io_w0),
    .io_cpi(mLo_47_io_cpi),
    .io_result(mLo_47_io_result)
  );
  ApmProduct_6 mHi_47 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_47_io_clk),
    .io_rstN(mHi_47_io_rstN),
    .io_x0(mHi_47_io_x0),
    .io_w0(mHi_47_io_w0),
    .io_cpi(mHi_47_io_cpi),
    .io_result(mHi_47_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_48 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_48_io_in),
    .io_out(fp8Lo_48_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_48 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_48_io_in),
    .io_out(fp8Hi_48_io_out)
  );
  ApmProduct mLo_48 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_48_io_clk),
    .io_rstN(mLo_48_io_rstN),
    .io_x0(mLo_48_io_x0),
    .io_w0(mLo_48_io_w0),
    .io_result(mLo_48_io_result)
  );
  ApmProduct mHi_48 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_48_io_clk),
    .io_rstN(mHi_48_io_rstN),
    .io_x0(mHi_48_io_x0),
    .io_w0(mHi_48_io_w0),
    .io_result(mHi_48_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_49 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_49_io_in),
    .io_out(fp8Lo_49_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_49 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_49_io_in),
    .io_out(fp8Hi_49_io_out)
  );
  ApmProduct_2 mLo_49 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_49_io_clk),
    .io_rstN(mLo_49_io_rstN),
    .io_x0(mLo_49_io_x0),
    .io_w0(mLo_49_io_w0),
    .io_cpi(mLo_49_io_cpi),
    .io_result(mLo_49_io_result)
  );
  ApmProduct_2 mHi_49 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_49_io_clk),
    .io_rstN(mHi_49_io_rstN),
    .io_x0(mHi_49_io_x0),
    .io_w0(mHi_49_io_w0),
    .io_cpi(mHi_49_io_cpi),
    .io_result(mHi_49_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_50 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_50_io_in),
    .io_out(fp8Lo_50_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_50 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_50_io_in),
    .io_out(fp8Hi_50_io_out)
  );
  ApmProduct_2 mLo_50 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_50_io_clk),
    .io_rstN(mLo_50_io_rstN),
    .io_x0(mLo_50_io_x0),
    .io_w0(mLo_50_io_w0),
    .io_cpi(mLo_50_io_cpi),
    .io_result(mLo_50_io_result)
  );
  ApmProduct_2 mHi_50 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_50_io_clk),
    .io_rstN(mHi_50_io_rstN),
    .io_x0(mHi_50_io_x0),
    .io_w0(mHi_50_io_w0),
    .io_cpi(mHi_50_io_cpi),
    .io_result(mHi_50_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_51 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_51_io_in),
    .io_out(fp8Lo_51_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_51 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_51_io_in),
    .io_out(fp8Hi_51_io_out)
  );
  ApmProduct_6 mLo_51 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_51_io_clk),
    .io_rstN(mLo_51_io_rstN),
    .io_x0(mLo_51_io_x0),
    .io_w0(mLo_51_io_w0),
    .io_cpi(mLo_51_io_cpi),
    .io_result(mLo_51_io_result)
  );
  ApmProduct_6 mHi_51 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_51_io_clk),
    .io_rstN(mHi_51_io_rstN),
    .io_x0(mHi_51_io_x0),
    .io_w0(mHi_51_io_w0),
    .io_cpi(mHi_51_io_cpi),
    .io_result(mHi_51_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_52 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_52_io_in),
    .io_out(fp8Lo_52_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_52 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_52_io_in),
    .io_out(fp8Hi_52_io_out)
  );
  ApmProduct mLo_52 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_52_io_clk),
    .io_rstN(mLo_52_io_rstN),
    .io_x0(mLo_52_io_x0),
    .io_w0(mLo_52_io_w0),
    .io_result(mLo_52_io_result)
  );
  ApmProduct mHi_52 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_52_io_clk),
    .io_rstN(mHi_52_io_rstN),
    .io_x0(mHi_52_io_x0),
    .io_w0(mHi_52_io_w0),
    .io_result(mHi_52_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_53 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_53_io_in),
    .io_out(fp8Lo_53_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_53 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_53_io_in),
    .io_out(fp8Hi_53_io_out)
  );
  ApmProduct_2 mLo_53 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_53_io_clk),
    .io_rstN(mLo_53_io_rstN),
    .io_x0(mLo_53_io_x0),
    .io_w0(mLo_53_io_w0),
    .io_cpi(mLo_53_io_cpi),
    .io_result(mLo_53_io_result)
  );
  ApmProduct_2 mHi_53 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_53_io_clk),
    .io_rstN(mHi_53_io_rstN),
    .io_x0(mHi_53_io_x0),
    .io_w0(mHi_53_io_w0),
    .io_cpi(mHi_53_io_cpi),
    .io_result(mHi_53_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_54 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_54_io_in),
    .io_out(fp8Lo_54_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_54 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_54_io_in),
    .io_out(fp8Hi_54_io_out)
  );
  ApmProduct_2 mLo_54 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_54_io_clk),
    .io_rstN(mLo_54_io_rstN),
    .io_x0(mLo_54_io_x0),
    .io_w0(mLo_54_io_w0),
    .io_cpi(mLo_54_io_cpi),
    .io_result(mLo_54_io_result)
  );
  ApmProduct_2 mHi_54 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_54_io_clk),
    .io_rstN(mHi_54_io_rstN),
    .io_x0(mHi_54_io_x0),
    .io_w0(mHi_54_io_w0),
    .io_cpi(mHi_54_io_cpi),
    .io_result(mHi_54_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_55 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_55_io_in),
    .io_out(fp8Lo_55_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_55 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_55_io_in),
    .io_out(fp8Hi_55_io_out)
  );
  ApmProduct_6 mLo_55 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_55_io_clk),
    .io_rstN(mLo_55_io_rstN),
    .io_x0(mLo_55_io_x0),
    .io_w0(mLo_55_io_w0),
    .io_cpi(mLo_55_io_cpi),
    .io_result(mLo_55_io_result)
  );
  ApmProduct_6 mHi_55 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_55_io_clk),
    .io_rstN(mHi_55_io_rstN),
    .io_x0(mHi_55_io_x0),
    .io_w0(mHi_55_io_w0),
    .io_cpi(mHi_55_io_cpi),
    .io_result(mHi_55_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_56 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_56_io_in),
    .io_out(fp8Lo_56_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_56 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_56_io_in),
    .io_out(fp8Hi_56_io_out)
  );
  ApmProduct mLo_56 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_56_io_clk),
    .io_rstN(mLo_56_io_rstN),
    .io_x0(mLo_56_io_x0),
    .io_w0(mLo_56_io_w0),
    .io_result(mLo_56_io_result)
  );
  ApmProduct mHi_56 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_56_io_clk),
    .io_rstN(mHi_56_io_rstN),
    .io_x0(mHi_56_io_x0),
    .io_w0(mHi_56_io_w0),
    .io_result(mHi_56_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_57 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_57_io_in),
    .io_out(fp8Lo_57_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_57 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_57_io_in),
    .io_out(fp8Hi_57_io_out)
  );
  ApmProduct_2 mLo_57 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_57_io_clk),
    .io_rstN(mLo_57_io_rstN),
    .io_x0(mLo_57_io_x0),
    .io_w0(mLo_57_io_w0),
    .io_cpi(mLo_57_io_cpi),
    .io_result(mLo_57_io_result)
  );
  ApmProduct_2 mHi_57 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_57_io_clk),
    .io_rstN(mHi_57_io_rstN),
    .io_x0(mHi_57_io_x0),
    .io_w0(mHi_57_io_w0),
    .io_cpi(mHi_57_io_cpi),
    .io_result(mHi_57_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_58 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_58_io_in),
    .io_out(fp8Lo_58_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_58 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_58_io_in),
    .io_out(fp8Hi_58_io_out)
  );
  ApmProduct_2 mLo_58 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_58_io_clk),
    .io_rstN(mLo_58_io_rstN),
    .io_x0(mLo_58_io_x0),
    .io_w0(mLo_58_io_w0),
    .io_cpi(mLo_58_io_cpi),
    .io_result(mLo_58_io_result)
  );
  ApmProduct_2 mHi_58 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_58_io_clk),
    .io_rstN(mHi_58_io_rstN),
    .io_x0(mHi_58_io_x0),
    .io_w0(mHi_58_io_w0),
    .io_cpi(mHi_58_io_cpi),
    .io_result(mHi_58_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_59 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_59_io_in),
    .io_out(fp8Lo_59_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_59 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_59_io_in),
    .io_out(fp8Hi_59_io_out)
  );
  ApmProduct_6 mLo_59 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_59_io_clk),
    .io_rstN(mLo_59_io_rstN),
    .io_x0(mLo_59_io_x0),
    .io_w0(mLo_59_io_w0),
    .io_cpi(mLo_59_io_cpi),
    .io_result(mLo_59_io_result)
  );
  ApmProduct_6 mHi_59 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_59_io_clk),
    .io_rstN(mHi_59_io_rstN),
    .io_x0(mHi_59_io_x0),
    .io_w0(mHi_59_io_w0),
    .io_cpi(mHi_59_io_cpi),
    .io_result(mHi_59_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_60 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_60_io_in),
    .io_out(fp8Lo_60_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_60 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_60_io_in),
    .io_out(fp8Hi_60_io_out)
  );
  ApmProduct mLo_60 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_60_io_clk),
    .io_rstN(mLo_60_io_rstN),
    .io_x0(mLo_60_io_x0),
    .io_w0(mLo_60_io_w0),
    .io_result(mLo_60_io_result)
  );
  ApmProduct mHi_60 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_60_io_clk),
    .io_rstN(mHi_60_io_rstN),
    .io_x0(mHi_60_io_x0),
    .io_w0(mHi_60_io_w0),
    .io_result(mHi_60_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_61 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_61_io_in),
    .io_out(fp8Lo_61_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_61 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_61_io_in),
    .io_out(fp8Hi_61_io_out)
  );
  ApmProduct_2 mLo_61 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_61_io_clk),
    .io_rstN(mLo_61_io_rstN),
    .io_x0(mLo_61_io_x0),
    .io_w0(mLo_61_io_w0),
    .io_cpi(mLo_61_io_cpi),
    .io_result(mLo_61_io_result)
  );
  ApmProduct_2 mHi_61 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_61_io_clk),
    .io_rstN(mHi_61_io_rstN),
    .io_x0(mHi_61_io_x0),
    .io_w0(mHi_61_io_w0),
    .io_cpi(mHi_61_io_cpi),
    .io_result(mHi_61_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_62 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_62_io_in),
    .io_out(fp8Lo_62_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_62 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_62_io_in),
    .io_out(fp8Hi_62_io_out)
  );
  ApmProduct_2 mLo_62 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_62_io_clk),
    .io_rstN(mLo_62_io_rstN),
    .io_x0(mLo_62_io_x0),
    .io_w0(mLo_62_io_w0),
    .io_cpi(mLo_62_io_cpi),
    .io_result(mLo_62_io_result)
  );
  ApmProduct_2 mHi_62 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_62_io_clk),
    .io_rstN(mHi_62_io_rstN),
    .io_x0(mHi_62_io_x0),
    .io_w0(mHi_62_io_w0),
    .io_cpi(mHi_62_io_cpi),
    .io_result(mHi_62_io_result)
  );
  Fp8E4M3ToQ8 fp8Lo_63 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 89:25]
    .io_in(fp8Lo_63_io_in),
    .io_out(fp8Lo_63_io_out)
  );
  Fp8E4M3ToQ8 fp8Hi_63 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 90:25]
    .io_in(fp8Hi_63_io_in),
    .io_out(fp8Hi_63_io_out)
  );
  ApmProduct_6 mLo_63 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 114:23]
    .io_clk(mLo_63_io_clk),
    .io_rstN(mLo_63_io_rstN),
    .io_x0(mLo_63_io_x0),
    .io_w0(mLo_63_io_w0),
    .io_cpi(mLo_63_io_cpi),
    .io_result(mLo_63_io_result)
  );
  ApmProduct_6 mHi_63 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 123:23]
    .io_clk(mHi_63_io_clk),
    .io_rstN(mHi_63_io_rstN),
    .io_x0(mHi_63_io_x0),
    .io_w0(mHi_63_io_w0),
    .io_cpi(mHi_63_io_cpi),
    .io_result(mHi_63_io_result)
  );
  ApmAccumulator accumApmLo_0 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
    .io_clk(accumApmLo_0_io_clk),
    .io_rstN(accumApmLo_0_io_rstN),
    .io_enable(accumApmLo_0_io_enable),
    .io_clear(accumApmLo_0_io_clear),
    .io_addend(accumApmLo_0_io_addend),
    .io_result(accumApmLo_0_io_result)
  );
  ApmAccumulator accumApmLo_1 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
    .io_clk(accumApmLo_1_io_clk),
    .io_rstN(accumApmLo_1_io_rstN),
    .io_enable(accumApmLo_1_io_enable),
    .io_clear(accumApmLo_1_io_clear),
    .io_addend(accumApmLo_1_io_addend),
    .io_result(accumApmLo_1_io_result)
  );
  ApmAccumulator accumApmLo_2 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
    .io_clk(accumApmLo_2_io_clk),
    .io_rstN(accumApmLo_2_io_rstN),
    .io_enable(accumApmLo_2_io_enable),
    .io_clear(accumApmLo_2_io_clear),
    .io_addend(accumApmLo_2_io_addend),
    .io_result(accumApmLo_2_io_result)
  );
  ApmAccumulator accumApmLo_3 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
    .io_clk(accumApmLo_3_io_clk),
    .io_rstN(accumApmLo_3_io_rstN),
    .io_enable(accumApmLo_3_io_enable),
    .io_clear(accumApmLo_3_io_clear),
    .io_addend(accumApmLo_3_io_addend),
    .io_result(accumApmLo_3_io_result)
  );
  ApmAccumulator accumApmLo_4 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
    .io_clk(accumApmLo_4_io_clk),
    .io_rstN(accumApmLo_4_io_rstN),
    .io_enable(accumApmLo_4_io_enable),
    .io_clear(accumApmLo_4_io_clear),
    .io_addend(accumApmLo_4_io_addend),
    .io_result(accumApmLo_4_io_result)
  );
  ApmAccumulator accumApmLo_5 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
    .io_clk(accumApmLo_5_io_clk),
    .io_rstN(accumApmLo_5_io_rstN),
    .io_enable(accumApmLo_5_io_enable),
    .io_clear(accumApmLo_5_io_clear),
    .io_addend(accumApmLo_5_io_addend),
    .io_result(accumApmLo_5_io_result)
  );
  ApmAccumulator accumApmLo_6 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
    .io_clk(accumApmLo_6_io_clk),
    .io_rstN(accumApmLo_6_io_rstN),
    .io_enable(accumApmLo_6_io_enable),
    .io_clear(accumApmLo_6_io_clear),
    .io_addend(accumApmLo_6_io_addend),
    .io_result(accumApmLo_6_io_result)
  );
  ApmAccumulator accumApmLo_7 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
    .io_clk(accumApmLo_7_io_clk),
    .io_rstN(accumApmLo_7_io_rstN),
    .io_enable(accumApmLo_7_io_enable),
    .io_clear(accumApmLo_7_io_clear),
    .io_addend(accumApmLo_7_io_addend),
    .io_result(accumApmLo_7_io_result)
  );
  ApmAccumulator accumApmLo_8 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
    .io_clk(accumApmLo_8_io_clk),
    .io_rstN(accumApmLo_8_io_rstN),
    .io_enable(accumApmLo_8_io_enable),
    .io_clear(accumApmLo_8_io_clear),
    .io_addend(accumApmLo_8_io_addend),
    .io_result(accumApmLo_8_io_result)
  );
  ApmAccumulator accumApmLo_9 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
    .io_clk(accumApmLo_9_io_clk),
    .io_rstN(accumApmLo_9_io_rstN),
    .io_enable(accumApmLo_9_io_enable),
    .io_clear(accumApmLo_9_io_clear),
    .io_addend(accumApmLo_9_io_addend),
    .io_result(accumApmLo_9_io_result)
  );
  ApmAccumulator accumApmLo_10 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
    .io_clk(accumApmLo_10_io_clk),
    .io_rstN(accumApmLo_10_io_rstN),
    .io_enable(accumApmLo_10_io_enable),
    .io_clear(accumApmLo_10_io_clear),
    .io_addend(accumApmLo_10_io_addend),
    .io_result(accumApmLo_10_io_result)
  );
  ApmAccumulator accumApmLo_11 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
    .io_clk(accumApmLo_11_io_clk),
    .io_rstN(accumApmLo_11_io_rstN),
    .io_enable(accumApmLo_11_io_enable),
    .io_clear(accumApmLo_11_io_clear),
    .io_addend(accumApmLo_11_io_addend),
    .io_result(accumApmLo_11_io_result)
  );
  ApmAccumulator accumApmLo_12 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
    .io_clk(accumApmLo_12_io_clk),
    .io_rstN(accumApmLo_12_io_rstN),
    .io_enable(accumApmLo_12_io_enable),
    .io_clear(accumApmLo_12_io_clear),
    .io_addend(accumApmLo_12_io_addend),
    .io_result(accumApmLo_12_io_result)
  );
  ApmAccumulator accumApmLo_13 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
    .io_clk(accumApmLo_13_io_clk),
    .io_rstN(accumApmLo_13_io_rstN),
    .io_enable(accumApmLo_13_io_enable),
    .io_clear(accumApmLo_13_io_clear),
    .io_addend(accumApmLo_13_io_addend),
    .io_result(accumApmLo_13_io_result)
  );
  ApmAccumulator accumApmLo_14 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
    .io_clk(accumApmLo_14_io_clk),
    .io_rstN(accumApmLo_14_io_rstN),
    .io_enable(accumApmLo_14_io_enable),
    .io_clear(accumApmLo_14_io_clear),
    .io_addend(accumApmLo_14_io_addend),
    .io_result(accumApmLo_14_io_result)
  );
  ApmAccumulator accumApmLo_15 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 150:44]
    .io_clk(accumApmLo_15_io_clk),
    .io_rstN(accumApmLo_15_io_rstN),
    .io_enable(accumApmLo_15_io_enable),
    .io_clear(accumApmLo_15_io_clear),
    .io_addend(accumApmLo_15_io_addend),
    .io_result(accumApmLo_15_io_result)
  );
  ApmAccumulator accumApmHi_0 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
    .io_clk(accumApmHi_0_io_clk),
    .io_rstN(accumApmHi_0_io_rstN),
    .io_enable(accumApmHi_0_io_enable),
    .io_clear(accumApmHi_0_io_clear),
    .io_addend(accumApmHi_0_io_addend),
    .io_result(accumApmHi_0_io_result)
  );
  ApmAccumulator accumApmHi_1 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
    .io_clk(accumApmHi_1_io_clk),
    .io_rstN(accumApmHi_1_io_rstN),
    .io_enable(accumApmHi_1_io_enable),
    .io_clear(accumApmHi_1_io_clear),
    .io_addend(accumApmHi_1_io_addend),
    .io_result(accumApmHi_1_io_result)
  );
  ApmAccumulator accumApmHi_2 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
    .io_clk(accumApmHi_2_io_clk),
    .io_rstN(accumApmHi_2_io_rstN),
    .io_enable(accumApmHi_2_io_enable),
    .io_clear(accumApmHi_2_io_clear),
    .io_addend(accumApmHi_2_io_addend),
    .io_result(accumApmHi_2_io_result)
  );
  ApmAccumulator accumApmHi_3 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
    .io_clk(accumApmHi_3_io_clk),
    .io_rstN(accumApmHi_3_io_rstN),
    .io_enable(accumApmHi_3_io_enable),
    .io_clear(accumApmHi_3_io_clear),
    .io_addend(accumApmHi_3_io_addend),
    .io_result(accumApmHi_3_io_result)
  );
  ApmAccumulator accumApmHi_4 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
    .io_clk(accumApmHi_4_io_clk),
    .io_rstN(accumApmHi_4_io_rstN),
    .io_enable(accumApmHi_4_io_enable),
    .io_clear(accumApmHi_4_io_clear),
    .io_addend(accumApmHi_4_io_addend),
    .io_result(accumApmHi_4_io_result)
  );
  ApmAccumulator accumApmHi_5 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
    .io_clk(accumApmHi_5_io_clk),
    .io_rstN(accumApmHi_5_io_rstN),
    .io_enable(accumApmHi_5_io_enable),
    .io_clear(accumApmHi_5_io_clear),
    .io_addend(accumApmHi_5_io_addend),
    .io_result(accumApmHi_5_io_result)
  );
  ApmAccumulator accumApmHi_6 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
    .io_clk(accumApmHi_6_io_clk),
    .io_rstN(accumApmHi_6_io_rstN),
    .io_enable(accumApmHi_6_io_enable),
    .io_clear(accumApmHi_6_io_clear),
    .io_addend(accumApmHi_6_io_addend),
    .io_result(accumApmHi_6_io_result)
  );
  ApmAccumulator accumApmHi_7 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
    .io_clk(accumApmHi_7_io_clk),
    .io_rstN(accumApmHi_7_io_rstN),
    .io_enable(accumApmHi_7_io_enable),
    .io_clear(accumApmHi_7_io_clear),
    .io_addend(accumApmHi_7_io_addend),
    .io_result(accumApmHi_7_io_result)
  );
  ApmAccumulator accumApmHi_8 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
    .io_clk(accumApmHi_8_io_clk),
    .io_rstN(accumApmHi_8_io_rstN),
    .io_enable(accumApmHi_8_io_enable),
    .io_clear(accumApmHi_8_io_clear),
    .io_addend(accumApmHi_8_io_addend),
    .io_result(accumApmHi_8_io_result)
  );
  ApmAccumulator accumApmHi_9 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
    .io_clk(accumApmHi_9_io_clk),
    .io_rstN(accumApmHi_9_io_rstN),
    .io_enable(accumApmHi_9_io_enable),
    .io_clear(accumApmHi_9_io_clear),
    .io_addend(accumApmHi_9_io_addend),
    .io_result(accumApmHi_9_io_result)
  );
  ApmAccumulator accumApmHi_10 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
    .io_clk(accumApmHi_10_io_clk),
    .io_rstN(accumApmHi_10_io_rstN),
    .io_enable(accumApmHi_10_io_enable),
    .io_clear(accumApmHi_10_io_clear),
    .io_addend(accumApmHi_10_io_addend),
    .io_result(accumApmHi_10_io_result)
  );
  ApmAccumulator accumApmHi_11 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
    .io_clk(accumApmHi_11_io_clk),
    .io_rstN(accumApmHi_11_io_rstN),
    .io_enable(accumApmHi_11_io_enable),
    .io_clear(accumApmHi_11_io_clear),
    .io_addend(accumApmHi_11_io_addend),
    .io_result(accumApmHi_11_io_result)
  );
  ApmAccumulator accumApmHi_12 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
    .io_clk(accumApmHi_12_io_clk),
    .io_rstN(accumApmHi_12_io_rstN),
    .io_enable(accumApmHi_12_io_enable),
    .io_clear(accumApmHi_12_io_clear),
    .io_addend(accumApmHi_12_io_addend),
    .io_result(accumApmHi_12_io_result)
  );
  ApmAccumulator accumApmHi_13 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
    .io_clk(accumApmHi_13_io_clk),
    .io_rstN(accumApmHi_13_io_rstN),
    .io_enable(accumApmHi_13_io_enable),
    .io_clear(accumApmHi_13_io_clear),
    .io_addend(accumApmHi_13_io_addend),
    .io_result(accumApmHi_13_io_result)
  );
  ApmAccumulator accumApmHi_14 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
    .io_clk(accumApmHi_14_io_clk),
    .io_rstN(accumApmHi_14_io_rstN),
    .io_enable(accumApmHi_14_io_enable),
    .io_clear(accumApmHi_14_io_clear),
    .io_addend(accumApmHi_14_io_addend),
    .io_result(accumApmHi_14_io_result)
  );
  ApmAccumulator accumApmHi_15 ( // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 151:44]
    .io_clk(accumApmHi_15_io_clk),
    .io_rstN(accumApmHi_15_io_rstN),
    .io_enable(accumApmHi_15_io_enable),
    .io_clear(accumApmHi_15_io_clear),
    .io_addend(accumApmHi_15_io_addend),
    .io_result(accumApmHi_15_io_result)
  );
  assign io_validO = validR; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 208:15]
  assign io_acc = {io_acc_hi,io_acc_lo}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 209:29]
  assign io_postResult = {io_acc_hi,io_acc_lo}; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 210:36]
  assign fp8Lo_io_in = wWord[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_io_in = wWord[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_io_x0 = io_postMode ? postLo : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_io_w0 = io_postMode ? postLo : regularWLo; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mHi_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_io_x0 = io_postMode ? postHi : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_io_w0 = io_postMode ? postHi : regularWHi; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign fp8Lo_1_io_in = wWord_1[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_1_io_in = wWord_1[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_1_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_1_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_1_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_1_io_w0 = io_postMode ? 18'h0 : regularWLo_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_1_io_cpi = mLo_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_1_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_1_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_1_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_1_io_w0 = io_postMode ? 18'h0 : regularWHi_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_1_io_cpi = mHi_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_2_io_in = wWord_2[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_2_io_in = wWord_2[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_2_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_2_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_2_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_2_io_w0 = io_postMode ? 18'h0 : regularWLo_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_2_io_cpi = mLo_1_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_2_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_2_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_2_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_2_io_w0 = io_postMode ? 18'h0 : regularWHi_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_2_io_cpi = mHi_1_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_3_io_in = wWord_3[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_3_io_in = wWord_3[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_3_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_3_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_3_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_3_io_w0 = io_postMode ? 18'h0 : regularWLo_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_3_io_cpi = mLo_2_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_3_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_3_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_3_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_3_io_w0 = io_postMode ? 18'h0 : regularWHi_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_3_io_cpi = mHi_2_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_4_io_in = wWord_4[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_4_io_in = wWord_4[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_4_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_4_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_4_io_x0 = io_postMode ? postLo_4 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_4_io_w0 = io_postMode ? postLo_4 : regularWLo_4; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mHi_4_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_4_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_4_io_x0 = io_postMode ? postHi_4 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_4_io_w0 = io_postMode ? postHi_4 : regularWHi_4; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign fp8Lo_5_io_in = wWord_5[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_5_io_in = wWord_5[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_5_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_5_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_5_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_5_io_w0 = io_postMode ? 18'h0 : regularWLo_5; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_5_io_cpi = mLo_4_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_5_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_5_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_5_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_5_io_w0 = io_postMode ? 18'h0 : regularWHi_5; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_5_io_cpi = mHi_4_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_6_io_in = wWord_6[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_6_io_in = wWord_6[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_6_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_6_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_6_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_6_io_w0 = io_postMode ? 18'h0 : regularWLo_6; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_6_io_cpi = mLo_5_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_6_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_6_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_6_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_6_io_w0 = io_postMode ? 18'h0 : regularWHi_6; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_6_io_cpi = mHi_5_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_7_io_in = wWord_7[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_7_io_in = wWord_7[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_7_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_7_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_7_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_7_io_w0 = io_postMode ? 18'h0 : regularWLo_7; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_7_io_cpi = mLo_6_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_7_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_7_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_7_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_7_io_w0 = io_postMode ? 18'h0 : regularWHi_7; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_7_io_cpi = mHi_6_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_8_io_in = wWord_8[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_8_io_in = wWord_8[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_8_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_8_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_8_io_x0 = io_postMode ? postLo_8 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_8_io_w0 = io_postMode ? postLo_8 : regularWLo_8; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mHi_8_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_8_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_8_io_x0 = io_postMode ? postHi_8 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_8_io_w0 = io_postMode ? postHi_8 : regularWHi_8; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign fp8Lo_9_io_in = wWord_9[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_9_io_in = wWord_9[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_9_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_9_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_9_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_9_io_w0 = io_postMode ? 18'h0 : regularWLo_9; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_9_io_cpi = mLo_8_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_9_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_9_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_9_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_9_io_w0 = io_postMode ? 18'h0 : regularWHi_9; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_9_io_cpi = mHi_8_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_10_io_in = wWord_10[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_10_io_in = wWord_10[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_10_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_10_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_10_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_10_io_w0 = io_postMode ? 18'h0 : regularWLo_10; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_10_io_cpi = mLo_9_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_10_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_10_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_10_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_10_io_w0 = io_postMode ? 18'h0 : regularWHi_10; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_10_io_cpi = mHi_9_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_11_io_in = wWord_11[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_11_io_in = wWord_11[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_11_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_11_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_11_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_11_io_w0 = io_postMode ? 18'h0 : regularWLo_11; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_11_io_cpi = mLo_10_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_11_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_11_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_11_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_11_io_w0 = io_postMode ? 18'h0 : regularWHi_11; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_11_io_cpi = mHi_10_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_12_io_in = wWord_12[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_12_io_in = wWord_12[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_12_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_12_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_12_io_x0 = io_postMode ? postLo_12 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_12_io_w0 = io_postMode ? postLo_12 : regularWLo_12; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mHi_12_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_12_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_12_io_x0 = io_postMode ? postHi_12 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_12_io_w0 = io_postMode ? postHi_12 : regularWHi_12; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign fp8Lo_13_io_in = wWord_13[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_13_io_in = wWord_13[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_13_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_13_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_13_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_13_io_w0 = io_postMode ? 18'h0 : regularWLo_13; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_13_io_cpi = mLo_12_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_13_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_13_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_13_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_13_io_w0 = io_postMode ? 18'h0 : regularWHi_13; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_13_io_cpi = mHi_12_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_14_io_in = wWord_14[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_14_io_in = wWord_14[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_14_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_14_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_14_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_14_io_w0 = io_postMode ? 18'h0 : regularWLo_14; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_14_io_cpi = mLo_13_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_14_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_14_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_14_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_14_io_w0 = io_postMode ? 18'h0 : regularWHi_14; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_14_io_cpi = mHi_13_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_15_io_in = wWord_15[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_15_io_in = wWord_15[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_15_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_15_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_15_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_15_io_w0 = io_postMode ? 18'h0 : regularWLo_15; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_15_io_cpi = mLo_14_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_15_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_15_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_15_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_15_io_w0 = io_postMode ? 18'h0 : regularWHi_15; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_15_io_cpi = mHi_14_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_16_io_in = wWord_16[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_16_io_in = wWord_16[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_16_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_16_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_16_io_x0 = io_postMode ? postLo_16 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_16_io_w0 = io_postMode ? postLo_16 : regularWLo_16; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mHi_16_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_16_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_16_io_x0 = io_postMode ? postHi_16 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_16_io_w0 = io_postMode ? postHi_16 : regularWHi_16; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign fp8Lo_17_io_in = wWord_17[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_17_io_in = wWord_17[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_17_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_17_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_17_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_17_io_w0 = io_postMode ? 18'h0 : regularWLo_17; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_17_io_cpi = mLo_16_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_17_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_17_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_17_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_17_io_w0 = io_postMode ? 18'h0 : regularWHi_17; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_17_io_cpi = mHi_16_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_18_io_in = wWord_18[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_18_io_in = wWord_18[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_18_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_18_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_18_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_18_io_w0 = io_postMode ? 18'h0 : regularWLo_18; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_18_io_cpi = mLo_17_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_18_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_18_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_18_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_18_io_w0 = io_postMode ? 18'h0 : regularWHi_18; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_18_io_cpi = mHi_17_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_19_io_in = wWord_19[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_19_io_in = wWord_19[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_19_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_19_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_19_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_19_io_w0 = io_postMode ? 18'h0 : regularWLo_19; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_19_io_cpi = mLo_18_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_19_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_19_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_19_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_19_io_w0 = io_postMode ? 18'h0 : regularWHi_19; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_19_io_cpi = mHi_18_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_20_io_in = wWord_20[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_20_io_in = wWord_20[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_20_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_20_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_20_io_x0 = io_postMode ? postLo_20 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_20_io_w0 = io_postMode ? postLo_20 : regularWLo_20; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mHi_20_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_20_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_20_io_x0 = io_postMode ? postHi_20 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_20_io_w0 = io_postMode ? postHi_20 : regularWHi_20; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign fp8Lo_21_io_in = wWord_21[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_21_io_in = wWord_21[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_21_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_21_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_21_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_21_io_w0 = io_postMode ? 18'h0 : regularWLo_21; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_21_io_cpi = mLo_20_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_21_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_21_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_21_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_21_io_w0 = io_postMode ? 18'h0 : regularWHi_21; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_21_io_cpi = mHi_20_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_22_io_in = wWord_22[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_22_io_in = wWord_22[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_22_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_22_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_22_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_22_io_w0 = io_postMode ? 18'h0 : regularWLo_22; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_22_io_cpi = mLo_21_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_22_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_22_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_22_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_22_io_w0 = io_postMode ? 18'h0 : regularWHi_22; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_22_io_cpi = mHi_21_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_23_io_in = wWord_23[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_23_io_in = wWord_23[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_23_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_23_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_23_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_23_io_w0 = io_postMode ? 18'h0 : regularWLo_23; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_23_io_cpi = mLo_22_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_23_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_23_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_23_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_23_io_w0 = io_postMode ? 18'h0 : regularWHi_23; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_23_io_cpi = mHi_22_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_24_io_in = wWord_24[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_24_io_in = wWord_24[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_24_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_24_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_24_io_x0 = io_postMode ? postLo_24 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_24_io_w0 = io_postMode ? postLo_24 : regularWLo_24; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mHi_24_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_24_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_24_io_x0 = io_postMode ? postHi_24 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_24_io_w0 = io_postMode ? postHi_24 : regularWHi_24; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign fp8Lo_25_io_in = wWord_25[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_25_io_in = wWord_25[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_25_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_25_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_25_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_25_io_w0 = io_postMode ? 18'h0 : regularWLo_25; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_25_io_cpi = mLo_24_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_25_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_25_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_25_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_25_io_w0 = io_postMode ? 18'h0 : regularWHi_25; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_25_io_cpi = mHi_24_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_26_io_in = wWord_26[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_26_io_in = wWord_26[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_26_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_26_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_26_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_26_io_w0 = io_postMode ? 18'h0 : regularWLo_26; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_26_io_cpi = mLo_25_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_26_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_26_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_26_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_26_io_w0 = io_postMode ? 18'h0 : regularWHi_26; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_26_io_cpi = mHi_25_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_27_io_in = wWord_27[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_27_io_in = wWord_27[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_27_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_27_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_27_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_27_io_w0 = io_postMode ? 18'h0 : regularWLo_27; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_27_io_cpi = mLo_26_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_27_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_27_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_27_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_27_io_w0 = io_postMode ? 18'h0 : regularWHi_27; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_27_io_cpi = mHi_26_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_28_io_in = wWord_28[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_28_io_in = wWord_28[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_28_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_28_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_28_io_x0 = io_postMode ? postLo_28 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_28_io_w0 = io_postMode ? postLo_28 : regularWLo_28; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mHi_28_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_28_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_28_io_x0 = io_postMode ? postHi_28 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_28_io_w0 = io_postMode ? postHi_28 : regularWHi_28; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign fp8Lo_29_io_in = wWord_29[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_29_io_in = wWord_29[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_29_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_29_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_29_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_29_io_w0 = io_postMode ? 18'h0 : regularWLo_29; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_29_io_cpi = mLo_28_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_29_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_29_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_29_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_29_io_w0 = io_postMode ? 18'h0 : regularWHi_29; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_29_io_cpi = mHi_28_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_30_io_in = wWord_30[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_30_io_in = wWord_30[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_30_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_30_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_30_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_30_io_w0 = io_postMode ? 18'h0 : regularWLo_30; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_30_io_cpi = mLo_29_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_30_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_30_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_30_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_30_io_w0 = io_postMode ? 18'h0 : regularWHi_30; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_30_io_cpi = mHi_29_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_31_io_in = wWord_31[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_31_io_in = wWord_31[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_31_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_31_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_31_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_31_io_w0 = io_postMode ? 18'h0 : regularWLo_31; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_31_io_cpi = mLo_30_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_31_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_31_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_31_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_31_io_w0 = io_postMode ? 18'h0 : regularWHi_31; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_31_io_cpi = mHi_30_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_32_io_in = wWord_32[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_32_io_in = wWord_32[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_32_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_32_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_32_io_x0 = io_postMode ? postLo_32 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_32_io_w0 = io_postMode ? postLo_32 : regularWLo_32; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mHi_32_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_32_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_32_io_x0 = io_postMode ? postHi_32 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_32_io_w0 = io_postMode ? postHi_32 : regularWHi_32; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign fp8Lo_33_io_in = wWord_33[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_33_io_in = wWord_33[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_33_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_33_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_33_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_33_io_w0 = io_postMode ? 18'h0 : regularWLo_33; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_33_io_cpi = mLo_32_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_33_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_33_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_33_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_33_io_w0 = io_postMode ? 18'h0 : regularWHi_33; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_33_io_cpi = mHi_32_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_34_io_in = wWord_34[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_34_io_in = wWord_34[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_34_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_34_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_34_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_34_io_w0 = io_postMode ? 18'h0 : regularWLo_34; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_34_io_cpi = mLo_33_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_34_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_34_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_34_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_34_io_w0 = io_postMode ? 18'h0 : regularWHi_34; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_34_io_cpi = mHi_33_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_35_io_in = wWord_35[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_35_io_in = wWord_35[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_35_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_35_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_35_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_35_io_w0 = io_postMode ? 18'h0 : regularWLo_35; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_35_io_cpi = mLo_34_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_35_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_35_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_35_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_35_io_w0 = io_postMode ? 18'h0 : regularWHi_35; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_35_io_cpi = mHi_34_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_36_io_in = wWord_36[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_36_io_in = wWord_36[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_36_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_36_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_36_io_x0 = io_postMode ? postLo_36 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_36_io_w0 = io_postMode ? postLo_36 : regularWLo_36; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mHi_36_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_36_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_36_io_x0 = io_postMode ? postHi_36 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_36_io_w0 = io_postMode ? postHi_36 : regularWHi_36; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign fp8Lo_37_io_in = wWord_37[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_37_io_in = wWord_37[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_37_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_37_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_37_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_37_io_w0 = io_postMode ? 18'h0 : regularWLo_37; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_37_io_cpi = mLo_36_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_37_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_37_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_37_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_37_io_w0 = io_postMode ? 18'h0 : regularWHi_37; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_37_io_cpi = mHi_36_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_38_io_in = wWord_38[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_38_io_in = wWord_38[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_38_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_38_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_38_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_38_io_w0 = io_postMode ? 18'h0 : regularWLo_38; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_38_io_cpi = mLo_37_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_38_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_38_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_38_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_38_io_w0 = io_postMode ? 18'h0 : regularWHi_38; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_38_io_cpi = mHi_37_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_39_io_in = wWord_39[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_39_io_in = wWord_39[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_39_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_39_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_39_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_39_io_w0 = io_postMode ? 18'h0 : regularWLo_39; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_39_io_cpi = mLo_38_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_39_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_39_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_39_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_39_io_w0 = io_postMode ? 18'h0 : regularWHi_39; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_39_io_cpi = mHi_38_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_40_io_in = wWord_40[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_40_io_in = wWord_40[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_40_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_40_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_40_io_x0 = io_postMode ? postLo_40 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_40_io_w0 = io_postMode ? postLo_40 : regularWLo_40; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mHi_40_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_40_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_40_io_x0 = io_postMode ? postHi_40 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_40_io_w0 = io_postMode ? postHi_40 : regularWHi_40; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign fp8Lo_41_io_in = wWord_41[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_41_io_in = wWord_41[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_41_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_41_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_41_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_41_io_w0 = io_postMode ? 18'h0 : regularWLo_41; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_41_io_cpi = mLo_40_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_41_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_41_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_41_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_41_io_w0 = io_postMode ? 18'h0 : regularWHi_41; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_41_io_cpi = mHi_40_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_42_io_in = wWord_42[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_42_io_in = wWord_42[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_42_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_42_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_42_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_42_io_w0 = io_postMode ? 18'h0 : regularWLo_42; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_42_io_cpi = mLo_41_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_42_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_42_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_42_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_42_io_w0 = io_postMode ? 18'h0 : regularWHi_42; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_42_io_cpi = mHi_41_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_43_io_in = wWord_43[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_43_io_in = wWord_43[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_43_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_43_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_43_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_43_io_w0 = io_postMode ? 18'h0 : regularWLo_43; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_43_io_cpi = mLo_42_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_43_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_43_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_43_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_43_io_w0 = io_postMode ? 18'h0 : regularWHi_43; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_43_io_cpi = mHi_42_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_44_io_in = wWord_44[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_44_io_in = wWord_44[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_44_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_44_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_44_io_x0 = io_postMode ? postLo_44 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_44_io_w0 = io_postMode ? postLo_44 : regularWLo_44; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mHi_44_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_44_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_44_io_x0 = io_postMode ? postHi_44 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_44_io_w0 = io_postMode ? postHi_44 : regularWHi_44; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign fp8Lo_45_io_in = wWord_45[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_45_io_in = wWord_45[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_45_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_45_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_45_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_45_io_w0 = io_postMode ? 18'h0 : regularWLo_45; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_45_io_cpi = mLo_44_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_45_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_45_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_45_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_45_io_w0 = io_postMode ? 18'h0 : regularWHi_45; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_45_io_cpi = mHi_44_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_46_io_in = wWord_46[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_46_io_in = wWord_46[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_46_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_46_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_46_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_46_io_w0 = io_postMode ? 18'h0 : regularWLo_46; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_46_io_cpi = mLo_45_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_46_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_46_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_46_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_46_io_w0 = io_postMode ? 18'h0 : regularWHi_46; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_46_io_cpi = mHi_45_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_47_io_in = wWord_47[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_47_io_in = wWord_47[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_47_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_47_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_47_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_47_io_w0 = io_postMode ? 18'h0 : regularWLo_47; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_47_io_cpi = mLo_46_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_47_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_47_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_47_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_47_io_w0 = io_postMode ? 18'h0 : regularWHi_47; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_47_io_cpi = mHi_46_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_48_io_in = wWord_48[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_48_io_in = wWord_48[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_48_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_48_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_48_io_x0 = io_postMode ? postLo_48 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_48_io_w0 = io_postMode ? postLo_48 : regularWLo_48; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mHi_48_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_48_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_48_io_x0 = io_postMode ? postHi_48 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_48_io_w0 = io_postMode ? postHi_48 : regularWHi_48; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign fp8Lo_49_io_in = wWord_49[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_49_io_in = wWord_49[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_49_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_49_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_49_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_49_io_w0 = io_postMode ? 18'h0 : regularWLo_49; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_49_io_cpi = mLo_48_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_49_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_49_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_49_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_49_io_w0 = io_postMode ? 18'h0 : regularWHi_49; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_49_io_cpi = mHi_48_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_50_io_in = wWord_50[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_50_io_in = wWord_50[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_50_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_50_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_50_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_50_io_w0 = io_postMode ? 18'h0 : regularWLo_50; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_50_io_cpi = mLo_49_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_50_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_50_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_50_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_50_io_w0 = io_postMode ? 18'h0 : regularWHi_50; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_50_io_cpi = mHi_49_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_51_io_in = wWord_51[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_51_io_in = wWord_51[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_51_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_51_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_51_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_51_io_w0 = io_postMode ? 18'h0 : regularWLo_51; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_51_io_cpi = mLo_50_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_51_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_51_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_51_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_51_io_w0 = io_postMode ? 18'h0 : regularWHi_51; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_51_io_cpi = mHi_50_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_52_io_in = wWord_52[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_52_io_in = wWord_52[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_52_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_52_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_52_io_x0 = io_postMode ? postLo_52 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_52_io_w0 = io_postMode ? postLo_52 : regularWLo_52; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mHi_52_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_52_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_52_io_x0 = io_postMode ? postHi_52 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_52_io_w0 = io_postMode ? postHi_52 : regularWHi_52; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign fp8Lo_53_io_in = wWord_53[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_53_io_in = wWord_53[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_53_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_53_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_53_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_53_io_w0 = io_postMode ? 18'h0 : regularWLo_53; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_53_io_cpi = mLo_52_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_53_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_53_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_53_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_53_io_w0 = io_postMode ? 18'h0 : regularWHi_53; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_53_io_cpi = mHi_52_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_54_io_in = wWord_54[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_54_io_in = wWord_54[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_54_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_54_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_54_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_54_io_w0 = io_postMode ? 18'h0 : regularWLo_54; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_54_io_cpi = mLo_53_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_54_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_54_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_54_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_54_io_w0 = io_postMode ? 18'h0 : regularWHi_54; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_54_io_cpi = mHi_53_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_55_io_in = wWord_55[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_55_io_in = wWord_55[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_55_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_55_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_55_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_55_io_w0 = io_postMode ? 18'h0 : regularWLo_55; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_55_io_cpi = mLo_54_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_55_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_55_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_55_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_55_io_w0 = io_postMode ? 18'h0 : regularWHi_55; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_55_io_cpi = mHi_54_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_56_io_in = wWord_56[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_56_io_in = wWord_56[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_56_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_56_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_56_io_x0 = io_postMode ? postLo_56 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_56_io_w0 = io_postMode ? postLo_56 : regularWLo_56; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mHi_56_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_56_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_56_io_x0 = io_postMode ? postHi_56 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_56_io_w0 = io_postMode ? postHi_56 : regularWHi_56; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign fp8Lo_57_io_in = wWord_57[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_57_io_in = wWord_57[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_57_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_57_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_57_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_57_io_w0 = io_postMode ? 18'h0 : regularWLo_57; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_57_io_cpi = mLo_56_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_57_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_57_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_57_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_57_io_w0 = io_postMode ? 18'h0 : regularWHi_57; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_57_io_cpi = mHi_56_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_58_io_in = wWord_58[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_58_io_in = wWord_58[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_58_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_58_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_58_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_58_io_w0 = io_postMode ? 18'h0 : regularWLo_58; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_58_io_cpi = mLo_57_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_58_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_58_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_58_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_58_io_w0 = io_postMode ? 18'h0 : regularWHi_58; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_58_io_cpi = mHi_57_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_59_io_in = wWord_59[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_59_io_in = wWord_59[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_59_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_59_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_59_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_59_io_w0 = io_postMode ? 18'h0 : regularWLo_59; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_59_io_cpi = mLo_58_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_59_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_59_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_59_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_59_io_w0 = io_postMode ? 18'h0 : regularWHi_59; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_59_io_cpi = mHi_58_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_60_io_in = wWord_60[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_60_io_in = wWord_60[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_60_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_60_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_60_io_x0 = io_postMode ? postLo_60 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_60_io_w0 = io_postMode ? postLo_60 : regularWLo_60; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mHi_60_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_60_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_60_io_x0 = io_postMode ? postHi_60 : regularX_0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_60_io_w0 = io_postMode ? postHi_60 : regularWHi_60; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign fp8Lo_61_io_in = wWord_61[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_61_io_in = wWord_61[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_61_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_61_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_61_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_61_io_w0 = io_postMode ? 18'h0 : regularWLo_61; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_61_io_cpi = mLo_60_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_61_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_61_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_61_io_x0 = io_postMode ? 18'h0 : regularX_1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_61_io_w0 = io_postMode ? 18'h0 : regularWHi_61; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_61_io_cpi = mHi_60_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_62_io_in = wWord_62[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_62_io_in = wWord_62[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_62_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_62_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_62_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_62_io_w0 = io_postMode ? 18'h0 : regularWLo_62; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_62_io_cpi = mLo_61_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_62_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_62_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_62_io_x0 = io_postMode ? 18'h0 : regularX_2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_62_io_w0 = io_postMode ? 18'h0 : regularWHi_62; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_62_io_cpi = mHi_61_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign fp8Lo_63_io_in = wWord_63[7:0]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 91:27]
  assign fp8Hi_63_io_in = wWord_63[15:8]; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 92:27]
  assign mLo_63_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 116:18]
  assign mLo_63_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 117:19]
  assign mLo_63_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 118:23]
  assign mLo_63_io_w0 = io_postMode ? 18'h0 : regularWLo_63; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 119:23]
  assign mLo_63_io_cpi = mLo_62_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign mHi_63_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 125:18]
  assign mHi_63_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 126:19]
  assign mHi_63_io_x0 = io_postMode ? 18'h0 : regularX_3; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 127:23]
  assign mHi_63_io_w0 = io_postMode ? 18'h0 : regularWHi_63; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 128:23]
  assign mHi_63_io_cpi = mHi_62_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign accumApmLo_0_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 177:29]
  assign accumApmLo_0_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 178:30]
  assign accumApmLo_0_io_enable = validD2 & (postD2 | lowLaneEnable); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 179:43]
  assign accumApmLo_0_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 180:42]
  assign accumApmLo_0_io_addend = mLo_3_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign accumApmLo_1_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 177:29]
  assign accumApmLo_1_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 178:30]
  assign accumApmLo_1_io_enable = validD2 & (postD2 | lowLaneEnable_1); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 179:43]
  assign accumApmLo_1_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 180:42]
  assign accumApmLo_1_io_addend = mLo_7_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign accumApmLo_2_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 177:29]
  assign accumApmLo_2_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 178:30]
  assign accumApmLo_2_io_enable = validD2 & (postD2 | lowLaneEnable_2); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 179:43]
  assign accumApmLo_2_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 180:42]
  assign accumApmLo_2_io_addend = mLo_11_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign accumApmLo_3_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 177:29]
  assign accumApmLo_3_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 178:30]
  assign accumApmLo_3_io_enable = validD2 & (postD2 | lowLaneEnable_3); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 179:43]
  assign accumApmLo_3_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 180:42]
  assign accumApmLo_3_io_addend = mLo_15_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign accumApmLo_4_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 177:29]
  assign accumApmLo_4_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 178:30]
  assign accumApmLo_4_io_enable = validD2 & (postD2 | lowLaneEnable_4); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 179:43]
  assign accumApmLo_4_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 180:42]
  assign accumApmLo_4_io_addend = mLo_19_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign accumApmLo_5_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 177:29]
  assign accumApmLo_5_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 178:30]
  assign accumApmLo_5_io_enable = validD2 & (postD2 | lowLaneEnable_5); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 179:43]
  assign accumApmLo_5_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 180:42]
  assign accumApmLo_5_io_addend = mLo_23_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign accumApmLo_6_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 177:29]
  assign accumApmLo_6_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 178:30]
  assign accumApmLo_6_io_enable = validD2 & (postD2 | lowLaneEnable_6); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 179:43]
  assign accumApmLo_6_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 180:42]
  assign accumApmLo_6_io_addend = mLo_27_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign accumApmLo_7_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 177:29]
  assign accumApmLo_7_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 178:30]
  assign accumApmLo_7_io_enable = validD2 & (postD2 | lowLaneEnable_7); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 179:43]
  assign accumApmLo_7_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 180:42]
  assign accumApmLo_7_io_addend = mLo_31_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign accumApmLo_8_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 177:29]
  assign accumApmLo_8_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 178:30]
  assign accumApmLo_8_io_enable = validD2 & (postD2 | lowLaneEnable_8); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 179:43]
  assign accumApmLo_8_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 180:42]
  assign accumApmLo_8_io_addend = mLo_35_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign accumApmLo_9_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 177:29]
  assign accumApmLo_9_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 178:30]
  assign accumApmLo_9_io_enable = validD2 & (postD2 | lowLaneEnable_9); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 179:43]
  assign accumApmLo_9_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 180:42]
  assign accumApmLo_9_io_addend = mLo_39_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign accumApmLo_10_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 177:29]
  assign accumApmLo_10_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 178:30]
  assign accumApmLo_10_io_enable = validD2 & (postD2 | lowLaneEnable_10); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 179:43]
  assign accumApmLo_10_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 180:42]
  assign accumApmLo_10_io_addend = mLo_43_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign accumApmLo_11_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 177:29]
  assign accumApmLo_11_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 178:30]
  assign accumApmLo_11_io_enable = validD2 & (postD2 | lowLaneEnable_11); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 179:43]
  assign accumApmLo_11_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 180:42]
  assign accumApmLo_11_io_addend = mLo_47_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign accumApmLo_12_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 177:29]
  assign accumApmLo_12_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 178:30]
  assign accumApmLo_12_io_enable = validD2 & (postD2 | lowLaneEnable_12); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 179:43]
  assign accumApmLo_12_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 180:42]
  assign accumApmLo_12_io_addend = mLo_51_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign accumApmLo_13_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 177:29]
  assign accumApmLo_13_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 178:30]
  assign accumApmLo_13_io_enable = validD2 & (postD2 | lowLaneEnable_13); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 179:43]
  assign accumApmLo_13_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 180:42]
  assign accumApmLo_13_io_addend = mLo_55_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign accumApmLo_14_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 177:29]
  assign accumApmLo_14_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 178:30]
  assign accumApmLo_14_io_enable = validD2 & (postD2 | lowLaneEnable_14); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 179:43]
  assign accumApmLo_14_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 180:42]
  assign accumApmLo_14_io_addend = mLo_59_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign accumApmLo_15_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 177:29]
  assign accumApmLo_15_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 178:30]
  assign accumApmLo_15_io_enable = validD2 & (postD2 | lowLaneEnable_15); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 179:43]
  assign accumApmLo_15_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 180:42]
  assign accumApmLo_15_io_addend = mLo_63_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 121:19 73:23]
  assign accumApmHi_0_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 183:29]
  assign accumApmHi_0_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 184:30]
  assign accumApmHi_0_io_enable = validD2 & (postD2 | highLaneEnable); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 185:43]
  assign accumApmHi_0_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 186:42]
  assign accumApmHi_0_io_addend = mHi_3_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign accumApmHi_1_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 183:29]
  assign accumApmHi_1_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 184:30]
  assign accumApmHi_1_io_enable = validD2 & (postD2 | highLaneEnable_1); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 185:43]
  assign accumApmHi_1_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 186:42]
  assign accumApmHi_1_io_addend = mHi_7_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign accumApmHi_2_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 183:29]
  assign accumApmHi_2_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 184:30]
  assign accumApmHi_2_io_enable = validD2 & (postD2 | highLaneEnable_2); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 185:43]
  assign accumApmHi_2_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 186:42]
  assign accumApmHi_2_io_addend = mHi_11_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign accumApmHi_3_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 183:29]
  assign accumApmHi_3_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 184:30]
  assign accumApmHi_3_io_enable = validD2 & (postD2 | highLaneEnable_3); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 185:43]
  assign accumApmHi_3_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 186:42]
  assign accumApmHi_3_io_addend = mHi_15_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign accumApmHi_4_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 183:29]
  assign accumApmHi_4_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 184:30]
  assign accumApmHi_4_io_enable = validD2 & (postD2 | highLaneEnable_4); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 185:43]
  assign accumApmHi_4_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 186:42]
  assign accumApmHi_4_io_addend = mHi_19_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign accumApmHi_5_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 183:29]
  assign accumApmHi_5_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 184:30]
  assign accumApmHi_5_io_enable = validD2 & (postD2 | highLaneEnable_5); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 185:43]
  assign accumApmHi_5_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 186:42]
  assign accumApmHi_5_io_addend = mHi_23_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign accumApmHi_6_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 183:29]
  assign accumApmHi_6_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 184:30]
  assign accumApmHi_6_io_enable = validD2 & (postD2 | highLaneEnable_6); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 185:43]
  assign accumApmHi_6_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 186:42]
  assign accumApmHi_6_io_addend = mHi_27_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign accumApmHi_7_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 183:29]
  assign accumApmHi_7_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 184:30]
  assign accumApmHi_7_io_enable = validD2 & (postD2 | highLaneEnable_7); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 185:43]
  assign accumApmHi_7_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 186:42]
  assign accumApmHi_7_io_addend = mHi_31_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign accumApmHi_8_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 183:29]
  assign accumApmHi_8_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 184:30]
  assign accumApmHi_8_io_enable = validD2 & (postD2 | highLaneEnable_8); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 185:43]
  assign accumApmHi_8_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 186:42]
  assign accumApmHi_8_io_addend = mHi_35_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign accumApmHi_9_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 183:29]
  assign accumApmHi_9_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 184:30]
  assign accumApmHi_9_io_enable = validD2 & (postD2 | highLaneEnable_9); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 185:43]
  assign accumApmHi_9_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 186:42]
  assign accumApmHi_9_io_addend = mHi_39_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign accumApmHi_10_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 183:29]
  assign accumApmHi_10_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 184:30]
  assign accumApmHi_10_io_enable = validD2 & (postD2 | highLaneEnable_10); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 185:43]
  assign accumApmHi_10_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 186:42]
  assign accumApmHi_10_io_addend = mHi_43_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign accumApmHi_11_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 183:29]
  assign accumApmHi_11_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 184:30]
  assign accumApmHi_11_io_enable = validD2 & (postD2 | highLaneEnable_11); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 185:43]
  assign accumApmHi_11_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 186:42]
  assign accumApmHi_11_io_addend = mHi_47_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign accumApmHi_12_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 183:29]
  assign accumApmHi_12_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 184:30]
  assign accumApmHi_12_io_enable = validD2 & (postD2 | highLaneEnable_12); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 185:43]
  assign accumApmHi_12_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 186:42]
  assign accumApmHi_12_io_addend = mHi_51_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign accumApmHi_13_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 183:29]
  assign accumApmHi_13_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 184:30]
  assign accumApmHi_13_io_enable = validD2 & (postD2 | highLaneEnable_13); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 185:43]
  assign accumApmHi_13_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 186:42]
  assign accumApmHi_13_io_addend = mHi_55_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign accumApmHi_14_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 183:29]
  assign accumApmHi_14_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 184:30]
  assign accumApmHi_14_io_enable = validD2 & (postD2 | highLaneEnable_14); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 185:43]
  assign accumApmHi_14_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 186:42]
  assign accumApmHi_14_io_addend = mHi_59_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  assign accumApmHi_15_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 183:29]
  assign accumApmHi_15_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 184:30]
  assign accumApmHi_15_io_enable = validD2 & (postD2 | highLaneEnable_15); // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 185:43]
  assign accumApmHi_15_io_clear = clearD2 | postD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 186:42]
  assign accumApmHi_15_io_addend = mHi_63_io_result; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 130:19 74:23]
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 139:26]
      validD1 <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 139:26]
    end else begin
      validD1 <= io_validI; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 153:13]
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 140:26]
      validD2 <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 140:26]
    end else begin
      validD2 <= validD1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 154:13]
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 141:25]
      validR <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 141:25]
    end else begin
      validR <= validD2; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 155:12]
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 142:26]
      clearD1 <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 142:26]
    end else begin
      clearD1 <= io_accClear; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 156:13]
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 143:26]
      clearD2 <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 143:26]
    end else begin
      clearD2 <= clearD1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 157:13]
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 144:25]
      postD1 <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 144:25]
    end else begin
      postD1 <= io_postMode; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 158:12]
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 145:25]
      postD2 <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 145:25]
    end else begin
      postD2 <= postD1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 159:12]
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 146:25]
      modeD1 <= 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 146:25]
    end else begin
      modeD1 <= io_computeMode; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 160:12]
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 147:25]
      modeD2 <= 2'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 147:25]
    end else begin
      modeD2 <= modeD1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 161:12]
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 148:25]
      maskD1 <= 32'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 148:25]
    end else begin
      maskD1 <= io_laneMask; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 162:12]
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 149:25]
      maskD2 <= 32'h0; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 149:25]
    end else begin
      maskD2 <= maskD1; // @[\\src\\main\\scala\\macaccel\\MacPeArray.scala 163:12]
    end
  end
endmodule
// USE_HELD_BIAS is valid only when the enclosing synchronous bias bank
// holds its read output until the next tile read. Standalone engines keep
// their own snapshot by default; MacAccelCore owns and meets this contract.
module MacEngine #(parameter COMPACT_S16_OUTPUT = 0, parameter ENABLE_FP8 = 1,
                   parameter USE_HELD_BIAS = 0)(
  input           io_clk, // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 21:14]
  input           io_rstN, // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 21:14]
  input           io_start, // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 21:14]
  output          io_busy, // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 21:14]
  output          io_done, // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 21:14]
  input           io_doneClear, // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 21:14]
  input  [15:0]   io_cfgPixels, // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 21:14]
  input  [15:0]   io_cfgCin, // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 21:14]
  input  [15:0]   io_cfgCout, // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 21:14]
  input  [1:0]    io_cfgComputeMode, // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 21:14]
  input  [1:0]    io_cfgActivation, // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 21:14]
  input  [1:0]    io_cfgOutputFormat, // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 21:14]
  input  [7:0]    io_cfgOutShift, // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 21:14]
  output          io_wtRe, // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 21:14]
  output [31:0]   io_wtRaddr, // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 21:14]
  input  [1023:0] io_wtRdata, // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 21:14]
  output          io_inRe, // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 21:14]
  output [31:0]   io_inRaddr, // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 21:14]
  input  [63:0]   io_inRdata, // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 21:14]
  output          io_biasRe, // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 21:14]
  output [31:0]   io_biasRaddr, // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 21:14]
  input  [1535:0] io_biasRdata, // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 21:14]
  output          io_outWe, // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 21:14]
  output [31:0]   io_outWaddr, // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 21:14]
  output [31:0]   io_outWdata // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 21:14]
);
  wire  pe_io_clk; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 55:18]
  wire  pe_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 55:18]
  wire  pe_io_validI; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 55:18]
  wire  pe_io_accClear; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 55:18]
  wire [1:0] pe_io_computeMode; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 55:18]
  wire  pe_io_postMode; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 55:18]
  wire [31:0] pe_io_laneMask; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 55:18]
  wire [63:0] pe_io_x; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 55:18]
  wire [1023:0] pe_io_w; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 55:18]
  wire [575:0] pe_io_postData; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 55:18]
  wire  pe_io_validO; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 55:18]
  wire [1535:0] pe_io_acc; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 55:18]
  wire [1535:0] pe_io_postResult; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 55:18]
  wire  _T_1 = ~io_rstN; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 59:40]
  reg [3:0] state; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 75:24]
  reg  busyR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 79:24]
  reg  doneR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 80:24]
  reg [4:0] pixelsR;
  reg [8:0] cinR;
  reg [8:0] coutR;
  reg [6:0] cinTilesR;
  reg [4:0] coutTilesR;
  reg [5:0] coutStepR;
  reg [1:0] computeModeR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 87:31]
  reg [1:0] activationR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 88:30]
  reg [1:0] outputFormatR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 89:32]
  reg [7:0] shiftR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 90:25]
  reg [4:0] pixelIndex;
  reg [6:0] ciTileIndex;
  reg [4:0] coTileIndex;
  reg [5:0] laneIndex; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 95:28]
  reg [6:0] readCommandCi;
  reg  readCommandLast; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 101:34]
  reg  readDataValid; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 102:32]
  reg [6:0] readDataCi;
  reg  readDataLast; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 104:31]
  reg  peValid; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 108:26]
  reg  peClear; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 109:26]
  reg  pePostMode; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 110:29]
  reg  peLast; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 111:25]
  reg  peLastD1; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 112:27]
  reg  peLastD2; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 113:27]
  reg  peLastD3; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 114:27]
  reg [31:0] peMask; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 115:25]
  reg [63:0] peX; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 116:22]
  reg [1023:0] peW; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 117:22]
  reg [575:0] pePostData; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 118:29]
  reg [1535:0] accSnapshot; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 121:30]
  wire [1535:0] biasSnapshot; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 122:31]
  reg [1535:0] postSnapshot; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 123:31]
  reg [47:0] postInputR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 124:29]
  reg [47:0] writeSumR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 125:28]
  reg [47:0] writeSquareR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 126:31]
  reg  wtReR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 130:24]
  reg [31:0] wtRaddrR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 131:27]
  reg  inReR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 132:24]
  reg [31:0] inRaddrR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 133:27]
  reg  biasReR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 134:26]
  reg [31:0] biasRaddrR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 135:29]
  reg  outWeR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 136:25]
  reg [31:0] outWaddrR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 137:28]
  reg [31:0] outWdataR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 138:28]
  // Equivalent lane selection; no register or FSM changes.
  reg [47:0] select_lane48_acc;
  wire [5:0] selectionLaneShared;
  wire [5:0] physicalIndexShared;
  // Constant-indexed lane mux (former select_lane48 function body).
  always @* begin
    case(physicalIndexShared[4:0])
        5'd0: select_lane48_acc=accSnapshot[0+:48];
        5'd1: select_lane48_acc=accSnapshot[48+:48];
        5'd2: select_lane48_acc=accSnapshot[96+:48];
        5'd3: select_lane48_acc=accSnapshot[144+:48];
        5'd4: select_lane48_acc=accSnapshot[192+:48];
        5'd5: select_lane48_acc=accSnapshot[240+:48];
        5'd6: select_lane48_acc=accSnapshot[288+:48];
        5'd7: select_lane48_acc=accSnapshot[336+:48];
        5'd8: select_lane48_acc=accSnapshot[384+:48];
        5'd9: select_lane48_acc=accSnapshot[432+:48];
        5'd10: select_lane48_acc=accSnapshot[480+:48];
        5'd11: select_lane48_acc=accSnapshot[528+:48];
        5'd12: select_lane48_acc=accSnapshot[576+:48];
        5'd13: select_lane48_acc=accSnapshot[624+:48];
        5'd14: select_lane48_acc=accSnapshot[672+:48];
        5'd15: select_lane48_acc=accSnapshot[720+:48];
        5'd16: select_lane48_acc=accSnapshot[768+:48];
        5'd17: select_lane48_acc=accSnapshot[816+:48];
        5'd18: select_lane48_acc=accSnapshot[864+:48];
        5'd19: select_lane48_acc=accSnapshot[912+:48];
        5'd20: select_lane48_acc=accSnapshot[960+:48];
        5'd21: select_lane48_acc=accSnapshot[1008+:48];
        5'd22: select_lane48_acc=accSnapshot[1056+:48];
        5'd23: select_lane48_acc=accSnapshot[1104+:48];
        5'd24: select_lane48_acc=accSnapshot[1152+:48];
        5'd25: select_lane48_acc=accSnapshot[1200+:48];
        5'd26: select_lane48_acc=accSnapshot[1248+:48];
        5'd27: select_lane48_acc=accSnapshot[1296+:48];
        5'd28: select_lane48_acc=accSnapshot[1344+:48];
        5'd29: select_lane48_acc=accSnapshot[1392+:48];
        5'd30: select_lane48_acc=accSnapshot[1440+:48];
        5'd31: select_lane48_acc=accSnapshot[1488+:48];
    endcase
  end
  reg [47:0] select_lane48_bias;
  // Constant-indexed lane mux (former select_lane48 function body).
  always @* begin
    case(selectionLaneShared[4:0])
        5'd0: select_lane48_bias=biasSnapshot[0+:48];
        5'd1: select_lane48_bias=biasSnapshot[48+:48];
        5'd2: select_lane48_bias=biasSnapshot[96+:48];
        5'd3: select_lane48_bias=biasSnapshot[144+:48];
        5'd4: select_lane48_bias=biasSnapshot[192+:48];
        5'd5: select_lane48_bias=biasSnapshot[240+:48];
        5'd6: select_lane48_bias=biasSnapshot[288+:48];
        5'd7: select_lane48_bias=biasSnapshot[336+:48];
        5'd8: select_lane48_bias=biasSnapshot[384+:48];
        5'd9: select_lane48_bias=biasSnapshot[432+:48];
        5'd10: select_lane48_bias=biasSnapshot[480+:48];
        5'd11: select_lane48_bias=biasSnapshot[528+:48];
        5'd12: select_lane48_bias=biasSnapshot[576+:48];
        5'd13: select_lane48_bias=biasSnapshot[624+:48];
        5'd14: select_lane48_bias=biasSnapshot[672+:48];
        5'd15: select_lane48_bias=biasSnapshot[720+:48];
        5'd16: select_lane48_bias=biasSnapshot[768+:48];
        5'd17: select_lane48_bias=biasSnapshot[816+:48];
        5'd18: select_lane48_bias=biasSnapshot[864+:48];
        5'd19: select_lane48_bias=biasSnapshot[912+:48];
        5'd20: select_lane48_bias=biasSnapshot[960+:48];
        5'd21: select_lane48_bias=biasSnapshot[1008+:48];
        5'd22: select_lane48_bias=biasSnapshot[1056+:48];
        5'd23: select_lane48_bias=biasSnapshot[1104+:48];
        5'd24: select_lane48_bias=biasSnapshot[1152+:48];
        5'd25: select_lane48_bias=biasSnapshot[1200+:48];
        5'd26: select_lane48_bias=biasSnapshot[1248+:48];
        5'd27: select_lane48_bias=biasSnapshot[1296+:48];
        5'd28: select_lane48_bias=biasSnapshot[1344+:48];
        5'd29: select_lane48_bias=biasSnapshot[1392+:48];
        5'd30: select_lane48_bias=biasSnapshot[1440+:48];
        5'd31: select_lane48_bias=biasSnapshot[1488+:48];
    endcase
  end
  reg [47:0] select_lane48_post;
  // Constant-indexed lane mux (former select_lane48 function body).
  always @* begin
    case(physicalIndexShared[4:0])
        5'd0: select_lane48_post=postSnapshot[0+:48];
        5'd1: select_lane48_post=postSnapshot[48+:48];
        5'd2: select_lane48_post=postSnapshot[96+:48];
        5'd3: select_lane48_post=postSnapshot[144+:48];
        5'd4: select_lane48_post=postSnapshot[192+:48];
        5'd5: select_lane48_post=postSnapshot[240+:48];
        5'd6: select_lane48_post=postSnapshot[288+:48];
        5'd7: select_lane48_post=postSnapshot[336+:48];
        5'd8: select_lane48_post=postSnapshot[384+:48];
        5'd9: select_lane48_post=postSnapshot[432+:48];
        5'd10: select_lane48_post=postSnapshot[480+:48];
        5'd11: select_lane48_post=postSnapshot[528+:48];
        5'd12: select_lane48_post=postSnapshot[576+:48];
        5'd13: select_lane48_post=postSnapshot[624+:48];
        5'd14: select_lane48_post=postSnapshot[672+:48];
        5'd15: select_lane48_post=postSnapshot[720+:48];
        5'd16: select_lane48_post=postSnapshot[768+:48];
        5'd17: select_lane48_post=postSnapshot[816+:48];
        5'd18: select_lane48_post=postSnapshot[864+:48];
        5'd19: select_lane48_post=postSnapshot[912+:48];
        5'd20: select_lane48_post=postSnapshot[960+:48];
        5'd21: select_lane48_post=postSnapshot[1008+:48];
        5'd22: select_lane48_post=postSnapshot[1056+:48];
        5'd23: select_lane48_post=postSnapshot[1104+:48];
        5'd24: select_lane48_post=postSnapshot[1152+:48];
        5'd25: select_lane48_post=postSnapshot[1200+:48];
        5'd26: select_lane48_post=postSnapshot[1248+:48];
        5'd27: select_lane48_post=postSnapshot[1296+:48];
        5'd28: select_lane48_post=postSnapshot[1344+:48];
        5'd29: select_lane48_post=postSnapshot[1392+:48];
        5'd30: select_lane48_post=postSnapshot[1440+:48];
        5'd31: select_lane48_post=postSnapshot[1488+:48];
    endcase
  end

  wire  packedModeShared = computeModeR != 2'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 177:41]
  wire  _narrowShared_T_1 = computeModeR == 2'h2; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 179:20]
  wire  narrowShared = computeModeR == 2'h1 | _narrowShared_T_1; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 178:60]
  // During writeback, the shared selectors prepare the next lane while
  // the registered sum/square formats and writes the current lane.
  assign selectionLaneShared = state == 4'hc ? laneIndex + 6'd1 : laneIndex;
  wire [4:0] physicalIndexShared_packedPhysical = {selectionLaneShared[0],selectionLaneShared[4:1]}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 189:12]
  assign physicalIndexShared = packedModeShared ? {{1'd0}, physicalIndexShared_packedPhysical} : selectionLaneShared; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 191:10]
  wire [47:0] accVectorShared_0 = accSnapshot[47:0]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_1 = accSnapshot[95:48]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_2 = accSnapshot[143:96]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_3 = accSnapshot[191:144]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_4 = accSnapshot[239:192]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_5 = accSnapshot[287:240]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_6 = accSnapshot[335:288]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_7 = accSnapshot[383:336]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_8 = accSnapshot[431:384]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_9 = accSnapshot[479:432]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_10 = accSnapshot[527:480]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_11 = accSnapshot[575:528]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_12 = accSnapshot[623:576]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_13 = accSnapshot[671:624]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_14 = accSnapshot[719:672]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_15 = accSnapshot[767:720]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_16 = accSnapshot[815:768]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_17 = accSnapshot[863:816]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_18 = accSnapshot[911:864]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_19 = accSnapshot[959:912]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_20 = accSnapshot[1007:960]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_21 = accSnapshot[1055:1008]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_22 = accSnapshot[1103:1056]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_23 = accSnapshot[1151:1104]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_24 = accSnapshot[1199:1152]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_25 = accSnapshot[1247:1200]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_26 = accSnapshot[1295:1248]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_27 = accSnapshot[1343:1296]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_28 = accSnapshot[1391:1344]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_29 = accSnapshot[1439:1392]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_30 = accSnapshot[1487:1440]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] accVectorShared_31 = accSnapshot[1535:1488]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 197:47]
  wire [47:0] biasVectorShared_0 = biasSnapshot[47:0]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_1 = biasSnapshot[95:48]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_2 = biasSnapshot[143:96]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_3 = biasSnapshot[191:144]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_4 = biasSnapshot[239:192]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_5 = biasSnapshot[287:240]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_6 = biasSnapshot[335:288]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_7 = biasSnapshot[383:336]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_8 = biasSnapshot[431:384]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_9 = biasSnapshot[479:432]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_10 = biasSnapshot[527:480]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_11 = biasSnapshot[575:528]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_12 = biasSnapshot[623:576]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_13 = biasSnapshot[671:624]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_14 = biasSnapshot[719:672]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_15 = biasSnapshot[767:720]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_16 = biasSnapshot[815:768]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_17 = biasSnapshot[863:816]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_18 = biasSnapshot[911:864]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_19 = biasSnapshot[959:912]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_20 = biasSnapshot[1007:960]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_21 = biasSnapshot[1055:1008]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_22 = biasSnapshot[1103:1056]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_23 = biasSnapshot[1151:1104]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_24 = biasSnapshot[1199:1152]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_25 = biasSnapshot[1247:1200]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_26 = biasSnapshot[1295:1248]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_27 = biasSnapshot[1343:1296]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_28 = biasSnapshot[1391:1344]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_29 = biasSnapshot[1439:1392]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_30 = biasSnapshot[1487:1440]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] biasVectorShared_31 = biasSnapshot[1535:1488]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 199:49]
  wire [47:0] postVectorShared_0 = postSnapshot[47:0]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_1 = postSnapshot[95:48]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_2 = postSnapshot[143:96]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_3 = postSnapshot[191:144]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_4 = postSnapshot[239:192]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_5 = postSnapshot[287:240]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_6 = postSnapshot[335:288]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_7 = postSnapshot[383:336]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_8 = postSnapshot[431:384]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_9 = postSnapshot[479:432]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_10 = postSnapshot[527:480]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_11 = postSnapshot[575:528]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_12 = postSnapshot[623:576]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_13 = postSnapshot[671:624]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_14 = postSnapshot[719:672]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_15 = postSnapshot[767:720]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_16 = postSnapshot[815:768]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_17 = postSnapshot[863:816]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_18 = postSnapshot[911:864]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_19 = postSnapshot[959:912]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_20 = postSnapshot[1007:960]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_21 = postSnapshot[1055:1008]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_22 = postSnapshot[1103:1056]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_23 = postSnapshot[1151:1104]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_24 = postSnapshot[1199:1152]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_25 = postSnapshot[1247:1200]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_26 = postSnapshot[1295:1248]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_27 = postSnapshot[1343:1296]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_28 = postSnapshot[1391:1344]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_29 = postSnapshot[1439:1392]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_30 = postSnapshot[1487:1440]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] postVectorShared_31 = postSnapshot[1535:1488]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 201:49]
  wire [47:0] _GEN_1 = 5'h1 == physicalIndexShared[4:0] ? accVectorShared_1 : accVectorShared_0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_2 = 5'h2 == physicalIndexShared[4:0] ? accVectorShared_2 : _GEN_1; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_3 = 5'h3 == physicalIndexShared[4:0] ? accVectorShared_3 : _GEN_2; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_4 = 5'h4 == physicalIndexShared[4:0] ? accVectorShared_4 : _GEN_3; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_5 = 5'h5 == physicalIndexShared[4:0] ? accVectorShared_5 : _GEN_4; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_6 = 5'h6 == physicalIndexShared[4:0] ? accVectorShared_6 : _GEN_5; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_7 = 5'h7 == physicalIndexShared[4:0] ? accVectorShared_7 : _GEN_6; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_8 = 5'h8 == physicalIndexShared[4:0] ? accVectorShared_8 : _GEN_7; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_9 = 5'h9 == physicalIndexShared[4:0] ? accVectorShared_9 : _GEN_8; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_10 = 5'ha == physicalIndexShared[4:0] ? accVectorShared_10 : _GEN_9; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_11 = 5'hb == physicalIndexShared[4:0] ? accVectorShared_11 : _GEN_10; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_12 = 5'hc == physicalIndexShared[4:0] ? accVectorShared_12 : _GEN_11; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_13 = 5'hd == physicalIndexShared[4:0] ? accVectorShared_13 : _GEN_12; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_14 = 5'he == physicalIndexShared[4:0] ? accVectorShared_14 : _GEN_13; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_15 = 5'hf == physicalIndexShared[4:0] ? accVectorShared_15 : _GEN_14; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_16 = 5'h10 == physicalIndexShared[4:0] ? accVectorShared_16 : _GEN_15; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_17 = 5'h11 == physicalIndexShared[4:0] ? accVectorShared_17 : _GEN_16; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_18 = 5'h12 == physicalIndexShared[4:0] ? accVectorShared_18 : _GEN_17; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_19 = 5'h13 == physicalIndexShared[4:0] ? accVectorShared_19 : _GEN_18; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_20 = 5'h14 == physicalIndexShared[4:0] ? accVectorShared_20 : _GEN_19; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_21 = 5'h15 == physicalIndexShared[4:0] ? accVectorShared_21 : _GEN_20; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_22 = 5'h16 == physicalIndexShared[4:0] ? accVectorShared_22 : _GEN_21; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_23 = 5'h17 == physicalIndexShared[4:0] ? accVectorShared_23 : _GEN_22; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_24 = 5'h18 == physicalIndexShared[4:0] ? accVectorShared_24 : _GEN_23; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_25 = 5'h19 == physicalIndexShared[4:0] ? accVectorShared_25 : _GEN_24; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_26 = 5'h1a == physicalIndexShared[4:0] ? accVectorShared_26 : _GEN_25; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_27 = 5'h1b == physicalIndexShared[4:0] ? accVectorShared_27 : _GEN_26; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_28 = 5'h1c == physicalIndexShared[4:0] ? accVectorShared_28 : _GEN_27; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_29 = 5'h1d == physicalIndexShared[4:0] ? accVectorShared_29 : _GEN_28; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_30 = 5'h1e == physicalIndexShared[4:0] ? accVectorShared_30 : _GEN_29; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [47:0] _GEN_31 = select_lane48_acc; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:{36,36}]
  wire [31:0] _sum32Shared_T_1 = _GEN_31[31:0]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:44]
  wire [47:0] _GEN_33 = 5'h1 == laneIndex[4:0] ? biasVectorShared_1 : biasVectorShared_0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_34 = 5'h2 == laneIndex[4:0] ? biasVectorShared_2 : _GEN_33; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_35 = 5'h3 == laneIndex[4:0] ? biasVectorShared_3 : _GEN_34; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_36 = 5'h4 == laneIndex[4:0] ? biasVectorShared_4 : _GEN_35; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_37 = 5'h5 == laneIndex[4:0] ? biasVectorShared_5 : _GEN_36; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_38 = 5'h6 == laneIndex[4:0] ? biasVectorShared_6 : _GEN_37; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_39 = 5'h7 == laneIndex[4:0] ? biasVectorShared_7 : _GEN_38; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_40 = 5'h8 == laneIndex[4:0] ? biasVectorShared_8 : _GEN_39; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_41 = 5'h9 == laneIndex[4:0] ? biasVectorShared_9 : _GEN_40; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_42 = 5'ha == laneIndex[4:0] ? biasVectorShared_10 : _GEN_41; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_43 = 5'hb == laneIndex[4:0] ? biasVectorShared_11 : _GEN_42; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_44 = 5'hc == laneIndex[4:0] ? biasVectorShared_12 : _GEN_43; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_45 = 5'hd == laneIndex[4:0] ? biasVectorShared_13 : _GEN_44; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_46 = 5'he == laneIndex[4:0] ? biasVectorShared_14 : _GEN_45; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_47 = 5'hf == laneIndex[4:0] ? biasVectorShared_15 : _GEN_46; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_48 = 5'h10 == laneIndex[4:0] ? biasVectorShared_16 : _GEN_47; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_49 = 5'h11 == laneIndex[4:0] ? biasVectorShared_17 : _GEN_48; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_50 = 5'h12 == laneIndex[4:0] ? biasVectorShared_18 : _GEN_49; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_51 = 5'h13 == laneIndex[4:0] ? biasVectorShared_19 : _GEN_50; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_52 = 5'h14 == laneIndex[4:0] ? biasVectorShared_20 : _GEN_51; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_53 = 5'h15 == laneIndex[4:0] ? biasVectorShared_21 : _GEN_52; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_54 = 5'h16 == laneIndex[4:0] ? biasVectorShared_22 : _GEN_53; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_55 = 5'h17 == laneIndex[4:0] ? biasVectorShared_23 : _GEN_54; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_56 = 5'h18 == laneIndex[4:0] ? biasVectorShared_24 : _GEN_55; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_57 = 5'h19 == laneIndex[4:0] ? biasVectorShared_25 : _GEN_56; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_58 = 5'h1a == laneIndex[4:0] ? biasVectorShared_26 : _GEN_57; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_59 = 5'h1b == laneIndex[4:0] ? biasVectorShared_27 : _GEN_58; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_60 = 5'h1c == laneIndex[4:0] ? biasVectorShared_28 : _GEN_59; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_61 = 5'h1d == laneIndex[4:0] ? biasVectorShared_29 : _GEN_60; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_62 = 5'h1e == laneIndex[4:0] ? biasVectorShared_30 : _GEN_61; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [47:0] _GEN_63 = select_lane48_bias; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:{21,21}]
  wire [31:0] _sum32Shared_T_3 = _GEN_63[31:0]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 206:29]
  wire [31:0] sum32Shared = $signed(_sum32Shared_T_1) + $signed(_sum32Shared_T_3); // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 205:51]
  wire [15:0] _sum32ExtendedShared_T_1 = sum32Shared[31] ? 16'hffff : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 207:39]
  wire [31:0] _sum32ExtendedShared_T_2 = $signed(_sum32Shared_T_1) + $signed(_sum32Shared_T_3); // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 208:19]
  wire [47:0] sum32ExtendedShared = {_sum32ExtendedShared_T_1,_sum32ExtendedShared_T_2}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 208:27]
  wire [47:0] _sum48Shared_T = _GEN_31; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 210:21]
  wire [47:0] _sum48Shared_T_1 = _GEN_63; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 210:46]
  wire [47:0] _sum48Shared_T_4 = $signed(_sum48Shared_T) + $signed(_sum48Shared_T_1); // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 210:28]
  wire [47:0] sum48Shared = narrowShared ? $signed(sum32ExtendedShared) : $signed(_sum48Shared_T_4); // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 209:26]
  wire  _GEN_66 = io_doneClear ? 1'h0 : doneR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 227:24 228:13 80:24]
  wire [15:0] cin = io_cfgCin == 16'h0 ? 16'h1 : io_cfgCin; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 238:24]
  wire [15:0] cout = io_cfgCout == 16'h0 ? 16'h1 : io_cfgCout; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 239:25]
  wire  packedMode = io_cfgComputeMode != 2'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 240:46]
  wire [15:0] _cinTilesR_T_1 = cin + 16'h3; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 252:29]
  wire [15:0] _cinTilesR_T_2 = _cinTilesR_T_1 / 3'h4; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 252:46]
  wire [15:0] _coutTilesR_T_1 = cout + 16'h1f; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 255:33]
  wire [15:0] _coutTilesR_T_2 = _coutTilesR_T_1 / 6'h20; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 255:58]
  wire [15:0] _coutTilesR_T_4 = cout + 16'hf; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 258:33]
  wire [15:0] _coutTilesR_T_5 = _coutTilesR_T_4 / 5'h10; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 258:50]
  wire [5:0] _GEN_67 = packedMode ? 6'h20 : 6'h10; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 253:28 254:23 257:23]
  wire  _T_4 = ciTileIndex < cinTilesR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 271:26]
  wire [31:0] _inRaddrR_T = pixelIndex * cinTilesR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 274:34]
  wire [31:0] _GEN_631 = {{16'd0}, ciTileIndex}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 274:46]
  wire [31:0] _inRaddrR_T_2 = _inRaddrR_T + _GEN_631; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 274:46]
  wire [31:0] _wtRaddrR_T = coTileIndex * cinTilesR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 275:35]
  wire [31:0] _wtRaddrR_T_2 = _wtRaddrR_T + _GEN_631; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 275:47]
  wire [15:0] _readCommandLast_T_1 = ciTileIndex + 16'h1; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 277:42]
  wire [8:0] ciBase = {readDataCi[6:0], 2'b0};
  wire [8:0] coBase = coTileIndex[4:0] * coutStepR[5:0];
  wire [8:0] cinRemaining = cinR[8:0] > ciBase ?
      cinR[8:0] - ciBase : 9'b0;
  wire [8:0] coutRemaining = coutR[8:0] > coBase ?
      coutR[8:0] - coBase : 9'b0;
  wire  logicalLaneValid_0 = 32'h0 < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_1 = 32'h1 < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_2 = 32'h2 < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_3 = 32'h3 < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_4 = 32'h4 < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_5 = 32'h5 < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_6 = 32'h6 < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_7 = 32'h7 < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_8 = 32'h8 < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_9 = 32'h9 < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_10 = 32'ha < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_11 = 32'hb < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_12 = 32'hc < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_13 = 32'hd < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_14 = 32'he < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_15 = 32'hf < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_16 = 32'h10 < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_17 = 32'h11 < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_18 = 32'h12 < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_19 = 32'h13 < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_20 = 32'h14 < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_21 = 32'h15 < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_22 = 32'h16 < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_23 = 32'h17 < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_24 = 32'h18 < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_25 = 32'h19 < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_26 = 32'h1a < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_27 = 32'h1b < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_28 = 32'h1c < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_29 = 32'h1d < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_30 = 32'h1e < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire  logicalLaneValid_31 = 32'h1f < coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 301:44]
  wire [15:0] source = io_wtRdata[15:0]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low = logicalLaneValid_0 ? source[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high = logicalLaneValid_1 ? source[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_0_T = {high,low}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_91 = logicalLaneValid_0 ? source : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_92 = packedModeShared ? _wPad_0_T : _GEN_91; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_1 = io_wtRdata[79:64]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_1 = logicalLaneValid_2 ? source_1[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_1 = logicalLaneValid_3 ? source_1[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_4_T = {high_1,low_1}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_93 = logicalLaneValid_1 ? source_1 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_94 = packedModeShared ? _wPad_4_T : _GEN_93; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_2 = io_wtRdata[143:128]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_2 = logicalLaneValid_4 ? source_2[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_2 = logicalLaneValid_5 ? source_2[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_8_T = {high_2,low_2}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_95 = logicalLaneValid_2 ? source_2 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_96 = packedModeShared ? _wPad_8_T : _GEN_95; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_3 = io_wtRdata[207:192]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_3 = logicalLaneValid_6 ? source_3[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_3 = logicalLaneValid_7 ? source_3[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_12_T = {high_3,low_3}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_97 = logicalLaneValid_3 ? source_3 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_98 = packedModeShared ? _wPad_12_T : _GEN_97; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_4 = io_wtRdata[271:256]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_4 = logicalLaneValid_8 ? source_4[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_4 = logicalLaneValid_9 ? source_4[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_16_T = {high_4,low_4}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_99 = logicalLaneValid_4 ? source_4 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_100 = packedModeShared ? _wPad_16_T : _GEN_99; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_5 = io_wtRdata[335:320]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_5 = logicalLaneValid_10 ? source_5[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_5 = logicalLaneValid_11 ? source_5[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_20_T = {high_5,low_5}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_101 = logicalLaneValid_5 ? source_5 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_102 = packedModeShared ? _wPad_20_T : _GEN_101; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_6 = io_wtRdata[399:384]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_6 = logicalLaneValid_12 ? source_6[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_6 = logicalLaneValid_13 ? source_6[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_24_T = {high_6,low_6}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_103 = logicalLaneValid_6 ? source_6 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_104 = packedModeShared ? _wPad_24_T : _GEN_103; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_7 = io_wtRdata[463:448]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_7 = logicalLaneValid_14 ? source_7[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_7 = logicalLaneValid_15 ? source_7[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_28_T = {high_7,low_7}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_105 = logicalLaneValid_7 ? source_7 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_106 = packedModeShared ? _wPad_28_T : _GEN_105; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_8 = io_wtRdata[527:512]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_8 = logicalLaneValid_16 ? source_8[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_8 = logicalLaneValid_17 ? source_8[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_32_T = {high_8,low_8}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_107 = logicalLaneValid_8 ? source_8 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_108 = packedModeShared ? _wPad_32_T : _GEN_107; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_9 = io_wtRdata[591:576]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_9 = logicalLaneValid_18 ? source_9[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_9 = logicalLaneValid_19 ? source_9[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_36_T = {high_9,low_9}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_109 = logicalLaneValid_9 ? source_9 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_110 = packedModeShared ? _wPad_36_T : _GEN_109; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_10 = io_wtRdata[655:640]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_10 = logicalLaneValid_20 ? source_10[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_10 = logicalLaneValid_21 ? source_10[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_40_T = {high_10,low_10}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_111 = logicalLaneValid_10 ? source_10 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_112 = packedModeShared ? _wPad_40_T : _GEN_111; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_11 = io_wtRdata[719:704]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_11 = logicalLaneValid_22 ? source_11[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_11 = logicalLaneValid_23 ? source_11[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_44_T = {high_11,low_11}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_113 = logicalLaneValid_11 ? source_11 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_114 = packedModeShared ? _wPad_44_T : _GEN_113; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_12 = io_wtRdata[783:768]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_12 = logicalLaneValid_24 ? source_12[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_12 = logicalLaneValid_25 ? source_12[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_48_T = {high_12,low_12}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_115 = logicalLaneValid_12 ? source_12 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_116 = packedModeShared ? _wPad_48_T : _GEN_115; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_13 = io_wtRdata[847:832]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_13 = logicalLaneValid_26 ? source_13[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_13 = logicalLaneValid_27 ? source_13[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_52_T = {high_13,low_13}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_117 = logicalLaneValid_13 ? source_13 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_118 = packedModeShared ? _wPad_52_T : _GEN_117; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_14 = io_wtRdata[911:896]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_14 = logicalLaneValid_28 ? source_14[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_14 = logicalLaneValid_29 ? source_14[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_56_T = {high_14,low_14}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_119 = logicalLaneValid_14 ? source_14 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_120 = packedModeShared ? _wPad_56_T : _GEN_119; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_15 = io_wtRdata[975:960]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_15 = logicalLaneValid_30 ? source_15[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_15 = logicalLaneValid_31 ? source_15[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_60_T = {high_15,low_15}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_121 = logicalLaneValid_15 ? source_15 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_122 = packedModeShared ? _wPad_60_T : _GEN_121; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] xPad_0 = 19'h0 < cinRemaining ? io_inRdata[15:0] : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 305:37 306:22 295:24]
  wire [15:0] wPad_0 = 19'h0 < cinRemaining ? _GEN_92 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_4 = 19'h0 < cinRemaining ? _GEN_94 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_8 = 19'h0 < cinRemaining ? _GEN_96 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_12 = 19'h0 < cinRemaining ? _GEN_98 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_16 = 19'h0 < cinRemaining ? _GEN_100 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_20 = 19'h0 < cinRemaining ? _GEN_102 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_24 = 19'h0 < cinRemaining ? _GEN_104 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_28 = 19'h0 < cinRemaining ? _GEN_106 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_32 = 19'h0 < cinRemaining ? _GEN_108 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_36 = 19'h0 < cinRemaining ? _GEN_110 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_40 = 19'h0 < cinRemaining ? _GEN_112 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_44 = 19'h0 < cinRemaining ? _GEN_114 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_48 = 19'h0 < cinRemaining ? _GEN_116 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_52 = 19'h0 < cinRemaining ? _GEN_118 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_56 = 19'h0 < cinRemaining ? _GEN_120 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_60 = 19'h0 < cinRemaining ? _GEN_122 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] source_16 = io_wtRdata[31:16]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_16 = logicalLaneValid_0 ? source_16[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_16 = logicalLaneValid_1 ? source_16[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_1_T = {high_16,low_16}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_140 = logicalLaneValid_0 ? source_16 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_141 = packedModeShared ? _wPad_1_T : _GEN_140; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_17 = io_wtRdata[95:80]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_17 = logicalLaneValid_2 ? source_17[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_17 = logicalLaneValid_3 ? source_17[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_5_T = {high_17,low_17}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_142 = logicalLaneValid_1 ? source_17 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_143 = packedModeShared ? _wPad_5_T : _GEN_142; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_18 = io_wtRdata[159:144]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_18 = logicalLaneValid_4 ? source_18[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_18 = logicalLaneValid_5 ? source_18[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_9_T = {high_18,low_18}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_144 = logicalLaneValid_2 ? source_18 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_145 = packedModeShared ? _wPad_9_T : _GEN_144; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_19 = io_wtRdata[223:208]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_19 = logicalLaneValid_6 ? source_19[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_19 = logicalLaneValid_7 ? source_19[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_13_T = {high_19,low_19}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_146 = logicalLaneValid_3 ? source_19 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_147 = packedModeShared ? _wPad_13_T : _GEN_146; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_20 = io_wtRdata[287:272]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_20 = logicalLaneValid_8 ? source_20[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_20 = logicalLaneValid_9 ? source_20[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_17_T = {high_20,low_20}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_148 = logicalLaneValid_4 ? source_20 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_149 = packedModeShared ? _wPad_17_T : _GEN_148; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_21 = io_wtRdata[351:336]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_21 = logicalLaneValid_10 ? source_21[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_21 = logicalLaneValid_11 ? source_21[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_21_T = {high_21,low_21}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_150 = logicalLaneValid_5 ? source_21 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_151 = packedModeShared ? _wPad_21_T : _GEN_150; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_22 = io_wtRdata[415:400]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_22 = logicalLaneValid_12 ? source_22[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_22 = logicalLaneValid_13 ? source_22[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_25_T = {high_22,low_22}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_152 = logicalLaneValid_6 ? source_22 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_153 = packedModeShared ? _wPad_25_T : _GEN_152; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_23 = io_wtRdata[479:464]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_23 = logicalLaneValid_14 ? source_23[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_23 = logicalLaneValid_15 ? source_23[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_29_T = {high_23,low_23}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_154 = logicalLaneValid_7 ? source_23 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_155 = packedModeShared ? _wPad_29_T : _GEN_154; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_24 = io_wtRdata[543:528]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_24 = logicalLaneValid_16 ? source_24[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_24 = logicalLaneValid_17 ? source_24[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_33_T = {high_24,low_24}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_156 = logicalLaneValid_8 ? source_24 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_157 = packedModeShared ? _wPad_33_T : _GEN_156; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_25 = io_wtRdata[607:592]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_25 = logicalLaneValid_18 ? source_25[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_25 = logicalLaneValid_19 ? source_25[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_37_T = {high_25,low_25}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_158 = logicalLaneValid_9 ? source_25 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_159 = packedModeShared ? _wPad_37_T : _GEN_158; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_26 = io_wtRdata[671:656]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_26 = logicalLaneValid_20 ? source_26[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_26 = logicalLaneValid_21 ? source_26[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_41_T = {high_26,low_26}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_160 = logicalLaneValid_10 ? source_26 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_161 = packedModeShared ? _wPad_41_T : _GEN_160; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_27 = io_wtRdata[735:720]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_27 = logicalLaneValid_22 ? source_27[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_27 = logicalLaneValid_23 ? source_27[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_45_T = {high_27,low_27}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_162 = logicalLaneValid_11 ? source_27 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_163 = packedModeShared ? _wPad_45_T : _GEN_162; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_28 = io_wtRdata[799:784]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_28 = logicalLaneValid_24 ? source_28[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_28 = logicalLaneValid_25 ? source_28[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_49_T = {high_28,low_28}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_164 = logicalLaneValid_12 ? source_28 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_165 = packedModeShared ? _wPad_49_T : _GEN_164; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_29 = io_wtRdata[863:848]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_29 = logicalLaneValid_26 ? source_29[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_29 = logicalLaneValid_27 ? source_29[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_53_T = {high_29,low_29}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_166 = logicalLaneValid_13 ? source_29 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_167 = packedModeShared ? _wPad_53_T : _GEN_166; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_30 = io_wtRdata[927:912]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_30 = logicalLaneValid_28 ? source_30[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_30 = logicalLaneValid_29 ? source_30[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_57_T = {high_30,low_30}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_168 = logicalLaneValid_14 ? source_30 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_169 = packedModeShared ? _wPad_57_T : _GEN_168; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_31 = io_wtRdata[991:976]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_31 = logicalLaneValid_30 ? source_31[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_31 = logicalLaneValid_31 ? source_31[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_61_T = {high_31,low_31}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_170 = logicalLaneValid_15 ? source_31 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_171 = packedModeShared ? _wPad_61_T : _GEN_170; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] xPad_1 = 19'h1 < cinRemaining ? io_inRdata[31:16] : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 305:37 306:22 295:24]
  wire [15:0] wPad_1 = 19'h1 < cinRemaining ? _GEN_141 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_5 = 19'h1 < cinRemaining ? _GEN_143 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_9 = 19'h1 < cinRemaining ? _GEN_145 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_13 = 19'h1 < cinRemaining ? _GEN_147 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_17 = 19'h1 < cinRemaining ? _GEN_149 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_21 = 19'h1 < cinRemaining ? _GEN_151 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_25 = 19'h1 < cinRemaining ? _GEN_153 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_29 = 19'h1 < cinRemaining ? _GEN_155 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_33 = 19'h1 < cinRemaining ? _GEN_157 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_37 = 19'h1 < cinRemaining ? _GEN_159 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_41 = 19'h1 < cinRemaining ? _GEN_161 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_45 = 19'h1 < cinRemaining ? _GEN_163 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_49 = 19'h1 < cinRemaining ? _GEN_165 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_53 = 19'h1 < cinRemaining ? _GEN_167 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_57 = 19'h1 < cinRemaining ? _GEN_169 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_61 = 19'h1 < cinRemaining ? _GEN_171 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] source_32 = io_wtRdata[47:32]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_32 = logicalLaneValid_0 ? source_32[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_32 = logicalLaneValid_1 ? source_32[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_2_T = {high_32,low_32}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_189 = logicalLaneValid_0 ? source_32 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_190 = packedModeShared ? _wPad_2_T : _GEN_189; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_33 = io_wtRdata[111:96]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_33 = logicalLaneValid_2 ? source_33[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_33 = logicalLaneValid_3 ? source_33[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_6_T = {high_33,low_33}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_191 = logicalLaneValid_1 ? source_33 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_192 = packedModeShared ? _wPad_6_T : _GEN_191; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_34 = io_wtRdata[175:160]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_34 = logicalLaneValid_4 ? source_34[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_34 = logicalLaneValid_5 ? source_34[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_10_T = {high_34,low_34}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_193 = logicalLaneValid_2 ? source_34 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_194 = packedModeShared ? _wPad_10_T : _GEN_193; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_35 = io_wtRdata[239:224]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_35 = logicalLaneValid_6 ? source_35[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_35 = logicalLaneValid_7 ? source_35[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_14_T = {high_35,low_35}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_195 = logicalLaneValid_3 ? source_35 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_196 = packedModeShared ? _wPad_14_T : _GEN_195; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_36 = io_wtRdata[303:288]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_36 = logicalLaneValid_8 ? source_36[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_36 = logicalLaneValid_9 ? source_36[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_18_T = {high_36,low_36}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_197 = logicalLaneValid_4 ? source_36 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_198 = packedModeShared ? _wPad_18_T : _GEN_197; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_37 = io_wtRdata[367:352]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_37 = logicalLaneValid_10 ? source_37[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_37 = logicalLaneValid_11 ? source_37[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_22_T = {high_37,low_37}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_199 = logicalLaneValid_5 ? source_37 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_200 = packedModeShared ? _wPad_22_T : _GEN_199; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_38 = io_wtRdata[431:416]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_38 = logicalLaneValid_12 ? source_38[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_38 = logicalLaneValid_13 ? source_38[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_26_T = {high_38,low_38}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_201 = logicalLaneValid_6 ? source_38 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_202 = packedModeShared ? _wPad_26_T : _GEN_201; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_39 = io_wtRdata[495:480]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_39 = logicalLaneValid_14 ? source_39[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_39 = logicalLaneValid_15 ? source_39[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_30_T = {high_39,low_39}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_203 = logicalLaneValid_7 ? source_39 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_204 = packedModeShared ? _wPad_30_T : _GEN_203; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_40 = io_wtRdata[559:544]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_40 = logicalLaneValid_16 ? source_40[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_40 = logicalLaneValid_17 ? source_40[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_34_T = {high_40,low_40}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_205 = logicalLaneValid_8 ? source_40 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_206 = packedModeShared ? _wPad_34_T : _GEN_205; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_41 = io_wtRdata[623:608]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_41 = logicalLaneValid_18 ? source_41[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_41 = logicalLaneValid_19 ? source_41[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_38_T = {high_41,low_41}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_207 = logicalLaneValid_9 ? source_41 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_208 = packedModeShared ? _wPad_38_T : _GEN_207; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_42 = io_wtRdata[687:672]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_42 = logicalLaneValid_20 ? source_42[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_42 = logicalLaneValid_21 ? source_42[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_42_T = {high_42,low_42}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_209 = logicalLaneValid_10 ? source_42 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_210 = packedModeShared ? _wPad_42_T : _GEN_209; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_43 = io_wtRdata[751:736]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_43 = logicalLaneValid_22 ? source_43[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_43 = logicalLaneValid_23 ? source_43[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_46_T = {high_43,low_43}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_211 = logicalLaneValid_11 ? source_43 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_212 = packedModeShared ? _wPad_46_T : _GEN_211; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_44 = io_wtRdata[815:800]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_44 = logicalLaneValid_24 ? source_44[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_44 = logicalLaneValid_25 ? source_44[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_50_T = {high_44,low_44}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_213 = logicalLaneValid_12 ? source_44 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_214 = packedModeShared ? _wPad_50_T : _GEN_213; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_45 = io_wtRdata[879:864]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_45 = logicalLaneValid_26 ? source_45[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_45 = logicalLaneValid_27 ? source_45[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_54_T = {high_45,low_45}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_215 = logicalLaneValid_13 ? source_45 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_216 = packedModeShared ? _wPad_54_T : _GEN_215; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_46 = io_wtRdata[943:928]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_46 = logicalLaneValid_28 ? source_46[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_46 = logicalLaneValid_29 ? source_46[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_58_T = {high_46,low_46}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_217 = logicalLaneValid_14 ? source_46 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_218 = packedModeShared ? _wPad_58_T : _GEN_217; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_47 = io_wtRdata[1007:992]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_47 = logicalLaneValid_30 ? source_47[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_47 = logicalLaneValid_31 ? source_47[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_62_T = {high_47,low_47}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_219 = logicalLaneValid_15 ? source_47 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_220 = packedModeShared ? _wPad_62_T : _GEN_219; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] xPad_2 = 19'h2 < cinRemaining ? io_inRdata[47:32] : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 305:37 306:22 295:24]
  wire [15:0] wPad_2 = 19'h2 < cinRemaining ? _GEN_190 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_6 = 19'h2 < cinRemaining ? _GEN_192 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_10 = 19'h2 < cinRemaining ? _GEN_194 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_14 = 19'h2 < cinRemaining ? _GEN_196 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_18 = 19'h2 < cinRemaining ? _GEN_198 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_22 = 19'h2 < cinRemaining ? _GEN_200 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_26 = 19'h2 < cinRemaining ? _GEN_202 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_30 = 19'h2 < cinRemaining ? _GEN_204 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_34 = 19'h2 < cinRemaining ? _GEN_206 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_38 = 19'h2 < cinRemaining ? _GEN_208 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_42 = 19'h2 < cinRemaining ? _GEN_210 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_46 = 19'h2 < cinRemaining ? _GEN_212 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_50 = 19'h2 < cinRemaining ? _GEN_214 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_54 = 19'h2 < cinRemaining ? _GEN_216 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_58 = 19'h2 < cinRemaining ? _GEN_218 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_62 = 19'h2 < cinRemaining ? _GEN_220 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] source_48 = io_wtRdata[63:48]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_48 = logicalLaneValid_0 ? source_48[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_48 = logicalLaneValid_1 ? source_48[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_3_T = {high_48,low_48}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_238 = logicalLaneValid_0 ? source_48 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_239 = packedModeShared ? _wPad_3_T : _GEN_238; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_49 = io_wtRdata[127:112]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_49 = logicalLaneValid_2 ? source_49[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_49 = logicalLaneValid_3 ? source_49[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_7_T = {high_49,low_49}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_240 = logicalLaneValid_1 ? source_49 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_241 = packedModeShared ? _wPad_7_T : _GEN_240; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_50 = io_wtRdata[191:176]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_50 = logicalLaneValid_4 ? source_50[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_50 = logicalLaneValid_5 ? source_50[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_11_T = {high_50,low_50}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_242 = logicalLaneValid_2 ? source_50 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_243 = packedModeShared ? _wPad_11_T : _GEN_242; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_51 = io_wtRdata[255:240]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_51 = logicalLaneValid_6 ? source_51[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_51 = logicalLaneValid_7 ? source_51[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_15_T = {high_51,low_51}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_244 = logicalLaneValid_3 ? source_51 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_245 = packedModeShared ? _wPad_15_T : _GEN_244; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_52 = io_wtRdata[319:304]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_52 = logicalLaneValid_8 ? source_52[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_52 = logicalLaneValid_9 ? source_52[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_19_T = {high_52,low_52}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_246 = logicalLaneValid_4 ? source_52 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_247 = packedModeShared ? _wPad_19_T : _GEN_246; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_53 = io_wtRdata[383:368]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_53 = logicalLaneValid_10 ? source_53[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_53 = logicalLaneValid_11 ? source_53[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_23_T = {high_53,low_53}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_248 = logicalLaneValid_5 ? source_53 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_249 = packedModeShared ? _wPad_23_T : _GEN_248; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_54 = io_wtRdata[447:432]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_54 = logicalLaneValid_12 ? source_54[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_54 = logicalLaneValid_13 ? source_54[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_27_T = {high_54,low_54}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_250 = logicalLaneValid_6 ? source_54 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_251 = packedModeShared ? _wPad_27_T : _GEN_250; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_55 = io_wtRdata[511:496]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_55 = logicalLaneValid_14 ? source_55[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_55 = logicalLaneValid_15 ? source_55[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_31_T = {high_55,low_55}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_252 = logicalLaneValid_7 ? source_55 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_253 = packedModeShared ? _wPad_31_T : _GEN_252; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_56 = io_wtRdata[575:560]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_56 = logicalLaneValid_16 ? source_56[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_56 = logicalLaneValid_17 ? source_56[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_35_T = {high_56,low_56}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_254 = logicalLaneValid_8 ? source_56 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_255 = packedModeShared ? _wPad_35_T : _GEN_254; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_57 = io_wtRdata[639:624]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_57 = logicalLaneValid_18 ? source_57[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_57 = logicalLaneValid_19 ? source_57[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_39_T = {high_57,low_57}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_256 = logicalLaneValid_9 ? source_57 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_257 = packedModeShared ? _wPad_39_T : _GEN_256; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_58 = io_wtRdata[703:688]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_58 = logicalLaneValid_20 ? source_58[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_58 = logicalLaneValid_21 ? source_58[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_43_T = {high_58,low_58}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_258 = logicalLaneValid_10 ? source_58 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_259 = packedModeShared ? _wPad_43_T : _GEN_258; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_59 = io_wtRdata[767:752]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_59 = logicalLaneValid_22 ? source_59[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_59 = logicalLaneValid_23 ? source_59[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_47_T = {high_59,low_59}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_260 = logicalLaneValid_11 ? source_59 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_261 = packedModeShared ? _wPad_47_T : _GEN_260; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_60 = io_wtRdata[831:816]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_60 = logicalLaneValid_24 ? source_60[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_60 = logicalLaneValid_25 ? source_60[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_51_T = {high_60,low_60}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_262 = logicalLaneValid_12 ? source_60 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_263 = packedModeShared ? _wPad_51_T : _GEN_262; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_61 = io_wtRdata[895:880]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_61 = logicalLaneValid_26 ? source_61[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_61 = logicalLaneValid_27 ? source_61[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_55_T = {high_61,low_61}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_264 = logicalLaneValid_13 ? source_61 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_265 = packedModeShared ? _wPad_55_T : _GEN_264; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_62 = io_wtRdata[959:944]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_62 = logicalLaneValid_28 ? source_62[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_62 = logicalLaneValid_29 ? source_62[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_59_T = {high_62,low_62}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_266 = logicalLaneValid_14 ? source_62 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_267 = packedModeShared ? _wPad_59_T : _GEN_266; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] source_63 = io_wtRdata[1023:1008]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 308:38]
  wire [7:0] low_63 = logicalLaneValid_30 ? source_63[7:0] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 313:30]
  wire [7:0] high_63 = logicalLaneValid_31 ? source_63[15:8] : 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 314:31]
  wire [15:0] _wPad_63_T = {high_63,low_63}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 316:45]
  wire [15:0] _GEN_268 = logicalLaneValid_15 ? source_63 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 318:44 319:41]
  wire [15:0] _GEN_269 = packedModeShared ? _wPad_63_T : _GEN_268; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 310:32 316:39]
  wire [15:0] xPad_3 = 19'h3 < cinRemaining ? io_inRdata[63:48] : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 305:37 306:22 295:24]
  wire [15:0] wPad_3 = 19'h3 < cinRemaining ? _GEN_239 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_7 = 19'h3 < cinRemaining ? _GEN_241 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_11 = 19'h3 < cinRemaining ? _GEN_243 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_15 = 19'h3 < cinRemaining ? _GEN_245 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_19 = 19'h3 < cinRemaining ? _GEN_247 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_23 = 19'h3 < cinRemaining ? _GEN_249 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_27 = 19'h3 < cinRemaining ? _GEN_251 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_31 = 19'h3 < cinRemaining ? _GEN_253 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_35 = 19'h3 < cinRemaining ? _GEN_255 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_39 = 19'h3 < cinRemaining ? _GEN_257 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_43 = 19'h3 < cinRemaining ? _GEN_259 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_47 = 19'h3 < cinRemaining ? _GEN_261 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_51 = 19'h3 < cinRemaining ? _GEN_263 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_55 = 19'h3 < cinRemaining ? _GEN_265 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_59 = 19'h3 < cinRemaining ? _GEN_267 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire [15:0] wPad_63 = 19'h3 < cinRemaining ? _GEN_269 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 296:24 305:37]
  wire  maskPad_16 = packedModeShared & logicalLaneValid_16; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 331:41]
  wire  maskPad_17 = packedModeShared & logicalLaneValid_17; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 331:41]
  wire  maskPad_18 = packedModeShared & logicalLaneValid_18; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 331:41]
  wire  maskPad_19 = packedModeShared & logicalLaneValid_19; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 331:41]
  wire  maskPad_20 = packedModeShared & logicalLaneValid_20; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 331:41]
  wire  maskPad_21 = packedModeShared & logicalLaneValid_21; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 331:41]
  wire  maskPad_22 = packedModeShared & logicalLaneValid_22; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 331:41]
  wire  maskPad_23 = packedModeShared & logicalLaneValid_23; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 331:41]
  wire  maskPad_24 = packedModeShared & logicalLaneValid_24; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 331:41]
  wire  maskPad_25 = packedModeShared & logicalLaneValid_25; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 331:41]
  wire  maskPad_26 = packedModeShared & logicalLaneValid_26; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 331:41]
  wire  maskPad_27 = packedModeShared & logicalLaneValid_27; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 331:41]
  wire  maskPad_28 = packedModeShared & logicalLaneValid_28; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 331:41]
  wire  maskPad_29 = packedModeShared & logicalLaneValid_29; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 331:41]
  wire  maskPad_30 = packedModeShared & logicalLaneValid_30; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 331:41]
  wire  maskPad_31 = packedModeShared & logicalLaneValid_31; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 331:41]
  wire [7:0] peMask_lo_lo = {logicalLaneValid_7,logicalLaneValid_6,logicalLaneValid_5,logicalLaneValid_4,
    logicalLaneValid_3,logicalLaneValid_2,logicalLaneValid_1,logicalLaneValid_0}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 341:29]
  wire [15:0] peMask_lo = {logicalLaneValid_15,logicalLaneValid_14,logicalLaneValid_13,logicalLaneValid_12,
    logicalLaneValid_11,logicalLaneValid_10,logicalLaneValid_9,logicalLaneValid_8,peMask_lo_lo}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 341:29]
  wire [7:0] peMask_hi_lo = {maskPad_23,maskPad_22,maskPad_21,maskPad_20,maskPad_19,maskPad_18,maskPad_17,maskPad_16}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 341:29]
  wire [31:0] _peMask_T = {maskPad_31,maskPad_30,maskPad_29,maskPad_28,maskPad_27,maskPad_26,maskPad_25,maskPad_24,
    peMask_hi_lo,peMask_lo}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 341:29]
  wire [63:0] _peX_T = {xPad_3,xPad_2,xPad_1,xPad_0}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 342:23]
  wire [127:0] peW_lo_lo_lo = {wPad_7,wPad_6,wPad_5,wPad_4,wPad_3,wPad_2,wPad_1,wPad_0}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 343:23]
  wire [255:0] peW_lo_lo = {wPad_15,wPad_14,wPad_13,wPad_12,wPad_11,wPad_10,wPad_9,wPad_8,peW_lo_lo_lo}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 343:23]
  wire [127:0] peW_lo_hi_lo = {wPad_23,wPad_22,wPad_21,wPad_20,wPad_19,wPad_18,wPad_17,wPad_16}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 343:23]
  wire [511:0] peW_lo = {wPad_31,wPad_30,wPad_29,wPad_28,wPad_27,wPad_26,wPad_25,wPad_24,peW_lo_hi_lo,peW_lo_lo}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 343:23]
  wire [127:0] peW_hi_lo_lo = {wPad_39,wPad_38,wPad_37,wPad_36,wPad_35,wPad_34,wPad_33,wPad_32}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 343:23]
  wire [255:0] peW_hi_lo = {wPad_47,wPad_46,wPad_45,wPad_44,wPad_43,wPad_42,wPad_41,wPad_40,peW_hi_lo_lo}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 343:23]
  wire [127:0] peW_hi_hi_lo = {wPad_55,wPad_54,wPad_53,wPad_52,wPad_51,wPad_50,wPad_49,wPad_48}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 343:23]
  wire [511:0] peW_hi = {wPad_63,wPad_62,wPad_61,wPad_60,wPad_59,wPad_58,wPad_57,wPad_56,peW_hi_hi_lo,peW_hi_lo}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 343:23]
  wire [1023:0] _peW_T = {peW_hi,peW_lo}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 343:23]
  wire  _GEN_289 = readDataValid & readDataCi == 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 165:13 335:29 339:19]
  wire  _GEN_290 = readDataValid & readDataLast; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 167:12 335:29 340:18]
  wire  _state_T = activationR == 2'h3; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 378:34]
  wire [3:0] _state_T_1 = activationR == 2'h3 ? 4'h7 : 4'hb; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 378:21]
  wire [31:0] _GEN_639 = {{16'd0}, coutStepR}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 400:43]
  wire [31:0] lanesThis = coutRemaining > _GEN_639 ? {{16'd0}, coutStepR} : coutRemaining; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 400:28]
  wire [47:0] _clipped_T = postInputR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 409:37]
  wire [17:0] _clipped_T_5 = |_clipped_T[46:17] ? 18'h1ffff : _clipped_T[17:0]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 409:25]
  wire [17:0] clipped = ~postInputR[47] ? _clipped_T_5 : 18'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 404:17 405:39 409:19]
  wire [17:0] postVector_0 = 5'h0 == laneIndex[4:0] ? clipped : pePostData[17:0]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_1 = 5'h1 == laneIndex[4:0] ? clipped : pePostData[35:18]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_2 = 5'h2 == laneIndex[4:0] ? clipped : pePostData[53:36]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_3 = 5'h3 == laneIndex[4:0] ? clipped : pePostData[71:54]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_4 = 5'h4 == laneIndex[4:0] ? clipped : pePostData[89:72]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_5 = 5'h5 == laneIndex[4:0] ? clipped : pePostData[107:90]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_6 = 5'h6 == laneIndex[4:0] ? clipped : pePostData[125:108]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_7 = 5'h7 == laneIndex[4:0] ? clipped : pePostData[143:126]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_8 = 5'h8 == laneIndex[4:0] ? clipped : pePostData[161:144]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_9 = 5'h9 == laneIndex[4:0] ? clipped : pePostData[179:162]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_10 = 5'ha == laneIndex[4:0] ? clipped : pePostData[197:180]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_11 = 5'hb == laneIndex[4:0] ? clipped : pePostData[215:198]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_12 = 5'hc == laneIndex[4:0] ? clipped : pePostData[233:216]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_13 = 5'hd == laneIndex[4:0] ? clipped : pePostData[251:234]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_14 = 5'he == laneIndex[4:0] ? clipped : pePostData[269:252]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_15 = 5'hf == laneIndex[4:0] ? clipped : pePostData[287:270]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_16 = 5'h10 == laneIndex[4:0] ? clipped : pePostData[305:288]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_17 = 5'h11 == laneIndex[4:0] ? clipped : pePostData[323:306]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_18 = 5'h12 == laneIndex[4:0] ? clipped : pePostData[341:324]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_19 = 5'h13 == laneIndex[4:0] ? clipped : pePostData[359:342]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_20 = 5'h14 == laneIndex[4:0] ? clipped : pePostData[377:360]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_21 = 5'h15 == laneIndex[4:0] ? clipped : pePostData[395:378]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_22 = 5'h16 == laneIndex[4:0] ? clipped : pePostData[413:396]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_23 = 5'h17 == laneIndex[4:0] ? clipped : pePostData[431:414]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_24 = 5'h18 == laneIndex[4:0] ? clipped : pePostData[449:432]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_25 = 5'h19 == laneIndex[4:0] ? clipped : pePostData[467:450]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_26 = 5'h1a == laneIndex[4:0] ? clipped : pePostData[485:468]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_27 = 5'h1b == laneIndex[4:0] ? clipped : pePostData[503:486]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_28 = 5'h1c == laneIndex[4:0] ? clipped : pePostData[521:504]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_29 = 5'h1d == laneIndex[4:0] ? clipped : pePostData[539:522]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_30 = 5'h1e == laneIndex[4:0] ? clipped : pePostData[557:540]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [17:0] postVector_31 = 5'h1f == laneIndex[4:0] ? clipped : pePostData[575:558]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 415:20 417:{31,31}]
  wire [143:0] pePostData_lo_lo = {postVector_7,postVector_6,postVector_5,postVector_4,postVector_3,postVector_2,
    postVector_1,postVector_0}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 418:34]
  wire [287:0] pePostData_lo = {postVector_15,postVector_14,postVector_13,postVector_12,postVector_11,postVector_10,
    postVector_9,postVector_8,pePostData_lo_lo}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 418:34]
  wire [143:0] pePostData_hi_lo = {postVector_23,postVector_22,postVector_21,postVector_20,postVector_19,postVector_18,
    postVector_17,postVector_16}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 418:34]
  wire [575:0] _pePostData_T = {postVector_31,postVector_30,postVector_29,postVector_28,postVector_27,postVector_26,
    postVector_25,postVector_24,pePostData_hi_lo,pePostData_lo}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 418:34]
  wire [5:0] _T_52 = laneIndex + 6'h1; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 420:24]
  wire [31:0] _GEN_640 = {{26'd0}, _T_52}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 420:30]
  wire  _T_53 = _GEN_640 >= lanesThis; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 420:30]
  wire [3:0] _GEN_330 = _GEN_640 >= lanesThis ? 4'h9 : 4'h7; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 420:44 421:17 424:17]
  wire [5:0] _GEN_331 = _GEN_640 >= lanesThis ? laneIndex : _T_52; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 420:44 423:21 95:28]
  wire [1535:0] _GEN_332 = pe_io_validO ? pe_io_postResult : postSnapshot; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 439:28 440:24 123:31]
  wire [5:0] _GEN_333 = pe_io_validO ? 6'h0 : laneIndex; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 439:28 441:21 95:28]
  wire [3:0] _GEN_334 = pe_io_validO ? 4'hb : state; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 439:28 442:17 75:24]
  wire [47:0] _GEN_336 = 5'h1 == physicalIndexShared[4:0] ? postVectorShared_1 : postVectorShared_0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_337 = 5'h2 == physicalIndexShared[4:0] ? postVectorShared_2 : _GEN_336; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_338 = 5'h3 == physicalIndexShared[4:0] ? postVectorShared_3 : _GEN_337; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_339 = 5'h4 == physicalIndexShared[4:0] ? postVectorShared_4 : _GEN_338; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_340 = 5'h5 == physicalIndexShared[4:0] ? postVectorShared_5 : _GEN_339; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_341 = 5'h6 == physicalIndexShared[4:0] ? postVectorShared_6 : _GEN_340; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_342 = 5'h7 == physicalIndexShared[4:0] ? postVectorShared_7 : _GEN_341; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_343 = 5'h8 == physicalIndexShared[4:0] ? postVectorShared_8 : _GEN_342; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_344 = 5'h9 == physicalIndexShared[4:0] ? postVectorShared_9 : _GEN_343; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_345 = 5'ha == physicalIndexShared[4:0] ? postVectorShared_10 : _GEN_344; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_346 = 5'hb == physicalIndexShared[4:0] ? postVectorShared_11 : _GEN_345; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_347 = 5'hc == physicalIndexShared[4:0] ? postVectorShared_12 : _GEN_346; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_348 = 5'hd == physicalIndexShared[4:0] ? postVectorShared_13 : _GEN_347; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_349 = 5'he == physicalIndexShared[4:0] ? postVectorShared_14 : _GEN_348; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_350 = 5'hf == physicalIndexShared[4:0] ? postVectorShared_15 : _GEN_349; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_351 = 5'h10 == physicalIndexShared[4:0] ? postVectorShared_16 : _GEN_350; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_352 = 5'h11 == physicalIndexShared[4:0] ? postVectorShared_17 : _GEN_351; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_353 = 5'h12 == physicalIndexShared[4:0] ? postVectorShared_18 : _GEN_352; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_354 = 5'h13 == physicalIndexShared[4:0] ? postVectorShared_19 : _GEN_353; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_355 = 5'h14 == physicalIndexShared[4:0] ? postVectorShared_20 : _GEN_354; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_356 = 5'h15 == physicalIndexShared[4:0] ? postVectorShared_21 : _GEN_355; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_357 = 5'h16 == physicalIndexShared[4:0] ? postVectorShared_22 : _GEN_356; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_358 = 5'h17 == physicalIndexShared[4:0] ? postVectorShared_23 : _GEN_357; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_359 = 5'h18 == physicalIndexShared[4:0] ? postVectorShared_24 : _GEN_358; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_360 = 5'h19 == physicalIndexShared[4:0] ? postVectorShared_25 : _GEN_359; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_361 = 5'h1a == physicalIndexShared[4:0] ? postVectorShared_26 : _GEN_360; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_362 = 5'h1b == physicalIndexShared[4:0] ? postVectorShared_27 : _GEN_361; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_363 = 5'h1c == physicalIndexShared[4:0] ? postVectorShared_28 : _GEN_362; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_364 = 5'h1d == physicalIndexShared[4:0] ? postVectorShared_29 : _GEN_363; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_365 = 5'h1e == physicalIndexShared[4:0] ? postVectorShared_30 : _GEN_364; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [47:0] _GEN_366 = select_lane48_post; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 450:{22,22}]
  wire [8:0] _squareShift_T = {shiftR, 1'h0}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 464:35]
  wire [8:0] squareShift = _squareShift_T + 9'h7; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 464:41]
  wire [8:0] normalShift = {3'h0,shiftR[5:0]}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 466:30]
  wire [8:0] sharedShiftAmount = _state_T ? squareShift : normalShift; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 467:36]
  wire [47:0] sharedShiftInput = _state_T ? $signed(writeSquareR) : $signed(writeSumR); // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 468:35]
  wire [47:0] sharedShiftResult = $signed(sharedShiftInput) >>> sharedShiftAmount; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 470:50]
  wire [47:0] _squareScaled_T_1 = $signed(sharedShiftInput) >>> sharedShiftAmount; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 473:44]
  wire [47:0] squareScaled = squareShift >= 9'h30 ? 48'h0 : _squareScaled_T_1; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 472:31]
  wire  _activated_T = $signed(sharedShiftResult) < 48'sh0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 478:36]
  wire [47:0] _activated_T_1 = $signed(sharedShiftResult) < 48'sh0 ? $signed(48'sh0) : $signed(sharedShiftResult); // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 478:27]
  wire [47:0] _GEN_367 = |_squareScaled_T_1[46:7] ? $signed(48'sh7f) : $signed(sharedShiftResult); // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 476:19 482:57 483:23]
  wire [47:0] _GEN_368 = _activated_T ? $signed(48'sh0) : $signed(_GEN_367); // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 480:31 481:23]
  wire [47:0] _activated_T_4 = squareShift >= 9'h30 ? 48'h0 : _squareScaled_T_1; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 487:26]
  wire [47:0] _activated_T_5 = |squareScaled[47:7] ? $signed(48'sh7f) : $signed(_activated_T_4); // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 486:27]
  wire [47:0] _GEN_369 = _state_T ? $signed(_activated_T_5) : $signed(sharedShiftResult); // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 476:19 485:69 486:21]
  wire [47:0] _GEN_370 = activationR == 2'h2 ? $signed(_GEN_368) : $signed(_GEN_369); // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 479:66]
  wire [47:0] activatedBits = activationR == 2'h1 ? $signed(_activated_T_1) : $signed(_GEN_370); // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 499:39]
  wire  activatedSign = activatedBits[47]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 500:42]
  wire [40:0] s8Upper = activatedBits[47:7]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 501:36]
  wire [39:0] u8Upper = activatedBits[47:8]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 502:36]
  wire [32:0] s16Upper = activatedBits[47:15]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 503:37]
  wire [16:0] i32Upper = activatedBits[47:31]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 504:37]
  wire  _T_65 = ~activatedSign; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 505:14]
  wire [7:0] _GEN_372 = activatedSign & ~(&s8Upper) ? 8'h80 : activatedBits[7:0]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 507:52 508:19 510:19]
  wire [7:0] s8Value = ~activatedSign & |s8Upper ? 8'h7f : _GEN_372; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 505:45 506:19]
  wire [7:0] _GEN_374 = |u8Upper ? 8'hff : activatedBits[7:0]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 514:33 515:19 517:19]
  wire [7:0] u8Value = activatedSign ? 8'h0 : _GEN_374; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 512:29 513:19]
  wire [15:0] _GEN_376 = activatedSign & ~(&s16Upper) ? 16'h8000 : activatedBits[15:0]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 521:53 522:20 524:20]
  wire [15:0] s16Value = _T_65 & |s16Upper ? 16'h7fff : _GEN_376; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 519:46 520:20]
  wire [31:0] _GEN_378 = activatedSign & ~(&i32Upper) ? 32'h80000000 : activatedBits[31:0]; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 528:53 529:20 531:20]
  wire [31:0] i32Value = _T_65 & |i32Upper ? 32'h7fffffff : _GEN_378; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 526:46 527:20]
  wire [31:0] _formatted_T = {24'h0,s8Value}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 536:53]
  wire [31:0] _formatted_T_1 = {24'h0,u8Value}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 537:35]
  wire [31:0] _formatted_T_2 = {16'h0,s16Value}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 538:36]
  wire [31:0] _formatted_T_4 = 2'h1 == outputFormatR ? _formatted_T_1 : _formatted_T; // @[src/main/scala/chisel3/util/Mux.scala 77:13]
  wire [31:0] _formatted_T_6 = 2'h2 == outputFormatR ? _formatted_T_2 : _formatted_T_4; // @[src/main/scala/chisel3/util/Mux.scala 77:13]
  wire [31:0] formatted = 2'h3 == outputFormatR ? i32Value : _formatted_T_6; // @[src/main/scala/chisel3/util/Mux.scala 77:13]
  wire [31:0] _outWaddrR_T = pixelIndex * coutTilesR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 544:34]
  wire [31:0] _GEN_644 = {{16'd0}, coTileIndex}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 544:47]
  wire [31:0] _outWaddrR_T_2 = _outWaddrR_T + _GEN_644; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 544:47]
  // DMA selects 16 slots for S16 tiles; standalone cores keep the legacy
  // 32-slot layout. Constant shifts avoid a variable stride multiplier.
  wire [37:0] _outWaddrR_T_3 = COMPACT_S16_OUTPUT && computeModeR == 2'h0 ?
    {2'b0, _outWaddrR_T_2, 4'b0} : {1'b0, _outWaddrR_T_2, 5'b0};
  wire [37:0] _GEN_645 = {{32'd0}, laneIndex}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 545:27]
  wire [37:0] _outWaddrR_T_5 = _outWaddrR_T_3 + _GEN_645; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 545:27]
  wire [15:0] _T_88 = coTileIndex + 16'h1; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 551:28]
  wire [15:0] _T_91 = pixelIndex + 16'h1; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 552:29]
  wire  _GEN_380 = _T_91 >= pixelsR ? 1'h0 : busyR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 552:47 553:21 79:24]
  wire  _GEN_381 = _T_91 >= pixelsR | _GEN_66; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 552:47 554:21]
  wire [3:0] _GEN_382 = _T_91 >= pixelsR ? 4'h0 : 4'h1; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 552:47 555:21 560:21]
  wire [15:0] _GEN_383 = _T_91 >= pixelsR ? pixelIndex : _T_91; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 552:47 557:26 92:29]
  wire [15:0] _GEN_384 = _T_91 >= pixelsR ? coTileIndex : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 552:47 558:27 94:30]
  wire [15:0] _GEN_385 = _T_91 >= pixelsR ? ciTileIndex : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 552:47 559:27 93:30]
  wire  _GEN_386 = _T_88 >= coutTilesR ? _GEN_380 : busyR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 551:49 79:24]
  wire  _GEN_387 = _T_88 >= coutTilesR ? _GEN_381 : _GEN_66; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 551:49]
  wire [3:0] _GEN_388 = _T_88 >= coutTilesR ? _GEN_382 : 4'h1; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 551:49 565:19]
  wire [15:0] _GEN_389 = _T_88 >= coutTilesR ? _GEN_383 : pixelIndex; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 551:49 92:29]
  wire [15:0] _GEN_390 = _T_88 >= coutTilesR ? _GEN_384 : _T_88; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 551:49 563:25]
  wire [15:0] _GEN_391 = _T_88 >= coutTilesR ? _GEN_385 : 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 551:49 564:25]
  wire  _GEN_392 = _T_53 ? _GEN_386 : busyR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 550:44 79:24]
  wire  _GEN_393 = _T_53 ? _GEN_387 : _GEN_66; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 550:44]
  wire [3:0] _GEN_394 = _T_53 ? _GEN_388 : 4'hc; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 550:44 569:17]
  wire [15:0] _GEN_395 = _T_53 ? _GEN_389 : pixelIndex; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 550:44 92:29]
  wire [15:0] _GEN_396 = _T_53 ? _GEN_390 : coTileIndex; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 550:44 94:30]
  wire [15:0] _GEN_397 = _T_53 ? _GEN_391 : ciTileIndex; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 550:44 93:30]
  wire [37:0] _GEN_400 = 4'hc == state ? _outWaddrR_T_5 : {{6'd0}, outWaddrR}; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 544:19 137:28]
  wire [31:0] _GEN_401 = 4'hc == state ? formatted : outWdataR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 546:19 138:28]
  wire  _GEN_402 = 4'hc == state ? _GEN_392 : busyR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 79:24]
  wire  _GEN_403 = 4'hc == state ? _GEN_393 : _GEN_66; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
  wire [3:0] _GEN_404 = 4'hc == state ? _GEN_394 : state; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 75:24]
  wire [15:0] _GEN_405 = 4'hc == state ? _GEN_395 : pixelIndex; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 92:29]
  wire [15:0] _GEN_406 = 4'hc == state ? _GEN_396 : coTileIndex; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 94:30]
  wire [15:0] _GEN_407 = 4'hc == state ? _GEN_397 : ciTileIndex; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 93:30]
  wire [5:0] _GEN_408 = 4'hc == state ? _GEN_331 : laneIndex; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 95:28]
  wire [47:0] _GEN_409 = (4'hb == state || (4'hc == state && !_T_53)) ? $signed(sum48Shared) : $signed(writeSumR); // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 449:19 125:28]
  wire [47:0] _GEN_410 = (4'hb == state || (4'hc == state && !_T_53)) ? _GEN_366 : writeSquareR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 450:22 126:31]
  wire [3:0] _GEN_411 = 4'hb == state ? 4'hc : _GEN_404; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 451:15]
  wire  _GEN_412 = 4'hb == state ? 1'h0 : 4'hc == state; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 171:12 231:19]
  wire [37:0] _GEN_413 = 4'hb == state ? {{6'd0}, outWaddrR} : _GEN_400; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 137:28]
  wire [31:0] _GEN_414 = 4'hb == state ? outWdataR : _GEN_401; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 138:28]
  wire  _GEN_415 = 4'hb == state ? busyR : _GEN_402; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 79:24]
  wire  _GEN_416 = 4'hb == state ? _GEN_66 : _GEN_403; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
  wire [15:0] _GEN_417 = 4'hb == state ? pixelIndex : _GEN_405; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 92:29]
  wire [15:0] _GEN_418 = 4'hb == state ? coTileIndex : _GEN_406; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 94:30]
  wire [15:0] _GEN_419 = 4'hb == state ? ciTileIndex : _GEN_407; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 93:30]
  wire [5:0] _GEN_420 = 4'hb == state ? laneIndex : _GEN_408; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 95:28]
  wire [1535:0] _GEN_421 = 4'ha == state ? _GEN_332 : postSnapshot; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 123:31]
  wire [5:0] _GEN_422 = 4'ha == state ? _GEN_333 : _GEN_420; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
  wire [3:0] _GEN_423 = 4'ha == state ? _GEN_334 : _GEN_411; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
  wire [47:0] _GEN_424 = 4'ha == state ? $signed(writeSumR) : $signed(_GEN_409); // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 125:28]
  wire [47:0] _GEN_425 = 4'ha == state ? writeSquareR : _GEN_410; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 126:31]
  wire  _GEN_426 = 4'ha == state ? 1'h0 : _GEN_412; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 171:12 231:19]
  wire [37:0] _GEN_427 = 4'ha == state ? {{6'd0}, outWaddrR} : _GEN_413; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 137:28]
  wire [31:0] _GEN_428 = 4'ha == state ? outWdataR : _GEN_414; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 138:28]
  wire  _GEN_429 = 4'ha == state ? busyR : _GEN_415; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 79:24]
  wire  _GEN_430 = 4'ha == state ? _GEN_66 : _GEN_416; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
  wire [15:0] _GEN_431 = 4'ha == state ? pixelIndex : _GEN_417; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 92:29]
  wire [15:0] _GEN_432 = 4'ha == state ? coTileIndex : _GEN_418; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 94:30]
  wire [15:0] _GEN_433 = 4'ha == state ? ciTileIndex : _GEN_419; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 93:30]
  wire [31:0] _GEN_435 = 4'h9 == state ? 32'hffffffff : peMask; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 433:16 115:25]
  wire [3:0] _GEN_436 = 4'h9 == state ? 4'ha : _GEN_423; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 434:15]
  wire [1535:0] _GEN_437 = 4'h9 == state ? postSnapshot : _GEN_421; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 123:31]
  wire [5:0] _GEN_438 = 4'h9 == state ? laneIndex : _GEN_422; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 95:28]
  wire [47:0] _GEN_439 = 4'h9 == state ? $signed(writeSumR) : $signed(_GEN_424); // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 125:28]
  wire [47:0] _GEN_440 = 4'h9 == state ? writeSquareR : _GEN_425; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 126:31]
  wire  _GEN_441 = 4'h9 == state ? 1'h0 : _GEN_426; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 171:12 231:19]
  wire [37:0] _GEN_442 = 4'h9 == state ? {{6'd0}, outWaddrR} : _GEN_427; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 137:28]
  wire [31:0] _GEN_443 = 4'h9 == state ? outWdataR : _GEN_428; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 138:28]
  wire  _GEN_444 = 4'h9 == state ? busyR : _GEN_429; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 79:24]
  wire  _GEN_445 = 4'h9 == state ? _GEN_66 : _GEN_430; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
  wire [15:0] _GEN_446 = 4'h9 == state ? pixelIndex : _GEN_431; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 92:29]
  wire [15:0] _GEN_447 = 4'h9 == state ? coTileIndex : _GEN_432; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 94:30]
  wire [15:0] _GEN_448 = 4'h9 == state ? ciTileIndex : _GEN_433; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 93:30]
  wire [575:0] _GEN_449 = 4'h8 == state ? _pePostData_T : pePostData; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 418:20 118:29]
  wire [3:0] _GEN_450 = 4'h8 == state ? _GEN_330 : _GEN_436; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
  wire [5:0] _GEN_451 = 4'h8 == state ? _GEN_331 : _GEN_438; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
  wire  _GEN_452 = 4'h8 == state ? 1'h0 : 4'h9 == state; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 164:13 231:19]
  wire [31:0] _GEN_453 = 4'h8 == state ? peMask : _GEN_435; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 115:25]
  wire [1535:0] _GEN_454 = 4'h8 == state ? postSnapshot : _GEN_437; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 123:31]
  wire [47:0] _GEN_455 = 4'h8 == state ? $signed(writeSumR) : $signed(_GEN_439); // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 125:28]
  wire [47:0] _GEN_456 = 4'h8 == state ? writeSquareR : _GEN_440; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 126:31]
  wire  _GEN_457 = 4'h8 == state ? 1'h0 : _GEN_441; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 171:12 231:19]
  wire [37:0] _GEN_458 = 4'h8 == state ? {{6'd0}, outWaddrR} : _GEN_442; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 137:28]
  wire [31:0] _GEN_459 = 4'h8 == state ? outWdataR : _GEN_443; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 138:28]
  wire  _GEN_460 = 4'h8 == state ? busyR : _GEN_444; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 79:24]
  wire  _GEN_461 = 4'h8 == state ? _GEN_66 : _GEN_445; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
  wire [15:0] _GEN_462 = 4'h8 == state ? pixelIndex : _GEN_446; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 92:29]
  wire [15:0] _GEN_463 = 4'h8 == state ? coTileIndex : _GEN_447; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 94:30]
  wire [15:0] _GEN_464 = 4'h8 == state ? ciTileIndex : _GEN_448; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 93:30]
  wire [47:0] _GEN_465 = 4'h7 == state ? $signed(sum48Shared) : $signed(postInputR); // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 393:20 124:29]
  wire [3:0] _GEN_466 = 4'h7 == state ? 4'h8 : _GEN_450; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 394:15]
  wire [575:0] _GEN_467 = 4'h7 == state ? pePostData : _GEN_449; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 118:29]
  wire [5:0] _GEN_468 = 4'h7 == state ? laneIndex : _GEN_451; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 95:28]
  wire  _GEN_469 = 4'h7 == state ? 1'h0 : _GEN_452; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 164:13 231:19]
  wire [31:0] _GEN_470 = 4'h7 == state ? peMask : _GEN_453; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 115:25]
  wire [1535:0] _GEN_471 = 4'h7 == state ? postSnapshot : _GEN_454; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 123:31]
  wire [47:0] _GEN_472 = 4'h7 == state ? $signed(writeSumR) : $signed(_GEN_455); // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 125:28]
  wire [47:0] _GEN_473 = 4'h7 == state ? writeSquareR : _GEN_456; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 126:31]
  wire  _GEN_474 = 4'h7 == state ? 1'h0 : _GEN_457; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 171:12 231:19]
  wire [37:0] _GEN_475 = 4'h7 == state ? {{6'd0}, outWaddrR} : _GEN_458; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 137:28]
  wire [31:0] _GEN_476 = 4'h7 == state ? outWdataR : _GEN_459; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 138:28]
  wire  _GEN_477 = 4'h7 == state ? busyR : _GEN_460; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 79:24]
  wire  _GEN_478 = 4'h7 == state ? _GEN_66 : _GEN_461; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
  wire [15:0] _GEN_479 = 4'h7 == state ? pixelIndex : _GEN_462; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 92:29]
  wire [15:0] _GEN_480 = 4'h7 == state ? coTileIndex : _GEN_463; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 94:30]
  wire [15:0] _GEN_481 = 4'h7 == state ? ciTileIndex : _GEN_464; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 93:30]
  wire [1535:0] _GEN_482 = 4'h2 == state ? io_biasRdata : biasSnapshot; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 375:22 122:31]
  wire [5:0] _GEN_483 = 4'h2 == state ? 6'h0 : _GEN_468; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 376:19]
  wire [575:0] _GEN_484 = 4'h2 == state ? 576'h0 : _GEN_467; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 377:20]
  wire [3:0] _GEN_485 = 4'h2 == state ? _state_T_1 : _GEN_466; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 378:15]
  wire [47:0] _GEN_486 = 4'h2 == state ? $signed(postInputR) : $signed(_GEN_465); // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 124:29]
  wire  _GEN_487 = 4'h2 == state ? 1'h0 : _GEN_469; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 164:13 231:19]
  wire [31:0] _GEN_488 = 4'h2 == state ? peMask : _GEN_470; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 115:25]
  wire [1535:0] _GEN_489 = 4'h2 == state ? postSnapshot : _GEN_471; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 123:31]
  wire [47:0] _GEN_490 = 4'h2 == state ? $signed(writeSumR) : $signed(_GEN_472); // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 125:28]
  wire [47:0] _GEN_491 = 4'h2 == state ? writeSquareR : _GEN_473; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 126:31]
  wire  _GEN_492 = 4'h2 == state ? 1'h0 : _GEN_474; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 171:12 231:19]
  wire [37:0] _GEN_493 = 4'h2 == state ? {{6'd0}, outWaddrR} : _GEN_475; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 137:28]
  wire [31:0] _GEN_494 = 4'h2 == state ? outWdataR : _GEN_476; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 138:28]
  wire  _GEN_495 = 4'h2 == state ? busyR : _GEN_477; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 79:24]
  wire  _GEN_496 = 4'h2 == state ? _GEN_66 : _GEN_478; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
  wire [15:0] _GEN_497 = 4'h2 == state ? pixelIndex : _GEN_479; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 92:29]
  wire [15:0] _GEN_498 = 4'h2 == state ? coTileIndex : _GEN_480; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 94:30]
  wire [15:0] _GEN_499 = 4'h2 == state ? ciTileIndex : _GEN_481; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 93:30]
  wire [3:0] _GEN_500 = 4'h6 == state ? 4'h2 : _GEN_485; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 369:15]
  wire [1535:0] _GEN_501 = 4'h6 == state ? biasSnapshot : _GEN_482; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 122:31]
  wire [5:0] _GEN_502 = 4'h6 == state ? laneIndex : _GEN_483; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 95:28]
  wire [575:0] _GEN_503 = 4'h6 == state ? pePostData : _GEN_484; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 118:29]
  wire [47:0] _GEN_504 = 4'h6 == state ? $signed(postInputR) : $signed(_GEN_486); // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 124:29]
  wire  _GEN_505 = 4'h6 == state ? 1'h0 : _GEN_487; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 164:13 231:19]
  wire [31:0] _GEN_506 = 4'h6 == state ? peMask : _GEN_488; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 115:25]
  wire [1535:0] _GEN_507 = 4'h6 == state ? postSnapshot : _GEN_489; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 123:31]
  wire [47:0] _GEN_508 = 4'h6 == state ? $signed(writeSumR) : $signed(_GEN_490); // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 125:28]
  wire [47:0] _GEN_509 = 4'h6 == state ? writeSquareR : _GEN_491; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 126:31]
  wire  _GEN_510 = 4'h6 == state ? 1'h0 : _GEN_492; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 171:12 231:19]
  wire [37:0] _GEN_511 = 4'h6 == state ? {{6'd0}, outWaddrR} : _GEN_493; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 137:28]
  wire [31:0] _GEN_512 = 4'h6 == state ? outWdataR : _GEN_494; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 138:28]
  wire  _GEN_513 = 4'h6 == state ? busyR : _GEN_495; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 79:24]
  wire  _GEN_514 = 4'h6 == state ? _GEN_66 : _GEN_496; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
  wire [15:0] _GEN_515 = 4'h6 == state ? pixelIndex : _GEN_497; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 92:29]
  wire [15:0] _GEN_516 = 4'h6 == state ? coTileIndex : _GEN_498; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 94:30]
  wire [15:0] _GEN_517 = 4'h6 == state ? ciTileIndex : _GEN_499; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 93:30]
  wire [37:0] _GEN_531 = 4'h5 == state ? {{6'd0}, outWaddrR} : _GEN_511; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 137:28]
  wire [37:0] _GEN_552 = 4'h4 == state ? {{6'd0}, outWaddrR} : _GEN_531; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 137:28]
  wire [37:0] _GEN_584 = 4'h1 == state ? {{6'd0}, outWaddrR} : _GEN_552; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 137:28]
  wire [37:0] _GEN_629 = 4'h0 == state ? {{6'd0}, outWaddrR} : _GEN_584; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19 137:28]
  MacPeArray #(.ENABLE_FP8(ENABLE_FP8)) pe ( // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 55:18]
    .io_clk(pe_io_clk),
    .io_rstN(pe_io_rstN),
    .io_validI(pe_io_validI),
    .io_accClear(pe_io_accClear),
    .io_computeMode(pe_io_computeMode),
    .io_postMode(pe_io_postMode),
    .io_laneMask(pe_io_laneMask),
    .io_x(pe_io_x),
    .io_w(pe_io_w),
    .io_postData(pe_io_postData),
    .io_validO(pe_io_validO),
    .io_acc(pe_io_acc),
    .io_postResult(pe_io_postResult)
  );
  assign io_busy = busyR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 150:13]
  assign io_done = doneR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 151:13]
  assign io_wtRe = wtReR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 152:13]
  assign io_wtRaddr = wtRaddrR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 153:16]
  assign io_inRe = inReR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 154:13]
  assign io_inRaddr = inRaddrR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 155:16]
  assign io_biasRe = biasReR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 156:15]
  assign io_biasRaddr = biasRaddrR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 157:18]
  assign io_outWe = outWeR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 158:14]
  assign io_outWaddr = outWaddrR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 159:17]
  assign io_outWdata = outWdataR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 160:17]
  assign pe_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 56:13]
  assign pe_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 57:14]
  assign pe_io_validI = peValid; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 141:18]
  assign pe_io_accClear = peClear; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 142:20]
  assign pe_io_computeMode = computeModeR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 143:23]
  assign pe_io_postMode = pePostMode; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 144:20]
  assign pe_io_laneMask = peMask; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 145:20]
  assign pe_io_x = peX; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 146:13]
  assign pe_io_w = peW; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 147:13]
  assign pe_io_postData = pePostData; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 148:20]
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      state <= 4'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 234:24 263:17 75:24]
    end else if (4'h0 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (io_start) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 335:29]
        state <= 4'h1; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 344:30 345:19 75:24]
      end
    end else if (4'h1 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (readDataValid) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 353:40]
        if (readDataLast) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 355:17]
          state <= 4'h4;
        end
      end
    end else if (4'h4 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (pe_io_validO & peLastD3) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 363:15]
        state <= 4'h5;
      end
    end else if (4'h5 == state) begin
      state <= 4'h6;
    end else begin
      state <= _GEN_500;
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      busyR <= 1'h0;
    end else if (4'h0 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      busyR <= io_start; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 79:24]
    end else if (!(4'h1 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (!(4'h4 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
        if (!(4'h5 == state)) begin
          busyR <= _GEN_513;
        end
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      doneR <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 234:24 242:17]
    end else if (4'h0 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (io_start) begin
        doneR <= 1'h0;
      end else begin
        doneR <= _GEN_66;
      end
    end else if (4'h1 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      doneR <= _GEN_66;
    end else if (4'h4 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      doneR <= _GEN_66;
    end else if (4'h5 == state) begin
      doneR <= _GEN_66;
    end else begin
      doneR <= _GEN_514;
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      pixelsR <= 16'h1; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 234:24 237:27 81:26]
    end else if (4'h0 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 81:26]
      if (io_start) begin
        if (io_cfgPixels == 16'h0) begin
          pixelsR <= 16'h1;
        end else begin
          pixelsR <= io_cfgPixels;
        end
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      cinR <= 16'h1; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 234:24 238:24 82:23]
    end else if (4'h0 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 82:23]
      if (io_start) begin
        if (io_cfgCin == 16'h0) begin
          cinR <= 16'h1;
        end else begin
          cinR <= io_cfgCin;
        end
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      coutR <= 16'h1; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 234:24 239:25 83:24]
    end else if (4'h0 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 83:24]
      if (io_start) begin
        if (io_cfgCout == 16'h0) begin
          coutR <= 16'h1;
        end else begin
          coutR <= io_cfgCout;
        end
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      cinTilesR <= 16'h1; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 234:24 252:21 84:28]
    end else if (4'h0 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 84:28]
      if (io_start) begin
        cinTilesR <= _cinTilesR_T_2;
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      coutTilesR <= 16'h1; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 234:24 253:28 255:24 258:24 85:29]
    end else if (4'h0 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 85:29]
      if (io_start) begin
        if (packedMode) begin
          coutTilesR <= _coutTilesR_T_2;
        end else begin
          coutTilesR <= _coutTilesR_T_5;
        end
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      coutStepR <= 16'h10; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 234:24 86:28]
    end else if (4'h0 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 86:28]
      if (io_start) begin
        coutStepR <= {{10'd0}, _GEN_67};
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      computeModeR <= 2'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 234:24 246:24 87:31]
    end else if (4'h0 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 87:31]
      if (io_start) begin
        computeModeR <= io_cfgComputeMode;
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      activationR <= 2'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 234:24 247:23 88:30]
    end else if (4'h0 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 88:30]
      if (io_start) begin
        activationR <= io_cfgActivation;
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      outputFormatR <= 2'h2; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 234:24 248:25 89:32]
    end else if (4'h0 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 89:32]
      if (io_start) begin
        outputFormatR <= io_cfgOutputFormat;
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      shiftR <= 8'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 234:24 249:18 90:25]
    end else if (4'h0 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 90:25]
      if (io_start) begin
        shiftR <= io_cfgOutShift;
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      pixelIndex <= 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 234:24 260:22 92:29]
    end else if (4'h0 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (io_start) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 92:29]
        pixelIndex <= 16'h0;
      end
    end else if (!(4'h1 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (!(4'h4 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
        if (!(4'h5 == state)) begin
          pixelIndex <= _GEN_515;
        end
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      ciTileIndex <= 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 234:24 261:23 93:30]
    end else if (4'h0 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (io_start) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 271:39]
        ciTileIndex <= 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 278:23]
      end
    end else if (4'h1 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (ciTileIndex < cinTilesR) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 93:30]
        ciTileIndex <= _readCommandLast_T_1;
      end
    end else if (!(4'h4 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (!(4'h5 == state)) begin
        ciTileIndex <= _GEN_517;
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      coTileIndex <= 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 234:24 262:23 94:30]
    end else if (4'h0 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (io_start) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 94:30]
        coTileIndex <= 16'h0;
      end
    end else if (!(4'h1 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (!(4'h4 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
        if (!(4'h5 == state)) begin
          coTileIndex <= _GEN_516;
        end
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      laneIndex <= 6'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 95:28]
    end else if (!(4'h0 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (!(4'h1 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
        if (!(4'h4 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
          if (!(4'h5 == state)) begin
            laneIndex <= _GEN_502;
          end
        end
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      readCommandCi <= 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 100:32]
    end else if (!(4'h0 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (4'h1 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 100:32]
        if (ciTileIndex < cinTilesR) begin
          readCommandCi <= ciTileIndex;
        end
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      readCommandLast <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 101:34]
    end else if (!(4'h0 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (4'h1 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 101:34]
        if (ciTileIndex < cinTilesR) begin
          readCommandLast <= _readCommandLast_T_1 >= cinTilesR;
        end
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 102:32]
      readDataValid <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 102:32]
    end else begin
      readDataValid <= inReR; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 215:19]
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 216:17]
      readDataCi <= 16'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 217:18]
    end else if (inReR) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 103:29]
      readDataCi <= readCommandCi;
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 216:17]
      readDataLast <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 218:20]
    end else if (inReR) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 104:31]
      readDataLast <= readCommandLast;
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      peValid <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 164:13]
    end else if (4'h0 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      peValid <= 1'h0;
    end else if (4'h1 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      peValid <= readDataValid; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 164:13]
    end else if (4'h4 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      peValid <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 164:13]
    end else if (4'h5 == state) begin
      peValid <= 1'h0;
    end else begin
      peValid <= _GEN_505;
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      peClear <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 165:13]
    end else if (4'h0 == state) begin
      peClear <= 1'h0;
    end else begin
      peClear <= 4'h1 == state & _GEN_289;
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      pePostMode <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 166:16]
    end else if (4'h0 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      pePostMode <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 166:16]
    end else if (4'h1 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      pePostMode <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 164:13]
    end else if (4'h4 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      pePostMode <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 164:13]
    end else if (4'h5 == state) begin
      pePostMode <= 1'h0;
    end else begin
      pePostMode <= _GEN_505;
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      peLast <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 167:12]
    end else if (4'h0 == state) begin
      peLast <= 1'h0;
    end else begin
      peLast <= 4'h1 == state & _GEN_290;
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 223:25]
      peLastD1 <= 1'h0;
    end else begin
      peLastD1 <= peValid & peLast;
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 113:27]
      peLastD2 <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 113:27]
    end else begin
      peLastD2 <= peLastD1; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 224:14]
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 114:27]
      peLastD3 <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 114:27]
    end else begin
      peLastD3 <= peLastD2; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 225:14]
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      peMask <= 32'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 115:25]
    end else if (!(4'h0 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (4'h1 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
        if (readDataValid) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 115:25]
          peMask <= _peMask_T;
        end
      end else if (!(4'h4 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
        if (!(4'h5 == state)) begin
          peMask <= _GEN_506;
        end
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      peX <= 64'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 116:22]
    end else if (!(4'h0 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (4'h1 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 116:22]
        if (readDataValid) begin
          peX <= _peX_T;
        end
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      peW <= 1024'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 117:22]
    end else if (!(4'h0 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (4'h1 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 117:22]
        if (readDataValid) begin
          peW <= _peW_T;
        end
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      pePostData <= 576'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 118:29]
    end else if (!(4'h0 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (!(4'h1 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
        if (!(4'h4 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
          if (!(4'h5 == state)) begin
            pePostData <= _GEN_503;
          end
        end
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      accSnapshot <= 1536'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 121:30]
    end else if (!(4'h0 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (!(4'h1 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
        if (4'h4 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 121:30]
          if (pe_io_validO & peLastD3) begin
            accSnapshot <= pe_io_acc;
          end
        end
      end
    end
  end
  generate if (USE_HELD_BIAS) begin : g_held_bias
    assign biasSnapshot = io_biasRdata;
  end else begin : g_snapshot_bias
    reg [1535:0] snapshot;
    assign biasSnapshot = snapshot;
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      snapshot <= 1536'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 122:31]
    end else if (!(4'h0 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (!(4'h1 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
        if (!(4'h4 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
          if (!(4'h5 == state)) begin
            snapshot <= _GEN_501;
          end
        end
      end
    end
  end
  end endgenerate
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      postSnapshot <= 1536'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 123:31]
    end else if (!(4'h0 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (!(4'h1 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
        if (!(4'h4 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
          if (!(4'h5 == state)) begin
            postSnapshot <= _GEN_507;
          end
        end
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      postInputR <= 48'sh0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 124:29]
    end else if (!(4'h0 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (!(4'h1 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
        if (!(4'h4 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
          if (!(4'h5 == state)) begin
            postInputR <= _GEN_504;
          end
        end
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      writeSumR <= 48'sh0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 125:28]
    end else if (!(4'h0 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (!(4'h1 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
        if (!(4'h4 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
          if (!(4'h5 == state)) begin
            writeSumR <= _GEN_508;
          end
        end
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      writeSquareR <= 48'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 126:31]
    end else if (!(4'h0 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (!(4'h1 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
        if (!(4'h4 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
          if (!(4'h5 == state)) begin
            writeSquareR <= _GEN_509;
          end
        end
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      wtReR <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 169:11]
    end else if (4'h0 == state) begin
      wtReR <= 1'h0;
    end else begin
      wtReR <= 4'h1 == state & _T_4;
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      wtRaddrR <= 32'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 131:27]
    end else if (!(4'h0 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (4'h1 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 131:27]
        if (ciTileIndex < cinTilesR) begin
          wtRaddrR <= _wtRaddrR_T_2;
        end
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      inReR <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 169:11]
    end else if (4'h0 == state) begin
      inReR <= 1'h0;
    end else begin
      inReR <= 4'h1 == state & _T_4;
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      inRaddrR <= 32'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 133:27]
    end else if (!(4'h0 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (4'h1 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 133:27]
        if (ciTileIndex < cinTilesR) begin
          inRaddrR <= _inRaddrR_T_2;
        end
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      biasReR <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 170:13]
    end else if (4'h0 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      biasReR <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 170:13]
    end else if (4'h1 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      biasReR <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 170:13]
    end else if (4'h4 == state) begin
      biasReR <= 1'h0;
    end else begin
      biasReR <= 4'h5 == state;
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      biasRaddrR <= 32'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 135:29]
    end else if (!(4'h0 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (!(4'h1 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
        if (!(4'h4 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
          if (4'h5 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 135:29]
            biasRaddrR <= {{16'd0}, coTileIndex};
          end
        end
      end
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      outWeR <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 171:12]
    end else if (4'h0 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      outWeR <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 171:12]
    end else if (4'h1 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      outWeR <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 171:12]
    end else if (4'h4 == state) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      outWeR <= 1'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 171:12]
    end else if (4'h5 == state) begin
      outWeR <= 1'h0;
    end else begin
      outWeR <= _GEN_510;
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 137:28]
      outWaddrR <= 32'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 137:28]
    end else begin
      outWaddrR <= _GEN_629[31:0];
    end
  end
  always @(posedge io_clk or posedge _T_1) begin
    if (_T_1) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      outWdataR <= 32'h0; // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 138:28]
    end else if (!(4'h0 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
      if (!(4'h1 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
        if (!(4'h4 == state)) begin // @[\\src\\main\\scala\\macaccel\\MacEngine.scala 231:19]
          if (!(4'h5 == state)) begin
            outWdataR <= _GEN_512;
          end
        end
      end
    end
  end
endmodule
module MacAccelCore #(
  parameter COMPACT_S16_OUTPUT = 0,
  parameter integer WEIGHT_BANK_LINES = 1024,
  parameter ENABLE_FP8 = 1,
  parameter BIAS_WORD_WRITE = 0,
  parameter WEIGHT_WORD_WRITE = 0
)(
  input           io_clk, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 67:14]
  input           io_rstN, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 67:14]
  input           io_start, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 67:14]
  output          io_busy, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 67:14]
  output          io_done, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 67:14]
  input           io_doneClear, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 67:14]
  input  [15:0]   io_cfgPixels, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 67:14]
  input  [15:0]   io_cfgCin, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 67:14]
  input  [15:0]   io_cfgCout, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 67:14]
  input  [1:0]    io_cfgComputeMode, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 67:14]
  input  [1:0]    io_cfgActivation, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 67:14]
  input  [1:0]    io_cfgOutputFormat, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 67:14]
  input  [7:0]    io_cfgOutShift, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 67:14]
  input           io_hostInWe, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 67:14]
  input  [31:0]   io_hostInWaddr, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 67:14]
  input  [63:0]   io_hostInWdata, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 67:14]
  input           io_hostWtWe, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 67:14]
  input  [31:0]   io_hostWtWaddr, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 67:14]
  input  [1023:0] io_hostWtWdata, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 67:14]
  input           io_hostWtWordWe,
  input  [4:0]    io_hostWtWordIndex,
  input  [31:0]   io_hostWtWordData,
  input           io_hostBiasWe, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 67:14]
  input  [31:0]   io_hostBiasWaddr, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 67:14]
  input  [1535:0] io_hostBiasWdata, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 67:14]
  input           io_hostBiasWordWe,
  input           io_hostBiasZeroWe,
  input  [5:0]    io_hostBiasWordIndex,
  input  [31:0]   io_hostBiasWordData,
  input           io_hostOutRe, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 67:14]
  input  [31:0]   io_hostOutRaddr, // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 67:14]
  output [31:0]   io_hostOutRdata // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 67:14]
);
  wire  inputBank_io_clk; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 116:25]
  wire  inputBank_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 116:25]
  wire  inputBank_io_we; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 116:25]
  wire [31:0] inputBank_io_waddr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 116:25]
  wire [63:0] inputBank_io_wdata; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 116:25]
  wire  inputBank_io_re; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 116:25]
  wire [31:0] inputBank_io_raddr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 116:25]
  wire [63:0] inputBank_io_rdata; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 116:25]
  wire  weightBank_io_clk; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 117:26]
  wire  weightBank_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 117:26]
  wire  weightBank_io_we; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 117:26]
  wire [31:0] weightBank_io_waddr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 117:26]
  wire [1023:0] weightBank_io_wdata; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 117:26]
  wire  weightBank_io_re; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 117:26]
  wire [31:0] weightBank_io_raddr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 117:26]
  wire [1023:0] weightBank_io_rdata; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 117:26]
  wire  biasBank_io_clk; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 118:24]
  wire  biasBank_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 118:24]
  wire  biasBank_io_we; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 118:24]
  wire [31:0] biasBank_io_waddr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 118:24]
  wire [1535:0] biasBank_io_wdata; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 118:24]
  wire  biasBank_io_re; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 118:24]
  wire [31:0] biasBank_io_raddr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 118:24]
  wire [1535:0] biasBank_io_rdata; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 118:24]
  wire  outputBank_io_clk; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 119:26]
  wire  outputBank_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 119:26]
  wire  outputBank_io_we; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 119:26]
  wire [31:0] outputBank_io_waddr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 119:26]
  wire [31:0] outputBank_io_wdata; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 119:26]
  wire  outputBank_io_re; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 119:26]
  wire [31:0] outputBank_io_raddr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 119:26]
  wire [31:0] outputBank_io_rdata; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 119:26]
  wire  engine_io_clk; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 120:22]
  wire  engine_io_rstN; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 120:22]
  wire  engine_io_start; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 120:22]
  wire  engine_io_busy; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 120:22]
  wire  engine_io_done; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 120:22]
  wire  engine_io_doneClear; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 120:22]
  wire [15:0] engine_io_cfgPixels; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 120:22]
  wire [15:0] engine_io_cfgCin; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 120:22]
  wire [15:0] engine_io_cfgCout; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 120:22]
  wire [1:0] engine_io_cfgComputeMode; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 120:22]
  wire [1:0] engine_io_cfgActivation; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 120:22]
  wire [1:0] engine_io_cfgOutputFormat; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 120:22]
  wire [7:0] engine_io_cfgOutShift; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 120:22]
  wire  engine_io_wtRe; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 120:22]
  wire [31:0] engine_io_wtRaddr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 120:22]
  wire [1023:0] engine_io_wtRdata; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 120:22]
  wire  engine_io_inRe; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 120:22]
  wire [31:0] engine_io_inRaddr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 120:22]
  wire [63:0] engine_io_inRdata; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 120:22]
  wire  engine_io_biasRe; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 120:22]
  wire [31:0] engine_io_biasRaddr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 120:22]
  wire [1535:0] engine_io_biasRdata; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 120:22]
  wire  engine_io_outWe; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 120:22]
  wire [31:0] engine_io_outWaddr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 120:22]
  wire [31:0] engine_io_outWdata; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 120:22]
  Bank1R1W inputBank ( // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 116:25]
    .io_clk(inputBank_io_clk),
    .io_rstN(inputBank_io_rstN),
    .io_we(inputBank_io_we),
    .io_waddr(inputBank_io_waddr),
    .io_wdata(inputBank_io_wdata),
    .io_re(inputBank_io_re),
    .io_raddr(inputBank_io_raddr),
    .io_rdata(inputBank_io_rdata)
  );
  if (WEIGHT_BANK_LINES == 64) begin : g_compact_weight
  Bank1R1W_1_compact #(.WORD_WRITE(WEIGHT_WORD_WRITE)) weightBank (
    .io_clk(weightBank_io_clk),
    .io_rstN(weightBank_io_rstN),
    .io_we(weightBank_io_we),
    .io_waddr(weightBank_io_waddr),
    .io_wdata(weightBank_io_wdata),
    .io_wordWe(io_hostWtWordWe),
    .io_wordIndex(io_hostWtWordIndex),
    .io_wordData(io_hostWtWordData),
    .io_re(weightBank_io_re),
    .io_raddr(weightBank_io_raddr),
    .io_rdata(weightBank_io_rdata)
  );
  end else begin : g_full_weight
  Bank1R1W_1 weightBank ( // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 117:26]
    .io_clk(weightBank_io_clk),
    .io_rstN(weightBank_io_rstN),
    .io_we(weightBank_io_we),
    .io_waddr(weightBank_io_waddr),
    .io_wdata(weightBank_io_wdata),
    .io_re(weightBank_io_re),
    .io_raddr(weightBank_io_raddr),
    .io_rdata(weightBank_io_rdata)
  );
  end
  generate if (BIAS_WORD_WRITE) begin : g_word_bias
  MacBiasWordBank biasBank (
    .io_clk(biasBank_io_clk),
    .io_rstN(biasBank_io_rstN),
    .io_wordWe(io_hostBiasWordWe),
    .io_zeroWe(io_hostBiasZeroWe),
    .io_waddr(biasBank_io_waddr),
    .io_wordIndex(io_hostBiasWordIndex),
    .io_wordData(io_hostBiasWordData),
    .io_re(biasBank_io_re),
    .io_raddr(biasBank_io_raddr),
    .io_rdata(biasBank_io_rdata)
  );
  end else begin : g_wide_bias
  Bank1R1W_2 biasBank ( // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 118:24]
    .io_clk(biasBank_io_clk),
    .io_rstN(biasBank_io_rstN),
    .io_we(biasBank_io_we),
    .io_waddr(biasBank_io_waddr),
    .io_wdata(biasBank_io_wdata),
    .io_re(biasBank_io_re),
    .io_raddr(biasBank_io_raddr),
    .io_rdata(biasBank_io_rdata)
  );
  end endgenerate
  Bank1R1W_3 #(.DEPTH(COMPACT_S16_OUTPUT ? 4096 : 8192)) outputBank (
    .io_clk(outputBank_io_clk),
    .io_rstN(outputBank_io_rstN),
    .io_we(outputBank_io_we),
    .io_waddr(outputBank_io_waddr),
    .io_wdata(outputBank_io_wdata),
    .io_re(outputBank_io_re),
    .io_raddr(outputBank_io_raddr),
    .io_rdata(outputBank_io_rdata)
  );
  // biasBank read_data already holds all 1536 bits between tile reads.
  // Reuse it instead of registering a second copy in the engine.
  MacEngine #(.COMPACT_S16_OUTPUT(COMPACT_S16_OUTPUT),
              .ENABLE_FP8(ENABLE_FP8),.USE_HELD_BIAS(1)) engine (
    .io_clk(engine_io_clk),
    .io_rstN(engine_io_rstN),
    .io_start(engine_io_start),
    .io_busy(engine_io_busy),
    .io_done(engine_io_done),
    .io_doneClear(engine_io_doneClear),
    .io_cfgPixels(engine_io_cfgPixels),
    .io_cfgCin(engine_io_cfgCin),
    .io_cfgCout(engine_io_cfgCout),
    .io_cfgComputeMode(engine_io_cfgComputeMode),
    .io_cfgActivation(engine_io_cfgActivation),
    .io_cfgOutputFormat(engine_io_cfgOutputFormat),
    .io_cfgOutShift(engine_io_cfgOutShift),
    .io_wtRe(engine_io_wtRe),
    .io_wtRaddr(engine_io_wtRaddr),
    .io_wtRdata(engine_io_wtRdata),
    .io_inRe(engine_io_inRe),
    .io_inRaddr(engine_io_inRaddr),
    .io_inRdata(engine_io_inRdata),
    .io_biasRe(engine_io_biasRe),
    .io_biasRaddr(engine_io_biasRaddr),
    .io_biasRdata(engine_io_biasRdata),
    .io_outWe(engine_io_outWe),
    .io_outWaddr(engine_io_outWaddr),
    .io_outWdata(engine_io_outWdata)
  );
  assign io_busy = engine_io_busy; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 169:11]
  assign io_done = engine_io_done; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 170:11]
  assign io_hostOutRdata = outputBank_io_rdata; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 154:19]
  assign inputBank_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 123:17]
  assign inputBank_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 124:18]
  assign inputBank_io_we = io_hostInWe; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 130:19]
  assign inputBank_io_waddr = io_hostInWaddr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 131:22]
  assign inputBank_io_wdata = io_hostInWdata; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 132:22]
  assign inputBank_io_re = engine_io_inRe; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 133:19]
  assign inputBank_io_raddr = engine_io_inRaddr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 134:22]
  assign weightBank_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 123:17]
  assign weightBank_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 124:18]
  assign weightBank_io_we = io_hostWtWe; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 136:20]
  assign weightBank_io_waddr = io_hostWtWaddr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 137:23]
  assign weightBank_io_wdata = io_hostWtWdata; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 138:23]
  assign weightBank_io_re = engine_io_wtRe; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 139:20]
  assign weightBank_io_raddr = engine_io_wtRaddr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 140:23]
  assign biasBank_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 123:17]
  assign biasBank_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 124:18]
  assign biasBank_io_we = io_hostBiasWe; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 142:18]
  assign biasBank_io_waddr = io_hostBiasWaddr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 143:21]
  assign biasBank_io_wdata = io_hostBiasWdata; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 144:21]
  assign biasBank_io_re = engine_io_biasRe; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 145:18]
  assign biasBank_io_raddr = engine_io_biasRaddr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 146:21]
  assign outputBank_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 123:17]
  assign outputBank_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 124:18]
  assign outputBank_io_we = engine_io_outWe; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 149:20]
  assign outputBank_io_waddr = engine_io_outWaddr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 150:23]
  assign outputBank_io_wdata = engine_io_outWdata; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 151:23]
  assign outputBank_io_re = io_hostOutRe; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 152:20]
  assign outputBank_io_raddr = io_hostOutRaddr; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 153:23]
  assign engine_io_clk = io_clk; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 126:17]
  assign engine_io_rstN = io_rstN; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 127:18]
  assign engine_io_start = io_start; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 157:19]
  assign engine_io_doneClear = io_doneClear; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 158:23]
  assign engine_io_cfgPixels = io_cfgPixels; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 159:23]
  assign engine_io_cfgCin = io_cfgCin; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 160:20]
  assign engine_io_cfgCout = io_cfgCout; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 161:21]
  assign engine_io_cfgComputeMode = io_cfgComputeMode; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 162:28]
  assign engine_io_cfgActivation = io_cfgActivation; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 163:27]
  assign engine_io_cfgOutputFormat = io_cfgOutputFormat; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 164:29]
  assign engine_io_cfgOutShift = io_cfgOutShift; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 165:25]
  assign engine_io_wtRdata = weightBank_io_rdata; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 167:21]
  assign engine_io_inRdata = inputBank_io_rdata; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 166:21]
  assign engine_io_biasRdata = biasBank_io_rdata; // @[\\src\\main\\scala\\macaccel\\MacAccel.scala 168:23]
endmodule
