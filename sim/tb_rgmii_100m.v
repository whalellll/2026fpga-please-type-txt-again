`timescale 1ns/1ps

// Small behavioral shells for the Pango I/O primitives used by the RGMII
// wrapper.  This test checks the low-speed byte/valid contract, not pad delay.
module GTP_CLKBUFG(output CLKOUT,input CLKIN); assign CLKOUT=CLKIN; endmodule
module GTP_INBUF #(parameter IOSTANDARD="",parameter TERM_DDR="")
 (output O,input I); assign O=I; endmodule
module GTP_OUTBUF #(parameter IOSTANDARD="",parameter SLEW_RATE="",parameter DRIVE_STRENGTH="")
 (output O,input I); assign O=I; endmodule
module GTP_IODELAY_E2 #(parameter DELAY_STEP_SEL="",parameter [7:0] DELAY_STEP_VALUE=0,parameter TDELAY_EN="")
 (output DO,input DI,input EN_N,input DELAY_SEL,input[7:0]DELAY_STEP); assign DO=DI; endmodule
module GTP_ODDR_E1 #(parameter GRS_EN="",parameter ODDR_MODE="",parameter RS_TYPE="")
 (output reg Q,input CE,input CLK,input D0,input D1,input RS);
 always @(posedge CLK) if(CE) Q<=D0;
 always @(negedge CLK) if(CE) Q<=D1;
endmodule
module GTP_IDDR_E1 #(parameter GRS_EN="",parameter IDDR_MODE="",parameter RS_TYPE="")
 (output reg Q0,output reg Q1,input CE,input CLK,input D,input RS);
 always @(posedge CLK) if(CE) Q0<=D;
 always @(negedge CLK) if(CE) Q1<=D;
endmodule

module tb_rgmii_100m;
 reg rxc=0,rst=1,rx_ctl=0;
 reg[3:0]rxd=0;
 always #20 rxc=~rxc;
 wire mac_clk,mac_rx_error,mac_rx_valid,mac_rx_byte_valid;
 wire[7:0]mac_rx_data;
 wire tx_ready,txc,tx_ctl;wire[3:0]txd;
 rgmii_interface dut(
  .rst(rst),.rx_restart(1'b0),.speed_100(1'b1),.rgmii_clk(mac_clk),.rgmii_clk_90p(1'b0),
  .tx_delay_step(8'd0),.rx_delay_step(8'd0),
  .mac_tx_data_valid(1'b0),.mac_tx_data(8'd0),.mac_tx_ready(tx_ready),
  .mac_rx_error(mac_rx_error),.mac_rx_data_valid(mac_rx_valid),
  .mac_rx_byte_valid(mac_rx_byte_valid),.mac_rx_data(mac_rx_data),
  .rgmii_rxc(rxc),.rgmii_rx_ctl(rx_ctl),.rgmii_rxd(rxd),
  .rgmii_txc(txc),.rgmii_tx_ctl(tx_ctl),.rgmii_txd(txd));

 task send_byte(input[7:0]b);begin
   @(negedge rxc);#2;rxd=b[3:0];rx_ctl=1;
   @(negedge rxc);#2;rxd=b[7:4];
 end endtask

 integer bytes=0;reg prev_valid=0;
 always @(posedge mac_clk) begin
   #3;
   if(mac_rx_valid&&!prev_valid)begin
     if(!mac_rx_byte_valid)$fatal(1,"RX_DV preceded first complete 100M byte");
     if(mac_rx_data!=8'h55)$fatal(1,"first byte %02x",mac_rx_data);
   end
   if(mac_rx_byte_valid)bytes=bytes+1;
   prev_valid=mac_rx_valid;
 end

 initial begin
   repeat(3)@(posedge rxc);rst=0;
   send_byte(8'h55);send_byte(8'hd5);send_byte(8'h01);send_byte(8'h23);
   @(negedge rxc);#2;rx_ctl=0;rxd=0;
   repeat(5)@(posedge rxc);
   if(bytes!=4)$fatal(1,"100M byte count %0d",bytes);
   if(mac_rx_valid)$fatal(1,"RX_DV did not fall");
   $display("PASS tb_rgmii_100m bytes=%0d",bytes);$finish;
 end
endmodule
