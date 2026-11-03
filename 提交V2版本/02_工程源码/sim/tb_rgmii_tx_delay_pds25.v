`timescale 1ps/1ps
// Real vendor IODELAY model is compiled separately. Other I/O shells only
// provide the digital clock/data contract; this bench tests the pad delay.
module GTP_CLKBUFG(output CLKOUT,input CLKIN);assign CLKOUT=CLKIN;endmodule
module GTP_INBUF #(parameter IOSTANDARD="",parameter TERM_DDR="")(output O,input I);assign O=I;endmodule
module GTP_OUTBUF #(parameter IOSTANDARD="",parameter SLEW_RATE="",parameter DRIVE_STRENGTH="")(output O,input I);assign O=I;endmodule
module GTP_ODDR_E1 #(parameter GRS_EN="",parameter ODDR_MODE="",parameter RS_TYPE="")
 (output reg Q,input CE,input CLK,input D0,input D1,input RS);
 always @(posedge CLK)if(CE)Q<=D0;
 always @(negedge CLK)if(CE)Q<=D1;
endmodule
module GTP_IDDR_E1 #(parameter GRS_EN="",parameter IDDR_MODE="",parameter RS_TYPE="")
 (output reg Q0,output reg Q1,input CE,input CLK,input D,input RS);
 always @(posedge CLK)if(CE)Q0<=D;
 always @(negedge CLK)if(CE)Q1<=D;
endmodule
module tb_rgmii_tx_delay_pds25;
reg clk=0;always #20000 clk=~clk;
reg [7:0]step=0;wire txc;wire[7:0]effective=step>123?123:step;
wire [7:0]reference_gray=(effective>>1)^effective;
wire reference_txc;
rgmii_interface dut(.rst(1'b0),.rx_restart(1'b0),.speed_100(1'b1),.rgmii_clk_90p(1'b0),
 .tx_delay_step(step),.rx_delay_step(8'd0),.mac_tx_data_valid(1'b0),.mac_tx_data(8'd0),
 .rgmii_rxc(clk),.rgmii_rx_ctl(1'b0),.rgmii_rxd(4'd0),.rgmii_txc(txc));
GTP_IODELAY_E2 #(.DELAY_STEP_SEL("PORT"),.DELAY_STEP_VALUE(8'd0)) original_reference(
 .DI(dut.rgmii_txc_obuf),.DELAY_SEL(1'b1),.DELAY_STEP(reference_gray),.DO(reference_txc),.EN_N(1'b0));
reg compare=0;integer events=0;time started;integer i;
always @(txc or reference_txc)if(compare)begin
 #1;if(txc!==reference_txc)$fatal(1,"vendor delay mismatch step=%0d effective=%0d t=%0t",step,effective,$time);
 events=events+1;
end
initial begin
 repeat(3)@(negedge clk);
 for(i=0;i<256;i=i+1)begin
  compare=0;step=i;#5000;compare=1;
  @(posedge clk);started=$time;@(posedge txc);
  if(($time-started)!==10*effective)$fatal(1,"rising delay step=%0d measured=%0t expected=%0d",step,$time-started,10*effective);
  @(negedge clk);started=$time;@(negedge txc);
  if(($time-started)!==10*effective)$fatal(1,"falling delay step=%0d measured=%0t expected=%0d",step,$time-started,10*effective);
  #5000;compare=0;@(negedge clk);
 end
 if(events<512)$fatal(1,"vacuous edge comparisons");
 $display("PASS tb_rgmii_tx_delay_pds25 vendor_model settings=256 edge_checks=512 unit10ps default100 preserved max123 clamped");$finish;
end
initial begin #40000000;$fatal(1,"timeout");end
endmodule
