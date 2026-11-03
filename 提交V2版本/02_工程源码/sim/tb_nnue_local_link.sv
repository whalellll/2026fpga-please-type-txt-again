`timescale 1ns/1ps
module tb_nnue_local_link;
 reg clk=0;always #10 clk=~clk;
 reg resetn=0,reg_we=0;reg [7:0] wa=0,ra=8'h0c;reg [31:0] wd=0;wire[31:0]rd;
 reg iwe=0,wwe=0,ready=0;reg[10:0]ia=0,waddr=0;reg[63:0]idata=0;
 reg[4:0]wword=0;reg[31:0]wdata=0;
 wire valid;wire[12:0]index;wire[31:0]data;
 wire req;wire[31:0]memaddr;wire[2:0]memlen;wire memwrite,wvalid,wlast,rready,irq;
 wire[31:0]memdata;wire[3:0]strb;
 mac_accel_dma_kernel #(.DDR_BYTES(1048576),.HALF_OUTPUT(1),.WEIGHT_BANK_LINES(64),.ENABLE_FP8(0),.ENABLE_LOCAL_LINK(1)) dut(
  .clk(clk),.resetn(resetn),.reg_wr_en(reg_we),.reg_wr_addr(wa),.reg_wr_data(wd),.reg_wr_strb(4'hf),
  .reg_rd_addr(ra),.reg_rd_data(rd),.mem_req_valid(req),.mem_req_ready(1'b0),.mem_req_write(memwrite),
  .mem_req_addr(memaddr),.mem_req_len(memlen),.mem_w_valid(wvalid),.mem_w_ready(1'b0),
  .mem_w_data(memdata),.mem_w_strb(strb),.mem_w_last(wlast),.mem_rsp_valid(1'b0),
  .mem_rsp_ready(rready),.mem_rsp_rdata(32'b0),.mem_rsp_last(1'b0),.mem_rsp_error(1'b0),.irq(irq),
  .link_input_we(iwe),.link_input_addr(ia),.link_input_data(idata),.link_weight_we(wwe),
  .link_weight_addr(waddr),.link_weight_word(wword),.link_weight_data(wdata),
  .link_output_valid(valid),.link_output_ready(ready),.link_output_index(index),.link_output_data(data));
 reg[63:0]inputs[0:63];reg[31:0]weights[0:2047],golden[0:31];
 integer i,n,ticks=0;reg held_valid=0;reg[31:0]held_data;reg[12:0]held_index;
 task write_reg(input[7:0]a,input[31:0]v);
  begin wa=a;wd=v;reg_we=1;@(negedge clk);reg_we=0;end
 endtask
 always @(posedge clk)begin
  ticks<=ticks+1;if(ticks>100000)$fatal(1,"bounded timeout");
  if(resetn&&req)$fatal(1,"local job touched DDR");
 end
 initial begin
  $readmemh("input.hex",inputs);$readmemh("weight.hex",weights);$readmemh("golden.hex",golden);
  repeat(4)@(negedge clk);resetn=1;
  for(i=0;i<64;i=i+1)begin iwe=1;ia=i;idata=inputs[i];@(negedge clk);end
  iwe=0;
  for(i=0;i<2048;i=i+1)begin wwe=1;waddr=i/32;wword=i%32;wdata=weights[i];@(negedge clk);end
  wwe=0;
  write_reg(8'h10,32'h01000001);write_reg(8'h14,32'h63000020);write_reg(8'h3c,7);write_reg(8'h08,1);
  n=0;ra=8'h0c;
  while(!(rd&2))begin
   ready=ticks%7!=0;@(posedge clk);
   if(valid)begin
    if(held_valid&&(data!==held_data||index!==held_index))$fatal(1,"local result unstable");
    if(ready)begin
     if(index!==n||data!==golden[n])$fatal(1,"lane%0d got%h want%h",n,data,golden[n]);
     n=n+1;held_valid=0;
    end else begin held_data=data;held_index=index;held_valid=1;end
   end
   @(negedge clk);
  end
  if(n!=32 || (rd&4))$fatal(1,"local job failed or incomplete n=%0d status=%h flags=%b",n,rd,dut.cfg_local);
  $display("NNUE_LOCAL_LINK_PASS outputs=%0d ddr_requests=0",n);$finish;
 end
endmodule
