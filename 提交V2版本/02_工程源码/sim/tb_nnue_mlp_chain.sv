`timescale 1ns/1ps
module tb_nnue_mlp_chain #(parameter integer CASES=6,parameter integer DENSE_PROFILE=1);
 reg clk=0;always #10 clk=~clk;
 reg resetn=0,start=0,abort=0,fvalid=0;reg[31:0]source=0;reg[8:0]fi=0;reg[15:0]fd=0;
 wire busy,done,error,fready;wire signed[31:0]score;wire[31:0]cycles;wire[3:0]jobs;
 wire rw;wire[7:0]ra;wire[31:0]rd,status;
 wire iwe,wwe,ovalid,oready;wire[10:0]ia,wa;wire[63:0]idata;wire[4:0]ww;wire[31:0]wdata,odata;wire[12:0]oi;
 wire nq,nready,nrr;wire[31:0]naddr;wire[2:0]nlen;
 wire dq,dready,drready,dwrite,dwv,dwl,irq;wire[31:0]daddr,dwd;wire[2:0]dlen;wire[3:0]dwstrb;
 reg active=0,owner=0;reg[31:0]address=0;reg[3:0]left=0;
 reg[31:0]memory[0:CASES*16384-1],golden[0:CASES*66-1];reg[15:0]features[0:CASES*512-1];
 integer ticks=0,c,i,reads=0,maxcycles=0;
 wire rspvalid=active && ticks%7!=0;
 wire rspready=owner?nrr:drready;
 wire rsplast=left==1;
 wire[31:0]rspdata=memory[address[19:2]];
 assign nready=!active&&ticks%11!=0;
 assign dready=!active&&!nq&&ticks%11!=0;
 nnue_mlp_chain #(.DDR_BASE(0),.DDR_BYTES(1048576)) chain(
  .clk(clk),.resetn(resetn),.start(start),.abort(abort),.stack_source(source),
  .busy(busy),.done(done),.error(error),.score(score),.cycles(cycles),.jobs(jobs),
  .feature_valid(fvalid),.feature_ready(fready),.feature_index(fi),.feature_data(fd),
  .mac_reg_we(rw),.mac_reg_addr(ra),.mac_reg_data(rd),.mac_status(status),
  .link_input_we(iwe),.link_input_addr(ia),.link_input_data(idata),
  .link_weight_we(wwe),.link_weight_addr(wa),.link_weight_word(ww),.link_weight_data(wdata),
  .link_output_valid(ovalid),.link_output_ready(oready),.link_output_index(oi),.link_output_data(odata),
  .mem_req_valid(nq),.mem_req_ready(nready),.mem_req_addr(naddr),.mem_req_len(nlen),
  .mem_rsp_valid(rspvalid&&owner),.mem_rsp_ready(nrr),.mem_rsp_rdata(rspdata),.mem_rsp_last(rsplast),.mem_rsp_error(1'b0));
 mac_accel_dma_kernel #(.DDR_BYTES(1048576),.HALF_OUTPUT(DENSE_PROFILE),.WEIGHT_BANK_LINES(64),.ENABLE_FP8(0),.ENABLE_LOCAL_LINK(1)) dense(
  .clk(clk),.resetn(resetn),.reg_wr_en(rw),.reg_wr_addr(ra),.reg_wr_data(rd),.reg_wr_strb(4'hf),
  .reg_rd_addr(8'h0c),.reg_rd_data(status),.mem_req_valid(dq),.mem_req_ready(dready),.mem_req_write(dwrite),
  .mem_req_addr(daddr),.mem_req_len(dlen),.mem_w_valid(dwv),.mem_w_ready(1'b0),
  .mem_w_data(dwd),.mem_w_strb(dwstrb),.mem_w_last(dwl),
  .mem_rsp_valid(rspvalid&&!owner),.mem_rsp_ready(drready),.mem_rsp_rdata(rspdata),.mem_rsp_last(rsplast),.mem_rsp_error(1'b0),.irq(irq),
  .link_input_we(iwe),.link_input_addr(ia),.link_input_data(idata),.link_weight_we(wwe),
  .link_weight_addr(wa),.link_weight_word(ww),.link_weight_data(wdata),
  .link_output_valid(ovalid),.link_output_ready(oready),.link_output_index(oi),.link_output_data(odata));
 always @(posedge clk)begin
  ticks<=ticks+1;if(ticks>3000000)$fatal(1,"timeout state=%0d layer=%0d dense=%h",chain.state,chain.layer,status);
  if(resetn)begin
   if(dq&&dwrite || dwv)$fatal(1,"intermediate DDR write");
   if(nq&&nready)begin active<=1;owner<=1;address<=naddr;left<={1'b0,nlen}+1'b1;end
   else if(dq&&dready)begin active<=1;owner<=0;address<=daddr;left<={1'b0,dlen}+1'b1;end
   if(rspvalid&&rspready)begin
    reads<=reads+1;address<=address+4;left<=left-1'b1;if(left==1)active<=0;
   end
   if(chain.state==8)begin
    if(chain.accum[chain.act_index]!==golden[c*66+chain.layer*32+chain.act_index])
     $fatal(1,"case%0d layer%0d lane%0d got%h want%h",c,chain.layer,chain.act_index,chain.accum[chain.act_index],golden[c*66+chain.layer*32+chain.act_index]);
   end
  end
 end
 initial begin
  $readmemh("model.hex",memory);$readmemh("golden.hex",golden);$readmemh("features.hex",features);
  repeat(4)@(negedge clk);resetn=1;
  for(c=0;c<CASES;c=c+1)begin
   reads=0;source=c*65536;start=1;@(negedge clk);start=0;
   for(i=0;i<512;i=i+1)begin
    fi=i;fd=features[c*512+i];fvalid=1;
    while(!fready)@(negedge clk);
    @(negedge clk);fvalid=0;if(i%17==0)@(negedge clk);
   end
   while(!done)@(negedge clk);
   if(error||score!==golden[c*66+65]||jobs!=6)$fatal(1,"case%0d final got%0d want%0d jobs%0d error%0d",c,score,$signed(golden[c*66+65]),jobs,error);
   if(reads!=8801)$fatal(1,"DDR budget got%0d want8801words",reads);
   if(cycles>maxcycles)maxcycles=cycles;
   if(dense.cfg_local!=0)$fatal(1,"legacy local mode leaked");
  end
  $display("NNUE_MLP_CHAIN_PASS cases=%0d layers=3 no_intermediate_DDR_write max_cycles=%0d",CASES,maxcycles);$finish;
 end
endmodule
