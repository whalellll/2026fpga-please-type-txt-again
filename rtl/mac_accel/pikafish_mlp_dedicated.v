`timescale 1ns/1ps
// Fixed official PFSB MLP: 1024->32, dual activation, 64->32,
// dual activation/concat, 128->1, skip and exact signed scaling.
// Eight banked SRAMs retain one complete FC0; eight small banks retain FC1.
// The original PFSB DDR layout is consumed directly. No generic PE/input/
// output/bias banks are instantiated. Model reuse requires an explicit
// invalidation when contents at a previously used stack_source change.
module pikafish_mlp_dedicated #(
 parameter [31:0] DDR_BASE=32'h1b000000,parameter integer DDR_BYTES=1048576
)(
 input wire clk,resetn,start,abort,invalidate,input wire [31:0] stack_source,
 output wire busy,output reg done,error,output reg signed [31:0] score,
 output reg [31:0] cycles,output reg [3:0] jobs,
 input wire feature_valid,output wire feature_ready,
 input wire [8:0] feature_index,input wire [15:0] feature_data,
 output wire mem_req_valid,input wire mem_req_ready,
 output wire [31:0] mem_req_addr,output wire [2:0] mem_req_len,
 input wire mem_rsp_valid,output wire mem_rsp_ready,
 input wire [31:0] mem_rsp_rdata,input wire mem_rsp_last,mem_rsp_error,
 output reg cache_valid,cache_hit,output reg [31:0] read_words
);
 localparam IDLE=0,FEATURES=1,FILL_REQ=2,FILL_DATA=3,DRAIN=4,
  INIT_REQ=5,INIT_USE=6,READ_X=7,USE_X=8,ISSUE=9,WAIT_LAYER=10,
  ACT_PRE=11,ACT_STORE=12,FINAL_PRE=13,FINAL_DONE=14,ERROR_END=15;
 reg [3:0] state;
 reg [1:0] layer,out_group;
 reg [7:0] input_group;
 reg [4:0] init_index,act_index;
 reg [8:0] feature_count;
 reg [15:0] feature_half;
 reg [31:0] source_q,cache_source;
 reg cancelled;
 reg [13:0] fill_index;
 reg [3:0] remaining;
 reg [31:0] features[0:255],feature_q,xword;
 reg [31:0] metadata[0:96],meta_q;
 reg [31:0] sq0[0:7],lin0[0:7],sq1[0:7],lin1[0:7];
 reg signed [31:0] accum[0:31],skip,forward_q;
 reg [31:0] square_q,sq_pack,lin_pack;
 reg [7:0] linear_q;
 wire [31:0] linear_store={linear_q,lin_pack[23:0]};
 wire [31:0] linear_store_padded;
`ifdef SYNTHESIS
 // Native CPU60 report: lin_pack[21] -> lin1 RAM DIH hold violation.
 // Preserve one identity LUT per pair; arithmetic and cycle count unchanged.
 genvar hold_pair;
 generate for(hold_pair=0;hold_pair<16;hold_pair=hold_pair+1)begin:g_linear_hold
  (* PAP_DONT_TOUCH *) GTP_LUT6D #(.INIT(64'hCCCCCCCC_AAAAAAAA)) u_linear_hold_lut(
   .I0(linear_store[hold_pair*2]),.I1(linear_store[hold_pair*2+1]),
   .I2(1'b0),.I3(1'b0),.I4(1'b0),.I5(1'b1),
   .Z5(linear_store_padded[hold_pair*2]),.Z(linear_store_padded[hold_pair*2+1]));
 end endgenerate
