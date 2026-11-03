`timescale 1ns/1ps
module tb_pikafish_mlp_dedicated #(parameter integer CASES=6);
 reg clk=0;always #10 clk=~clk;
 reg resetn=0,start=0,abort=0,invalidate=0,fvalid=0;
`ifdef SYNTHESIS
 GTP_GRS GRS_INST(.GRS_N(resetn));
`endif
 reg [31:0] source=0;reg [8:0] fi=0;reg [15:0] fd=0;
 wire busy,done,error,fready,cache_valid,cache_hit;
 wire signed [31:0] score;wire [31:0] cycles,read_words;wire [3:0] jobs;
 wire req,ready,rready;wire [31:0] address;wire [2:0] len;
 reg active=0;reg [31:0] pointer=0;reg [3:0] left=0;
 reg inject_error=0;
 wire rvalid=active && ticks%7!=0;
 wire rlast=left==1;
 wire [31:0] rdata=memory[pointer[19:2]];
 assign ready=!active && ticks%11!=0;
 reg [31:0] memory[0:CASES*16384-1],golden[0:CASES*66-1];
 reg [15:0] features[0:CASES*512-1];
 integer ticks=0,c=0,i,reads=0,maxcold=0,maxwarm=0;
 pikafish_mlp_dedicated #(.DDR_BASE(0),.DDR_BYTES(1048576)) chain(
  .clk(clk),.resetn(resetn),.start(start),.abort(abort),.invalidate(invalidate),.stack_source(source),
  .busy(busy),.done(done),.error(error),.score(score),.cycles(cycles),.jobs(jobs),
  .feature_valid(fvalid),.feature_ready(fready),.feature_index(fi),.feature_data(fd),
  .mem_req_valid(req),.mem_req_ready(ready),.mem_req_addr(address),.mem_req_len(len),
  .mem_rsp_valid(rvalid),.mem_rsp_ready(rready),.mem_rsp_rdata(rdata),.mem_rsp_last(rlast),.mem_rsp_error(inject_error),
  .cache_valid(cache_valid),.cache_hit(cache_hit),.read_words(read_words));
 always @(posedge clk)begin
  ticks<=ticks+1;if(ticks>5000000)$fatal(1,"timeout state=%0d layer=%0d",chain.state,chain.layer);
  if(!resetn)begin active<=0;left<=0;end
  else begin
   if(req&&ready)begin active<=1;pointer<=address;left<={1'b0,len}+1'b1;end
   if(rvalid&&rready)begin reads<=reads+1;pointer<=pointer+4;left<=left-1'b1;if(rlast)active<=0;end
   if(chain.state==chain.ACT_PRE)begin
    if(chain.accum[chain.act_index]!==golden[c*66+chain.layer*32+chain.act_index])
     $fatal(1,"case%0d layer%0d lane%0d got%h want%h",c,chain.layer,chain.act_index,chain.accum[chain.act_index],golden[c*66+chain.layer*32+chain.act_index]);
   end
   if(chain.state==chain.FINAL_PRE && chain.accum[0]!==golden[c*66+64])$fatal(1,"FC2 mismatch");
  end
 end
 task begin_features;
  begin
   reads=0;start=1;@(negedge clk);start=0;
   for(i=0;i<512;i=i+1)begin
    fi=i;fd=features[c*512+i];fvalid=1;
    while(!fready)@(negedge clk);
    @(negedge clk);fvalid=0;if(i%17==0)@(negedge clk);
   end
  end
 endtask
 task finish_check(input integer expected_reads);
  begin
   while(!done)@(negedge clk);
   if(error||score!==golden[c*66+65]||jobs!=6)$fatal(1,"case%0d final got%0d want%0d jobs%0d error%0d",c,score,$signed(golden[c*66+65]),jobs,error);
   if(reads!=expected_reads || read_words!=expected_reads)$fatal(1,"DDR got%0d/%0d want%0d",reads,read_words,expected_reads);
   if(!cache_valid || cache_hit!=(expected_reads==0))$fatal(1,"cache contract");
   @(negedge clk);
  end
 endtask
 initial begin
  $readmemh("model.hex",memory);$readmemh("golden.hex",golden);$readmemh("features.hex",features);
  repeat(4)@(negedge clk);resetn=1;
  for(c=0;c<CASES;c=c+1)begin
   source=c*65536;begin_features();finish_check(8801);if(cycles>maxcold)maxcold=cycles;
   begin_features();finish_check(0);if(cycles>maxwarm)maxwarm=cycles;
   invalidate=1;@(negedge clk);invalidate=0;
   begin_features();finish_check(8801);
  end
  c=0;source=0;invalidate=1;@(negedge clk);invalidate=0;
  begin_features();wait(active);repeat(3)@(negedge clk);abort=1;@(negedge clk);abort=0;
  while(!done)@(negedge clk);
  if(!error||cache_valid||active)$fatal(1,"abort must drain and invalidate");
  begin_features();finish_check(8801);
  invalidate=1;@(negedge clk);invalidate=0;
  begin_features();wait(active);inject_error=1;@(negedge clk);
  while(!done)@(negedge clk);inject_error=0;
  if(!error||cache_valid||active)$fatal(1,"DDR error must drain and invalidate");
  begin_features();finish_check(8801);
  start=1;@(negedge clk);start=0;fi=3;fd=0;fvalid=1;@(negedge clk);fvalid=0;
  while(!done)@(negedge clk);if(!error)$fatal(1,"feature order accepted");
  source=32'hffffffe0;start=1;@(negedge clk);start=0;
  while(!done)@(negedge clk);if(!error||req)$fatal(1,"range accepted");
  source=0;resetn=0;repeat(3)@(negedge clk);resetn=1;
  begin_features();finish_check(8801);
  $display("PIKAFISH_DEDICATED_PASS cases=%0d layers=3 cold_reads=8801 warm_reads=0 max_cold=%0d max_warm=%0d abort_error_order_range_reset=pass",CASES,maxcold,maxwarm);
  $finish;
 end
endmodule
