`timescale 1ns/1ps
module tb_nnue_stream_transform;
 parameter CASES=24;
 reg clk=0;always #10 clk=~clk;
 reg resetn=0,wb=0,wv=0,wc=0,wa=0,view=0,start=0,ready=0,swap=0;
 reg [31:0] tag=0,data=0,tag0=0,tag1=0;reg [8:0] index=0;
 wire wr_ready,busy,done,error,valid;wire [8:0] fi;wire [15:0] fd;wire [31:0] cycles;
 nnue_stream_transform dut(.clk(clk),.resetn(resetn),.write_begin(wb),.write_valid(wv),
  .write_commit(wc),.write_abort(wa),.write_view(view),.write_tag(tag),.write_data(data),
  .write_index(index),.write_ready(wr_ready),.start(start),.swap_views(swap),.expected_tag0(tag0),.expected_tag1(tag1),
  .busy(busy),.done(done),.error(error),.feature_valid(valid),.feature_ready(ready),
  .feature_index(fi),.feature_data(fd),.cycles(cycles));
 reg [31:0] accum[0:CASES*1024-1];reg [15:0] golden[0:CASES*512-1];
 integer c,v,i,n,ticks=0,max_cycles=0;reg held_valid=0;reg [15:0] held_data;
 always @(posedge clk)begin ticks<=ticks+1;if(ticks>3000000)$fatal(1,"bounded timeout");end
 initial begin
  $readmemh("accum.hex",accum);$readmemh("golden.hex",golden);
  repeat(4)@(negedge clk);resetn=1;
  for(c=0;c<CASES;c=c+1)begin
   for(v=0;v<2;v=v+1)begin
    view=v;tag=32'h75000000+c*2+v;wb=1;@(negedge clk);wb=0;
    for(i=0;i<512;i=i+1)begin
     if(!wr_ready)$fatal(1,"write refused while idle");
     index=i;data=accum[c*1024+v*512+i];wv=1;@(negedge clk);
    end
    wv=0;wc=1;@(negedge clk);wc=0;
   end
   tag0=32'h75000000+c*2;tag1=tag0+2;start=1;@(negedge clk);start=0;
   if(!done||!error||busy)$fatal(1,"stale view accepted");
   tag1=tag0+1;swap=c%2;start=1;@(negedge clk);start=0;n=0;held_valid=0;
   while(!done)begin
    ready=ticks%9!=0;@(posedge clk);
    if(valid)begin
     if(held_valid&&held_data!==fd)$fatal(1,"feature changed under stall");
     if(ready)begin
      if(fi!==n||fd!==golden[c*512+(swap?(n^256):n)])$fatal(1,"case%0d pair%0d got%h want%h",c,n,fd,golden[c*512+(swap?(n^256):n)]);
      n=n+1;held_valid=0;
     end else begin held_data=fd;held_valid=1;end
    end
    @(negedge clk);
   end
   if(error||n!=512)$fatal(1,"incomplete transform");
   if(cycles>max_cycles)max_cycles=cycles;
  end
  // An incomplete overwrite invalidates the old committed view.
  view=0;wb=1;@(negedge clk);wb=0;wv=1;index=0;data=0;@(negedge clk);wv=0;
  wc=1;@(negedge clk);wc=0;start=1;@(negedge clk);start=0;
  if(!done||!error||valid)$fatal(1,"partial view accepted");
  resetn=0;@(negedge clk);resetn=1;start=1;@(negedge clk);start=0;
  if(!done||!error)$fatal(1,"reset did not invalidate contexts");
  $display("NNUE_STREAM_TRANSFORM_PASS cases=%0d features=%0d max_cycles=%0d",CASES,CASES*1024,max_cycles);$finish;
 end
endmodule
