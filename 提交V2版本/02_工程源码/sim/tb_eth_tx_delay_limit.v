`timescale 1ns/1ps
module tb_eth_tx_delay_limit;
reg clk=0,resetn=0,wr=0;always #7 clk=~clk;
reg [31:0] addr=32'h1fe0101c,wdata=0;reg [3:0]strb=0;
wire [31:0]rdata;wire [7:0]tx_step,rx_step;
eth_mac_mmio dut(.sys_clk(clk),.sys_resetn(resetn),.addr(addr),.wr(wr),.wdata(wdata),.wstrb(strb),.rdata(rdata),
 .mac_clk(clk),.mac_resetn(resetn),.mac_rx_data(8'd0),.mac_rx_valid(1'b0),.mac_rx_byte_valid(1'b0),
 .mac_rx_error(1'b0),.mac_tx_ready(1'b1),.tx_delay_step(tx_step),.rx_delay_step(rx_step));
task write_delay(input[31:0]value,input[3:0]mask);begin
 @(negedge clk);wr=1;wdata=value;strb=mask;@(negedge clk);wr=0;#1;
end endtask
integer i;reg [7:0]wanted;
initial begin
 repeat(4)@(negedge clk);resetn=1;#1;
 if(tx_step!=100||rx_step!=247||rdata!=32'h0000f764)$fatal(1,"defaults/readback");
 for(i=0;i<256;i=i+1)begin
  wanted=i>123?123:i;write_delay(i,1);
  if(tx_step!==wanted||rdata[7:0]!==wanted||rx_step!=247)$fatal(1,"TX saturation %0d",i);
 end
 for(i=0;i<256;i=i+1)begin
  write_delay(i<<8,2);if(rx_step!==i[7:0]||tx_step!=123)$fatal(1,"RX/byte mask %0d",i);
 end
 write_delay(32'hffffffff,12);if(tx_step!=123||rx_step!=255)$fatal(1,"upper byte masks");
 write_delay(32'h00002264,3);if(tx_step!=100||rx_step!=34||rdata!=32'h00002264)$fatal(1,"combined write");
 $display("PASS tb_eth_tx_delay_limit writes=514 defaults100/247 saturation123 readback byte_masks");$finish;
end
endmodule
