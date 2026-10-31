`timescale 1ns/1ps

// One exact 400-sample frame of the project's XQT1 extractor. All twenty
// Goertzel bins time-share a registered signed32 multiplier. Per-frame
// pre-emphasis and bin state are reset exactly as in xqvoice_features.c.
// RAM is not reset; no read is permitted until all400 samples are written.
module voice_feature_core(
 input wire clk,resetn,start,
 input wire sample_valid,
 output wire sample_ready,
 input wire signed [15:0] sample_data,
 input wire signed [31:0] feature_offset,feature_scale,
 output wire busy,
 output reg done,
 output reg [31:0] cycles,
 output wire feature_valid,
 input wire feature_ready,
 output wire [4:0] feature_index,
 output reg [7:0] feature_data
);
 localparam IDLE=0,FILL=1,BIN=2,READ=3,REC_SET=4,WAIT_MUL=5,REC_USE=6,
  SQ1=7,SQ1_USE=8,SQ2_USE=9,COEF_USE=10,CROSS_LOW=11,CROSS_HIGH=12,
  ENERGY=13,LOG=14,NORM=15,NORM_USE=16,OUTPUT=17;
 reg [4:0] state,after_mul,bin_index;
 reg [8:0] sample_index;
 reg signed [15:0] previous;
 reg signed [15:0] pcm[0:399];
 reg signed [15:0] pcm_q;
 reg signed [31:0] s1,s2,mul_a,mul_b,offset_q,scale_q;
 reg signed [63:0] mul_q,energy_q,coefficient_product,cross_low_q;
 reg [63:0] log_value,log_copy;
 reg [5:0] log_bit;
 reg signed [31:0] coefficient;
 wire signed [31:0] pre_product=$signed(previous)*32'sd31785;
 wire signed [31:0] emphasized=$signed(sample_data)-($signed(pre_product)>>>15);
 wire signed [31:0] recurrence=$signed(pcm_q)+($signed(mul_q)>>>14)-s2;
 wire signed [63:0] cross_product=cross_low_q+($signed(mul_q)<<<32);
 wire [63:0] normalized=log_value<<(6'd63-log_bit);
 wire signed [31:0] log_energy=$signed({18'b0,log_bit,8'b0})+
                                    $signed({24'b0,normalized[62:55]});
 wire signed [63:0] rounded=mul_q>=0 ? ($signed(mul_q)+64'sd16384)>>>15 :
                        -( (-$signed(mul_q)+64'sd16384)>>>15 );
 assign busy=state!=IDLE;
 assign sample_ready=state==FILL;
 assign feature_valid=state==OUTPUT;
 assign feature_index=bin_index;
 always @*begin
  case(bin_index)
   0:coefficient=32729;1:coefficient=32679;2:coefficient=32610;3:coefficient=32522;
   4:coefficient=32413;5:coefficient=32138;6:coefficient=31786;7:coefficient=31357;
   8:coefficient=30853;9:coefficient=30274;10:coefficient=28899;11:coefficient=27246;
   12:coefficient=25330;13:coefficient=23170;14:coefficient=18205;15:coefficient=12540;
   16:coefficient=6393;17:coefficient=0;18:coefficient=-12540;default:coefficient=-23170;
  endcase
 end
 always @(posedge clk)begin
  if(state==READ)pcm_q<=pcm[sample_index];
  if(resetn && state==FILL && sample_valid)pcm[sample_index]<=$signed(emphasized)>>>4;
  mul_q<=$signed(mul_a)*$signed(mul_b);
 end
 always @(posedge clk)begin
  if(!resetn)begin
   state<=IDLE;done<=0;cycles<=0;sample_index<=0;bin_index<=0;
   previous<=0;s1<=0;s2<=0;mul_a<=0;mul_b<=0;offset_q<=0;scale_q<=0;
   feature_data<=0;after_mul<=IDLE;energy_q<=0;coefficient_product<=0;
   cross_low_q<=0;log_value<=0;log_copy<=0;log_bit<=0;
  end else begin
   done<=0;
   if(busy)cycles<=cycles+1'b1;
   case(state)
    IDLE:if(start)begin
     state<=FILL;cycles<=0;previous<=0;sample_index<=0;bin_index<=0;
     offset_q<=feature_offset;scale_q<=feature_scale;
    end
    FILL:if(sample_valid)begin
     previous<=sample_data;
     if(sample_index==399)begin sample_index<=0;state<=BIN;end
     else sample_index<=sample_index+1'b1;
    end
    BIN:begin s1<=0;s2<=0;sample_index<=0;state<=READ;end
    READ:state<=REC_SET;
    REC_SET:begin mul_a<=coefficient;mul_b<=s1;after_mul<=REC_USE;state<=WAIT_MUL;end
    WAIT_MUL:state<=after_mul;
    REC_USE:begin
     s2<=s1;s1<=recurrence;
     if(sample_index==399)state<=SQ1;
     else begin sample_index<=sample_index+1'b1;state<=READ;end
    end
    SQ1:begin mul_a<=s1;mul_b<=s1;after_mul<=SQ1_USE;state<=WAIT_MUL;end
    SQ1_USE:begin energy_q<=mul_q;mul_a<=s2;mul_b<=s2;after_mul<=SQ2_USE;state<=WAIT_MUL;end
    SQ2_USE:begin energy_q<=energy_q+mul_q;mul_a<=coefficient;mul_b<=s1;after_mul<=COEF_USE;state<=WAIT_MUL;end
    COEF_USE:begin
     coefficient_product<=mul_q;mul_a<=mul_q[31:0];mul_b<=s2;
     after_mul<=CROSS_LOW;state<=WAIT_MUL;
    end
    CROSS_LOW:begin
     // Reconstruct the low64 bits of a signed64 x signed32 product using
     // two signed32 products. The low word needs an unsigned correction.
     cross_low_q<=mul_q+(coefficient_product[31]?($signed({{32{s2[31]}},s2})<<<32):64'sd0);
     mul_a<=coefficient_product[63:32];mul_b<=s2;
     after_mul<=CROSS_HIGH;state<=WAIT_MUL;
    end
    CROSS_HIGH:begin energy_q<=energy_q-($signed(cross_product)>>>14);state<=ENERGY;end
    ENERGY:begin
     log_value<=energy_q<1?64'd1:energy_q;
     log_copy<=energy_q<1?64'd1:energy_q;log_bit<=0;state<=LOG;
    end
    LOG:if(log_copy>1)begin log_copy<=log_copy>>1;log_bit<=log_bit+1'b1;end
        else state<=NORM;
    NORM:begin mul_a<=log_energy-offset_q;mul_b<=scale_q;after_mul<=NORM_USE;state<=WAIT_MUL;end
    NORM_USE:begin
     feature_data<=rounded>127?8'd127:rounded< -128?8'h80:rounded[7:0];state<=OUTPUT;
    end
    OUTPUT:if(feature_ready)begin
     if(bin_index==19)begin state<=IDLE;done<=1;end
     else begin bin_index<=bin_index+1'b1;state<=BIN;end
    end
    default:state<=IDLE;
   endcase
  end
 end
endmodule
