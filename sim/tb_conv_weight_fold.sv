module tb_conv_weight_fold;
 reg [1023:0] vector;
 reg [543:0] encoded;
 wire [1023:0] reconstructed;
 mac_conv_weight_dma #(.FOLD_UPPER_HALF(1)) dut(.clk(1'b0),.resetn(1'b0),.read_data(reconstructed));
 function [31:0] golden;
  input [1023:0] v;integer i,n;reg[31:0] word;
  begin
   golden=0;
   for(i=0;i<32;i=i+1)begin
    word=v[i*32+:32];n=(5*(31-i))%32;
    golden=golden^((word<<n)|(word>>((32-n)%32)));
   end
  end
 endfunction
 integer bit_index,lane,trial;
 reg [31:0] random_bits=32'h8093cafe;
 task check;
  begin
   force dut.line_shift=vector;
   #1;
   encoded=dut.store_load;
   force dut.store_read=encoded;
   #1;
   if(reconstructed[511:0] !== vector[511:0] || golden(reconstructed)!==golden(vector))
    $fatal(1,"folded weight observable mismatch");
   if(encoded[511:0]!==vector[511:0] || reconstructed[991:512]!==480'b0)
    $fatal(1,"folded weight layout mismatch");
   release dut.line_shift;release dut.store_read;
  end
 endtask
 initial begin
  vector=0;check();vector='1;check();
  for(bit_index=0;bit_index<1024;bit_index=bit_index+1)begin vector=1024'b1<<bit_index;check();end
  for(trial=0;trial<4096;trial=trial+1)begin
   for(lane=0;lane<32;lane=lane+1)begin
    random_bits={random_bits[30:0],random_bits[31]^random_bits[21]^random_bits[1]^random_bits[0]};
    vector[lane*32+:32]=random_bits;
   end
   check();
  end
  $display("CONV_WEIGHT_FOLD_RTL_PASS basis=1024 randomized=4096 extremes=2");$finish;
 end
endmodule