`else
 assign linear_store_padded=linear_store;
`endif
 wire [13:0] fill_left=14'd8801-fill_index;
 wire [3:0] beats=fill_left>=8?4'd8:fill_left[3:0];
 wire [9:0] tail_index=fill_index-14'd8192;
 wire [8:0] fc1_word=tail_index-10'd32;
 wire response_good=state==FILL_DATA && mem_rsp_valid &&
   !mem_rsp_error && mem_rsp_last==(remaining==1) && !cancelled && !abort && !invalidate;
 wire [9:0] fc0_address={input_group,out_group};
 wire [5:0] fc1_address={input_group[3:0],out_group};
 wire [255:0] fc0_q,fc1_q;
 wire [6:0] meta_address=state==ISSUE && layer==2 ? 7'd64+{2'b0,input_group[4:0]} :
   layer==0 ? {2'b0,init_index} : layer==1 ? 7'd32+{2'b0,init_index} : 7'd96;
 wire [6:0] meta_write_address=tail_index<32?tail_index[6:0]:tail_index-10'd512;
 wire meta_write=response_good && fill_index>=8192 && (tail_index<32 || tail_index>=544);
 assign busy=state!=IDLE;
 assign feature_ready=state==FEATURES && !cancelled && !abort && !invalidate;
 assign mem_req_valid=state==FILL_REQ && !cancelled && !abort && !invalidate;
 assign mem_req_addr=source_q+32'h100+{16'b0,fill_index,2'b0};
 assign mem_req_len=beats-1'b1;
 assign mem_rsp_ready=state==FILL_DATA || state==DRAIN;

 genvar bank;
 generate for(bank=0;bank<8;bank=bank+1)begin:g_weight
  reg [31:0] fc0_mem[0:1023];
  reg [31:0] fc1_mem[0:63];
  reg [31:0] q0,q1;
  assign fc0_q[bank*32+:32]=q0;
  assign fc1_q[bank*32+:32]=q1;
  always @(posedge clk)begin
   if(response_good && fill_index<8192 && fill_index[2:0]==bank)
    fc0_mem[fill_index[12:3]]<=mem_rsp_rdata;
   if(response_good && fill_index>=8192 && tail_index>=32 && tail_index<544 && fc1_word[6:4]==bank)
    fc1_mem[{fc1_word[3:0],fc1_word[8:7]}]<=mem_rsp_rdata;
   if(state==ISSUE)begin q0<=fc0_mem[fc0_address];q1<=fc1_mem[fc1_address];end
  end
 end endgenerate
 always @(posedge clk)begin
  if(resetn && state==FEATURES && feature_valid && feature_ready && feature_index==feature_count)begin
   if(feature_count[0])features[feature_count[8:1]]<={feature_data,feature_half};
  end
  if(meta_write)metadata[meta_write_address]<=mem_rsp_rdata;
  meta_q<=metadata[meta_address];
  if(state==READ_X)begin
   if(layer==0)feature_q<=features[input_group];
   else if(layer==1)feature_q<=input_group[3]?lin0[input_group[2:0]]:sq0[input_group[2:0]];
   else case(input_group[4:3])
    0:feature_q<=sq0[input_group[2:0]];
    1:feature_q<=lin0[input_group[2:0]];
    2:feature_q<=sq1[input_group[2:0]];
    3:feature_q<=lin1[input_group[2:0]];
   endcase
  end
 end

 // SRAM read, 32 registered signed products, then eight registered dot4
 // accumulations. Groups rotate, so no accumulator forwarding is needed.
 reg rd_valid,prod_valid;
 reg [1:0] rd_layer,prod_layer,rd_group,prod_group;
 reg [31:0] rd_x;
 reg signed [16:0] product[0:31];
 wire signed [31:0] dot[0:7];
 genvar p,g;
 generate for(p=0;p<32;p=p+1)begin:g_product
  localparam integer O=p/4,I=p%4;
  wire signed [7:0] weight=rd_layer==0 ? fc0_q[((O/2)*8+I*2+(O%2))*8+:8] :
    rd_layer==1 ? fc1_q[O*32+I*8+:8] : O==0 ? meta_q[I*8+:8] : 8'sd0;
  always @(posedge clk)if(rd_valid)product[p]<=$signed({1'b0,rd_x[I*8+:8]})*weight;
 end
 for(g=0;g<8;g=g+1)begin:g_dot
  assign dot[g]=$signed({{15{product[g*4][16]}},product[g*4]})+
    $signed({{15{product[g*4+1][16]}},product[g*4+1]})+
    $signed({{15{product[g*4+2][16]}},product[g*4+2]})+
    $signed({{15{product[g*4+3][16]}},product[g*4+3]});
 end
 for(g=0;g<32;g=g+1)begin:g_accumulator
  always @(posedge clk)if(resetn)begin
   if(state==INIT_USE && init_index==g)accum[g]<=meta_q;
   else if(prod_valid && prod_group==g/8 && (prod_layer!=2 || g==0))
    accum[g]<=accum[g]+dot[g%8];
  end
 end endgenerate
 always @(posedge clk)begin
  if(!resetn)begin rd_valid<=0;prod_valid<=0;rd_layer<=0;prod_layer<=0;rd_group<=0;prod_group<=0;rd_x<=0;end
  else begin
   rd_valid<=state==ISSUE && !abort && !invalidate && !cancelled;
   prod_valid<=rd_valid && !abort && !invalidate && !cancelled;
   if(state==ISSUE)begin rd_layer<=layer;rd_group<=out_group;rd_x<=xword;end
   if(rd_valid)begin prod_layer<=rd_layer;prod_group<=rd_group;end
  end
 end
 wire signed [31:0] av=accum[act_index];
 wire signed [15:0] narrow=av>32767?16'sd32767:av< -32768?-16'sd32768:av[15:0];
 wire signed [31:0] shifted=av >>> (layer==0?7:6);
 wire [31:0] shifted_square=square_q>>(layer==0?21:19);
 wire [7:0] square_byte=shifted_square>127?8'd127:shifted_square[7:0];
 wire signed [63:0] scaled=$signed(forward_q)*64'sd75;
 wire signed [63:0] rounded=scaled<0?-((-scaled)>>>7):scaled>>>7;
 wire last_input=layer==0?input_group==255:layer==1?input_group==15:input_group==31;
 always @(posedge clk)begin
  if(!resetn)begin
   state<=IDLE;done<=0;error<=0;score<=0;cycles<=0;jobs<=0;read_words<=0;
   cache_valid<=0;cache_hit<=0;cache_source<=0;source_q<=0;cancelled<=0;
   layer<=0;out_group<=0;input_group<=0;init_index<=0;act_index<=0;
   feature_count<=0;feature_half<=0;fill_index<=0;remaining<=0;
   xword<=0;skip<=0;forward_q<=0;square_q<=0;linear_q<=0;sq_pack<=0;lin_pack<=0;
  end else begin
   if(busy)cycles<=cycles+1'b1;
   if(invalidate)cache_valid<=0;
   if((abort || invalidate) && busy)begin cancelled<=1;cache_valid<=0;end
   if((abort || invalidate || cancelled) && busy && state!=FILL_DATA && state!=DRAIN && state!=ERROR_END)
    state<=ERROR_END;
   else case(state)
    IDLE:if(start)begin
     done<=0;error<=0;score<=0;cycles<=0;jobs<=0;read_words<=0;cancelled<=0;
     layer<=0;input_group<=0;out_group<=0;feature_count<=0;source_q<=stack_source;
     cache_hit<=cache_valid && cache_source==stack_source && !invalidate;
     if(stack_source<DDR_BASE || {1'b0,stack_source}+33'h8a84>{1'b0,DDR_BASE}+DDR_BYTES || stack_source[4:0]!=0)
      begin error<=1;state<=ERROR_END;end
     else state<=FEATURES;
    end
    FEATURES:if(feature_valid)begin
     if(feature_index!=feature_count)begin error<=1;state<=ERROR_END;end
     else begin
      if(!feature_count[0])feature_half<=feature_data;
      if(feature_count==511)begin
       init_index<=0;
       if(cache_hit)state<=INIT_REQ;
       else begin fill_index<=0;cache_valid<=0;state<=FILL_REQ;end
      end else feature_count<=feature_count+1'b1;
     end
    end
    FILL_REQ:if(mem_req_ready)begin remaining<=beats;state<=FILL_DATA;end
    FILL_DATA:if(mem_rsp_valid)begin
     read_words<=read_words+1'b1;
     if(mem_rsp_error || mem_rsp_last!=(remaining==1))begin
      cache_valid<=0;error<=1;state<=mem_rsp_last?ERROR_END:DRAIN;
     end else if(cancelled || abort || invalidate)begin
      cache_valid<=0;error<=1;if(mem_rsp_last)state<=ERROR_END;
      else remaining<=remaining-1'b1;
     end else begin
      remaining<=remaining-1'b1;fill_index<=fill_index+1'b1;
      if(fill_index==8800)begin cache_valid<=1;cache_source<=source_q;init_index<=0;state<=INIT_REQ;end
      else if(remaining==1)state<=FILL_REQ;
     end
    end
    DRAIN:if(mem_rsp_valid)begin read_words<=read_words+1'b1;if(mem_rsp_last)state<=ERROR_END;end
    INIT_REQ:state<=INIT_USE;
    INIT_USE:if(layer==2 || init_index==31)begin input_group<=0;out_group<=0;state<=READ_X;end
             else begin init_index<=init_index+1'b1;state<=INIT_REQ;end
    READ_X:state<=USE_X;
    USE_X:begin xword<=feature_q;out_group<=0;state<=ISSUE;end
    ISSUE:begin
     if(layer==2 || out_group==3)begin
      if(layer==0 && input_group[5:0]==63 || layer!=0 && last_input)jobs<=jobs+1'b1;
      if(last_input)state<=WAIT_LAYER;
      else begin input_group<=input_group+1'b1;state<=READ_X;end
     end else out_group<=out_group+1'b1;
    end
    WAIT_LAYER:if(!rd_valid && !prod_valid)begin
     if(layer==2)state<=FINAL_PRE;
     else begin if(layer==0)skip<=accum[30]-accum[31];act_index<=0;state<=ACT_PRE;end
    end
    ACT_PRE:begin
     square_q<=$signed(narrow)*$signed(narrow);
     linear_q<=shifted<0?8'd0:shifted>127?8'd127:shifted[7:0];state<=ACT_STORE;
    end
    ACT_STORE:begin
     sq_pack[act_index[1:0]*8+:8]<=square_byte;lin_pack[act_index[1:0]*8+:8]<=linear_q;
     if(act_index[1:0]==3)begin
      if(layer==0)begin sq0[act_index[4:2]]<={square_byte,sq_pack[23:0]};lin0[act_index[4:2]]<=linear_store_padded;end
      else begin sq1[act_index[4:2]]<={square_byte,sq_pack[23:0]};lin1[act_index[4:2]]<=linear_store_padded;end
     end
     if(act_index==31)begin layer<=layer+1'b1;init_index<=0;state<=INIT_REQ;end
     else begin act_index<=act_index+1'b1;state<=ACT_PRE;end
    end
    FINAL_PRE:begin forward_q<=accum[0]+skip;state<=FINAL_DONE;end
    FINAL_DONE:begin score<=rounded[31:0];done<=1;state<=IDLE;end
    ERROR_END:begin error<=1;done<=1;cache_valid<=0;state<=IDLE;end
    default:begin error<=1;cache_valid<=0;state<=ERROR_END;end
   endcase
  end
 end
endmodule
