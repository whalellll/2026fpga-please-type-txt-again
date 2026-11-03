`timescale 1ns/1ps
module tb_nnue_start_frontend;
 reg clk=0;always #10 clk=~clk;
 reg resetn=0,we=0,gb=0,gv=0,gc=0,view=0;
`ifdef SYNTHESIS
 GTP_GRS GRS_INST(.GRS_N(resetn));
`endif
 reg[6:0] wa=0,ra=0;reg[31:0] wd=0,data=0,tag=0;
 reg[8:0] index=0;wire[31:0] rd;wire busy,req,rready;
 wire[31:0] addr;wire[2:0] len;
 integer ticks=0,i,v,mode,warm,reads=0,seen=0,timeout;
 reg active=0;reg[31:0] pointer=0;reg[3:0] left=0;
 reg[31:0] memory[0:262143],accum[0:1023],golden[0:65];
 reg[15:0] features[0:511];
 wire rv=active && ticks%7!=0;
 wire ready=!active && ticks%11!=0;
 nnue_pipeline_frontend #(.DDR_BASE(0),.DDR_BYTES(1048576),.PIKAFISH_ONLY(1)) dut(
  .clk(clk),.resetn(resetn),.reg_wr_en(we),.reg_wr_addr(wa),.reg_wr_data(wd),.reg_wr_strb(4'hf),
  .reg_rd_addr(ra),.reg_rd_data(rd),.gather_begin(gb),.gather_valid(gv),.gather_commit(gc),
  .gather_abort(1'b0),.gather_view(view),.gather_tag(tag),.gather_data(data),.gather_index(index),
  .active(busy),.mac_status(0),.link_output_valid(1'b0),.link_output_index(13'b0),.link_output_data(0),
  .mem_req_valid(req),.mem_req_ready(ready),.mem_req_addr(addr),.mem_req_len(len),
  .mem_rsp_valid(rv),.mem_rsp_ready(rready),.mem_rsp_rdata(memory[pointer[19:2]]),
  .mem_rsp_last(left==1),.mem_rsp_error(1'b0));
 always @(posedge clk)begin
  ticks<=ticks+1;if(ticks>1000000)$fatal(1,"bounded timeout");
  if(!resetn)begin active<=0;left<=0;end else begin
   if(req&&ready)begin active<=1;pointer<=addr;left<={1'b0,len}+1'b1;end
   if(rv&&rready)begin reads<=reads+1;pointer<=pointer+4;left<=left-1'b1;if(left==1)active<=0;end
   if(dut.ft_valid&&dut.ft_ready)begin
    if(dut.ft_data!==features[dut.ft_index])$fatal(1,"feature mismatch mode=%0d pair=%0d",mode,dut.ft_index);
    seen<=seen+1;
   end
  end
 end
 task wr(input[6:0] a,input[31:0] d);
  begin wa=a;wd=d;we=1;@(negedge clk);we=0;@(negedge clk);end
 endtask
 initial begin
  $readmemh("pfsb.hex",memory);$readmemh("accum.hex",accum);
  $readmemh("golden-start.hex",golden);$readmemh("features-start.hex",features);
  repeat(4)@(negedge clk);resetn=1;
  for(mode=0;mode<2;mode=mode+1)begin
   for(v=0;v<2;v=v+1)begin
    if(mode==0)begin
     wr('h1c,v*256);wr('h20,v+1);wr('h08,8);
     for(i=0;i<512;i=i+1)wr('h28,accum[v*512+i]);
     wr('h08,16);
    end else begin
     view=v;tag=v+1;gb=1;@(negedge clk);gb=0;
     for(i=0;i<512;i=i+1)begin index=i;data=accum[v*512+i];gv=1;@(negedge clk);end
     gv=0;gc=1;@(negedge clk);gc=0;@(negedge clk);
    end
   end
   wr('h10,'h64000);wr('h14,1);wr('h18,2);wr('h1c,0);wr('h08,64);
   for(warm=0;warm<2;warm=warm+1)begin
    reads=0;seen=0;wr('h08,1);ra='h0c;timeout=0;#1;
    while((!rd[1]||rd[0])&&timeout<100000)begin @(negedge clk);timeout=timeout+1;end
    if(timeout==100000||rd[2]||seen!=512)$fatal(1,"completion mode=%0d status=%h features=%0d",mode,rd,seen);
    ra='h2c;#1;if(rd!==golden[65])$fatal(1,"score got=%0d want=%0d",$signed(rd),$signed(golden[65]));
    ra='h34;#1;if(rd!=6)$fatal(1,"job count");
    ra='h48;#1;if(rd!=(warm?0:8801)||reads!=rd)$fatal(1,"cache reads");
    @(negedge clk);
   end
  end
  $display("NNUE_START_FRONTEND_PASS bucket=11 score=2392 manual_and_local_link=2 cold_and_warm=2 features_per_job=1024");$finish;
 end
endmodule
