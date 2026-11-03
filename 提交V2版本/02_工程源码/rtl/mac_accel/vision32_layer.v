`timescale 1ns/1ps
// Whole-layer NHWC4 -> compact NHWC, with DDR K-major/OC8 weights.
// MMIO occupies the former conv64-byte window, with a distinct V321 ID.
// Cancellation/timeout never resets the shared AXI adapter: accepted traffic
// drains before busy drops. An indefinitely stalled slave stays quarantined.
module vision32_layer #(
 parameter [31:0] DDR_BASE=32'h1b000000,
 parameter integer DDR_BYTES=1048576,
 parameter integer SERIAL_LEGACY_QUANT=1
)(
 input wire clk,resetn,
 input wire reg_wr_en,input wire [7:0] reg_wr_addr,
 input wire [31:0] reg_wr_data,input wire [3:0] reg_wr_strb,
 input wire [7:0] reg_rd_addr,output reg [31:0] reg_rd_data,
 output wire mem_req_valid,input wire mem_req_ready,
 output wire mem_req_write,output wire [31:0] mem_req_addr,output wire [2:0] mem_req_len,
 output wire mem_w_valid,input wire mem_w_ready,
 output reg [31:0] mem_w_data,output reg [3:0] mem_w_strb,output wire mem_w_last,
 input wire mem_rsp_valid,output wire mem_rsp_ready,
 input wire [31:0] mem_rsp_rdata,input wire mem_rsp_last,mem_rsp_error,
 output wire mem_abort,
 output wire busy_out
);
 localparam IDLE=0,VALIDATE=1,SIZES1=2,SIZES2=3,GUARD=4,LUT_PREP=5,
  PARAM_PREP=6,WEIGHT_PREP=7,R_REQ=8,R_WAIT=9,TILE_PREP=10,PIXEL_PREP=11,
  FILL_SCAN=12,FILL_SCALAR=13,FILL_ZERO=14,FILL_ADV=15,FEED=16,DRAIN=17,
  Q_BEGIN=18,Q_ADD=19,Q_MUL=20,Q_SHIFT=21,Q_LOOKUP=22,Q_LUT_USE=23,Q_STORE=24,
  O_PREP=25,W_REQ=26,W_DATA=27,W_RESP=28,NEXT_PIXEL=29,FINISH=30,
  E_CHECK=31,E_ROUND=32,E_LOOKUP=33,E_STORE=34,Q_MUL_STEP=35;
 localparam RK_LUT=0,RK_PARAM=1,RK_WEIGHT=2,RK_INPUT=3,RK_SCALAR=4,RK_EXACT=5;
 reg [5:0] state,return_state;
 reg [2:0] read_kind;
 reg done,error,stop_pending;
 reg [7:0] error_code;
 reg [31:0] cycles,read_bytes,write_bytes,mac_cycles;
 reg [31:0] c_input,c_weight,c_output,c_param,c_lut,c_width,c_height,c_ci,c_co;
 reg [31:0] c_kernel,c_stride,c_padding,c_flags,c_timeout,c_model,c_frame;
 reg [4:0] cfg_index;
 reg [9:0] width_r,height_r,ow_r,oh_r;
 reg [8:0] cout_r;
 reg [9:0] cin_r,cin_stride_r;
 reg [2:0] kernel_r,padding_r;
 reg [1:0] stride_r;
 reg [10:0] depth_r;
 reg [5:0] groups_r;
 reg [18:0] input_pixels,output_pixels;
 reg [31:0] input_bytes,weight_bytes,output_bytes,param_bytes;
 wire busy=state!=IDLE;
 assign busy_out=busy;
 wire full_write=reg_wr_en && reg_wr_strb==4'hf;
 wire control_write=reg_wr_en && reg_wr_addr[5:0]==6'h08 && reg_wr_strb[0];
 wire [11:0] width_span={2'b0,width_r}+{8'b0,padding_r,1'b0}-{9'b0,kernel_r};
 wire [11:0] height_span={2'b0,height_r}+{8'b0,padding_r,1'b0}-{9'b0,kernel_r};
 wire [32:0] ddr_end={1'b0,DDR_BASE}+DDR_BYTES;
 wire [32:0] in_end={1'b0,c_input}+input_bytes;
 wire [32:0] wt_end={1'b0,c_weight}+weight_bytes;
 wire [32:0] out_end={1'b0,c_output}+output_bytes;
 wire [32:0] par_end={1'b0,c_param}+param_bytes;
 wire exact_mode=c_flags[2];
 wire [32:0] lut_end={1'b0,c_lut}+(exact_mode?33'd65536:33'd256);
 wire geometry_ok=c_width!=0 && c_width<=640 && c_height!=0 && c_height<=640 &&
  c_ci!=0 && c_ci<=512 && c_co!=0 && c_co<=256 &&
  (c_kernel==1 || c_kernel==3 || c_kernel==6) && (c_stride==1 || c_stride==2) &&
  c_padding<c_kernel && c_width+2*c_padding>=c_kernel && c_height+2*c_padding>=c_kernel &&
  (c_flags<=2 || c_flags==4 || c_flags==5) && c_timeout>=16;
 wire range_ok=c_input[1:0]==0 && c_weight[1:0]==0 && c_output[1:0]==0 &&
  c_param[1:0]==0 && c_lut[1:0]==0 && c_input>=DDR_BASE && c_weight>=DDR_BASE &&
  c_output>=DDR_BASE && c_param>=DDR_BASE && in_end<=ddr_end && wt_end<=ddr_end &&
  out_end<=ddr_end && par_end<=ddr_end &&
  (!c_flags[0] || (c_lut>=DDR_BASE && lut_end<=ddr_end)) &&
  ({1'b0,c_output}>=in_end || out_end<={1'b0,c_input}) &&
  ({1'b0,c_output}>=wt_end || out_end<={1'b0,c_weight}) &&
  ({1'b0,c_output}>=par_end || out_end<={1'b0,c_param}) &&
  (!c_flags[0] || ({1'b0,c_output}>=lut_end || out_end<={1'b0,c_lut}));

 // No reset of RAM contents; descriptor/order ensures initialization first.
 // Split the1152 rows into power-of-two memories. A single1152-row array
 // maps to2048 rows of LUTRAM; this preserves all weights with no read bubble.
 reg [31:0] weight_lo[0:1023] /* synthesis syn_ramstyle="block_ram" */;
 reg [31:0] weight_hi[0:1023] /* synthesis syn_ramstyle="block_ram" */;
 reg [31:0] weight_tail_lo[0:127] /* synthesis syn_ramstyle="block_ram" */;
 reg [31:0] weight_tail_hi[0:127] /* synthesis syn_ramstyle="block_ram" */;
 reg [31:0] input0[0:63] /* synthesis syn_ramstyle="lut_ram" */;
 reg [31:0] input1[0:63] /* synthesis syn_ramstyle="lut_ram" */;
 reg [31:0] input2[0:63] /* synthesis syn_ramstyle="lut_ram" */;
 reg [31:0] input3[0:63] /* synthesis syn_ramstyle="lut_ram" */;
 reg [31:0] lut_mem[0:63] /* synthesis syn_ramstyle="lut_ram" */;
 reg signed [31:0] biases[0:7];
 reg [30:0] scales[0:7];
 reg [5:0] shifts[0:7];
 reg [31:0] load_addr,weight_ptr,param_ptr;
 reg [11:0] load_remaining,load_index;
 reg [1:0] param_phase;
 reg [2:0] param_channel;
 // The SoC DDR bridge packs each AXI transaction into one native32-byte line.
 // Split at that boundary even when a tensor/parameter group is only4-aligned.
 wire [3:0] read_line_words=4'd8-{1'b0,load_addr[4:2]};
 wire [3:0] read_burst_words=load_remaining<read_line_words ?
  load_remaining[3:0] : read_line_words;
 reg [8:0] oc_base;
 reg [18:0] pixel_base;
 reg [9:0] walk_x,walk_y,pixel_x[0:3],pixel_y[0:3];
 reg [2:0] prepare_pixel;
 reg [3:0] pixel_valid;
 reg [10:0] k_base;
 reg [7:0] chunk_length,fill_offset;
 reg buffer_bank;
 reg [1:0] fill_pixel;
 reg [9:0] fill_ci,chunk_ci,next_ci;
 reg [2:0] fill_kx,fill_ky,chunk_kx,chunk_ky,next_kx,next_ky;
 reg [31:0] input_pack,cache_word,cache_tag;
 reg cache_valid;
 wire signed [12:0] gather_x=(stride_r==2 ? $signed({2'b0,pixel_x[fill_pixel],1'b0}) :
  $signed({3'b0,pixel_x[fill_pixel]}))+$signed({10'b0,fill_kx})-$signed({10'b0,padding_r});
 wire signed [12:0] gather_y=(stride_r==2 ? $signed({2'b0,pixel_y[fill_pixel],1'b0}) :
  $signed({3'b0,pixel_y[fill_pixel]}))+$signed({10'b0,fill_ky})-$signed({10'b0,padding_r});
 wire gather_zero=!pixel_valid[fill_pixel] || gather_x<0 || gather_y<0 ||
  gather_x>=$signed({3'b0,width_r}) || gather_y>=$signed({3'b0,height_r});
 wire [18:0] gather_pixel=gather_y[9:0]*width_r+gather_x[9:0];
 wire [31:0] gather_addr=c_input+gather_pixel*cin_stride_r+fill_ci;
 wire [31:0] gather_aligned={gather_addr[31:2],2'b0};
 wire [9:0] ci_left=cin_r-fill_ci;
 wire [7:0] chunk_left=chunk_length-fill_offset;
 wire fast_word=fill_ci[1:0]==0 && fill_offset[1:0]==0 && ci_left>=4 && chunk_left>=4;
 wire [3:0] input_burst_words=ci_left>=32 && chunk_left>=32 ? 4'd8 :
  ci_left<chunk_left ? {1'b0,ci_left[4:2]} : {1'b0,chunk_left[4:2]};
 wire [7:0] scalar_value=gather_zero ? 8'd0 : (cache_word>>{gather_addr[1:0],3'b0});
 wire [31:0] scalar_pack=(input_pack & ~(32'hff<<{fill_offset[1:0],3'b0})) |
  ({24'b0,scalar_value}<<{fill_offset[1:0],3'b0});
 wire input_rsp_write=state==R_WAIT && read_kind==RK_INPUT && mem_rsp_valid && !stop_pending && !mem_rsp_error;
 wire input_scalar_write=state==FILL_SCALAR && (fill_offset[1:0]==3 || fill_offset+1==chunk_length);
 wire input_zero_write=state==FILL_ZERO;
 wire input_we=input_rsp_write || input_scalar_write || input_zero_write;
 wire [5:0] input_wa={buffer_bank,fill_offset[6:2]};
 wire [31:0] input_wd=input_rsp_write ? mem_rsp_rdata : input_zero_write ? 32'd0 : scalar_pack;
 reg [7:0] feed_index;
 reg [2:0] drain_count;
 wire [63:0] weight_q;
 reg [31:0] weight_main_lo_q,weight_main_hi_q,weight_tail_lo_q,weight_tail_hi_q;
 reg weight_tail_selected_q;
 assign weight_q=weight_tail_selected_q ? {weight_tail_hi_q,weight_tail_lo_q} :
   {weight_main_hi_q,weight_main_lo_q};
 reg [31:0] activations_q;
 reg read_valid;
 wire [10:0] weight_ra=k_base+feed_index;
 wire [15:0] full_depth=cin_r*kernel_r*kernel_r;
 wire [5:0] input_ra={buffer_bank,feed_index[6:2]};
 wire [31:0] input_r0=input0[input_ra]>>{feed_index[1:0],3'b0};
 wire [31:0] input_r1=input1[input_ra]>>{feed_index[1:0],3'b0};
 wire [31:0] input_r2=input2[input_ra]>>{feed_index[1:0],3'b0};
 wire [31:0] input_r3=input3[input_ra]>>{feed_index[1:0],3'b0};
 wire [1023:0] accumulators;
 wire pe_clear=state==TILE_PREP;
 vision32_pe u_pe(.clk(clk),.resetn(resetn),.clear(pe_clear),.valid(read_valid),
  .activations(activations_q),.weights(weight_q),.accumulators(accumulators));
 always @(posedge clk)begin
  if(state==R_WAIT && mem_rsp_valid && !stop_pending && !mem_rsp_error)begin
   if(read_kind==RK_WEIGHT)begin
    if(!load_index[11])begin
     if(load_index[0])weight_hi[load_index[10:1]]<=mem_rsp_rdata;
     else weight_lo[load_index[10:1]]<=mem_rsp_rdata;
    end else if(load_index[11:8]==4'h8)begin
     if(load_index[0])weight_tail_hi[load_index[7:1]]<=mem_rsp_rdata;
     else weight_tail_lo[load_index[7:1]]<=mem_rsp_rdata;
    end
   end
   if(read_kind==RK_LUT)lut_mem[load_index[5:0]]<=mem_rsp_rdata;
  end
  if(input_we)begin
   case(fill_pixel)
    0:input0[input_wa]<=input_wd;1:input1[input_wa]<=input_wd;
    2:input2[input_wa]<=input_wd;3:input3[input_wa]<=input_wd;
   endcase
  end
  if(state==FEED)begin
   weight_main_lo_q<=weight_lo[weight_ra[9:0]];
   weight_main_hi_q<=weight_hi[weight_ra[9:0]];
   weight_tail_lo_q<=weight_tail_lo[weight_ra[6:0]];
   weight_tail_hi_q<=weight_tail_hi[weight_ra[6:0]];
   weight_tail_selected_q<=weight_ra[10];
   activations_q<={input_r3[7:0],input_r2[7:0],input_r1[7:0],input_r0[7:0]};
  end
  if(!resetn)read_valid<=0;else read_valid<=state==FEED;
 end

 reg [1:0] q_pixel;
 reg [2:0] q_channel;
 reg signed [31:0] selected_acc;
 integer select_index;
 always @*begin
  selected_acc=0;
  for(select_index=0;select_index<32;select_index=select_index+1)
   if({q_pixel,q_channel}==select_index)selected_acc=accumulators[select_index*32+:32];
 end
 reg signed [32:0] biased;
 reg signed [63:0] product;
 reg [4:0] legacy_mul_bit;
 // Legal scales are nonnegative31-bit. A signed33-bit bias times that scale
 // fits64 bits. Shift the combined accumulator right instead of using a wide
 // dedicated multiplier. Modes2/4/5 bypass this legacy-only sequence.
 wire signed [33:0] legacy_mul_sum=
  $signed({product[63],product[63:31]})+
  (scales[q_channel][legacy_mul_bit] ? $signed({biased[32],biased}) : 34'sd0);
 reg [5:0] quant_shift;
 reg [7:0] quant_byte,result_byte;
 reg [31:0] lut_q;
 wire signed [63:0] round_unit=64'sd1<<(quant_shift-1'b1);
 wire signed [63:0] rounded=quant_shift==0 ? product : product>=0 ?
  (product+round_unit)>>>quant_shift : -((-product+round_unit)>>>quant_shift);
 // Picture_new's independent numerical contract: reject I32 bias overflow,
 // ties-to-even shift, S16 saturation, optional signed-byte LUT[pre+32768].
 // Reuse the bus and keep only the most recently read four table entries.
 reg [31:0] exact_magnitude,exact_lut_word,exact_lut_tag;
 reg exact_negative,exact_lut_valid;
 reg [15:0] exact_pre;
 wire [31:0] exact_quotient=exact_magnitude>>quant_shift;
 wire [31:0] exact_remainder=exact_magnitude & ((32'd1<<quant_shift)-1'b1);
 wire [31:0] exact_half=32'd1<<(quant_shift-1'b1);
 wire exact_increment=quant_shift!=0 && (exact_remainder>exact_half ||
  (exact_remainder==exact_half && exact_quotient[0]));
 // For any I32 magnitude, shift>=32 rounds to zero, including INT_MIN/2^32.
 wire [31:0] exact_rounded=quant_shift>=32 ? 32'd0 : exact_quotient+exact_increment;
 wire [15:0] exact_saturated=exact_negative ?
  (exact_rounded>=32768 ? 16'h8000 : -exact_rounded[15:0]) :
  (exact_rounded>32767 ? 16'h7fff : exact_rounded[15:0]);
 wire [15:0] exact_index=exact_pre^16'h8000;
 wire [31:0] exact_address=c_lut+{16'b0,exact_index};
 wire [7:0] exact_lut_byte=exact_lut_word>>{exact_index[1:0],3'b0};
 reg [255:0] output_pack;
 reg [287:0] write_packet;
 reg [31:0] write_addr;
 reg [5:0] write_count;
 reg [1:0] write_offset;
 reg [3:0] write_remaining,write_index,write_burst_left;
 wire [3:0] write_line_words=4'd8-{1'b0,write_addr[4:2]};
 wire [3:0] write_burst_words=write_remaining<write_line_words ?
  write_remaining : write_line_words;
 wire [3:0] channels_here=cout_r-oc_base>=8 ? 4'd8 : {1'b0,cout_r[2:0]};
 wire [31:0] output_element=(pixel_base+q_pixel)*cout_r+oc_base;
 wire [31:0] output_addr=c_output+(c_flags[1] ? output_element<<2 : exact_mode ? output_element<<1 : output_element);
 wire [5:0] output_count=c_flags[1] ? {channels_here,2'b0} : exact_mode ? {1'b0,channels_here,1'b0} : {2'b0,channels_here};
 assign mem_req_valid=state==R_REQ || state==W_REQ;
 assign mem_req_write=state==W_REQ;
 assign mem_req_addr=state==W_REQ ? write_addr : load_addr;
 assign mem_req_len=state==W_REQ ? write_burst_words-1'b1 : read_burst_words-1'b1;
 assign mem_w_valid=state==W_DATA;
 assign mem_w_last=write_burst_left==1;
 assign mem_rsp_ready=state==R_WAIT || state==W_RESP;
 assign mem_abort=0;
 integer byte_lane;
 always @*begin
  mem_w_data=0;
  case(write_index)
   0:mem_w_data=write_packet[31:0];1:mem_w_data=write_packet[63:32];
   2:mem_w_data=write_packet[95:64];3:mem_w_data=write_packet[127:96];
   4:mem_w_data=write_packet[159:128];5:mem_w_data=write_packet[191:160];
   6:mem_w_data=write_packet[223:192];7:mem_w_data=write_packet[255:224];
   8:mem_w_data=write_packet[287:256];default:mem_w_data=0;
  endcase
  for(byte_lane=0;byte_lane<4;byte_lane=byte_lane+1)
   mem_w_strb[byte_lane]=(write_index*4+byte_lane>=write_offset) &&
    (write_index*4+byte_lane<write_offset+write_count);
 end
 always @*begin
  case(reg_rd_addr[5:0])
   6'h00:reg_rd_data=32'h56333231;
   6'h04:reg_rd_data={24'b0,3'b0,stop_pending,1'b0,error,done,busy};
   6'h0c:reg_rd_data={27'b0,cfg_index};
   6'h10:case(cfg_index)
    0:reg_rd_data=c_input;1:reg_rd_data=c_weight;2:reg_rd_data=c_output;3:reg_rd_data=c_param;
    4:reg_rd_data=c_lut;5:reg_rd_data=c_width;6:reg_rd_data=c_height;7:reg_rd_data=c_ci;
    8:reg_rd_data=c_co;9:reg_rd_data=c_kernel;10:reg_rd_data=c_stride;11:reg_rd_data=c_padding;
    12:reg_rd_data=c_flags;13:reg_rd_data=c_timeout;14:reg_rd_data=c_model;15:reg_rd_data=c_frame;
    default:reg_rd_data=0;
   endcase
   6'h14:reg_rd_data=cycles;6'h18:reg_rd_data=read_bytes;6'h1c:reg_rd_data=write_bytes;
   6'h20:reg_rd_data=mac_cycles;6'h24:reg_rd_data={24'b0,error_code};
   6'h28:reg_rd_data={26'b0,state};6'h2c:reg_rd_data=32'h00010001;
   6'h30:reg_rd_data=c_frame;6'h34:reg_rd_data=c_model;
   6'h38:reg_rd_data=32'h00040801;6'h3c:reg_rd_data={21'b0,depth_r};
   default:reg_rd_data=0;
  endcase
 end
 always @(posedge clk)begin
  if(!resetn)begin
   state<=IDLE;done<=0;error<=0;stop_pending<=0;error_code<=0;
   cycles<=0;read_bytes<=0;write_bytes<=0;mac_cycles<=0;cfg_index<=0;
   c_input<=0;c_weight<=0;c_output<=0;c_param<=0;c_lut<=0;c_width<=0;c_height<=0;
   c_ci<=0;c_co<=0;c_kernel<=1;c_stride<=1;c_padding<=0;c_flags<=0;c_timeout<=495000000;c_model<=0;c_frame<=0;
   cache_valid<=0;buffer_bank<=0;read_kind<=0;return_state<=IDLE;
   exact_lut_valid<=0;
   load_addr<=0;load_remaining<=0;load_index<=0;write_addr<=0;write_index<=0;
   write_remaining<=0;write_burst_left<=0;write_count<=0;write_offset<=0;write_packet<=0;
   fill_offset<=0;fill_pixel<=0;feed_index<=0;input_pack<=0;
  end else begin
   if(busy)begin
    cycles<=cycles+1'b1;
    if(cycles>=c_timeout && !stop_pending)begin stop_pending<=1;error_code<=8'd5;end
   end
   if(read_valid)mac_cycles<=mac_cycles+1'b1;
   if(state==R_WAIT && mem_rsp_valid)read_bytes<=read_bytes+4;
   if(mem_w_valid && mem_w_ready)write_bytes<=write_bytes+4;
   if(!busy && full_write)begin
    if(reg_wr_addr[5:0]==6'h0c)cfg_index<=reg_wr_data[4:0];
    if(reg_wr_addr[5:0]==6'h10)case(cfg_index)
     0:c_input<=reg_wr_data;1:c_weight<=reg_wr_data;2:c_output<=reg_wr_data;3:c_param<=reg_wr_data;
     4:c_lut<=reg_wr_data;5:c_width<=reg_wr_data;6:c_height<=reg_wr_data;7:c_ci<=reg_wr_data;
     8:c_co<=reg_wr_data;9:c_kernel<=reg_wr_data;10:c_stride<=reg_wr_data;11:c_padding<=reg_wr_data;
     12:c_flags<=reg_wr_data;13:c_timeout<=reg_wr_data;14:c_model<=reg_wr_data;15:c_frame<=reg_wr_data;
     default:begin end
    endcase
   end
   if(control_write && !busy && reg_wr_data[2])begin done<=0;error<=0;stop_pending<=0;error_code<=0;end
   if(control_write && busy && reg_wr_data[1] && !stop_pending)begin stop_pending<=1;error_code<=8'd4;end
   case(state)
    IDLE:if(control_write && reg_wr_data[0])begin
     state<=VALIDATE;done<=0;error<=0;stop_pending<=0;error_code<=0;cycles<=0;
     read_bytes<=0;write_bytes<=0;mac_cycles<=0;cache_valid<=0;buffer_bank<=0;exact_lut_valid<=0;
    end
    VALIDATE:if(!geometry_ok)begin stop_pending<=1;error_code<=1;state<=FINISH;end
     else begin width_r<=c_width[9:0];height_r<=c_height[9:0];cin_r<=c_ci[9:0];cout_r<=c_co[8:0];
      cin_stride_r<=(c_ci[9:0]+3)&10'h3fc;kernel_r<=c_kernel[2:0];stride_r<=c_stride[1:0];
      padding_r<=c_padding[2:0];state<=SIZES1;end
    SIZES1:if(full_depth>1152)begin stop_pending<=1;error_code<=2;state<=FINISH;end
    else begin
     depth_r<=full_depth[10:0];groups_r<=(cout_r+7)>>3;
     input_pixels<=width_r*height_r;
     ow_r<=(stride_r==2 ? width_span>>1 : width_span)+1'b1;
     oh_r<=(stride_r==2 ? height_span>>1 : height_span)+1'b1;
     state<=SIZES2;
    end
    SIZES2:begin
     input_bytes<=input_pixels*cin_stride_r;weight_bytes<=groups_r*depth_r*8;
     output_pixels<=ow_r*oh_r;output_bytes<=ow_r*oh_r*cout_r*(c_flags[1]?4:exact_mode?2:1);
     param_bytes<=groups_r*96;state<=GUARD;
    end
    GUARD:if(!range_ok || depth_r==0 || depth_r>1152 || ow_r==0 || ow_r>640 || oh_r==0 || oh_r>640)begin
      stop_pending<=1;error_code<=2;state<=FINISH;
     end else begin oc_base<=0;weight_ptr<=c_weight;param_ptr<=c_param;state<=c_flags[0]&&!exact_mode?LUT_PREP:PARAM_PREP;end
    LUT_PREP:begin load_addr<=c_lut;load_remaining<=64;load_index<=0;read_kind<=RK_LUT;
     return_state<=PARAM_PREP;state<=R_REQ;end
    PARAM_PREP:begin load_addr<=param_ptr;load_remaining<=24;load_index<=0;read_kind<=RK_PARAM;
     param_phase<=0;param_channel<=0;return_state<=WEIGHT_PREP;state<=R_REQ;end
    WEIGHT_PREP:begin load_addr<=weight_ptr;load_remaining<={depth_r,1'b0};load_index<=0;read_kind<=RK_WEIGHT;
     return_state<=TILE_PREP;pixel_base<=0;walk_x<=0;walk_y<=0;state<=R_REQ;end
    R_REQ:if(mem_req_ready)state<=R_WAIT;
    R_WAIT:if(mem_rsp_valid)begin
     load_addr<=load_addr+4;load_remaining<=load_remaining-1'b1;load_index<=load_index+1'b1;
     if(mem_rsp_error)begin stop_pending<=1;error_code<=3;end
     if(!stop_pending && !mem_rsp_error)case(read_kind)
      RK_PARAM:begin
       case(param_phase)
        0:biases[param_channel]<=mem_rsp_rdata;
        1:begin scales[param_channel]<=mem_rsp_rdata[30:0];
         if(mem_rsp_rdata[31] || (exact_mode && mem_rsp_rdata!=1))begin stop_pending<=1;error_code<=6;end end
        2:begin shifts[param_channel]<=mem_rsp_rdata[5:0];
         if(mem_rsp_rdata>62)begin stop_pending<=1;error_code<=6;end end
       endcase
       if(param_phase==2)begin param_phase<=0;param_channel<=param_channel+1'b1;end
       else param_phase<=param_phase+1'b1;
      end
      RK_INPUT:begin fill_offset<=fill_offset+4;fill_ci<=fill_ci+4;end
      RK_SCALAR:begin cache_word<=mem_rsp_rdata;cache_tag<=load_addr;cache_valid<=1;end
      RK_EXACT:begin exact_lut_word<=mem_rsp_rdata;exact_lut_tag<=load_addr;exact_lut_valid<=1;end
      default:begin end
     endcase
     if(mem_rsp_last)begin
      if(stop_pending || mem_rsp_error)state<=FINISH;
      else if(load_remaining==1)state<=return_state;
      else state<=R_REQ;
     end
    end
    TILE_PREP:begin prepare_pixel<=0;pixel_valid<=0;k_base<=0;chunk_length<=depth_r>128?128:depth_r[7:0];
     chunk_ci<=0;chunk_kx<=0;chunk_ky<=0;state<=PIXEL_PREP;end
    PIXEL_PREP:begin
     pixel_x[prepare_pixel[1:0]]<=walk_x;pixel_y[prepare_pixel[1:0]]<=walk_y;
     pixel_valid[prepare_pixel[1:0]]<=pixel_base+prepare_pixel<output_pixels;
     if(walk_x+1>=ow_r)begin walk_x<=0;walk_y<=walk_y+1'b1;end else walk_x<=walk_x+1'b1;
     if(prepare_pixel==3)begin fill_pixel<=0;fill_offset<=0;fill_ci<=0;fill_kx<=0;fill_ky<=0;
      input_pack<=0;state<=FILL_SCAN;end else prepare_pixel<=prepare_pixel+1'b1;
    end
    FILL_SCAN:begin
     if(gather_zero)state<=fast_word?FILL_ZERO:FILL_SCALAR;
     else if(fast_word && gather_addr[1:0]==0)begin
      load_addr<=gather_addr;load_remaining<=input_burst_words;load_index<=0;read_kind<=RK_INPUT;
      return_state<=FILL_ADV;state<=R_REQ;
     end else if(cache_valid && cache_tag==gather_aligned)state<=FILL_SCALAR;
     else begin load_addr<=gather_aligned;load_remaining<=1;load_index<=0;read_kind<=RK_SCALAR;
      return_state<=FILL_SCALAR;state<=R_REQ;end
    end
    FILL_ZERO:begin fill_offset<=fill_offset+4;fill_ci<=fill_ci+4;state<=FILL_ADV;end
    FILL_SCALAR:begin input_pack<=scalar_pack;fill_offset<=fill_offset+1'b1;fill_ci<=fill_ci+1'b1;state<=FILL_ADV;end
    FILL_ADV:begin
     if(fill_ci==cin_r)begin fill_ci<=0;
      if(fill_kx+1==kernel_r)begin fill_kx<=0;fill_ky<=fill_ky+1'b1;end else fill_kx<=fill_kx+1'b1;
     end
     if(fill_offset>=chunk_length)begin
      fill_offset<=0;input_pack<=0;
      if(fill_pixel==3)begin
       next_ci<=fill_ci==cin_r?0:fill_ci;
       next_kx<=fill_ci==cin_r ? (fill_kx+1==kernel_r?0:fill_kx+1'b1) : fill_kx;
       next_ky<=fill_ci==cin_r && fill_kx+1==kernel_r ? fill_ky+1'b1 : fill_ky;
       feed_index<=0;state<=FEED;
      end else begin fill_pixel<=fill_pixel+1'b1;fill_ci<=chunk_ci;fill_kx<=chunk_kx;fill_ky<=chunk_ky;state<=FILL_SCAN;end
     end else state<=FILL_SCAN;
    end
    FEED:if(feed_index+1>=chunk_length)begin drain_count<=0;state<=DRAIN;end
     else feed_index<=feed_index+1'b1;
    DRAIN:if(drain_count==3)begin
      if(k_base+chunk_length>=depth_r)begin q_pixel<=0;q_channel<=0;output_pack<=0;state<=Q_BEGIN;end
      else begin k_base<=k_base+chunk_length;chunk_length<=depth_r-k_base-chunk_length>128?128:depth_r-k_base-chunk_length;
       chunk_ci<=next_ci;chunk_kx<=next_kx;chunk_ky<=next_ky;
       fill_ci<=next_ci;fill_kx<=next_kx;fill_ky<=next_ky;fill_pixel<=0;fill_offset<=0;input_pack<=0;
       buffer_bank<=!buffer_bank;state<=FILL_SCAN;end
     end else drain_count<=drain_count+1'b1;
    Q_BEGIN:if(c_flags[1])begin output_pack[q_channel*32+:32]<=selected_acc;
      if(q_channel+1>=channels_here)state<=O_PREP;else q_channel<=q_channel+1'b1;
     end else state<=Q_ADD;
    Q_ADD:begin biased<=$signed({selected_acc[31],selected_acc})+$signed({biases[q_channel][31],biases[q_channel]});
     quant_shift<=shifts[q_channel];state<=exact_mode?E_CHECK:Q_MUL;end
    E_CHECK:if(biased[32]!=biased[31])begin stop_pending<=1;error_code<=9;state<=FINISH;end
     else begin exact_negative<=biased[31];exact_magnitude<=biased[31] ? -biased[31:0] : biased[31:0];state<=E_ROUND;end
    E_ROUND:begin exact_pre<=exact_saturated;state<=c_flags[0]?E_LOOKUP:E_STORE;end
    E_LOOKUP:if(exact_lut_valid && exact_lut_tag=={exact_address[31:2],2'b0})state<=E_STORE;
     else begin load_addr<={exact_address[31:2],2'b0};load_remaining<=1;load_index<=0;
      read_kind<=RK_EXACT;return_state<=E_STORE;state<=R_REQ;end
    E_STORE:begin
     output_pack[q_channel*16+:16]<=c_flags[0]?{{8{exact_lut_byte[7]}},exact_lut_byte}:exact_pre;
     if(q_channel+1>=channels_here)state<=O_PREP;else begin q_channel<=q_channel+1'b1;state<=Q_BEGIN;end
    end
    Q_MUL:if(SERIAL_LEGACY_QUANT)begin product<=0;legacy_mul_bit<=0;state<=Q_MUL_STEP;end
     else begin product<=biased*$signed({1'b0,scales[q_channel]});state<=Q_SHIFT;end
    Q_MUL_STEP:begin
     product<={legacy_mul_sum,product[30:1]};
     if(legacy_mul_bit==30)state<=Q_SHIFT;else legacy_mul_bit<=legacy_mul_bit+1'b1;
    end
    Q_SHIFT:begin quant_byte<=rounded>127?8'd127:rounded< -128?8'h80:rounded[7:0];
     state<=c_flags[0]?Q_LOOKUP:Q_STORE;end
    Q_LOOKUP:begin lut_q<=lut_mem[quant_byte[7:2]];state<=Q_LUT_USE;end
    Q_LUT_USE:begin result_byte<=lut_q>>{quant_byte[1:0],3'b0};state<=Q_STORE;end
    Q_STORE:begin output_pack[q_channel*8+:8]<=c_flags[0]?result_byte:quant_byte;
     if(q_channel+1>=channels_here)state<=O_PREP;else begin q_channel<=q_channel+1'b1;state<=Q_BEGIN;end end
    O_PREP:begin
     write_packet<={32'b0,output_pack}<<{output_addr[1:0],3'b0};
     write_addr<={output_addr[31:2],2'b0};write_count<=output_count;write_offset<=output_addr[1:0];
     write_remaining<=(output_addr[1:0]+output_count+3)>>2;write_index<=0;state<=W_REQ;
    end
    W_REQ:if(mem_req_ready)begin write_burst_left<=write_burst_words;state<=W_DATA;end
    W_DATA:if(mem_w_ready)begin
     write_addr<=write_addr+4;write_index<=write_index+1'b1;write_remaining<=write_remaining-1'b1;
     write_burst_left<=write_burst_left-1'b1;if(write_burst_left==1)state<=W_RESP;
    end
    W_RESP:if(mem_rsp_valid)begin
     if(mem_rsp_error)begin stop_pending<=1;error_code<=3;state<=FINISH;end
     else if(stop_pending)state<=FINISH;
     else if(write_remaining!=0)state<=W_REQ;else state<=NEXT_PIXEL;
    end
    NEXT_PIXEL:if(q_pixel!=3 && pixel_valid[q_pixel+1'b1])begin
      q_pixel<=q_pixel+1'b1;q_channel<=0;output_pack<=0;state<=Q_BEGIN;
     end else if(pixel_base+4<output_pixels)begin pixel_base<=pixel_base+4;state<=TILE_PREP;end
     else if(oc_base+8<cout_r)begin oc_base<=oc_base+8;weight_ptr<=weight_ptr+{depth_r,3'b0};
      param_ptr<=param_ptr+96;state<=PARAM_PREP;end
     else state<=FINISH;
    FINISH:begin state<=IDLE;done<=1;error<=stop_pending;end
    default:begin end
   endcase
   if(stop_pending && state!=IDLE && state!=FINISH && state!=R_REQ && state!=R_WAIT &&
      state!=W_REQ && state!=W_DATA && state!=W_RESP)state<=FINISH;
  end
 end
endmodule
