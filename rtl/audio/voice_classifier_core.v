`timescale 1ns/1ps

// Fixed SD77 XQT1 40->64->32->25 classifier. A validated full6020-byte
// model image is loaded once. Four signed8 products share each vector word.
// The input/model ports are accepted only while idle; results hold under stall.
module voice_classifier_core(
 input wire clk,resetn,start,
 input wire model_we,input wire [10:0] model_addr,input wire [31:0] model_data,
 input wire input_we,input wire [3:0] input_addr,input wire [31:0] input_data,
 input wire [4:0] shift1,shift2,shift3,
 output wire busy,output reg done,output reg [31:0] cycles,
 output wire result_valid,input wire result_ready,
 output wire [1:0] result_layer,output wire [6:0] result_index,
 output reg [7:0] result_data,output reg [7:0] token,output reg [9:0] confidence
);
 localparam IDLE=0,BIAS_READ=1,BIAS_USE=2,READ=3,PRODUCT=4,DOT=5,QUANT=6,OUTPUT=7,FINAL=8,DIVIDE=9;
 reg [3:0] state;
 reg [1:0] layer;
 reg [6:0] row;
 reg [4:0] group_index;
 reg [10:0] row_weight;
 reg [31:0] model_mem[0:2047],vector_mem[0:47];
 reg [31:0] model_q,vector_q,packed_result;
 reg signed [15:0] p0,p1,p2,p3;
 reg signed [47:0] accumulator;
 reg [4:0] shift_q[0:2];
 reg signed [9:0] best,second;
 reg [7:0] best_token;
 wire [4:0] groups=layer==0?5'd10:layer==1?5'd16:5'd8;
 wire [6:0] rows=layer==0?7'd64:layer==1?7'd32:7'd25;
 wire [10:0] bias_base=layer==0?11'd672:layer==1?11'd1248:11'd1480;
 wire [5:0] vector_base=layer==0?6'd0:layer==1?6'd16:6'd32;
 wire [5:0] destination_base=layer==0?6'd16:6'd32;
 wire [10:0] read_address=state==BIAS_READ?bias_base+row:row_weight+group_index;
 wire signed [17:0] dot_sum=$signed({{2{p0[15]}},p0})+$signed({{2{p1[15]}},p1})+
                          $signed({{2{p2[15]}},p2})+$signed({{2{p3[15]}},p3});
 wire signed [47:0] shifted=$signed(accumulator)>>>shift_q[layer];
 wire [7:0] quantized=(layer!=2 && shifted<0)?8'd0:
                      shifted>127?8'd127:shifted< -128?8'h80:shifted[7:0];
 wire signed [9:0] value=$signed({{2{result_data[7]}},result_data});
 wire [7:0] margin=best-second;
 reg [17:0] dividend,quotient;
 reg [7:0] remainder_q;
 reg [4:0] divide_bit;
 wire [8:0] trial={remainder_q,dividend[17]};
 wire [17:0] quotient_next={quotient[16:0],trial>=255};
 wire [17:0] margin_wide={10'b0,margin};
 wire host_vector_write=!busy && input_we && input_addr<10;
 wire result_vector_write=state==OUTPUT && result_ready && layer!=2 && row[1:0]==3;
 wire [5:0] vector_write_address=host_vector_write?{2'b0,input_addr}:destination_base+row[6:2];
 wire [31:0] vector_write_data=host_vector_write?input_data:{result_data,packed_result[23:0]};
 assign busy=state!=IDLE;
 assign result_valid=state==OUTPUT;
 assign result_layer=layer;
 assign result_index=row;
 always @(posedge clk)begin
  if(resetn && !busy && model_we)model_mem[model_addr]<=model_data;
  model_q<=model_mem[read_address];
  if(resetn && (host_vector_write || result_vector_write))vector_mem[vector_write_address]<=vector_write_data;
  if(state==READ)vector_q<=vector_mem[vector_base+group_index];
 end
 always @(posedge clk)begin
  if(!resetn)begin
   state<=IDLE;layer<=0;row<=0;group_index<=0;row_weight<=32;
   accumulator<=0;packed_result<=0;result_data<=0;done<=0;cycles<=0;
   token<=0;confidence<=0;best<=-129;second<=-129;best_token<=0;
   dividend<=0;quotient<=0;remainder_q<=0;divide_bit<=0;
   p0<=0;p1<=0;p2<=0;p3<=0;shift_q[0]<=0;shift_q[1]<=0;shift_q[2]<=0;
  end else begin
   done<=0;if(busy)cycles<=cycles+1'b1;
   case(state)
    IDLE:if(start)begin
     layer<=0;row<=0;group_index<=0;row_weight<=32;cycles<=0;
     shift_q[0]<=shift1;shift_q[1]<=shift2;shift_q[2]<=shift3;
     best<=-129;second<=-129;best_token<=0;state<=BIAS_READ;
    end
    BIAS_READ:state<=BIAS_USE;
    BIAS_USE:begin accumulator<={{16{model_q[31]}},model_q};group_index<=0;state<=READ;end
    READ:state<=PRODUCT;
    PRODUCT:begin
     p0<=$signed(vector_q[7:0])*$signed(model_q[7:0]);
     p1<=$signed(vector_q[15:8])*$signed(model_q[15:8]);
     p2<=$signed(vector_q[23:16])*$signed(model_q[23:16]);
     p3<=$signed(vector_q[31:24])*$signed(model_q[31:24]);state<=DOT;
    end
    DOT:begin
     accumulator<=accumulator+$signed(dot_sum);
     if(group_index+1'b1>=groups)state<=QUANT;
     else begin group_index<=group_index+1'b1;state<=READ;end
    end
    QUANT:begin result_data<=quantized;state<=OUTPUT;end
    OUTPUT:if(result_ready)begin
     packed_result[row[1:0]*8+:8]<=result_data;
     if(layer==2)begin
      if(value>best)begin second<=best;best<=value;best_token<={1'b0,row};end
      else if(value>second)second<=value;
     end
     if(row+1'b1>=rows)begin
      row<=0;group_index<=0;
      if(layer==2)state<=FINAL;
      else begin layer<=layer+1'b1;row_weight<=layer==0?11'd736:11'd1280;state<=BIAS_READ;end
     end else begin row<=row+1'b1;row_weight<=row_weight+groups;state<=BIAS_READ;end
    end
    FINAL:begin
     token<=best_token;
     dividend<=(margin_wide<<10)-(margin_wide<<4)-(margin_wide<<3);
     quotient<=0;remainder_q<=0;divide_bit<=17;state<=DIVIDE;
    end
    DIVIDE:begin
     remainder_q<=trial>=255?trial-9'd255:trial;
     quotient<=quotient_next;dividend<=dividend<<1;
     if(divide_bit==0)begin confidence<=quotient_next[9:0];done<=1;state<=IDLE;end
     else divide_bit<=divide_bit-1'b1;
    end
    default:state<=IDLE;
   endcase
  end
 end
endmodule
