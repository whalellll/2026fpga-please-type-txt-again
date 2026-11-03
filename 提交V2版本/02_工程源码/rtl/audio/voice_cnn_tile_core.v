`timescale 1ns/1ps
// Programmable form of the small voice classifier's four signed8 products.
// One resident layer, compact signed8 inputs, exact unbiased signed32 outputs.
// No DDR master: cancel is local and cannot leave an accepted bus transaction.
module voice_cnn_tile_core(
 input wire clk,resetn,wr,input wire [7:0] addr,input wire [31:0] wdata,
 output reg [31:0] rdata,output wire [31:0] status
);
 localparam IDLE=0,READ=1,PRODUCT=2,DOT=3,Q_BIAS=4,Q_PRODUCT=5,Q_ROUND=6,Q_STORE=7;
 reg [2:0] state;
 reg quant_mode;
 reg [4:0] param_address;
 reg [31:0] param_valid;
 reg signed [31:0] param_bias[0:31];
 reg [31:0] param_mult[0:31];
 reg [5:0] param_shift[0:31];
 reg signed [31:0] bias_q,raw_q,clamp_lo,clamp_hi;
 reg [30:0] mult_q;
 reg [5:0] shift_q;
 reg signed [32:0] biased_q;
 reg signed [63:0] quant_product,quant_result;
 wire [63:0] quant_magnitude=quant_product[63] ? -quant_product : quant_product;
 wire [63:0] quant_rounded=(quant_magnitude+(64'd1<<(shift_q-1'b1)))>>shift_q;
 wire signed [63:0] quant_signed=quant_product[63] ? -$signed(quant_rounded) : $signed(quant_rounded);
 wire signed [31:0] quant_clamped=quant_result<$signed(clamp_lo) ? clamp_lo :
   quant_result>$signed(clamp_hi) ? clamp_hi : quant_result[31:0];
 reg done,error_q;
 reg [31:0] dimensions,pixels_config,cycles;
 reg [11:0] model_count;
 reg [10:0] input_count;
 reg [8:0] output_address;
 reg [9:0] output_count;
 reg [6:0] groups,group_index;
 reg [5:0] channels,row;
 reg [4:0] pixels,pixel;
 reg [11:0] weight_base;
 reg [10:0] input_base;
 reg [31:0] weights[0:2047],inputs[0:1023],outputs[0:511];
 reg [31:0] weight_q,input_q,output_q;
 reg signed [15:0] p0,p1,p2,p3;
 reg signed [31:0] accumulator;
 wire busy=state!=IDLE;
 assign status={29'b0,error_q,done,busy};
 wire control=wr && addr==8'h88;
 wire cancel=control && wdata[1];
 wire [31:0] configured_groups=dimensions[15:0]>>2;
 wire valid_config=dimensions[15:0]>=4 && dimensions[15:0]<=256 && dimensions[1:0]==0 &&
   dimensions[31:16]>=1 && dimensions[31:16]<=32 && pixels_config>=1 && pixels_config<=16;
 wire [31:0] required_model=configured_groups*{16'b0,dimensions[31:16]};
 wire [31:0] required_input=configured_groups*pixels_config;
 wire quant_config_ok=(param_valid & (32'hffffffff>>(32-dimensions[31:16])))==
   (32'hffffffff>>(32-dimensions[31:16])) &&
   ((clamp_lo==0 && clamp_hi==127) || (clamp_lo==-32768 && clamp_hi==32767));
 wire signed [17:0] dot_sum=$signed({{2{p0[15]}},p0})+$signed({{2{p1[15]}},p1})+
    $signed({{2{p2[15]}},p2})+$signed({{2{p3[15]}},p3});
 wire signed [31:0] total=accumulator+$signed(dot_sum);
 wire output_write=(state==DOT && group_index+1==groups && !quant_mode) || state==Q_STORE;
 wire [31:0] output_write_data=state==Q_STORE ? quant_clamped : total;
 always @(posedge clk)begin
  if(resetn && !busy && wr && addr==8'h94 && model_count<2048)weights[model_count[10:0]]<=wdata;
  if(resetn && !busy && wr && addr==8'h9c && input_count<1024)inputs[input_count[9:0]]<=wdata;
  if(state==READ)begin
   weight_q<=weights[weight_base+group_index];
   input_q<=inputs[input_base+group_index];
  end
  // One physical RAM write port, shared by the raw and epilogue modes.
  if(output_write)outputs[output_count[8:0]]<=output_write_data;
  if(resetn && !busy && wr)case(addr)
   8'hc4:param_bias[param_address]<=wdata;
   8'hc8:param_mult[param_address]<=wdata;
   8'hcc:param_shift[param_address]<=wdata[5:0];
   default:begin end
  endcase
  output_q<=outputs[output_address];
 end
 always @*begin
  rdata=0;
  case(addr)
   8'h80:rdata=32'h56434e31;
   8'h84:rdata=32'h00010000;
   8'h8c:rdata={29'b0,error_q,done,busy};
   8'ha0:rdata=dimensions;
   8'ha4:rdata=pixels_config;
   8'ha8:rdata=cycles;
   8'hac:rdata={23'b0,output_address};
   8'hb0:rdata=done && !error_q && {1'b0,output_address}<output_count ? output_q:0;
   8'hb4:rdata={20'b0,model_count};
   8'hb8:rdata={21'b0,input_count};
   8'hbc:rdata={31'b0,quant_mode};
   8'hdc:rdata=1;
   8'he0:rdata=param_valid;
   default:begin end
  endcase
 end
 always @(posedge clk)begin
  if(!resetn)begin
   state<=IDLE;done<=0;error_q<=0;dimensions<=0;pixels_config<=0;cycles<=0;
   model_count<=0;input_count<=0;output_address<=0;output_count<=0;
   groups<=0;group_index<=0;channels<=0;row<=0;pixels<=0;pixel<=0;
   weight_base<=0;input_base<=0;accumulator<=0;p0<=0;p1<=0;p2<=0;p3<=0;
   quant_mode<=0;param_address<=0;param_valid<=0;clamp_lo<=0;clamp_hi<=127;
   bias_q<=0;raw_q<=0;mult_q<=0;shift_q<=1;biased_q<=0;quant_product<=0;quant_result<=0;
  end else if(cancel)begin
   state<=IDLE;done<=0;error_q<=0;input_count<=0;output_count<=0;
   if(wdata[2])begin model_count<=0;param_valid<=0;quant_mode<=0;end
  end else begin
   if(busy)cycles<=cycles+1'b1;
   if(!busy && wr)case(addr)
    8'h94:if(model_count<2048)model_count<=model_count+1'b1;
    8'h9c:if(input_count<1024)input_count<=input_count+1'b1;
    8'ha0:dimensions<=wdata;
    8'ha4:pixels_config<=wdata;
    8'hac:output_address<=wdata[8:0];
    8'hbc:quant_mode<=wdata[0];
    8'hc0:param_address<=wdata[4:0];
    8'hc4:param_valid[param_address]<=0;
    8'hc8:param_valid[param_address]<=0;
    8'hcc:param_valid[param_address]<=wdata>=1 && wdata<=60 &&
       param_mult[param_address]>=1 && param_mult[param_address]<=31'd1073741824;
    8'hd0:clamp_lo<=$signed(wdata);
    8'hd4:clamp_hi<=$signed(wdata);
    8'h88:if(wdata[0])begin
     done<=0;error_q<=0;cycles<=0;
     if(!valid_config || model_count<required_model || input_count<required_input ||
        (quant_mode && !quant_config_ok))begin done<=1;error_q<=1;end
     else begin
      groups<=configured_groups[6:0];channels<=dimensions[21:16];pixels<=pixels_config[4:0];
      row<=0;pixel<=0;group_index<=0;weight_base<=0;input_base<=0;output_count<=0;accumulator<=0;state<=READ;
     end
    end
    default:begin end
   endcase
   case(state)
    READ:state<=PRODUCT;
    PRODUCT:begin
     p0<=$signed(input_q[7:0])*$signed(weight_q[7:0]);
     p1<=$signed(input_q[15:8])*$signed(weight_q[15:8]);
     p2<=$signed(input_q[23:16])*$signed(weight_q[23:16]);
     p3<=$signed(input_q[31:24])*$signed(weight_q[31:24]);state<=DOT;
    end
    DOT:begin
     if(group_index+1==groups)begin
      bias_q<=param_bias[row];mult_q<=param_mult[row];shift_q<=param_shift[row];
      if(quant_mode)begin raw_q<=total;state<=Q_BIAS;end
      else begin
      output_count<=output_count+1'b1;group_index<=0;accumulator<=0;
      if(row+1==channels)begin
       row<=0;weight_base<=0;input_base<=input_base+groups;
       if(pixel+1==pixels)begin state<=IDLE;done<=1;end
       else begin pixel<=pixel+1'b1;state<=READ;end
      end else begin row<=row+1'b1;weight_base<=weight_base+groups;state<=READ;end
      end
     end else begin accumulator<=total;group_index<=group_index+1'b1;state<=READ;end
    end
    Q_BIAS:begin biased_q<=$signed({raw_q[31],raw_q})+$signed({bias_q[31],bias_q});state<=Q_PRODUCT;end
    Q_PRODUCT:begin quant_product<=biased_q*$signed({1'b0,mult_q});state<=Q_ROUND;end
    Q_ROUND:begin quant_result<=quant_signed;state<=Q_STORE;end
    Q_STORE:begin
     output_count<=output_count+1'b1;group_index<=0;accumulator<=0;
     if(row+1==channels)begin
      row<=0;weight_base<=0;input_base<=input_base+groups;
      if(pixel+1==pixels)begin state<=IDLE;done<=1;end
      else begin pixel<=pixel+1'b1;state<=READ;end
     end else begin row<=row+1'b1;weight_base<=weight_base+groups;state<=READ;end
    end
    default:begin end
   endcase
  end
 end
endmodule
