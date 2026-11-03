`timescale 1ns/1ps

// Two1024-lane S16 accumulators written directly by StageA. Tags identify
// committed complete views; partial/aborted updates are never consumable.
// Output packs two official clip(a)*clip(b)>>9 U8 features per beat.
module nnue_stream_transform(
 input wire clk,resetn,
 input wire write_begin,write_valid,write_commit,write_abort,write_view,
 input wire [31:0] write_tag,write_data,
 input wire [8:0] write_index,
 output wire write_ready,
 input wire start,swap_views,
 input wire [31:0] expected_tag0,expected_tag1,
 output wire busy,output reg done,output reg error,
 output wire feature_valid,input wire feature_ready,
 output wire [8:0] feature_index,output reg [15:0] feature_data,
 output reg [31:0] cycles
);
 localparam IDLE=0,READ_A=1,HOLD_A=2,READ_B=3,MULTIPLY=4,PACK=5,OUTPUT=6;
 reg [2:0] state;
 reg [8:0] pair_index;
 reg [31:0] memory[0:1023];
 reg [31:0] memory_q,first_q;
 reg [31:0] tags[0:1];
 reg [1:0] valid_views;
 reg staging_view,staging_active,staging_error;
 reg [9:0] staging_count;
 reg [31:0] staging_tag;
 reg [15:0] product0,product1;
 wire [9:0] read_address={pair_index[8]^swap_views,state==READ_B,pair_index[7:0]};
 wire signed [15:0] a0=$signed(first_q[15:0]),a1=$signed(first_q[31:16]);
 wire signed [15:0] b0=$signed(memory_q[15:0]),b1=$signed(memory_q[31:16]);
 wire [7:0] ca0=a0<0?8'd0:a0>255?8'd255:a0[7:0];
 wire [7:0] ca1=a1<0?8'd0:a1>255?8'd255:a1[7:0];
 wire [7:0] cb0=b0<0?8'd0:b0>255?8'd255:b0[7:0];
 wire [7:0] cb1=b1<0?8'd0:b1>255?8'd255:b1[7:0];
 assign busy=state!=IDLE;
 assign write_ready=!busy;
 assign feature_valid=state==OUTPUT;
 assign feature_index=pair_index;
 always @(posedge clk)begin
  if(state==READ_A || state==READ_B)memory_q<=memory[read_address];
  if(resetn && write_valid && write_ready && staging_active && !staging_error &&
     write_view==staging_view && {1'b0,write_index}==staging_count && staging_count<512)
   memory[{write_view,write_index}]<=write_data;
 end
 always @(posedge clk)begin
  if(!resetn)begin
   state<=IDLE;pair_index<=0;feature_data<=0;cycles<=0;done<=0;error<=0;
   valid_views<=0;staging_active<=0;staging_error<=0;staging_count<=0;
   staging_tag<=0;staging_view<=0;tags[0]<=0;tags[1]<=0;first_q<=0;product0<=0;product1<=0;
  end else begin
   done<=0;if(busy)cycles<=cycles+1'b1;
   if(write_begin && write_ready)begin
    valid_views[write_view]<=0;staging_active<=1;staging_view<=write_view;
    staging_tag<=write_tag;staging_count<=0;staging_error<=0;
   end
   if(write_valid && write_ready)begin
    if(!staging_active || staging_error || write_view!=staging_view ||
       {1'b0,write_index}!=staging_count || staging_count>=512)begin
     staging_error<=1;valid_views[write_view]<=0;
    end else staging_count<=staging_count+1'b1;
   end
   if(write_commit && write_ready)begin
    if(staging_active && !staging_error && write_view==staging_view && staging_count==512)begin
     valid_views[write_view]<=1;tags[write_view]<=staging_tag;
    end else begin valid_views[write_view]<=0;staging_error<=1;end
    staging_active<=0;
   end
   if(write_abort)begin
    valid_views[write_view]<=0;staging_active<=0;
    if(busy)begin state<=IDLE;done<=1;error<=1;end
   end else case(state)
    IDLE:if(start)begin
     cycles<=0;pair_index<=0;
     if(valid_views!=2'b11 || tags[0]!=expected_tag0 || tags[1]!=expected_tag1 || staging_active ||
        write_begin || write_valid || write_commit)begin
      error<=1;done<=1;
     end else begin error<=0;state<=READ_A;end
    end
    READ_A:state<=HOLD_A;
    HOLD_A:begin first_q<=memory_q;state<=READ_B;end
    READ_B:state<=MULTIPLY;
    MULTIPLY:begin product0<=ca0*cb0;product1<=ca1*cb1;state<=PACK;end
    PACK:begin feature_data<={1'b0,product1[15:9],1'b0,product0[15:9]};state<=OUTPUT;end
    OUTPUT:if(feature_ready)begin
     if(pair_index==511)begin state<=IDLE;done<=1;end
     else begin pair_index<=pair_index+1'b1;state<=READ_A;end
    end
    default:begin state<=IDLE;done<=1;error<=1;end
   endcase
  end
 end
endmodule
