`timescale 1ns/1ps
// Autonomous dependent StageA jobs + optional exact existing NNUE pipeline.
// Context addresses are a private virtual scratch subwindow: they terminate in
// synchronous SRAM here, never at DDR. Context validity is per batch. CPU
// rollback exports are explicit and happen only after all computation succeeds.
module pikafish_eval_batch #(
 parameter [31:0] DDR_BASE=32'h1b000000,
 parameter integer DDR_BYTES=1048576,
 parameter integer CONTEXT_OFFSET=20'hf0000
)(
 input wire clk,resetn,reg_wr_en,
 input wire [6:0] reg_wr_addr,reg_rd_addr,
 input wire [31:0] reg_wr_data,input wire [3:0] reg_wr_strb,
 output reg [31:0] reg_rd_data,output wire active,
 input wire engines_busy,
 output reg gather_we,output reg [7:0] gather_addr,
 output reg [31:0] gather_data,input wire [31:0] gather_status,
 output reg nnue_we,output reg [6:0] nnue_addr,nnue_read_addr,
 output reg [31:0] nnue_data,input wire [31:0] nnue_read_data,
 // Intercept only the gather's local context transactions.
 input wire g_req_valid,g_req_write,input wire [31:0] g_req_addr,
 input wire [2:0] g_req_len,input wire g_external_ready,output wire local_select,local_owned,
 output wire local_req_ready,local_w_ready,local_rsp_valid,
 output wire [31:0] local_rsp_data,output wire local_rsp_last,local_rsp_error,
 input wire g_w_valid,g_w_last,input wire [31:0] g_w_data,
 input wire [3:0] g_w_strb,input wire g_rsp_ready,
 // Batch list fetches and completed-snapshot exports share the existing adapter.
 output reg mem_req_valid,output reg mem_req_write,
 output reg [31:0] mem_req_addr,output reg [2:0] mem_req_len,
 input wire mem_req_ready,
 output reg mem_w_valid,output wire [31:0] mem_w_data,
 output wire [3:0] mem_w_strb,output wire mem_w_last,input wire mem_w_ready,
 input wire mem_rsp_valid,mem_rsp_last,mem_rsp_error,
 input wire [31:0] mem_rsp_rdata,output reg mem_rsp_ready
);
 localparam [31:0] CONTEXT_BASE=DDR_BASE+CONTEXT_OFFSET;
 localparam I=0,JREQ=1,JREAD=2,CHECK=3,GCFG=4,GWAIT=5,
  VCFG=6,VWAIT=7,VFEED=8,VCMIT=9,NCFG=10,NWAIT=11,NSCORE=12,
  EXPORT_NEXT=13,XREQ=14,XWAIT=15,XWRITE=16,XRESP=17,DRAIN=18,
  N_ABORT=19,N_DRAIN=20;
 reg [4:0] state;
 reg done,error,stop_q;
 reg [7:0] error_code;
 reg [31:0] list_q,stack_q,config_q,cycles,score_q;
 reg [3:0] count_q,completed;
 reg count_valid;
 reg [2:0] job_index,export_slot;
 reg [3:0] step;
 reg [31:0] job[0:7];
 reg [31:0] exports[0:7];
 reg [7:0] valid_slots;
 reg [8:0] word_index;
 reg view_q;
 reg [31:0] external_read_words,local_read_words,local_write_words,export_words;
 reg [3:0] x_remaining;
 reg [31:0] contexts[0:4095];
 reg [31:0] context_q;
 wire [2:0] selected_slot=view_q?config_q[6:4]:config_q[2:0];
 // Independent local burst endpoint, with one SRAM read wait cycle.
 localparam L_IDLE=0,L_WAIT=1,L_READ=2,L_WRITE=3,L_RESP=4;
 reg [2:0] local_state;
 reg [11:0] local_word;
 reg [3:0] local_left;
 reg local_error_q;
 wire [32:0] local_limit={1'b0,g_req_addr}+(({30'b0,g_req_len}+1)<<2);
 assign active=state!=I;
 assign local_select=active && g_req_addr>=CONTEXT_BASE &&
   g_req_addr<CONTEXT_BASE+16384;
 assign local_owned=local_state!=L_IDLE;
 assign local_req_ready=local_state==L_IDLE;
 assign local_w_ready=local_state==L_WRITE;
 assign local_rsp_valid=local_state==L_READ || local_state==L_RESP;
 assign local_rsp_data=local_state==L_READ?context_q:0;
 assign local_rsp_last=local_state==L_RESP || local_left==1;
 assign local_rsp_error=local_error_q;
 wire local_accept=g_req_valid && local_select && local_req_ready;
 wire local_write=local_state==L_WRITE && g_w_valid;
 wire local_read=local_state==L_READ && g_rsp_ready;
 wire export_send=state==XWRITE && mem_w_ready;
 wire view_send=state==VFEED;
 wire [11:0] normal_read={state==VWAIT || state==VFEED || state==VCMIT ?
     selected_slot:export_slot,word_index};
 wire [11:0] context_read=local_owned ? local_word :
   ((view_send || export_send) ? normal_read+12'd1:normal_read);
 assign mem_w_data=context_q;
 assign mem_w_strb=4'hf;
 assign mem_w_last=x_remaining==1;
 wire response=mem_rsp_valid && mem_rsp_ready;
 wire parent_local=job[0]>=CONTEXT_BASE && job[0]<CONTEXT_BASE+16384;
 wire [2:0] parent_slot=job[0][13:11];
 wire parent_valid=job[0][1:0]==0 && job[0]>=DDR_BASE &&
   {1'b0,job[0]}+33'd2048<={1'b0,DDR_BASE}+DDR_BYTES &&
   (parent_local ? (job[0][10:0]==0 && valid_slots[parent_slot]) :
   !(job[0]<CONTEXT_BASE+16384 && {1'b0,job[0]}+33'd2048>{1'b0,CONTEXT_BASE}));
 wire descriptor_valid=job[1][1:0]==0 && job[1]>=DDR_BASE &&
   {1'b0,job[1]}+({1'b0,job[2]}<<2)<={1'b0,DDR_BASE}+DDR_BYTES &&
   !(job[1]<CONTEXT_BASE+16384 && {1'b0,job[1]}+({1'b0,job[2]}<<2)>{1'b0,CONTEXT_BASE});
 wire export_valid=job[3]==0 || (job[3][1:0]==0 && job[3]>=DDR_BASE &&
   {1'b0,job[3]}+33'd2048<={1'b0,DDR_BASE}+DDR_BYTES &&
   !(job[3]<CONTEXT_BASE+16384 && {1'b0,job[3]}+33'd2048>{1'b0,CONTEXT_BASE}));
 wire header_valid=CONTEXT_OFFSET%16384==0 && CONTEXT_OFFSET+16384<=DDR_BYTES &&
   count_valid && count_q!=0 && count_q<=8 && list_q[4:0]==0 &&
   list_q>=DDR_BASE && {1'b0,list_q}+({29'b0,count_q}<<5)<={1'b0,DDR_BASE}+DDR_BYTES &&
   !(list_q<CONTEXT_BASE+16384 && {1'b0,list_q}+({29'b0,count_q}<<5)>{1'b0,CONTEXT_BASE}) &&
   (config_q & 32'hfffff888)==0 && (!config_q[9] ||
   (stack_q[1:0]==0 && stack_q>=DDR_BASE &&
   {1'b0,stack_q}+33'h8a84<={1'b0,DDR_BASE}+DDR_BYTES &&
   !(stack_q<CONTEXT_BASE+16384 && {1'b0,stack_q}+33'h8a84>{1'b0,CONTEXT_BASE})));
 always @(posedge clk)begin
  context_q<=contexts[context_read];
  if(local_write)contexts[local_word]<=g_w_data;
 end
 always @(posedge clk)begin
  if(!resetn)begin
   local_state<=L_IDLE;local_word<=0;local_left<=0;local_error_q<=0;
  end else case(local_state)
   L_IDLE:if(local_accept)begin
    local_word<=(g_req_addr-CONTEXT_BASE)>>2;
    local_left<={1'b0,g_req_len}+1'b1;
    local_error_q<=g_req_addr[1:0]!=0 || local_limit>{1'b0,CONTEXT_BASE}+16384;
    local_state<=g_req_write?L_WRITE:L_WAIT;
   end
   L_WAIT:local_state<=L_READ;
   L_READ:if(g_rsp_ready)begin
    local_word<=local_word+1'b1;local_left<=local_left-1'b1;
    local_state<=local_left==1?L_IDLE:L_WAIT;
   end
   L_WRITE:if(g_w_valid)begin
    if(g_w_strb!=4'hf || g_w_last!=(local_left==1))local_error_q<=1;
    local_word<=local_word+1'b1;local_left<=local_left-1'b1;
    if(local_left==1)local_state<=L_RESP;
   end
   L_RESP:if(g_rsp_ready)local_state<=L_IDLE;
   default:local_state<=L_IDLE;
  endcase
 end
 always @*begin
  reg_rd_data=0;
  case(reg_rd_addr)
   7'h00:reg_rd_data=32'h50464231;
   7'h04:reg_rd_data=32'h00010001;
   7'h0c:reg_rd_data={16'b0,error_code,5'b0,error,done,active};
   7'h10:reg_rd_data=list_q;
   7'h14:reg_rd_data={28'b0,count_q};
   7'h18:reg_rd_data=stack_q;
   7'h1c:reg_rd_data=config_q;
   7'h20:reg_rd_data=cycles;
   7'h24:reg_rd_data={28'b0,completed};
   7'h28:reg_rd_data=score_q;
   7'h2c:reg_rd_data=CONTEXT_BASE;
   7'h30:reg_rd_data=external_read_words;
   7'h34:reg_rd_data=local_read_words;
   7'h38:reg_rd_data=local_write_words;
   7'h3c:reg_rd_data=export_words;
   7'h40:reg_rd_data=32'h00080200; //8 slots,512 words each
   default:begin end
  endcase
  gather_we=0;gather_addr=0;gather_data=0;
  nnue_we=0;nnue_addr=0;nnue_data=0;nnue_read_addr=7'h0c;
  mem_req_valid=0;mem_req_write=0;mem_req_addr=0;mem_req_len=0;
  mem_w_valid=0;mem_rsp_ready=0;
  case(state)
   JREQ:begin mem_req_valid=1;mem_req_addr=list_q+{24'b0,job_index,5'b0};mem_req_len=7;end
   JREAD,DRAIN,XRESP:mem_rsp_ready=1;
   GCFG:begin
    gather_we=1;
    case(step)
     0:begin gather_addr=8'h08;gather_data=2;end
     1:begin gather_addr=8'h10;gather_data=job[0];end
     2:begin gather_addr=8'h14;gather_data=job[1];end
     3:begin gather_addr=8'h18;gather_data=CONTEXT_BASE+{18'b0,job_index,11'b0};end
     4:begin gather_addr=8'h1c;gather_data=job[2];end
     5:begin gather_addr=8'h28;gather_data=0;end
     default:begin gather_addr=8'h08;gather_data=1;end
    endcase
   end
   VCFG:begin
    nnue_we=1;
    case(step)
     0:begin nnue_addr=7'h1c;nnue_data={23'b0,view_q,8'b0};end
     1:begin nnue_addr=7'h20;nnue_data=view_q?2:1;end
     default:begin nnue_addr=7'h08;nnue_data=8;end
    endcase
   end
   VFEED:begin nnue_we=1;nnue_addr=7'h28;nnue_data=context_q;end
   VCMIT:begin nnue_we=1;nnue_addr=7'h08;nnue_data=16;end
   NCFG:begin
    nnue_we=1;
    case(step)
     0:begin nnue_addr=7'h08;nnue_data=2;end
     1:begin nnue_addr=7'h10;nnue_data=stack_q;end
     2:begin nnue_addr=7'h14;nnue_data=1;end
     3:begin nnue_addr=7'h18;nnue_data=2;end
     4:begin nnue_addr=7'h1c;nnue_data={31'b0,config_q[8]};end
     default:begin nnue_addr=7'h08;nnue_data=1;end
    endcase
   end
   NSCORE:nnue_read_addr=7'h2c;
   N_ABORT:begin nnue_we=1;nnue_addr=7'h08;nnue_data=4;end
   XREQ:begin
    mem_req_valid=1;mem_req_write=1;mem_req_len=7;
    mem_req_addr=exports[export_slot]+{21'b0,word_index,2'b0};
   end
   XWRITE:mem_w_valid=1;
   default:begin end
  endcase
 end
 task finish_error;
  input [7:0] code;
  begin state<=I;done<=1;error<=1;error_code<=code;valid_slots<=0;end
 endtask
 integer k;
 always @(posedge clk)begin
  if(!resetn)begin
   state<=I;done<=0;error<=0;stop_q<=0;error_code<=0;
   list_q<=DDR_BASE;stack_q<=DDR_BASE;config_q<=0;count_q<=0;count_valid<=1;
   cycles<=0;score_q<=0;completed<=0;job_index<=0;export_slot<=0;
   step<=0;word_index<=0;view_q<=0;valid_slots<=0;x_remaining<=0;
   external_read_words<=0;local_read_words<=0;local_write_words<=0;export_words<=0;
   for(k=0;k<8;k=k+1)begin job[k]<=0;exports[k]<=0;end
  end else begin
   if(active)cycles<=cycles+1;
   if(local_read)local_read_words<=local_read_words+1;
   if(local_write)local_write_words<=local_write_words+1;
   if(active && g_req_valid && !local_select && g_external_ready && !g_req_write)
    external_read_words<=external_read_words+{29'b0,g_req_len}+1;
   if(reg_wr_en && reg_wr_strb==4'hf)begin
    if(reg_wr_addr==7'h08 && reg_wr_data[2] && active)stop_q<=1;
    if(!active)case(reg_wr_addr)
     7'h10:list_q<=reg_wr_data;
     7'h14:begin count_q<=reg_wr_data[3:0];count_valid<=reg_wr_data[31:4]==0;end
     7'h18:stack_q<=reg_wr_data;
     7'h1c:config_q<=reg_wr_data;
     7'h08:begin
      if(reg_wr_data[1])begin done<=0;error<=0;error_code<=0;end
      if(reg_wr_data[0])begin
       cycles<=0;score_q<=0;completed<=0;job_index<=0;export_slot<=0;
       step<=0;if(!config_q[10])valid_slots<=0;
       done<=0;error<=0;error_code<=0;stop_q<=0;
       local_read_words<=0;local_write_words<=0;external_read_words<=0;export_words<=0;
       if(engines_busy || !header_valid)begin valid_slots<=0;done<=1;error<=1;error_code<=1;end
       else state<=JREQ;
      end
     end
     default:begin end
    endcase
   end
   case(state)
    I:begin end
    JREQ:if(mem_req_ready)begin state<=JREAD;step<=0;end
    JREAD:if(response)begin
     if(mem_rsp_error || mem_rsp_last!=(step==7))begin
      error_code<=2;if(mem_rsp_last)finish_error(2);else state<=DRAIN;
     end else begin
      job[step[2:0]]<=mem_rsp_rdata;step<=step+1;
      if(step==7)state<=CHECK;
     end
    end
    CHECK:begin
     if(stop_q)finish_error(8);
     else if(!parent_valid || !descriptor_valid || !export_valid || job[2]>256 ||
       job[4]!=0 || job[5]!=0 || job[6]!=0 || job[7]!=0)finish_error(3);
     else begin exports[job_index]<=job[3];step<=0;state<=GCFG;end
    end
    GCFG:if(step==6)state<=GWAIT;else step<=step+1;
    GWAIT:if(!gather_status[0] && gather_status[1] && !local_owned)begin
     if(gather_status[2])finish_error(4);
     else if(stop_q)finish_error(8);
     else begin
      valid_slots[job_index]<=1;completed<=completed+1;
      if({1'b0,job_index}+4'd1==count_q)begin
       if(config_q[9])begin
        if((config_q[2:0]>job_index) || (config_q[6:4]>job_index))finish_error(5);
        else begin view_q<=0;step<=0;word_index<=0;state<=VCFG;end
       end else begin export_slot<=0;word_index<=0;state<=EXPORT_NEXT;end
      end else begin job_index<=job_index+1;state<=JREQ;end
     end
    end
    VCFG:if(step==2)begin state<=VWAIT;word_index<=0;end else step<=step+1;
    VWAIT:state<=VFEED;
    VFEED:begin
     word_index<=word_index+1;
     if(word_index==511)state<=VCMIT;
    end
    VCMIT:begin
     if(!view_q)begin view_q<=1;word_index<=0;step<=0;state<=VCFG;end
     else begin step<=0;state<=NCFG;end
    end
    NCFG:if(step==5)state<=NWAIT;else step<=step+1;
    NWAIT:begin
     if(stop_q)state<=N_ABORT;
     else if(!nnue_read_data[0] && nnue_read_data[1])begin
      if(nnue_read_data[2])finish_error(6);else state<=NSCORE;
     end
    end
    NSCORE:begin score_q<=nnue_read_data;export_slot<=0;word_index<=0;state<=EXPORT_NEXT;end
    N_ABORT:state<=N_DRAIN;
    N_DRAIN:if(!nnue_read_data[0])finish_error(8);
    EXPORT_NEXT:begin
     if(stop_q)finish_error(8);
     else if(exports[export_slot]!=0)begin word_index<=0;state<=XREQ;end
     else if({1'b0,export_slot}+4'd1==count_q)begin state<=I;done<=1;end
     else export_slot<=export_slot+1;
    end
    XREQ:if(mem_req_ready)begin x_remaining<=8;state<=XWAIT;end
    XWAIT:state<=XWRITE;
    XWRITE:if(mem_w_ready)begin
     word_index<=word_index+1;x_remaining<=x_remaining-1;
     export_words<=export_words+1;
     if(x_remaining==1)state<=XRESP;
    end
    XRESP:if(response)begin
     if(mem_rsp_error || !mem_rsp_last)begin
      error_code<=7;if(mem_rsp_last)finish_error(7);else state<=DRAIN;
     end else if(word_index==0)begin
      if({1'b0,export_slot}+4'd1==count_q)begin state<=I;done<=1;end
      else begin export_slot<=export_slot+1;state<=EXPORT_NEXT;end
     end else state<=XREQ;
    end
    DRAIN:if(response && mem_rsp_last)finish_error(error_code);
    default:finish_error(255);
   endcase
  end
 end
endmodule
