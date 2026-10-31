`timescale 1ns/1ps
module tb_mac_weight_lutram_equivalence #(parameter DEPTH=32,parameter AW=5);
 reg clk=0,resetn=0;always #5 clk=~clk;
 reg load_start=0,load_valid=0,load_last=0,load_abort=0;
 reg [AW:0] load_lines=0;
 reg [63:0] load_model_id=0;
 reg [31:0] load_generation=0,load_tile_id=0;
 reg [1023:0] load_data=0;
 reg activate=0,compute_idle=0,window_done=0,read_en=0;
 reg [AW-1:0] read_addr=0;
 wire ls0,ls1,lr0,lr1,err0,err1,ar0,ar1,av0,av1,pv0,pv1,rv0,rv1;
 wire [63:0] mid0,mid1;
 wire [31:0] gen0,gen1,tid0,tid1,reuse0,reuse1;
 wire [AW:0] lines0,lines1;
 wire [1023:0] data0,data1;
 `define INPUTS .clk(clk),.resetn(resetn),.load_start(load_start),.load_lines(load_lines),.load_model_id(load_model_id),.load_generation(load_generation),.load_tile_id(load_tile_id),.load_valid(load_valid),.load_data(load_data),.load_last(load_last),.load_abort(load_abort),.activate(activate),.compute_idle(compute_idle),.window_done(window_done),.read_en(read_en),.read_addr(read_addr)
 mac_weight_double_buffer_reference #(.DEPTH(DEPTH),.ADDR_WIDTH(AW)) reference(`INPUTS,.load_start_ready(ls0),.load_ready(lr0),.load_error(err0),.activate_ready(ar0),.active_valid(av0),.active_model_id(mid0),.active_generation(gen0),.active_tile_id(tid0),.active_lines(lines0),.reuse_count(reuse0),.read_valid(rv0),.read_data(data0),.pending_valid(pv0));
 mac_weight_double_buffer #(.DEPTH(DEPTH),.ADDR_WIDTH(AW)) candidate(`INPUTS,.load_start_ready(ls1),.load_ready(lr1),.load_error(err1),.activate_ready(ar1),.active_valid(av1),.active_model_id(mid1),.active_generation(gen1),.active_tile_id(tid1),.active_lines(lines1),.reuse_count(reuse1),.read_valid(rv1),.read_data(data1),.pending_valid(pv1));
 `undef INPUTS
 reg [31:0] random_bits=32'h80c0ffee;
 integer cycle,lane,writes=0,activations=0,reads=0,aborts=0,resets=0,errors=0;
 initial begin
  repeat(3) @(negedge clk);
  for(cycle=0;cycle<20000;cycle=cycle+1) begin
   if({ls0,lr0,err0,ar0,av0,pv0,rv0,mid0,gen0,tid0,lines0,reuse0,data0} !==
      {ls1,lr1,err1,ar1,av1,pv1,rv1,mid1,gen1,tid1,lines1,reuse1,data1})
    $fatal(1,"double-buffer public cycle mismatch cycle=%0d depth=%0d",cycle,DEPTH);
   random_bits={random_bits[30:0],random_bits[31]^random_bits[21]^random_bits[1]^random_bits[0]};
   resetn=cycle%3001!=0;
   load_abort=cycle%127==126;
   load_start=random_bits[0] && random_bits[4];
   load_lines=(cycle%29==0) ? 0 : (cycle%31==0) ? DEPTH+1 : 1+(random_bits[12:5]%DEPTH);
   load_model_id={random_bits,32'(cycle)};
   load_generation=cycle/499;load_tile_id=cycle/97;
   load_valid=random_bits[1] || random_bits[5];
   load_last=reference.write_index+1==reference.target_lines;
   if(cycle%43==0) load_last=!load_last;
   for(lane=0;lane<32;lane=lane+1)load_data[lane*32+:32]=random_bits^(32'h9e3779b9*lane)^cycle;
   activate=random_bits[2];compute_idle=random_bits[3];
   read_en=random_bits[6];read_addr=random_bits[AW+7:8];
   window_done=random_bits[7];
   if(resetn && load_valid && lr0)writes=writes+1;
   if(resetn && activate && ar0)activations=activations+1;
   if(resetn && read_en && av0 && {1'b0,read_addr}<lines0)reads=reads+1;
   if(load_abort)aborts=aborts+1;
   if(!resetn)resets=resets+1;
   if(err0)errors=errors+1;
   @(negedge clk);
  end
  if(writes<128 || activations<8 || reads<128 || aborts<8 || resets<5 || errors<4)
   $fatal(1,"insufficient double-buffer coverage w=%0d a=%0d r=%0d abort=%0d reset=%0d error=%0d",writes,activations,reads,aborts,resets,errors);
  $display("CONV_WEIGHT_PUBLIC_CYCLE_EQUIVALENCE_PASS depth=%0d cycles=20000 writes=%0d activations=%0d reads=%0d aborts=%0d resets=%0d errors=%0d",DEPTH,writes,activations,reads,aborts,resets,errors);
  $finish;
 end
endmodule
