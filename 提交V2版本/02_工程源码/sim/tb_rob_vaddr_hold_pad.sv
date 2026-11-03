`timescale 1ns/1ps
module tb_rob_vaddr_hold_pad;
  reg [31:0] data_in=0;
  wire [31:0] padded;
  PangoRobVaddrPad dut(.dataIn(data_in),.dataOut(padded));
  reg clk=0;
  always #5 clk=~clk;
  reg write_en=0;
  reg [4:0] address=0;
  reg [31:0] original[0:31];
  reg [31:0] candidate[0:31];
  integer n,i;
  reg [31:0] random_state=32'h80808019;
  always @(posedge clk) if(write_en) begin
    original[address]<=data_in;
    candidate[address]<=padded;
  end
  initial begin
    for(n=0;n<65536;n=n+1) begin
      @(negedge clk);
      random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
      data_in=(n<32) ? (32'h1<<n) : ((n<64) ? ~(32'h1<<(n-32)) : random_state);
      address=n%32;write_en=1;
      #1;
      if(padded!==data_in) $fatal(1,"ROB pad changed data or added a cycle n=%0d",n);
      @(posedge clk);#1;
      if(original[address]!==candidate[address]) $fatal(1,"ROB pad changed write edge n=%0d",n);
    end
    for(i=0;i<32;i=i+1) if(original[i]!==candidate[i]) $fatal(1,"ROB RAM capacity/address mismatch");
    $display("ROB_VADDR_PAD_IDENTITY_WRITE_EDGE_AND_32_SLOTS_PASS");$finish;
  end
endmodule
