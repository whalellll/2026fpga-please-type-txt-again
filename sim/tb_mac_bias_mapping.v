`timescale 1ns/1ps
module tb_bias_mapping;
  reg clk = 0;
  reg rst_n = 0;
  reg we = 0;
  reg re = 0;
  reg [31:0] waddr = 0;
  reg [31:0] raddr = 0;
  reg [1535:0] wdata = 0;
  wire [1535:0] expected_data;
  wire [1535:0] actual_data;
  reg [31:0] seed = 32'h52a6c819;
  integer cycle;
  integer lane;
  GTP_GRS GRS_INST(.GRS_N(1'b1));
  bias_bank_reference reference_bank(
    .io_clk(clk), .io_rstN(rst_n), .io_we(we), .io_waddr(waddr),
    .io_wdata(wdata), .io_re(re), .io_raddr(raddr), .io_rdata(expected_data));
  bias_bank mapped_bank(
    .io_clk(clk), .io_rstN(rst_n), .io_we(we), .io_waddr(waddr),
    .io_wdata(wdata), .io_re(re), .io_raddr(raddr), .io_rdata(actual_data));
  always #5 clk = ~clk;
  initial begin
    repeat (2) @(negedge clk);
    rst_n = 1;
    // Initialize every entry, since the architectural memory has no reset.
    for (cycle = 0; cycle < 16; cycle = cycle + 1) begin
      @(negedge clk);
      we = 1; re = 0; waddr = cycle;
      for (lane = 0; lane < 48; lane = lane + 1)
        wdata[lane*32 +: 32] = 32'h8273c51b ^ (lane * 32'h9e3779b9) ^ cycle;
    end
    @(negedge clk); we = 0;
    for (cycle = 0; cycle < 512; cycle = cycle + 1) begin
      @(negedge clk);
      seed = (seed << 1) ^ (seed[31] ? 32'h04c11db7 : 32'h0);
      we = (cycle % 3) != 0;
      re = (cycle % 4) != 0;
      waddr = (cycle % 11 == 0) ? (16 + seed[3:0]) : {28'b0, seed[3:0]};
      raddr = (cycle % 5 == 0) ? waddr : {27'b0, seed[12:8]};
      rst_n = !((cycle >= 50 && cycle <= 52) || cycle == 300);
      for (lane = 0; lane < 48; lane = lane + 1)
        wdata[lane*32 +: 32] = seed ^ (lane * 32'h9e3779b9) ^ cycle;
      @(posedge clk); #1;
      if (actual_data !== expected_data)
        $fatal(1, "BIAS_MAPPING_MISMATCH cycle=%0d we=%b re=%b wa=%h ra=%h", cycle, we, re, waddr, raddr);
    end
    $display("BIAS_MAPPING_GATE_PASS cycles=512 bits=1536 reset_hold_read_first_write_bounds");
    $finish;
  end
  initial begin
    #20000;
    $fatal(1, "BIAS_MAPPING_TIMEOUT");
  end
endmodule
