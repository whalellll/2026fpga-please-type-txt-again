`timescale 1ns/1ps
module fifo_output_check #(parameter WIDTH=58, parameter REVERSE=0, parameter SALT=1)(output reg done=0);
  reg wr_clk=0,rd_clk=0,resetn=0,wr_valid=0,rd_ready=0;
  reg [WIDTH-1:0] wr_data=0;
  wire wr_ready,rd_valid;wire [WIDTH-1:0] rd_data;
  localparam real WH=REVERSE ? 10.101010101 : 4.166666667;
  localparam real RH=REVERSE ? 4.166666667 : 10.101010101;
  always #(WH) wr_clk=~wr_clk;
  initial begin #(1.337+SALT*0.173);forever #(RH) rd_clk=~rd_clk;end
  axi_async_fifo #(.WIDTH(WIDTH)) dut(.*,.wr_resetn(resetn),.rd_resetn(resetn));
  function automatic [WIDTH-1:0] payload(input integer n);
    payload=(64'h9e3779b97f4a7c15*(n+1+SALT*97)) ^ 64'hc0decafe01234567;
  endfunction
  realtime last_rd_edge=-1000;
  always @(posedge rd_clk) last_rd_edge=$realtime;
  // The timing boundary is externally observable: even a source write into
  // an empty FIFO cannot change its payload output between destination edges.
  always @(rd_data) if(resetn && $realtime-last_rd_edge>0.0005)
    $fatal(1,"FIFO payload changed outside destination edge WIDTH=%0d",WIDTH);
  reg held=0;reg [WIDTH-1:0] held_data;
  always @(posedge rd_clk) begin
    if(!resetn) held<=0;
    else begin
      if(held && (!rd_valid || rd_data!==held_data)) $fatal(1,"FIFO stalled output changed");
      held<=rd_valid&&!rd_ready;held_data<=rd_data;
    end
  end
  reg [4:0] previous_wr_gray=0,previous_rd_gray=0;
  reg [4:0] gray_difference;
  always @(posedge wr_clk) if(!resetn) previous_wr_gray<=0;else begin
    gray_difference=dut.wr_gray^previous_wr_gray;
    if((gray_difference&(gray_difference-1))!=0) $fatal(1,"write Gray pointer skipped");
    previous_wr_gray<=dut.wr_gray;
  end
  always @(posedge rd_clk) if(!resetn) previous_rd_gray<=0;else begin
    gray_difference=dut.rd_gray^previous_rd_gray;
    if((gray_difference&(gray_difference-1))!=0) $fatal(1,"read Gray pointer skipped");
    previous_rd_gray<=dut.rd_gray;
  end
  task automatic put(input integer n);
    begin
      @(negedge wr_clk);wr_valid=1;wr_data=payload(n);
      @(posedge wr_clk);while(!wr_ready) @(posedge wr_clk);
      @(negedge wr_clk);wr_valid=0;
    end
  endtask
  task automatic full_burst(input integer base);
    integer i;
    begin
      // Sixteen source entries plus the destination elastic word. Prefetch
      // frees exactly one slot while the consumer remains stalled.
      for(i=0;i<17;i=i+1) put(base+i);
      repeat(5) begin @(posedge wr_clk);if(wr_ready) $fatal(1,"FIFO capacity exceeds17");end
      repeat(4) @(posedge rd_clk);
      if(!rd_valid || rd_data!==payload(base)) $fatal(1,"prefetched first word missing");
      @(negedge rd_clk);rd_ready=1;
      for(i=0;i<17;i=i+1) begin
        @(posedge rd_clk);
        if(!rd_valid || rd_data!==payload(base+i)) $fatal(1,"FIFO continuous17-beat throughput/order failed WIDTH=%0d beat=%0d",WIDTH,i);
      end
      @(negedge rd_clk);rd_ready=0;
      repeat(4) begin @(posedge rd_clk);if(rd_valid) $fatal(1,"FIFO ghost after drain");end
    end
  endtask
  integer i;
  initial begin
    #30;resetn=1;full_burst(0);
    for(i=0;i<4;i=i+1)put(100+i);
    repeat(4)@(posedge rd_clk);
    if(!rd_valid)$fatal(1,"reset fixture did not hold a prefetched word");
    resetn=0;#47;resetn=1;
    repeat(8)begin @(posedge rd_clk);if(rd_valid)$fatal(1,"FIFO retained pre-reset word");end
    full_burst(200);full_burst(300);full_burst(400);
    $display("FIFO_OUTPUT_BOUNDARY_CASE_PASS width=%0d reverse=%0d full_capacity=17 burst_beats_per_cycle=1",WIDTH,REVERSE);
    done=1;
  end
endmodule
module tb_axi_fifo_output_boundary;
  wire [4:0]done;
  fifo_output_check #(.WIDTH(58),.SALT(1)) ar(done[0]);
  fifo_output_check #(.WIDTH(58),.SALT(2)) aw(done[1]);
  fifo_output_check #(.WIDTH(41),.SALT(3)) w(done[2]);
  fifo_output_check #(.WIDTH(39),.REVERSE(1),.SALT(4)) r(done[3]);
  fifo_output_check #(.WIDTH(6),.REVERSE(1),.SALT(5)) b(done[4]);
  initial begin wait(&done);$display("AXI_FIFO_REGISTERED_OUTPUT_BOUNDARY_THROUGHPUT_RESET_PASS");$finish;end
  initial begin #100000;$fatal(1,"FIFO output test timeout done=%b",done);end
endmodule
