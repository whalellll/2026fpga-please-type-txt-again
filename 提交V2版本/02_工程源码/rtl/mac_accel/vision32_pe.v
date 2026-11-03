`timescale 1ns/1ps
// P4 x OC8 x IC1. Exactly32 independent signed8 multipliers, II=1.
// Products have a register boundary; clear discards the preceding tile.
module vision32_pe(
 input wire clk,resetn,clear,valid,
 input wire [31:0] activations,
 input wire [63:0] weights,
 output wire [1023:0] accumulators
);
 reg product_valid;
 always @(posedge clk)begin
  if(!resetn || clear)product_valid<=0;
  else product_valid<=valid;
 end
 genvar p,o;
 generate for(p=0;p<4;p=p+1)begin:g_pixel
  for(o=0;o<8;o=o+1)begin:g_output
   reg signed [15:0] product;
   reg signed [31:0] accumulator;
   always @(posedge clk)begin
    if(valid)product<=$signed(activations[p*8+:8])*$signed(weights[o*8+:8]);
    if(!resetn || clear)accumulator<=0;
    else if(product_valid)accumulator<=accumulator+$signed({{16{product[15]}},product});
   end
   assign accumulators[(p*8+o)*32+:32]=accumulator;
  end
 end endgenerate
endmodule
