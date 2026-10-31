`timescale 1ns/1ps
module GTP_CLKBUFG(input CLKIN,output CLKOUT);assign CLKOUT=CLKIN;endmodule
module GTP_INBUFDS(input I,input IB,output O);assign O=I;endmodule
module GTP_CFGCLK(input CE_N,input CLKIN);endmodule
module ref_clock(input clkin1,output clkout0,output lock);assign clkout0=clkin1;assign lock=1'b1;endmodule
module GTP_OUTBUF #(parameter IOSTANDARD="",parameter SLEW_RATE="",parameter DRIVE_STRENGTH="")(input I,output O);assign O=I;endmodule
module GTP_INBUF #(parameter IOSTANDARD="",parameter TERM_DDR="")(input I,output O);assign O=I;endmodule
module GTP_ODDR_E1 #(parameter GRS_EN="",parameter ODDR_MODE="",parameter RS_TYPE="")(input CE,input CLK,input D0,input D1,input RS,output reg Q);always@(posedge CLK)Q<=D0;always@(negedge CLK)Q<=D1;endmodule
module GTP_IDDR_E1 #(parameter GRS_EN="",parameter IDDR_MODE="",parameter RS_TYPE="")(input CE,input CLK,input D,input RS,output reg Q0,output reg Q1);always@(posedge CLK)Q0<=D;always@(negedge CLK)Q1<=D;endmodule
module GTP_IODELAY_E2 #(parameter DELAY_STEP_SEL="",parameter DELAY_STEP_VALUE=0,parameter TDELAY_EN="")(input DI,input DELAY_SEL,input[7:0]DELAY_STEP,input EN_N,output DO);assign DO=DI;endmodule
module ddr3_test(
 input ref_clk,input resetn,output core_clk,output pll_lock,output phy_pll_lock,output gpll_lock,output rst_gpll_lock,output ddrphy_cpd_lock,output ddr_init_done,
 input[27:0]axi_awaddr,input axi_awuser_ap,input[3:0]axi_awuser_id,input[3:0]axi_awlen,output axi_awready,input axi_awvalid,input[255:0]axi_wdata,input[31:0]axi_wstrb,output axi_wready,output[3:0]axi_wusero_id,output axi_wusero_last,
 input[27:0]axi_araddr,input axi_aruser_ap,input[3:0]axi_aruser_id,input[3:0]axi_arlen,output axi_arready,input axi_arvalid,output[255:0]axi_rdata,output[3:0]axi_rid,output axi_rlast,output axi_rvalid,
 input apb_clk,input apb_rst_n,input apb_sel,input apb_enable,input[7:0]apb_addr,input apb_write,input[15:0]apb_wdata,
 output mem_cs_n,output mem_rst_n,output mem_ck,output mem_ck_n,output mem_cke,output mem_ras_n,output mem_cas_n,output mem_we_n,output mem_odt,output[14:0]mem_a,output[2:0]mem_ba,inout[3:0]mem_dqs,inout[3:0]mem_dqs_n,inout[31:0]mem_dq,output[3:0]mem_dm,
 input dbg_gate_start,input dbg_cpd_start,input dbg_ddrphy_rst_n,input dbg_gpll_scan_rst,input samp_position_dyn_adj,input[31:0]init_samp_position_even,input[31:0]init_samp_position_odd,input wrcal_position_dyn_adj,input[31:0]init_wrcal_position,input force_read_clk_ctrl,input[15:0]init_slip_step,input[11:0]init_read_clk_ctrl,input debug_cpd_offset_adj,input debug_cpd_offset_dir,input[9:0]debug_cpd_offset,input ck_dly_en,input[7:0]init_ck_dly_step
);assign core_clk=ref_clk;assign ddr_init_done=resetn;assign axi_awready=1;assign axi_wready=axi_awvalid;assign axi_arready=1;assign axi_rvalid=0;assign axi_rdata=0;assign axi_rid=0;assign axi_rlast=1;endmodule
