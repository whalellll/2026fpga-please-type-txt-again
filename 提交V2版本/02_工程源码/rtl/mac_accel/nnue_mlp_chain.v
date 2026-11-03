`timescale 1ns/1ps

// Autonomous official PFSB tail. Reuses the existing dense PE for all three
// affine layers. Features, partial sums and dual activations remain on-chip.
// The old PFSB image is unchanged; the small row-major tail is packed locally.
module nnue_mlp_chain #(
 parameter [31:0] DDR_BASE=32'h1b000000,
 parameter integer DDR_BYTES=1048576
)(
 input wire clk,resetn,start,abort,
 input wire [31:0] stack_source,
 output wire busy,output reg done,output reg error,
 output reg signed [31:0] score,
 output reg [31:0] cycles,output reg [3:0] jobs,
 input wire feature_valid,output wire feature_ready,
 input wire [8:0] feature_index,input wire [15:0] feature_data,
 output reg mac_reg_we,output reg [7:0] mac_reg_addr,output reg [31:0] mac_reg_data,
 input wire [31:0] mac_status,
 output reg link_input_we,output reg [10:0] link_input_addr,output reg [63:0] link_input_data,
 output reg link_weight_we,output reg [10:0] link_weight_addr,
 output reg [4:0] link_weight_word,output reg [31:0] link_weight_data,
 input wire link_output_valid,output wire link_output_ready,
 input wire [12:0] link_output_index,input wire [31:0] link_output_data,
 output wire mem_req_valid,input wire mem_req_ready,
 output wire [31:0] mem_req_addr,output wire [2:0] mem_req_len,
 input wire mem_rsp_valid,output wire mem_rsp_ready,
 input wire [31:0] mem_rsp_rdata,input wire mem_rsp_last,mem_rsp_error
);
 localparam IDLE=0,FEATURES=1,TAIL_REQ=2,TAIL_DATA=3,INPUT_READ=4,INPUT_WRITE=5,
  CONFIG=6,CORE=7,ACT_CALC=8,ACT_PACK=9,W0_READ=10,W0_HOLD=11,W1_READ=12,
  W_PACK0=13,W_PACK1=14,W2_READ=15,W2_HOLD=16,W2_WRITE=17,CLEANUP=18,FINISH=19,DRAIN=20;
 reg [4:0] state;
 reg [1:0] layer,tile;
 reg [31:0] source_q;
 reg [8:0] feature_count;
 reg [15:0] feature_half;
 reg [31:0] features[0:255],tail[0:608];
 reg [31:0] feature_q,tail_q,weight0,weight1;
 reg signed [31:0] accum[0:31],bias1[0:31],bias2,skip;
 reg [31:0] sq0[0:7],lin0[0:7],sq1[0:7],lin1[0:7];
 reg [31:0] sq_pack,lin_pack;
 reg [9:0] tail_index;
 reg [3:0] remaining;
 reg [6:0] input_line;
 reg [3:0] config_step;
 reg [5:0] returned_words;
 reg [4:0] act_index;
 reg [3:0] co_pair;
 reg [4:0] ci_line;
 reg [4:0] word_number;
 reg [31:0] act_square;
 reg [7:0] act_linear;
 reg signed [31:0] forward_q;
 reg cancelled;
 wire [9:0] words_left=10'd609-tail_index;
 wire [3:0] request_beats=words_left>=8?4'd8:words_left[3:0];
 wire [9:0] tail_read_address=state==W0_READ ? 10'd32+{co_pair,5'b0}+{5'b0,ci_line} :
                              state==W1_READ ? 10'd48+{co_pair,5'b0}+{5'b0,ci_line} :
                              10'd576+{5'b0,ci_line};
 wire [7:0] feature_read_address={tile,input_line[5:0]};
 wire signed [31:0] act_value=accum[act_index];
 wire signed [15:0] act_narrow=act_value>32767?16'sd32767:act_value< -32768?-16'sd32768:act_value[15:0];
 wire [31:0] shifted_square=act_square>>(layer==0?21:19);
 wire [7:0] squared_byte=shifted_square>127?8'd127:shifted_square[7:0];
 wire signed [31:0] shifted_linear=$signed(act_value) >>> (layer==0?7:6);
 reg [31:0] activation_word;
 always @*begin
  if(layer==1)activation_word=input_line[3]?lin0[input_line[2:0]]:sq0[input_line[2:0]];
  else case(input_line[4:3])
   0:activation_word=sq0[input_line[2:0]];
   1:activation_word=lin0[input_line[2:0]];
   2:activation_word=sq1[input_line[2:0]];
   default:activation_word=lin1[input_line[2:0]];
  endcase
 end
 wire [31:0] input_word=layer==0?feature_q:activation_word;
 wire [6:0] input_lines=layer==0?7'd64:layer==1?7'd16:7'd32;
 wire [5:0] expected_words=layer==2?6'd1:6'd32;
 wire signed [63:0] scaled_product=$signed(forward_q)*64'sd75;
 wire signed [63:0] scaled_result=scaled_product<0 ? -((-scaled_product)>>>7) : scaled_product>>>7;
 assign busy=state!=IDLE;
 assign feature_ready=state==FEATURES;
 assign link_output_ready=state==CORE;
 assign mem_req_valid=state==TAIL_REQ;
 assign mem_req_addr=source_q+32'h8100+{20'b0,tail_index,2'b0};
 assign mem_req_len=request_beats-1'b1;
 assign mem_rsp_ready=state==TAIL_DATA || state==DRAIN;
 always @(posedge clk)begin
  if(state==INPUT_READ)feature_q<=features[feature_read_address];
  if(state==W0_READ || state==W1_READ || state==W2_READ)tail_q<=tail[tail_read_address];
  if(!resetn)feature_half<=0;
  else if(state==FEATURES && feature_valid && feature_index==feature_count)begin
   if(feature_count[0])features[feature_count[8:1]]<={feature_data,feature_half};
   else feature_half<=feature_data;
  end
  if(resetn && state==TAIL_DATA && mem_rsp_valid && !mem_rsp_error)tail[tail_index]<=mem_rsp_rdata;
 end
 always @*begin
  mac_reg_we=0;mac_reg_addr=0;mac_reg_data=0;
  link_input_we=0;link_input_addr={4'b0,input_line};link_input_data=0;
  link_weight_we=0;link_weight_addr={6'b0,ci_line};link_weight_word=0;link_weight_data=0;
  if(state==INPUT_WRITE)begin
   link_input_we=1;
   link_input_data={8'b0,input_word[31:24],8'b0,input_word[23:16],8'b0,input_word[15:8],8'b0,input_word[7:0]};
  end
  if(state==CONFIG)begin
   mac_reg_we=1;
   case(config_step)
    0:begin mac_reg_addr=8'h08;mac_reg_data=2;end
    1:begin mac_reg_addr=8'h10;mac_reg_data=layer==0?32'h01000001:layer==1?32'h00400001:32'h00800001;end
    2:begin mac_reg_addr=8'h14;mac_reg_data=layer==2?32'h63000001:32'h63000020;end
    3:begin mac_reg_addr=8'h18;mac_reg_data=DDR_BASE;end
    4:begin mac_reg_addr=8'h1c;mac_reg_data=layer==0?source_q+32'h100+{17'b0,tile,13'b0}:DDR_BASE;end
    5:begin mac_reg_addr=8'h20;mac_reg_data=DDR_BASE;end
    6:begin mac_reg_addr=8'h24;mac_reg_data=DDR_BASE;end
    7:begin mac_reg_addr=8'h3c;mac_reg_data=layer==0?3:7;end
    default:begin mac_reg_addr=8'h08;mac_reg_data=1;end
   endcase
  end
  if(state==CLEANUP)begin mac_reg_we=1;mac_reg_addr=8'h3c;mac_reg_data=0;end
  if(state==W_PACK0 || state==W_PACK1)begin
   link_weight_we=1;link_weight_word={co_pair,state==W_PACK1};
   link_weight_data=state==W_PACK0?{tail_q[15:8],weight0[15:8],tail_q[7:0],weight0[7:0]}:
                                      {weight1[31:24],weight0[31:24],weight1[23:16],weight0[23:16]};
  end
  if(state==W2_WRITE)begin
   link_weight_we=1;link_weight_word=word_number;
   if(word_number==0)link_weight_data={8'b0,weight0[15:8],8'b0,weight0[7:0]};
   else if(word_number==1)link_weight_data={8'b0,weight0[31:24],8'b0,weight0[23:16]};
  end
 end
 always @(posedge clk)begin
  if(!resetn)begin
   state<=IDLE;layer<=0;tile<=0;source_q<=0;feature_count<=0;
   tail_index<=0;remaining<=0;input_line<=0;config_step<=0;returned_words<=0;
   act_index<=0;co_pair<=0;ci_line<=0;word_number<=0;weight0<=0;weight1<=0;
   sq_pack<=0;lin_pack<=0;act_square<=0;act_linear<=0;bias2<=0;skip<=0;
   forward_q<=0;cancelled<=0;done<=0;error<=0;score<=0;cycles<=0;jobs<=0;
  end else begin
   if(busy)cycles<=cycles+1'b1;
   if(abort && busy)cancelled<=1;
   case(state)
    IDLE:if(start)begin
     done<=0;error<=0;cancelled<=0;cycles<=0;jobs<=0;feature_count<=0;layer<=0;tile<=0;
     if(stack_source<DDR_BASE || {1'b0,stack_source}+33'h8a84>{1'b0,DDR_BASE}+DDR_BYTES || stack_source[4:0]!=0)begin
      error<=1;done<=1;
     end else begin source_q<=stack_source;state<=FEATURES;end
    end
    FEATURES:if(cancelled || abort)begin error<=1;state<=CLEANUP;end
     else if(feature_valid)begin
      if(feature_index!=feature_count)begin error<=1;state<=CLEANUP;end
      else if(feature_count==511)begin tail_index<=0;state<=TAIL_REQ;end
      else feature_count<=feature_count+1'b1;
     end
    TAIL_REQ:if(mem_req_ready)begin remaining<=request_beats;state<=TAIL_DATA;end
    TAIL_DATA:if(mem_rsp_valid)begin
     if(mem_rsp_error || mem_rsp_last!=(remaining==1))begin
      error<=1;state<=mem_rsp_last?CLEANUP:DRAIN;
     end else begin
      if(tail_index<32)accum[tail_index[4:0]]<=mem_rsp_rdata;
      if(tail_index>=544 && tail_index<576)bias1[tail_index[4:0]]<=mem_rsp_rdata;
      if(tail_index==608)bias2<=mem_rsp_rdata;
      tail_index<=tail_index+1'b1;remaining<=remaining-1'b1;
      if(tail_index==608)begin
       input_line<=0;
       if(cancelled || abort)begin error<=1;state<=CLEANUP;end else state<=INPUT_READ;
      end else if(remaining==1)state<=TAIL_REQ;
     end
    end
    DRAIN:if(mem_rsp_valid && mem_rsp_last)state<=CLEANUP;
    INPUT_READ:state<=INPUT_WRITE;
    INPUT_WRITE:if(input_line+1'b1>=input_lines)begin config_step<=0;state<=CONFIG;end
                else begin input_line<=input_line+1'b1;state<=INPUT_READ;end
    CONFIG:if(config_step==8)begin returned_words<=0;state<=CORE;end
           else config_step<=config_step+1'b1;
    CORE:begin
     if(link_output_valid)begin
      if(link_output_index!={7'b0,returned_words} || returned_words>=expected_words)error<=1;
      else if(layer==0)accum[returned_words[4:0]]<=accum[returned_words[4:0]]+link_output_data;
      else if(layer==1)accum[returned_words[4:0]]<=bias1[returned_words[4:0]]+link_output_data;
      else forward_q<=link_output_data+bias2+skip;
      returned_words<=returned_words+1'b1;
     end
     if(mac_status[1])begin
      jobs<=jobs+1'b1;
      if(mac_status[2] || returned_words!=expected_words || error || cancelled || abort)begin error<=1;state<=CLEANUP;end
      else if(layer==0 && tile!=3)begin tile<=tile+1'b1;input_line<=0;state<=INPUT_READ;end
      else if(layer!=2)begin act_index<=0;state<=ACT_CALC;end
      else state<=CLEANUP;
     end
    end
    ACT_CALC:begin
     act_square<=$signed(act_narrow)*$signed(act_narrow);
     act_linear<=shifted_linear<0?8'd0:shifted_linear>127?8'd127:shifted_linear[7:0];
     if(layer==0 && act_index==30)skip<=act_value;
     if(layer==0 && act_index==31)skip<=skip-act_value;
     state<=ACT_PACK;
    end
    ACT_PACK:begin
     sq_pack[act_index[1:0]*8+:8]<=squared_byte;
     lin_pack[act_index[1:0]*8+:8]<=act_linear;
     if(act_index[1:0]==3)begin
      if(layer==0)begin sq0[act_index[4:2]]<={squared_byte,sq_pack[23:0]};lin0[act_index[4:2]]<={act_linear,lin_pack[23:0]};end
      else begin sq1[act_index[4:2]]<={squared_byte,sq_pack[23:0]};lin1[act_index[4:2]]<={act_linear,lin_pack[23:0]};end
     end
     if(act_index==31)begin
      layer<=layer+1'b1;ci_line<=0;co_pair<=0;
      state<=layer==0?W0_READ:W2_READ;
     end else begin act_index<=act_index+1'b1;state<=ACT_CALC;end
    end
    W0_READ:state<=W0_HOLD;
    W0_HOLD:begin weight0<=tail_q;state<=W1_READ;end
    W1_READ:state<=W_PACK0;
    W_PACK0:begin weight1<=tail_q;state<=W_PACK1;end
    W_PACK1:if(ci_line==15)begin
      ci_line<=0;
      if(co_pair==15)begin input_line<=0;state<=INPUT_READ;end
      else begin co_pair<=co_pair+1'b1;state<=W0_READ;end
     end else begin ci_line<=ci_line+1'b1;state<=W0_READ;end
    W2_READ:state<=W2_HOLD;
    W2_HOLD:begin weight0<=tail_q;word_number<=0;state<=W2_WRITE;end
    W2_WRITE:if(word_number==31)begin
      if(ci_line==31)begin input_line<=0;state<=INPUT_READ;end
      else begin ci_line<=ci_line+1'b1;state<=W2_READ;end
     end else word_number<=word_number+1'b1;
    CLEANUP:state<=FINISH;
    FINISH:begin
     if(!error && !cancelled)score<=scaled_result[31:0];
     else error<=1;
     done<=1;state<=IDLE;
    end
    default:begin error<=1;state<=CLEANUP;end
   endcase
  end
 end
endmodule
