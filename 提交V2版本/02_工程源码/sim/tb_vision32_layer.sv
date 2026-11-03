`timescale 1ns/1ps
module tb_vision32_layer;
 parameter CASES=79, SOC=0;
 reg clk=0; always #5 clk=~clk;
 reg resetn=0,wr=0;
 reg [7:0] wa=0,ra=0;
 reg [31:0] wd=0;
 reg [3:0] ws=15;
 wire [31:0] rd;
 wire req,ready,rwrite,wvalid,wready,wlast,rvalid,rready,rlast,rerror;
 wire [31:0] addr,wdata,rdata;
 wire [2:0] len;
 wire [3:0] strb;
 reg [31:0] memory[0:262143],cfg[0:15],ctl[0:5];
 reg [7:0] gold[0:131071];
 reg [31:0] rnd=32'h97531;
 reg active=0,is_write=0,rv=0,rl=0,re=0;
 reg [31:0] bus_addr=0,rrdata=0;
 reg [3:0] left=0;
 reg [1:0] phase=0;
 integer case_id=0,clock_count=0,read_beats=0,write_beats=0,writes_seen=0;
 integer fault=0,write_started_at=0;
 wire hold_read=(fault==3 || fault==5) && clock_count<220;
 wire hold_write_response=fault==4 && clock_count<write_started_at+60;
 assign ready=!active && rnd[0];
 assign wready=active && is_write && phase==0 && rnd[1];
 assign rvalid=rv;
 assign rdata=rrdata;
 assign rlast=rl;
 assign rerror=re;
 wire abort_unused;
 generate if(!SOC)begin:g_direct
  vision32_layer #(.DDR_BASE(32'h1b000000),.DDR_BYTES(1048576)) dut(
   .clk(clk),.resetn(resetn),.reg_wr_en(wr),.reg_wr_addr(wa),.reg_wr_data(wd),.reg_wr_strb(ws),
   .reg_rd_addr(ra),.reg_rd_data(rd),
   .mem_req_valid(req),.mem_req_ready(ready),.mem_req_write(rwrite),.mem_req_addr(addr),.mem_req_len(len),
   .mem_w_valid(wvalid),.mem_w_ready(wready),.mem_w_data(wdata),.mem_w_strb(strb),.mem_w_last(wlast),
   .mem_rsp_valid(rvalid),.mem_rsp_ready(rready),.mem_rsp_rdata(rdata),.mem_rsp_last(rlast),.mem_rsp_error(rerror),
   .mem_abort(abort_unused));
 end else begin:g_soc
  // A wrapper below exposes the existing top's AXI adapter through the same RAM.
  vision32_soc_mem_bridge dut(.clk(clk),.resetn(resetn),.wr(wr),.wa(wa),.wd(wd),.ws(ws),.ra(ra),.rd(rd),
   .req(req),.ready(ready),.rwrite(rwrite),.addr(addr),.len(len),.wvalid(wvalid),.wready(wready),
   .wdata(wdata),.strb(strb),.wlast(wlast),.rvalid(rvalid),.rready(rready),.rdata(rdata),.rlast(rlast),.rerror(rerror));
 end endgenerate
 integer b;
 always @(posedge clk)begin
  rnd<={rnd[30:0],rnd[31]^rnd[21]^rnd[1]^rnd[0]};
  if(!resetn)begin active<=0;rv<=0;phase<=0;end
  else begin
   if(req && ready)begin
    if(addr[1:0]!=0 || addr<32'h1b000000 || addr+4*(len+1)>32'h1b100000 ||
       {1'b0,addr[4:0]}+4*(len+1)>32)$fatal(1,"BAD_REQUEST_NATIVE_LINE %h len%0d",addr,len);
    active<=1;is_write<=rwrite;bus_addr<=addr;left<=len+1;phase<=0;
    if(rwrite)begin writes_seen<=writes_seen+1;write_started_at<=clock_count;end
   end
   if(active && !is_write && !rv && rnd[2] && !hold_read)begin
    rv<=1;rrdata<=memory[(bus_addr-32'h1b000000)>>2];rl<=left==1;re<=fault==1;
   end
   if(wvalid && wready)begin
    if(wlast!=(left==1))$fatal(1,"BAD_WLAST");
    if(bus_addr<({cfg[2][31:2],2'b00}) || bus_addr>=((cfg[2]+ctl[0]+3)&32'hfffffffc))
      $fatal(1,"WRITE_OUTSIDE_OUTPUT %h",bus_addr);
    for(b=0;b<4;b=b+1)if(strb[b])memory[(bus_addr-32'h1b000000)>>2][b*8+:8]<=wdata[b*8+:8];
    write_beats<=write_beats+1;
    if(left==1)phase<=1;
    else begin bus_addr<=bus_addr+4;left<=left-1;end
   end
   if(active && is_write && phase==1 && !rv && rnd[2] && !hold_write_response)begin
    rv<=1;rrdata<=0;rl<=1;re<=fault==2;
   end
   if(rv && rready)begin
    rv<=0;
    if(!is_write)read_beats<=read_beats+1;
    if(rl)begin active<=0;phase<=0;end
    else begin bus_addr<=bus_addr+4;left<=left-1;end
   end
  end
 end
 task write_reg(input [7:0] a,input [31:0] d);
 begin
  @(negedge clk);wr=1;wa=a;wd=d;ws=15;
  @(negedge clk);wr=0;
 end endtask
 integer j,n,t,oi,offset,aborted;
 reg [31:0] status,counter;
 reg [7:0] actual;
 string name;
 initial begin
  repeat(5)@(negedge clk);resetn=1;
  ra=8'h40;#1;
  if(rd!==32'h56333231)$fatal(1,"ID %h",rd);
  for(case_id=0;case_id<CASES;case_id=case_id+1)begin
   $readmemh($sformatf("case-%0d.cfg",case_id),cfg);
   $readmemh($sformatf("case-%0d.ctl",case_id),ctl);
   $readmemh($sformatf("case-%0d.mem",case_id),memory);
   $readmemh($sformatf("case-%0d.gold",case_id),gold,0,ctl[0]-1);
   offset=cfg[2]-32'h1b000000;
   for(j=(offset/4)-4;j<(offset+ctl[0]+3)/4+4;j=j+1)
     if(j>=0 && j<262144)memory[j]=32'ha5a5a5a5;
   for(j=0;j<16;j=j+1)begin write_reg(8'h4c,j);write_reg(8'h50,cfg[j]);end
   fault=ctl[2];if(fault==5)begin write_reg(8'h4c,13);write_reg(8'h50,40);end
   clock_count=0;read_beats=0;write_beats=0;writes_seen=0;aborted=0;
   write_reg(8'h48,1);
   // Configuration attempts during a job must not change the active descriptor.
   write_reg(8'h4c,5);write_reg(8'h50,0);
   ra=8'h44;
   begin:poll_done
    for(t=0;t<10000000;t=t+1)begin
     @(negedge clk);clock_count=clock_count+1;ra=8'h44;#1;status=rd;
     if((fault==3 && active && !is_write && !aborted) ||
        (fault==4 && writes_seen>0 && !aborted))begin
       write_reg(8'h48,2);aborted=1;
       repeat(5)@(negedge clk);
       ra=8'h44;#1;if(!rd[0])$fatal(1,"ABORT_DID_NOT_DRAIN");
     end
     if(!status[0] && status[1])disable poll_done;
    end
    $fatal(1,"POLL_TIMEOUT case%0d status%h",case_id,status);
   end
   if(status[2]!==ctl[1][0])$fatal(1,"STATUS case%0d got%h expectederror%0d",case_id,status,ctl[1]);
   if(active || rv)$fatal(1,"COMPLETED_WITH_BUS_OUTSTANDING");
   if(!ctl[1])begin
    for(j=0;j<ctl[0];j=j+1)begin
     oi=offset+j;actual=memory[oi/4]>>(8*(oi%4));
     if(actual!==gold[j])$fatal(1,"MISMATCH case%0d byte%0d got%h expected%h",case_id,j,actual,gold[j]);
    end
    for(j=offset-16;j<offset+ctl[0]+16;j=j+1)if(j>=0 && j<1048576 && (j<offset || j>=offset+ctl[0]))begin
     actual=memory[j/4]>>(8*(j%4));if(actual!==8'ha5)$fatal(1,"CANARY case%0d byte%0d",case_id,j);
    end
    ra=8'h60;#1;if(rd!==ctl[3])$fatal(1,"MAC_CYCLES case%0d got%0d expected%0d",case_id,rd,ctl[3]);
   end
   ra=8'h58;#1;if(rd!==read_beats*4)$fatal(1,"READ_COUNTER");
   ra=8'h5c;#1;if(rd!==write_beats*4)$fatal(1,"WRITE_COUNTER");
   ra=8'h54;#1;
   $display("VISION32_CASE_PASS index=%0d cycles=%0d reads=%0d writes=%0d error=%0d",case_id,rd,read_beats*4,write_beats*4,ctl[1]);
   write_reg(8'h48,4);
  end
  $display("VISION32_ALL_PASS cases=%0d soc=%0d",CASES,SOC);$finish;
 end
 initial begin #20000000000;$fatal(1,"SIM_TIMEOUT");end
endmodule

// Exercise the actual MAC top-level owner arbitration and AXI32 adapter.
// The test RAM sees address commands only after their actual AXI handshake.
module vision32_soc_mem_bridge(
 input wire clk,resetn,wr,input wire [7:0] wa,input wire [31:0] wd,
 input wire [3:0] ws,input wire [7:0] ra,output wire [31:0] rd,
 output wire req,input wire ready,output wire rwrite,output wire [31:0] addr,
 output wire [2:0] len,output wire wvalid,input wire wready,
 output wire [31:0] wdata,output wire [3:0] strb,output wire wlast,
 input wire rvalid,output wire rready,input wire [31:0] rdata,input wire rlast,rerror
);
 wire [31:0] araddr,awaddr;
 wire [7:0] arlen,awlen;
 wire [2:0] arsize,awsize;
 wire [1:0] arburst,awburst;
 wire arvalid,awvalid,rrdy,brdy;
 reg bus_write;
 always @(posedge clk)begin
  if(!resetn)bus_write<=0;
  else if(req && ready)bus_write<=rwrite;
 end
 assign req=arvalid || awvalid;
 assign rwrite=awvalid;
 assign addr=awvalid?awaddr:araddr;
 assign len=awvalid?awlen[2:0]:arlen[2:0];
 assign rready=bus_write?brdy:rrdy;
 mac_accel_ddr_kernel_top #(.DDR_BASE(32'h1b000000),.DDR_BYTES(1048576),
  .ENABLE_H128_SPARSE(0),.ENABLE_PFF1_GATHER(1),.ENABLE_NNUE_PIPELINE(1),
  .PIKAFISH_ONLY(1),.ENABLE_CONV(1),.ENABLE_VISION32(1)) u_soc(
  .clk(clk),.resetn(resetn),.reg_wr_en(wr),.reg_wr_addr({1'b0,wa}),
  .reg_wr_data(wd),.reg_wr_strb(ws),.reg_rd_addr({1'b0,ra}),.reg_rd_data(rd),.irq(),
  .m_axi_awaddr(awaddr),.m_axi_awlen(awlen),.m_axi_awsize(awsize),.m_axi_awburst(awburst),
  .m_axi_awvalid(awvalid),.m_axi_awready(ready),
  .m_axi_wdata(wdata),.m_axi_wstrb(strb),.m_axi_wlast(wlast),.m_axi_wvalid(wvalid),.m_axi_wready(wready),
  .m_axi_bresp(rerror?2'b10:2'b00),.m_axi_bvalid(rvalid && bus_write),.m_axi_bready(brdy),
  .m_axi_araddr(araddr),.m_axi_arlen(arlen),.m_axi_arsize(arsize),.m_axi_arburst(arburst),
  .m_axi_arvalid(arvalid),.m_axi_arready(ready && !awvalid),
  .m_axi_rdata(rdata),.m_axi_rresp(rerror?2'b10:2'b00),.m_axi_rlast(rlast),
  .m_axi_rvalid(rvalid && !bus_write),.m_axi_rready(rrdy));
endmodule
