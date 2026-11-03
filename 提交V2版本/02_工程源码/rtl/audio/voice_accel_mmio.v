`timescale 1ns/1ps

// Independent SYS-domain voice path. Live I2S samples stay in a local ring;
//16-frame feature/level queues allow bounded bulk service by Linux.
module voice_accel_mmio #(parameter integer CNN_ENABLE=0)(
 input wire clk,resetn,counter_clear,
 input wire [31:0] addr,wdata,input wire wr,input wire [3:0] wstrb,
 output wire hit,output reg [31:0] rdata,
 input wire [23:0] microphone_sample,input wire [31:0] microphone_count
);
 wire access=wr && hit && wstrb==4'hf;
 wire control=access && addr[7:0]==8'h08;
 wire clear=counter_clear || (control && wdata[1]);
 reg live_enable;
 reg [31:0] last_mic_count,capture_count,next_end,current_end,frame_number,overflows;
 reg [8:0] copy_index,copy_start;
 reg [1:0] copy_state;
 localparam COPY_IDLE=0,COPY_START=1,COPY_READ=2,COPY_SEND=3;
 reg [15:0] pcm[0:511],pcm_q;
 reg [7:0] chunk_index;
 reg [22:0] level_sum;
 reg [15:0] level_fifo[0:15];reg [31:0] level_end[0:15];
 reg [31:0] feature_fifo[0:79],feature_end[0:15],feature_sequence[0:15];
 reg [3:0] fp_write,fp_read,lp_write,lp_read;
 reg [4:0] fp_count,lp_count;
 reg [2:0] feature_word;
 reg [31:0] feature_pack;
 reg signed [31:0] offset_q,scale_q;
 reg [10:0] model_address;
 reg [3:0] input_address;
 reg [6:0] result_address;
 reg [4:0] shift1,shift2,shift3;
 reg [7:0] results[0:120];
 reg feature_done_q,class_done_q,error_q;
 wire mic_event=microphone_count!=last_mic_count;
 wire signed [15:0] pcm_sample=microphone_sample[23:8];
 wire [15:0] magnitude=pcm_sample[15] ? -pcm_sample : pcm_sample;
 wire [23:0] level_total={1'b0,level_sum}+{8'b0,magnitude};
 wire level_event=live_enable && mic_event && chunk_index==159;
 wire level_enqueue=level_event && lp_count<16;
 wire level_pop=control && wdata[4] && lp_count!=0;
 wire feature_pop=control && wdata[3] && fp_count!=0;
 wire signed [31:0] pending_samples=capture_count-next_end;
 wire window_drop=live_enable && copy_state==COPY_IDLE && !feature_busy && fp_count<16 && pending_samples>112;
 wire [1:0] overflow_delta={1'b0,level_event && !level_enqueue}+{1'b0,window_drop};
 wire [8:0] ring_read_index=copy_start+copy_index;
 wire feature_busy,feature_done,feature_valid,feature_ready;
 wire [4:0] feature_index;
 wire [7:0] feature_data;
 wire [31:0] feature_cycles,class_cycles;
 wire class_busy,class_done,result_valid;
 wire [1:0] result_layer;wire [6:0] result_index;
 wire [7:0] result_data,token;wire [9:0] confidence;
 wire feature_enqueue=feature_done && fp_count<16;
 wire manual_start=control && wdata[0] && !live_enable && !feature_busy && fp_count<16;
 wire manual_valid=access && addr[7:0]==8'h24 && !live_enable;
 wire class_start=control && wdata[2] && !class_busy;
 wire model_write=access && addr[7:0]==8'h14 && !class_busy;
 wire input_write=access && addr[7:0]==8'h34 && !class_busy && input_address<10;
 wire [6:0] fifo_write_index=fp_write*7'd5+{4'b0,feature_index[4:2]};
 wire [6:0] fifo_read_index=fp_read*7'd5+{4'b0,feature_word};
 assign hit=addr>=32'h1fe00800 && addr<32'h1fe00900;
 voice_feature_core u_features(
  .clk(clk),.resetn(resetn && !clear),.start(manual_start || copy_state==COPY_START),
  .sample_valid(live_enable ? copy_state==COPY_SEND : manual_valid),.sample_ready(feature_ready),
  .sample_data(live_enable ? pcm_q : wdata[15:0]),.feature_offset(offset_q),.feature_scale(scale_q),
  .busy(feature_busy),.done(feature_done),.cycles(feature_cycles),.feature_valid(feature_valid),
  .feature_ready(1'b1),.feature_index(feature_index),.feature_data(feature_data));
 generate if(CNN_ENABLE==0)begin:g_legacy_classifier
 voice_classifier_core u_classifier(
  .clk(clk),.resetn(resetn && !clear),.start(class_start),
  .model_we(model_write),.model_addr(model_address),.model_data(wdata),
  .input_we(input_write),.input_addr(input_address),.input_data(wdata),
  .shift1(shift1),.shift2(shift2),.shift3(shift3),.busy(class_busy),.done(class_done),.cycles(class_cycles),
  .result_valid(result_valid),.result_ready(1'b1),.result_layer(result_layer),.result_index(result_index),
  .result_data(result_data),.token(token),.confidence(confidence));
 end else begin:g_cnn_classifier
  assign class_busy=cnn_status[0];assign class_done=1'b0;
  assign class_cycles=0;assign result_valid=0;assign result_layer=0;
  assign result_index=0;assign result_data=0;assign token=0;assign confidence=0;
 end endgenerate
 wire [31:0] cnn_rdata,cnn_status;
 generate if(CNN_ENABLE!=0)begin:g_cnn
  voice_cnn_tile_core u_cnn(.clk(clk),.resetn(resetn && !clear),
   .wr(access && addr[7]),.addr(addr[7:0]),.wdata(wdata),.rdata(cnn_rdata),.status(cnn_status));
 end else begin:g_no_cnn
  assign cnn_rdata=0;assign cnn_status=0;
 end endgenerate
 always @(posedge clk)begin
  if(resetn && !clear && mic_event)pcm[capture_count[8:0]]<=pcm_sample;
  if(copy_state==COPY_READ)pcm_q<=pcm[ring_read_index];
  if(resetn && !clear && feature_valid && feature_index[1:0]==3)
   feature_fifo[fifo_write_index]<={feature_data,feature_pack[23:0]};
  if(resetn && !clear && feature_enqueue)begin
   feature_end[fp_write]<=current_end;feature_sequence[fp_write]<=frame_number;
  end
  if(resetn && !clear && level_enqueue)begin
   level_fifo[lp_write]<=level_total/24'd160;level_end[lp_write]<=capture_count+1'b1;
  end
  if(resetn && !clear && result_valid)
   results[(result_layer==0?7'd0:result_layer==1?7'd64:7'd96)+result_index]<=result_data;
 end
 always @*begin
  rdata=0;
  case(addr[7:0])
   8'h00:rdata=32'h56434531;
   8'h04:rdata=32'h00010000;
   8'h0c:rdata={live_enable,10'b0,lp_count,3'b0,fp_count,lp_count!=0,feature_ready,fp_count!=0,class_done_q,class_busy,error_q,feature_done_q,feature_busy};
   8'h10:rdata={21'b0,model_address};
   8'h18:rdata={11'b0,shift3,3'b0,shift2,3'b0,shift1};
   8'h1c:rdata=offset_q;
   8'h20:rdata=scale_q;
   8'h30:rdata={28'b0,input_address};
   8'h38:rdata={25'b0,result_address};
   8'h3c:rdata=result_address<121?{24'b0,results[result_address]}:0;
   8'h40:rdata=feature_cycles;
   8'h44:rdata=class_cycles;
   8'h48:rdata={14'b0,confidence,token};
   8'h4c:rdata=microphone_count;
   8'h50:rdata=overflows;
   8'h54:rdata=frame_number;
   8'h58:rdata=capture_count;
   8'h5c:rdata={31'b0,live_enable};
   8'h60:rdata={29'b0,feature_word};
   8'h64:rdata=fp_count!=0 && feature_word<5?feature_fifo[fifo_read_index]:0;
   8'h68:rdata=fp_count!=0?feature_end[fp_read]:0;
   8'h6c:rdata=fp_count!=0?feature_sequence[fp_read]:0;
   8'h70:rdata=lp_count!=0?{16'b0,level_fifo[lp_read]}:0;
   8'h74:rdata=lp_count!=0?level_end[lp_read]:0;
   8'h78:rdata={27'b0,lp_count};
   8'h7c:rdata=CNN_ENABLE!=0 ? 1:0;
   default:begin end
  endcase
  if(addr[7])rdata=cnn_rdata;
 end
 always @(posedge clk)begin
  if(!resetn)begin
   live_enable<=0;last_mic_count<=0;capture_count<=0;next_end<=400;current_end<=0;
   frame_number<=0;overflows<=0;copy_index<=0;copy_start<=0;copy_state<=COPY_IDLE;
   chunk_index<=0;level_sum<=0;fp_write<=0;fp_read<=0;lp_write<=0;lp_read<=0;fp_count<=0;lp_count<=0;
   feature_word<=0;feature_pack<=0;offset_q<=0;scale_q<=0;model_address<=0;input_address<=0;
   result_address<=0;shift1<=0;shift2<=0;shift3<=0;feature_done_q<=0;class_done_q<=0;error_q<=0;
  end else if(clear)begin
   last_mic_count<=counter_clear?0:microphone_count;capture_count<=0;next_end<=400;current_end<=0;
   frame_number<=0;overflows<=0;copy_index<=0;copy_start<=0;copy_state<=COPY_IDLE;
   chunk_index<=0;level_sum<=0;fp_write<=0;fp_read<=0;lp_write<=0;lp_read<=0;fp_count<=0;lp_count<=0;
   feature_done_q<=0;class_done_q<=0;error_q<=0;
  end else begin
   last_mic_count<=microphone_count;
   if(mic_event)begin
    capture_count<=capture_count+1'b1;
    if(chunk_index==159)begin chunk_index<=0;level_sum<=0;end
    else begin chunk_index<=chunk_index+1'b1;level_sum<=level_total[22:0];end
   end
   if(overflow_delta!=0)begin overflows<=overflows+overflow_delta;error_q<=1;end
   case({level_enqueue,level_pop})
    2'b10:lp_count<=lp_count+1'b1;2'b01:lp_count<=lp_count-1'b1;default:begin end
   endcase
   if(level_enqueue)lp_write<=lp_write+1'b1;
   if(level_pop)lp_read<=lp_read+1'b1;
   case({feature_enqueue,feature_pop})
    2'b10:fp_count<=fp_count+1'b1;2'b01:fp_count<=fp_count-1'b1;default:begin end
   endcase
   if(feature_pop)fp_read<=fp_read+1'b1;
   if(feature_enqueue)begin fp_write<=fp_write+1'b1;frame_number<=frame_number+1'b1;end
   if(feature_done)feature_done_q<=1;
   if(class_done)class_done_q<=1;
   if(feature_valid)feature_pack[feature_index[1:0]*8+:8]<=feature_data;
   if(manual_start)begin feature_done_q<=0;current_end<=0;end
   if(class_start)class_done_q<=0;
   if(live_enable)case(copy_state)
    COPY_IDLE:if(!feature_busy && fp_count<16 && pending_samples>=0)begin
     if(pending_samples>112)begin next_end<=next_end+160;end
     else begin copy_start<=next_end[8:0]-9'd400;copy_index<=0;current_end<=next_end;copy_state<=COPY_START;end
    end
    COPY_START:copy_state<=COPY_READ;
    COPY_READ:copy_state<=COPY_SEND;
    COPY_SEND:if(feature_ready)begin
     if(copy_index==399)begin copy_state<=COPY_IDLE;next_end<=next_end+160;end
     else begin copy_index<=copy_index+1'b1;copy_state<=COPY_READ;end
    end
   endcase
   if(access)case(addr[7:0])
    8'h10:if(!class_busy)model_address<=wdata[10:0];
    8'h14:if(!class_busy)model_address<=model_address+1'b1;
    8'h18:if(!class_busy)begin shift1<=wdata[4:0];shift2<=wdata[12:8];shift3<=wdata[20:16];end
    8'h1c:offset_q<=wdata;
    8'h20:scale_q<=wdata;
    8'h30:if(!class_busy)input_address<=wdata[3:0];
    8'h34:if(input_write)input_address<=input_address+1'b1;
    8'h38:result_address<=wdata[6:0];
    8'h5c:if(!feature_busy && copy_state==COPY_IDLE)live_enable<=wdata[0];
    8'h60:feature_word<=wdata[2:0];
    default:begin end
   endcase
  end
 end
endmodule
