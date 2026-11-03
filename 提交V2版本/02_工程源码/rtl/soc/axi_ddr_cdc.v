`timescale 1ns/1ps

// 32-bit AXI slave to the Pango DDR controller's 256-bit native AXI port.
// One SYS transaction is packed into one aligned 32-byte DDR beat.  Toggle
// handshakes carry requests across the unrelated SYS and DDR core clocks.
module axi_ddr_cdc(
 input wire sys_clk,input wire sys_resetn,
 input wire[3:0]s_arid,input wire[31:0]s_araddr,input wire[7:0]s_arlen,input wire[2:0]s_arsize,input wire[1:0]s_arburst,input wire s_arvalid,output wire s_arready,
 output reg[3:0]s_rid,output wire[31:0]s_rdata,output reg[1:0]s_rresp,output wire s_rlast,output wire s_rvalid,input wire s_rready,
 input wire[3:0]s_awid,input wire[31:0]s_awaddr,input wire[7:0]s_awlen,input wire[2:0]s_awsize,input wire[1:0]s_awburst,input wire s_awvalid,output wire s_awready,
 input wire[3:0]s_wid,input wire[31:0]s_wdata,input wire[3:0]s_wstrb,input wire s_wlast,input wire s_wvalid,output wire s_wready,
 output reg[3:0]s_bid,output reg[1:0]s_bresp,output wire s_bvalid,input wire s_bready,
 input wire ddr_clk,input wire ddr_resetn,input wire ddr_init_done,
 output reg[27:0]m_awaddr,output wire m_awuser_ap,output reg[3:0]m_awuser_id,output wire[3:0]m_awlen,output reg m_awvalid,input wire m_awready,
 output reg[255:0]m_wdata,output reg[31:0]m_wstrb,input wire m_wready,input wire[3:0]m_wusero_id,input wire m_wusero_last,
 output reg[27:0]m_araddr,output wire m_aruser_ap,output reg[3:0]m_aruser_id,output wire[3:0]m_arlen,output reg m_arvalid,input wire m_arready,
 input wire[255:0]m_rdata,input wire[3:0]m_rid,input wire m_rlast,input wire m_rvalid
);
 assign m_awuser_ap=0;assign m_aruser_ap=0;assign m_awlen=0;assign m_arlen=0;
 reg rd_rsp_t,wr_rsp_t;reg[255:0]rd_rsp_data;
 // SYS-domain read request/response.
 reg rd_req_t,rd_wait,rd_have,rd_local_err;reg[31:0]rd_req_addr,rd_cur_addr;reg[7:0]rd_beats_left;reg[255:0]rd_line;
 reg[1:0]rd_rsp_sync; wire rd_req_bad=(s_arlen>7)||(s_arsize!=2)||((s_arburst!=0)&&(s_arburst!=1))||({1'b0,s_araddr[4:0]}+(({1'b0,s_arlen}+1)<<2)>33);
 reg[1:0]init_sys_sync;wire cpu_ddr_ready=init_sys_sync[1];
 always@(posedge sys_clk)if(!sys_resetn)init_sys_sync<=0;else init_sys_sync<={init_sys_sync[0],ddr_init_done};
 assign s_arready=cpu_ddr_ready&&!rd_wait&&!rd_have;
 assign s_rvalid=rd_have;
 assign s_rdata=rd_line[{rd_cur_addr[4:2],5'b0}+:32];
 assign s_rlast=(rd_beats_left==0);
 always @(posedge sys_clk)begin
  if(!sys_resetn)begin rd_req_t<=0;rd_wait<=0;rd_have<=0;rd_local_err<=0;rd_req_addr<=0;rd_cur_addr<=0;rd_beats_left<=0;rd_line<=0;s_rid<=0;s_rresp<=0;rd_rsp_sync<=0;end
  else begin
   rd_rsp_sync<={rd_rsp_sync[0],rd_rsp_t};
   if(s_arvalid&&s_arready)begin s_rid<=s_arid;rd_cur_addr<=s_araddr;rd_beats_left<=s_arlen;rd_local_err<=rd_req_bad;s_rresp<=rd_req_bad?2'b11:2'b00;
    if(rd_req_bad)begin rd_line<=0;rd_have<=1;end else begin rd_req_addr<=s_araddr;rd_req_t<=~rd_req_t;rd_wait<=1;end end
   if(rd_wait&&(rd_rsp_sync[1]==rd_req_t))begin rd_line<=rd_rsp_data;rd_wait<=0;rd_have<=1;s_rresp<=0;end
   if(rd_have&&s_rready)begin if(rd_beats_left==0)rd_have<=0;else begin rd_beats_left<=rd_beats_left-1'b1;rd_cur_addr<=rd_cur_addr+4;end end
  end
 end

 // SYS-domain write gather.
 reg wr_collect,wr_wait,wr_resp;reg[31:0]wr_addr,wr_req_addr;reg[7:0]wr_left;reg[3:0]wr_req_id;reg[255:0]wr_req_data;reg[31:0]wr_req_strb;reg wr_req_t;reg[1:0]wr_rsp_sync;reg wr_bad;
 assign s_awready=cpu_ddr_ready&&!wr_collect&&!wr_wait&&!wr_resp;
 assign s_wready=wr_collect;
 assign s_bvalid=wr_resp;
 wire aw_bad=(s_awlen>7)||(s_awsize!=2)||((s_awburst!=0)&&(s_awburst!=1))||({1'b0,s_awaddr[4:0]}+(({1'b0,s_awlen}+1)<<2)>33);
 integer wb;
 always @(posedge sys_clk)begin
  if(!sys_resetn)begin wr_collect<=0;wr_wait<=0;wr_resp<=0;wr_addr<=0;wr_req_addr<=0;wr_left<=0;wr_req_id<=0;wr_req_data<=0;wr_req_strb<=0;wr_req_t<=0;wr_rsp_sync<=0;wr_bad<=0;s_bid<=0;s_bresp<=0;end
  else begin
   wr_rsp_sync<={wr_rsp_sync[0],wr_rsp_t};
   if(s_awvalid&&s_awready)begin wr_collect<=1;wr_addr<=s_awaddr;wr_req_addr<=s_awaddr;wr_left<=s_awlen;wr_req_id<=s_awid;wr_req_data<=0;wr_req_strb<=0;wr_bad<=aw_bad;s_bid<=s_awid;end
   if(wr_collect&&s_wvalid)begin
    if(!wr_bad&&(s_wid==wr_req_id))begin for(wb=0;wb<4;wb=wb+1)if(s_wstrb[wb])begin wr_req_data[((wr_addr[4:2]*32)+(wb*8))+:8]<=s_wdata[(wb*8)+:8];wr_req_strb[(wr_addr[4:2]*4)+wb]<=1;end end
    if((wr_left==0)||s_wlast)begin wr_collect<=0;if(wr_bad||(s_wid!=wr_req_id)||(s_wlast!=(wr_left==0)))begin s_bresp<=2'b11;wr_resp<=1;end else begin wr_req_t<=~wr_req_t;wr_wait<=1;s_bresp<=0;end end
    else begin wr_left<=wr_left-1'b1;wr_addr<=wr_addr+4;end
   end
   if(wr_wait&&(wr_rsp_sync[1]==wr_req_t))begin wr_wait<=0;wr_resp<=1;s_bresp<=0;end
   if(wr_resp&&s_bready)wr_resp<=0;
  end
 end

 // DDR-domain native-port state machines. Payload buses remain stable while
 // their toggle request is outstanding, so a two-flop control synchronizer is
 // sufficient for this bundled-data crossing.
 reg[1:0]rd_req_sync,wr_req_sync;reg rd_seen,wr_seen;
 reg rd_inflight;reg[1:0]wr_state;
 always @(posedge ddr_clk)begin
  if(!ddr_resetn)begin rd_req_sync<=0;wr_req_sync<=0;rd_seen<=0;wr_seen<=0;rd_rsp_t<=0;wr_rsp_t<=0;rd_rsp_data<=0;rd_inflight<=0;wr_state<=0;m_araddr<=0;m_aruser_id<=0;m_arvalid<=0;m_awaddr<=0;m_awuser_id<=0;m_awvalid<=0;m_wdata<=0;m_wstrb<=0;end
  else begin
   rd_req_sync<={rd_req_sync[0],rd_req_t};wr_req_sync<={wr_req_sync[0],wr_req_t};
   if(ddr_init_done&&!rd_inflight&&(rd_req_sync[1]!=rd_seen))begin m_araddr<={rd_req_addr[29:5],3'b000};m_aruser_id<=s_rid;m_arvalid<=1;rd_inflight<=1;rd_seen<=rd_req_sync[1];end
   if(m_arvalid&&m_arready)m_arvalid<=0;
   if(rd_inflight&&m_rvalid)begin rd_rsp_data<=m_rdata;rd_rsp_t<=rd_seen;rd_inflight<=0;end
   case(wr_state)
    0:if(ddr_init_done&&(wr_req_sync[1]!=wr_seen))begin m_awaddr<={wr_req_addr[29:5],3'b000};m_awuser_id<=wr_req_id;m_wdata<=wr_req_data;m_wstrb<=wr_req_strb;m_awvalid<=1;wr_seen<=wr_req_sync[1];wr_state<=1;end
    1:if(m_awvalid&&m_awready)begin m_awvalid<=0;wr_state<=2;end
    2:if(m_wready)begin wr_rsp_t<=wr_seen;wr_state<=0;end
    default:wr_state<=0;
   endcase
  end
 end
endmodule
