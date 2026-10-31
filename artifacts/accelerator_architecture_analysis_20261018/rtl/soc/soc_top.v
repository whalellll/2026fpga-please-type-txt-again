`timescale 1ns/1ps

module soc_top #(
 parameter integer CPU_DIVISOR = 12,
 parameter integer CPU_CLOCK_MODE = 1,
 parameter [31:0] CPU_PLL_VCO_HZ = CPU_CLOCK_MODE ? 32'd850500000 : 32'd891000000,
 parameter [31:0] CPU_HZ = (CPU_PLL_VCO_HZ + CPU_DIVISOR/2) / CPU_DIVISOR,
 parameter [31:0] SYS_HZ = 32'd49500000,
 parameter [31:0] TIMEBASE_HZ = 32'd49500000,
 // Candidate builds can elaborate the existing 2x4 convolution PE and
 // next-weight double buffer. Production keeps the proven disabled setting.
 parameter integer ENABLE_CONV_CANDIDATE = 0,
 // Temporary Pikafish boot profile. The generic MAC modules still default
 // to 1024 lines; this board candidate accepts at most 64 weight lines/job.
 parameter integer WEIGHT_BANK_LINES = 64,
 // Official Pikafish uses U8S8; the generic module keeps FP8 enabled.
 parameter ENABLE_FP8 = 0
)(
 input wire ref_clk_p,input wire ref_clk_n,input wire free_clk,input wire rst_board,
 input wire uart_rxd,output wire uart_txd,
 input wire ch9350_uart_rx,output wire ch9350_uart_tx,
 inout wire cmos1_scl,inout wire cmos1_sda,input wire cmos1_vsync,
 input wire cmos1_href,input wire cmos1_pclk,input wire[7:0]cmos1_data,
 output wire cmos1_reset,
 inout wire cmos2_scl,inout wire cmos2_sda,input wire cmos2_vsync,
 input wire cmos2_href,input wire cmos2_pclk,input wire[7:0]cmos2_data,
 output wire cmos2_reset,
 input wire rgmii_rxc,input wire rgmii_rx_ctl,input wire[3:0]rgmii_rxd,
 output wire rgmii_txc,output wire rgmii_tx_ctl,output wire[3:0]rgmii_txd,output wire phy_rstn,
 output wire spi_cs,output wire spi_dq0,input wire spi_dq1,
 output wire sd_clk,inout wire sd_cmd,inout wire sd_data0,
 inout wire sd_data1,inout wire sd_data2,inout wire sd_data3,
 input wire sd_detect_n,
 output wire audio_bclk,output wire audio_ws,input wire microphone_sd,
 output wire spk_din,
 output wire pixclk_out,output wire vs_out,output wire hs_out,output wire de_out,
 output wire[7:0]r_out,output wire[7:0]g_out,output wire[7:0]b_out,
 output wire hd_scl,inout wire hd_sda,output wire hdmi_init_done,
 output wire mem_cs_n,output wire mem_rst_n,output wire mem_ck,output wire mem_ck_n,
 output wire mem_cke,output wire mem_ras_n,output wire mem_cas_n,output wire mem_we_n,output wire mem_odt,
 output wire[14:0]mem_a,output wire[2:0]mem_ba,inout wire[3:0]mem_dqs,inout wire[3:0]mem_dqs_n,inout wire[31:0]mem_dq,output wire[3:0]mem_dm
);
 wire ref_clk; GTP_INBUFDS u_refclk(.I(ref_clk_p),.IB(ref_clk_n),.O(ref_clk));

 // The existing pixel, SYS, and HDMI configuration outputs keep their rates.
 // CLKOUT3 supplies the independently constrained CPU clock.
 wire pix_clk,sys_clk,cpu_clk,i2c_cfg_clk,video_pll_lock;
 wire video_cpu_clk,cpu_pll_lock;
 pll_video #(.CPU_DIVISOR(CPU_DIVISOR)) u_video_pll(
  .clkout0(pix_clk),.clkout1(sys_clk),.clkout2(i2c_cfg_clk),
  .clkout3(video_cpu_clk),.clkin1(free_clk),.lock(video_pll_lock));
 generate if(CPU_CLOCK_MODE == 1) begin:g_dedicated_cpu
  pll_cpu #(.CPU_DIVISOR(CPU_DIVISOR)) u_cpu_pll(
   .clkout0(),.clkout1(),.clkout2(),.clkout3(cpu_clk),
   .clkin1(free_clk),.lock(cpu_pll_lock));
 end else begin:g_shared_cpu
  assign cpu_clk=video_cpu_clk;
  assign cpu_pll_lock=1'b1;
 end endgenerate
 wire domains_async_resetn = rst_board && video_pll_lock && cpu_pll_lock;
 reg[2:0]sys_rst_pipe;
 reg[2:0]cpu_rst_pipe;
 always@(posedge sys_clk or negedge domains_async_resetn)
  if(!domains_async_resetn)sys_rst_pipe<=0;else sys_rst_pipe<={sys_rst_pipe[1:0],1'b1};
 always@(posedge cpu_clk or negedge domains_async_resetn)
  if(!domains_async_resetn)cpu_rst_pipe<=0;else cpu_rst_pipe<={cpu_rst_pipe[1:0],1'b1};
 wire sys_resetn=sys_rst_pipe[2];
 wire cpu_resetn=cpu_rst_pipe[2];
 // Hold the external Gigabit PHY in reset for about 85 ms at 49.5 MHz.  The old
 // 9.7 ms pulse sat on the reset-time boundary and could leave RGMII RXC in a
 // non-repeatable state after consecutive CRAM configurations.
 reg[22:0]phy_delay;always@(posedge sys_clk or negedge domains_async_resetn)if(!domains_async_resetn)phy_delay<=0;else if(!phy_delay[22])phy_delay<=phy_delay+1'b1;
 wire phy_reset_req;
 /* A software recovery request holds only the external PHY in reset for
  * about 2.5 s.  CPU, DDR and MAC ownership toggles remain intact so TFTP can
  * resume the same block after the link comes back. */
 reg[26:0]phy_recover_count;
 always@(posedge sys_clk or negedge domains_async_resetn)
  if(!domains_async_resetn)phy_recover_count<=0;
  else if(phy_reset_req)phy_recover_count<=1;
  else if(phy_recover_count)begin
   if(phy_recover_count>=27'd123750000)phy_recover_count<=0;
   else phy_recover_count<=phy_recover_count+1'b1;
  end
 assign phy_rstn=sys_resetn&&phy_delay[22]&&(phy_recover_count==0);
 wire eth_reset_req;
 reg[19:0]eth_reset_count;
 always@(posedge sys_clk or negedge domains_async_resetn)
  if(!domains_async_resetn)eth_reset_count<=0;
  else if(eth_reset_req)eth_reset_count<=1;
  else if(eth_reset_count)begin
   if(eth_reset_count[19])eth_reset_count<=0;
   else eth_reset_count<=eth_reset_count+1'b1;
  end
 wire eth_resetn=sys_resetn&&(eth_reset_count==0);

 reg[1:0]video_rst_pipe;always@(posedge pix_clk or negedge domains_async_resetn)
  if(!domains_async_resetn)video_rst_pipe<=0;else video_rst_pipe<={video_rst_pipe[0],1'b1};
 wire video_resetn=video_rst_pipe[1];

 // CPU master AXI
 wire[3:0]c_arid,c_rid,c_awid,c_wid,c_bid;wire[31:0]c_araddr,c_rdata,c_awaddr,c_wdata;wire[7:0]c_arlen,c_awlen;wire[2:0]c_arsize,c_arprot,c_awsize,c_awprot;wire[1:0]c_arburst,c_arlock,c_rresp,c_awburst,c_awlock,c_bresp;wire[3:0]c_arcache,c_awcache,c_wstrb;wire c_arvalid,c_arready,c_rlast,c_rvalid,c_rready,c_awvalid,c_awready,c_wlast,c_wvalid,c_wready,c_bvalid,c_bready;
 core_top u_cpu(.cpu_clk(cpu_clk),.cpu_resetn(cpu_resetn),.sys_clk(sys_clk),.sys_resetn(sys_resetn),.arid(c_arid),.araddr(c_araddr),.arlen(c_arlen),.arsize(c_arsize),.arburst(c_arburst),.arlock(c_arlock),.arcache(c_arcache),.arprot(c_arprot),.arvalid(c_arvalid),.arready(c_arready),.rid(c_rid),.rdata(c_rdata),.rresp(c_rresp),.rlast(c_rlast),.rvalid(c_rvalid),.rready(c_rready),.awid(c_awid),.awaddr(c_awaddr),.awlen(c_awlen),.awsize(c_awsize),.awburst(c_awburst),.awlock(c_awlock),.awcache(c_awcache),.awprot(c_awprot),.awvalid(c_awvalid),.awready(c_awready),.wid(c_wid),.wdata(c_wdata),.wstrb(c_wstrb),.wlast(c_wlast),.wvalid(c_wvalid),.wready(c_wready),.bid(c_bid),.bresp(c_bresp),.bvalid(c_bvalid),.bready(c_bready));

 // Slave 0 is the CPU-facing DDR port; slave 1 is BRAM/peripherals.
 wire[3:0]d_arid,d_rid,d_awid,d_wid,d_bid,l_arid,l_rid,l_awid,l_wid,l_bid;wire[31:0]d_araddr,d_rdata,d_awaddr,d_wdata,l_araddr,l_rdata,l_awaddr,l_wdata;wire[7:0]d_arlen,d_awlen,l_arlen,l_awlen;wire[2:0]d_arsize,d_awsize,l_arsize,l_awsize;wire[1:0]d_arburst,d_rresp,d_awburst,d_bresp,l_arburst,l_rresp,l_awburst,l_bresp;wire[3:0]d_wstrb,l_wstrb;wire d_arvalid,d_arready,d_rlast,d_rvalid,d_rready,d_awvalid,d_awready,d_wlast,d_wvalid,d_wready,d_bvalid,d_bready;wire l_arvalid,l_arready,l_rlast,l_rvalid,l_rready,l_awvalid,l_awready,l_wlast,l_wvalid,l_wready,l_bvalid,l_bready;
 axi_1x2 u_xbar(.clk(sys_clk),.resetn(sys_resetn),
 .s_arid(c_arid),.s_araddr(c_araddr),.s_arlen(c_arlen),.s_arsize(c_arsize),.s_arburst(c_arburst),.s_arlock(c_arlock),.s_arcache(c_arcache),.s_arprot(c_arprot),.s_arvalid(c_arvalid),.s_arready(c_arready),.s_rid(c_rid),.s_rdata(c_rdata),.s_rresp(c_rresp),.s_rlast(c_rlast),.s_rvalid(c_rvalid),.s_rready(c_rready),.s_awid(c_awid),.s_awaddr(c_awaddr),.s_awlen(c_awlen),.s_awsize(c_awsize),.s_awburst(c_awburst),.s_awlock(c_awlock),.s_awcache(c_awcache),.s_awprot(c_awprot),.s_awvalid(c_awvalid),.s_awready(c_awready),.s_wid(c_wid),.s_wdata(c_wdata),.s_wstrb(c_wstrb),.s_wlast(c_wlast),.s_wvalid(c_wvalid),.s_wready(c_wready),.s_bid(c_bid),.s_bresp(c_bresp),.s_bvalid(c_bvalid),.s_bready(c_bready),
 .m0_arid(d_arid),.m0_araddr(d_araddr),.m0_arlen(d_arlen),.m0_arsize(d_arsize),.m0_arburst(d_arburst),.m0_arvalid(d_arvalid),.m0_arready(d_arready),.m0_rid(d_rid),.m0_rdata(d_rdata),.m0_rresp(d_rresp),.m0_rlast(d_rlast),.m0_rvalid(d_rvalid),.m0_rready(d_rready),.m0_awid(d_awid),.m0_awaddr(d_awaddr),.m0_awlen(d_awlen),.m0_awsize(d_awsize),.m0_awburst(d_awburst),.m0_awvalid(d_awvalid),.m0_awready(d_awready),.m0_wid(d_wid),.m0_wdata(d_wdata),.m0_wstrb(d_wstrb),.m0_wlast(d_wlast),.m0_wvalid(d_wvalid),.m0_wready(d_wready),.m0_bid(d_bid),.m0_bresp(d_bresp),.m0_bvalid(d_bvalid),.m0_bready(d_bready),
 .m1_arid(l_arid),.m1_araddr(l_araddr),.m1_arlen(l_arlen),.m1_arsize(l_arsize),.m1_arburst(l_arburst),.m1_arvalid(l_arvalid),.m1_arready(l_arready),.m1_rid(l_rid),.m1_rdata(l_rdata),.m1_rresp(l_rresp),.m1_rlast(l_rlast),.m1_rvalid(l_rvalid),.m1_rready(l_rready),.m1_awid(l_awid),.m1_awaddr(l_awaddr),.m1_awlen(l_awlen),.m1_awsize(l_awsize),.m1_awburst(l_awburst),.m1_awvalid(l_awvalid),.m1_awready(l_awready),.m1_wid(l_wid),.m1_wdata(l_wdata),.m1_wstrb(l_wstrb),.m1_wlast(l_wlast),.m1_wvalid(l_wvalid),.m1_wready(l_wready),.m1_bid(l_bid),.m1_bresp(l_bresp),.m1_bvalid(l_bvalid),.m1_bready(l_bready));

 // CPU traffic has crossed into SYS before the crossbar. MAC DMA and the
 // 32-bit side of the existing DDR bridge also use SYS.
 wire[3:0]a_arid,a_rid,a_awid,a_wid,a_bid;wire[31:0]a_araddr,a_rdata,a_awaddr,a_wdata;wire[7:0]a_arlen,a_awlen;wire[2:0]a_arsize,a_awsize;wire[1:0]a_arburst,a_rresp,a_awburst,a_bresp;wire[3:0]a_wstrb;wire a_arvalid,a_arready,a_rlast,a_rvalid,a_rready,a_awvalid,a_awready,a_wlast,a_wvalid,a_wready,a_bvalid,a_bready;
 wire[31:0]mac_araddr,mac_rdata_axi,mac_awaddr,mac_wdata_axi;wire[7:0]mac_arlen,mac_awlen;wire[2:0]mac_arsize,mac_awsize;wire[1:0]mac_arburst,mac_rresp_axi,mac_awburst,mac_bresp_axi;wire[3:0]mac_wstrb_axi;wire mac_arvalid,mac_arready,mac_rlast,mac_rvalid,mac_rready,mac_awvalid,mac_awready,mac_wlast,mac_wvalid,mac_wready,mac_bvalid,mac_bready;
 axi_2x1_arbiter u_ddr_arbiter(.clk(sys_clk),.resetn(sys_resetn),
 .s0_arid(d_arid),.s0_araddr(d_araddr),.s0_arlen(d_arlen),.s0_arsize(d_arsize),.s0_arburst(d_arburst),.s0_arvalid(d_arvalid),.s0_arready(d_arready),.s0_rid(d_rid),.s0_rdata(d_rdata),.s0_rresp(d_rresp),.s0_rlast(d_rlast),.s0_rvalid(d_rvalid),.s0_rready(d_rready),.s0_awid(d_awid),.s0_awaddr(d_awaddr),.s0_awlen(d_awlen),.s0_awsize(d_awsize),.s0_awburst(d_awburst),.s0_awvalid(d_awvalid),.s0_awready(d_awready),.s0_wid(d_wid),.s0_wdata(d_wdata),.s0_wstrb(d_wstrb),.s0_wlast(d_wlast),.s0_wvalid(d_wvalid),.s0_wready(d_wready),.s0_bid(d_bid),.s0_bresp(d_bresp),.s0_bvalid(d_bvalid),.s0_bready(d_bready),
 .s1_araddr(mac_araddr),.s1_arlen(mac_arlen),.s1_arsize(mac_arsize),.s1_arburst(mac_arburst),.s1_arvalid(mac_arvalid),.s1_arready(mac_arready),.s1_rdata(mac_rdata_axi),.s1_rresp(mac_rresp_axi),.s1_rlast(mac_rlast),.s1_rvalid(mac_rvalid),.s1_rready(mac_rready),.s1_awaddr(mac_awaddr),.s1_awlen(mac_awlen),.s1_awsize(mac_awsize),.s1_awburst(mac_awburst),.s1_awvalid(mac_awvalid),.s1_awready(mac_awready),.s1_wdata(mac_wdata_axi),.s1_wstrb(mac_wstrb_axi),.s1_wlast(mac_wlast),.s1_wvalid(mac_wvalid),.s1_wready(mac_wready),.s1_bresp(mac_bresp_axi),.s1_bvalid(mac_bvalid),.s1_bready(mac_bready),
 .m_arid(a_arid),.m_araddr(a_araddr),.m_arlen(a_arlen),.m_arsize(a_arsize),.m_arburst(a_arburst),.m_arvalid(a_arvalid),.m_arready(a_arready),.m_rid(a_rid),.m_rdata(a_rdata),.m_rresp(a_rresp),.m_rlast(a_rlast),.m_rvalid(a_rvalid),.m_rready(a_rready),.m_awid(a_awid),.m_awaddr(a_awaddr),.m_awlen(a_awlen),.m_awsize(a_awsize),.m_awburst(a_awburst),.m_awvalid(a_awvalid),.m_awready(a_awready),.m_wid(a_wid),.m_wdata(a_wdata),.m_wstrb(a_wstrb),.m_wlast(a_wlast),.m_wvalid(a_wvalid),.m_wready(a_wready),.m_bid(a_bid),.m_bresp(a_bresp),.m_bvalid(a_bvalid),.m_bready(a_bready));

 wire[31:0]io_addr,io_wdata,io_rdata;wire[3:0]io_wstrb;wire io_wr,io_valid;
 wire console_char_valid;wire[7:0]console_char_data;
 wire hid_key_valid,hid_key_ready;wire[7:0]hid_key_data;
 wire[10:0]hid_mouse_x;wire[9:0]hid_mouse_y;wire[2:0]hid_mouse_buttons;
 wire[7:0]hid_mouse_dx,hid_mouse_dy,hid_mouse_wheel;
 wire[7:0]hid_keyboard_modifier,hid_keyboard_usage,hid_keyboard_ascii;
 wire hid_caps_lock,hid_keyboard_seen,hid_mouse_seen;
 wire[31:0]hid_keyboard_count,hid_mouse_count,hid_error_count,hid_dropped_count;
 wire[15:0]hid_mouse_left_press_count,hid_mouse_right_press_count;
 wire hid_gui_help,hid_gui_stats,hid_gui_speed_2x,hid_gui_cursor_alt,hid_gui_term_focus,hid_state_toggle;
 ch9350_hid_core #(.UART_BAUD_DIV(430),.GUI_PROFILE(1),
  .REPEAT_DELAY_CYCLES(24_750_000),.REPEAT_PERIOD_CYCLES(1_980_000)) u_ch9350(
  .clk(sys_clk),.resetn(sys_resetn),.ch9350_uart_rx(ch9350_uart_rx),.ch9350_uart_tx(ch9350_uart_tx),
  .key_valid(hid_key_valid),.key_data(hid_key_data),.key_ready(hid_key_ready),
  .mouse_x(hid_mouse_x),.mouse_y(hid_mouse_y),.mouse_buttons(hid_mouse_buttons),
  .mouse_last_dx(hid_mouse_dx),.mouse_last_dy(hid_mouse_dy),.mouse_last_wheel(hid_mouse_wheel),
  .keyboard_modifier(hid_keyboard_modifier),.keyboard_last_usage(hid_keyboard_usage),
  .keyboard_last_ascii(hid_keyboard_ascii),.caps_lock(hid_caps_lock),
  .keyboard_seen(hid_keyboard_seen),.mouse_seen(hid_mouse_seen),
  .keyboard_frame_count(hid_keyboard_count),.mouse_frame_count(hid_mouse_count),
  .mouse_left_press_count(hid_mouse_left_press_count),
  .mouse_right_press_count(hid_mouse_right_press_count),
  .parse_error_count(hid_error_count),.dropped_key_count(hid_dropped_count),
  .gui_help(hid_gui_help),.gui_stats(hid_gui_stats),.gui_speed_2x(hid_gui_speed_2x),
  .gui_cursor_alt(hid_gui_cursor_alt),.gui_term_focus(hid_gui_term_focus),.state_toggle(hid_state_toggle));
 axi_boot_periph #(.UART_BAUD_DIV(430)) u_local(.clk(sys_clk),.resetn(sys_resetn),.arid(l_arid),.araddr(l_araddr),.arlen(l_arlen),.arsize(l_arsize),.arburst(l_arburst),.arvalid(l_arvalid),.arready(l_arready),.rid(l_rid),.rdata(l_rdata),.rresp(l_rresp),.rlast(l_rlast),.rvalid(l_rvalid),.rready(l_rready),.awid(l_awid),.awaddr(l_awaddr),.awlen(l_awlen),.awsize(l_awsize),.awburst(l_awburst),.awvalid(l_awvalid),.awready(l_awready),.wid(l_wid),.wdata(l_wdata),.wstrb(l_wstrb),.wlast(l_wlast),.wvalid(l_wvalid),.wready(l_wready),.bid(l_bid),.bresp(l_bresp),.bvalid(l_bvalid),.bready(l_bready),.uart_rx(uart_rxd),.uart_tx(uart_txd),.hid_key_valid(hid_key_valid),.hid_key_data(hid_key_data),.hid_key_ready(hid_key_ready),.console_char_valid(console_char_valid),.console_char_data(console_char_data),.mmio_addr(io_addr),.mmio_wr(io_wr),.mmio_wdata(io_wdata),.mmio_wstrb(io_wstrb),.mmio_rdata(io_rdata),.mmio_valid(io_valid));

 // UART/HDMI console mirror.  Keyboard input continues to arrive through
 // uart_rxd; Linux echoes it back through LiteUART, so commands and their
 // output appear on both serial and HDMI.
 wire[4:0]video_text_row;wire[6:0]video_text_col;wire[7:0]video_text_data;
 wire[11:0]video_cursor;wire video_fifo_overflow;
 uart_console_text u_console_text(.sys_clk(sys_clk),.sys_resetn(sys_resetn),
  .char_valid(console_char_valid),.char_data(console_char_data),.pix_clk(pix_clk),
  .pix_resetn(video_resetn),.rd_row(video_text_row),.rd_col(video_text_col),
  .rd_data(video_text_data),.cursor_cell(video_cursor),.fifo_overflow(video_fifo_overflow));
 wire video_vs,video_hs,video_de;wire[7:0]video_r,video_g,video_b;
 video_linux_console u_video(.pix_clk(pix_clk),.rstn(video_resetn),
  .text_rd_row(video_text_row),.text_rd_col(video_text_col),
 .text_rd_data(video_text_data),.cursor_cell(video_cursor),.vs_out(video_vs),
  .hs_out(video_hs),.de_out(video_de),.r_out(video_r),.g_out(video_g),.b_out(video_b));

 // The framebuffer uses two fixed, non-overlapping DDR slots.  Software can
 // enable scanout and page-flip, but cannot supply an arbitrary DMA address.
 wire fb_enable_sys,fb_requested_buffer_sys,fb_clear_underflow_toggle_sys;
 wire camera_scanout_enable_sys,camera_published_buffer_sys;
 wire fb_dma_enable_sys=camera_scanout_enable_sys?1'b1:fb_enable_sys;
 wire fb_dma_requested_buffer_sys=camera_scanout_enable_sys?
  camera_published_buffer_sys:fb_requested_buffer_sys;
 wire fb_active_enable_pix,fb_active_buffer_pix,fb_underflow_pix;
 wire[31:0]fb_frame_count_pix,fb_underflow_count_pix;
 wire fb_dma_busy_ddr,fb_dma_error_ddr;
 wire fb_vs,fb_hs,fb_de;wire[7:0]fb_r,fb_g,fb_b;
 wire selected_vs=fb_active_enable_pix?fb_vs:video_vs;
 wire selected_hs=fb_active_enable_pix?fb_hs:video_hs;
 wire selected_de=fb_active_enable_pix?fb_de:video_de;
 wire[7:0]selected_r=fb_active_enable_pix?fb_r:video_r;
 wire[7:0]selected_g=fb_active_enable_pix?fb_g:video_g;
 wire[7:0]selected_b=fb_active_enable_pix?fb_b:video_b;

 // Bundle-and-toggle CDC.  CH9350 state is stable between low-rate UART
 // reports; the toggle transfers a coherent snapshot into the pixel domain.
 reg hid_toggle_meta,hid_toggle_sync,hid_toggle_seen_pix;
 reg[10:0]hid_mouse_x_pix;reg[9:0]hid_mouse_y_pix;reg[2:0]hid_mouse_buttons_pix;
 reg[7:0]hid_mouse_wheel_pix,hid_usage_pix;reg hid_keyboard_seen_pix,hid_mouse_seen_pix;
 reg[31:0]hid_keyboard_count_pix,hid_mouse_count_pix,hid_error_count_pix;
 reg hid_gui_help_pix,hid_gui_stats_pix,hid_gui_speed_pix,hid_gui_cursor_pix,hid_gui_term_pix;
 always@(posedge pix_clk or negedge video_resetn)begin
  if(!video_resetn)begin
   hid_toggle_meta<=0;hid_toggle_sync<=0;hid_toggle_seen_pix<=0;
   hid_mouse_x_pix<=11'd640;hid_mouse_y_pix<=10'd360;hid_mouse_buttons_pix<=0;
   hid_mouse_wheel_pix<=0;hid_usage_pix<=0;hid_keyboard_seen_pix<=0;hid_mouse_seen_pix<=0;
   hid_keyboard_count_pix<=0;hid_mouse_count_pix<=0;hid_error_count_pix<=0;
   hid_gui_help_pix<=0;hid_gui_stats_pix<=0;hid_gui_speed_pix<=0;hid_gui_cursor_pix<=0;hid_gui_term_pix<=1;
  end else begin
   hid_toggle_meta<=hid_state_toggle;hid_toggle_sync<=hid_toggle_meta;
   if(hid_toggle_sync!=hid_toggle_seen_pix)begin
    hid_toggle_seen_pix<=hid_toggle_sync;hid_mouse_x_pix<=hid_mouse_x;hid_mouse_y_pix<=hid_mouse_y;
    hid_mouse_buttons_pix<=hid_mouse_buttons;hid_mouse_wheel_pix<=hid_mouse_wheel;hid_usage_pix<=hid_keyboard_usage;
    hid_keyboard_seen_pix<=hid_keyboard_seen;hid_mouse_seen_pix<=hid_mouse_seen;
    hid_keyboard_count_pix<=hid_keyboard_count;hid_mouse_count_pix<=hid_mouse_count;hid_error_count_pix<=hid_error_count;
    hid_gui_help_pix<=hid_gui_help;hid_gui_stats_pix<=hid_gui_stats;hid_gui_speed_pix<=hid_gui_speed_2x;
    hid_gui_cursor_pix<=hid_gui_cursor_alt;hid_gui_term_pix<=hid_gui_term_focus;
   end
  end
 end
 wire gui_vs,gui_hs,gui_de;wire[7:0]gui_r,gui_g,gui_b;
 hid_gui_overlay #(.LINUX_PROFILE(1)) u_hid_gui(.pix_clk(pix_clk),.resetn(video_resetn),
  .hs_in(selected_hs),.vs_in(selected_vs),.de_in(selected_de),
  .r_in(selected_r),.g_in(selected_g),.b_in(selected_b),
  .mouse_x(hid_mouse_x_pix),.mouse_y(hid_mouse_y_pix),.mouse_buttons(hid_mouse_buttons_pix),
  .mouse_wheel(hid_mouse_wheel_pix),.last_usage(hid_usage_pix),
  .keyboard_seen(hid_keyboard_seen_pix),.mouse_seen(hid_mouse_seen_pix),
  .keyboard_count(hid_keyboard_count_pix),.mouse_count(hid_mouse_count_pix),.error_count(hid_error_count_pix),
  .gui_help(hid_gui_help_pix),.gui_stats(hid_gui_stats_pix),.gui_speed_2x(hid_gui_speed_pix),
  .gui_cursor_alt(hid_gui_cursor_pix),.gui_term_focus(hid_gui_term_pix),
  .hs_out(gui_hs),.vs_out(gui_vs),.de_out(gui_de),.r_out(gui_r),.g_out(gui_g),.b_out(gui_b));

 // Camera bypasses the HID overlay. Only camera_sd enables this HDMI-only HUD.
 // Its two pixel stages preserve the existing alignment and VSYNC switching.
 wire camera_fb_vs,camera_fb_hs,camera_fb_de;
 wire[7:0]camera_fb_r,camera_fb_g,camera_fb_b;
 wire[255:0]camera_hud_text_cpu;wire[2:0]camera_hud_style_cpu;
 wire camera_hud_toggle_cpu,camera_hud_ack_pix;
 camera_sd_hud u_camera_sd_hud(.clk(pix_clk),.resetn(video_resetn),
  .text_cpu(camera_hud_text_cpu),.style_cpu(camera_hud_style_cpu),
  .toggle_cpu(camera_hud_toggle_cpu),.ack_pix(camera_hud_ack_pix),
  .vs_in(fb_vs),.hs_in(fb_hs),.de_in(fb_de),.r_in(fb_r),.g_in(fb_g),.b_in(fb_b),
  .vs_out(camera_fb_vs),.hs_out(camera_fb_hs),.de_out(camera_fb_de),
  .r_out(camera_fb_r),.g_out(camera_fb_g),.b_out(camera_fb_b));
 reg camera_mode_p1,camera_mode_p2,camera_mode_active_pix,camera_fb_vs_d;
 always@(posedge pix_clk or negedge video_resetn)begin
  if(!video_resetn)begin
   camera_mode_p1<=0;camera_mode_p2<=0;camera_mode_active_pix<=0;
   camera_fb_vs_d<=0;
  end
  else begin
   camera_mode_p1<=camera_scanout_enable_sys;camera_mode_p2<=camera_mode_p1;
   camera_fb_vs_d<=camera_fb_vs;
   if(!camera_fb_vs_d&&camera_fb_vs)
    camera_mode_active_pix<=camera_mode_p2&&fb_active_enable_pix;
  end
 end
 wire camera_video_selected_pix=camera_mode_active_pix;
 wire hdmi_source_vs=camera_video_selected_pix?camera_fb_vs:gui_vs;
 wire hdmi_source_hs=camera_video_selected_pix?camera_fb_hs:gui_hs;
 wire hdmi_source_de=camera_video_selected_pix?camera_fb_de:gui_de;
 wire[7:0]hdmi_source_r=camera_video_selected_pix?camera_fb_r:gui_r;
 wire[7:0]hdmi_source_g=camera_video_selected_pix?camera_fb_g:gui_g;
 wire[7:0]hdmi_source_b=camera_video_selected_pix?camera_fb_b:gui_b;

 wire hdmi_init_i2c;
 ms72xx_tx_only #(.CLK_FRE(7_071_428)) u_hdmi_tx(.clk(i2c_cfg_clk),
  .rst_n(phy_rstn&&video_pll_lock),.init_over(hdmi_init_i2c),.iic_scl(hd_scl),
  .iic_sda(hd_sda),.busy_stat());
 reg hdmi_init_m,hdmi_init_s;always@(posedge pix_clk or negedge video_resetn)
  if(!video_resetn)begin hdmi_init_m<=0;hdmi_init_s<=0;end
  else begin hdmi_init_m<=hdmi_init_i2c;hdmi_init_s<=hdmi_init_m;end
 reg hdmi_init_d;reg hdmi_vs_q,hdmi_hs_q,hdmi_de_q;reg[7:0]hdmi_r_q,hdmi_g_q,hdmi_b_q;
 always@(posedge pix_clk)begin
  if(!video_resetn)begin hdmi_init_d<=0;hdmi_vs_q<=0;hdmi_hs_q<=0;hdmi_de_q<=0;hdmi_r_q<=0;hdmi_g_q<=0;hdmi_b_q<=0;end
  else begin hdmi_init_d<=hdmi_init_s;hdmi_vs_q<=hdmi_source_vs;hdmi_hs_q<=hdmi_source_hs;hdmi_de_q<=hdmi_source_de;hdmi_r_q<=hdmi_source_r;hdmi_g_q<=hdmi_source_g;hdmi_b_q<=hdmi_source_b;end
 end
 assign hdmi_init_done=hdmi_init_s;
 assign pixclk_out=pix_clk;
 assign vs_out=hdmi_init_d?hdmi_vs_q:1'b0;assign hs_out=hdmi_init_d?hdmi_hs_q:1'b0;
 assign de_out=hdmi_init_d?hdmi_de_q:1'b0;assign r_out=hdmi_init_d?hdmi_r_q:8'd0;
 assign g_out=hdmi_init_d?hdmi_g_q:8'd0;assign b_out=hdmi_init_d?hdmi_b_q:8'd0;

 wire[31:0]spi_rdata,sd_rdata,audio_rdata,eth_rdata,mac_reg_rdata,fb_reg_rdata,camera_reg_rdata;
 wire spi_hit,sd_hit,audio_hit,eth_hit,fb_hit,camera_hit,mac_irq,flash_clk_enable_n;
 wire camera_control_enable_cpu,camera_stop_request_cpu,camera_snapshot_hold_cpu;
 wire camera_cmos1_init_done_raw,camera_cmos2_init_done_raw,camera_sccb_nack_raw;
 reg camera_cmos1_init_done_c1,camera_cmos1_init_done_cpu;
 reg camera_cmos2_init_done_c1,camera_cmos2_init_done_cpu;
 reg camera_sccb_nack_c1,camera_sccb_nack_cpu;
 reg camera_frame_valid_cpu,camera_writer_busy_cpu,camera_idle_cpu,camera_stopping_cpu;
 reg camera_snapshot_ready_cpu,camera_snapshot_ready_c1;
 reg camera_snapshot_buffer_cpu,camera_snapshot_buffer_c1;
 reg[31:0]camera_snapshot_frame_count_cpu,camera_snapshot_frame_count_c1;
 reg camera_completed_buffer_cpu,camera_frame_error_cpu,camera_ddr_error_cpu;
 reg[31:0]camera_frame_count_cpu,camera_dropped_count_cpu,camera_bad_line_count_cpu;
 reg camera_frame_valid_c1,camera_frame_valid_c2,camera_frame_valid_c3;
 reg camera_writer_busy_c1,camera_idle_c1,camera_stopping_c1;
 reg camera_completed_buffer_c1,camera_frame_error_c1,camera_ddr_error_c1;
 reg[31:0]camera_frame_count_c1,camera_dropped_count_c1,camera_bad_line_count_c1;
 wire sys_hit=(io_addr>=32'h1fe0_0300)&&(io_addr<32'h1fe0_0320);
 wire hid_hit=(io_addr>=32'h1fe0_0400)&&(io_addr<32'h1fe0_042c);
 wire mac_hit=(io_addr>=32'h1fe1_0000)&&(io_addr<32'h1fe1_0200);
 reg[1:0]ddr_ready_sys;always@(posedge sys_clk)if(!sys_resetn)ddr_ready_sys<=0;else ddr_ready_sys<={ddr_ready_sys[0],ddr_init_done};
 reg[31:0]sys_rdata;always@*case(io_addr[4:2])
  0:sys_rdata=32'h5356_3300;1:sys_rdata={30'b0,phy_rstn,ddr_ready_sys[1]};
  2:sys_rdata=SYS_HZ;3:sys_rdata=32'h0000_001f;
  4:sys_rdata={31'b0,mac_irq};5:sys_rdata=CPU_HZ;
  6:sys_rdata=TIMEBASE_HZ;default:sys_rdata=0;
 endcase
 reg[31:0]hid_rdata;always@*case(io_addr[5:2])
  0:hid_rdata=32'h4348_3935;1:hid_rdata=32'h0002_0020;
  2:hid_rdata={21'b0,hid_gui_term_focus,hid_gui_cursor_alt,hid_gui_speed_2x,hid_gui_stats,hid_gui_help,hid_caps_lock,hid_mouse_seen,hid_keyboard_seen,hid_mouse_buttons};
  3:hid_rdata={11'b0,hid_mouse_y,hid_mouse_x};
  4:hid_rdata={hid_mouse_wheel,hid_mouse_dy,hid_mouse_dx,5'b0,hid_mouse_buttons};
  5:hid_rdata={8'b0,hid_keyboard_ascii,hid_keyboard_modifier,hid_keyboard_usage};
  6:hid_rdata=hid_keyboard_count;7:hid_rdata=hid_mouse_count;8:hid_rdata=hid_error_count;9:hid_rdata=hid_dropped_count;
  10:hid_rdata={hid_mouse_right_press_count,hid_mouse_left_press_count};
  default:hid_rdata=0;
 endcase
 assign io_valid=spi_hit||sd_hit||audio_hit||eth_hit||sys_hit||hid_hit||mac_hit||fb_hit||camera_hit;
 assign io_rdata=spi_hit?spi_rdata:sd_hit?sd_rdata:audio_hit?audio_rdata:eth_hit?eth_rdata:hid_hit?hid_rdata:
  mac_hit?mac_reg_rdata:fb_hit?fb_reg_rdata:camera_hit?camera_reg_rdata:sys_rdata;
 video_fb_mmio u_fb_regs(.clk(sys_clk),.resetn(sys_resetn),.addr(io_addr),
  .wr(io_wr),.wdata(io_wdata),.wstrb(io_wstrb),.rdata(fb_reg_rdata),.hit(fb_hit),
  .enable(fb_enable_sys),.requested_buffer(fb_requested_buffer_sys),
  .clear_underflow_toggle(fb_clear_underflow_toggle_sys),
  .active_enable_pix(fb_active_enable_pix),.active_buffer_pix(fb_active_buffer_pix),
  .underflow_pix(fb_underflow_pix),.frame_count_pix(fb_frame_count_pix),
  .underflow_count_pix(fb_underflow_count_pix),.dma_busy_ddr(fb_dma_busy_ddr),
  .dma_error_ddr(fb_dma_error_ddr));
 camera_mmio u_camera_regs(.clk(sys_clk),.resetn(sys_resetn),.addr(io_addr),
  .wr(io_wr),.wdata(io_wdata),.wstrb(io_wstrb),.rdata(camera_reg_rdata),.hit(camera_hit),
  .enable(camera_control_enable_cpu),.stop_request(camera_stop_request_cpu),
  .snapshot_hold(camera_snapshot_hold_cpu),.snapshot_ready(camera_snapshot_ready_cpu),
  .hud_text(camera_hud_text_cpu),.hud_style(camera_hud_style_cpu),
  .hud_toggle(camera_hud_toggle_cpu),.hud_ack(camera_hud_ack_pix),
  .snapshot_buffer(camera_snapshot_buffer_cpu),
  .snapshot_frame_count(camera_snapshot_frame_count_cpu),
  .cmos1_init_done(camera_cmos1_init_done_cpu),.cmos2_init_done(camera_cmos2_init_done_cpu),
  .frame_valid(camera_frame_valid_cpu),.writer_busy(camera_writer_busy_cpu),
  .idle(camera_idle_cpu),.stopping(camera_stopping_cpu),
  .completed_buffer(camera_completed_buffer_cpu),.sccb_nack(camera_sccb_nack_cpu),
 .frame_error(camera_frame_error_cpu),.ddr_error(camera_ddr_error_cpu),
 .frame_count(camera_frame_count_cpu),.dropped_count(camera_dropped_count_cpu),
 .bad_line_count(camera_bad_line_count_cpu));

 // Both sensors are initialized exactly as in the official dual-OV5640 demo;
 // CMOS2 is the fixed capture source for the bootloader camera command.
 wire camera_sensor_enable_ddr;
 reg camera_sensor_enable_c1,camera_sensor_enable_c2;
 always@(posedge sys_clk or negedge sys_resetn)begin
  if(!sys_resetn)begin
   camera_sensor_enable_c1<=0;camera_sensor_enable_c2<=0;
   camera_cmos1_init_done_c1<=0;camera_cmos1_init_done_cpu<=0;
   camera_cmos2_init_done_c1<=0;camera_cmos2_init_done_cpu<=0;
   camera_sccb_nack_c1<=0;camera_sccb_nack_cpu<=0;
  end
  else begin
   camera_sensor_enable_c1<=camera_sensor_enable_ddr;
   camera_sensor_enable_c2<=camera_sensor_enable_c1;
   camera_cmos1_init_done_c1<=camera_cmos1_init_done_raw;
   camera_cmos1_init_done_cpu<=camera_cmos1_init_done_c1;
   camera_cmos2_init_done_c1<=camera_cmos2_init_done_raw;
   camera_cmos2_init_done_cpu<=camera_cmos2_init_done_c1;
   camera_sccb_nack_c1<=camera_sccb_nack_raw;
   camera_sccb_nack_cpu<=camera_sccb_nack_c1;
  end
 end
 dual_ov5640_sensor #(.SCCB_DIVIDER_MAX(16'd2474)) u_dual_ov5640(
  .clk_50m(sys_clk),.clk_25m(sys_clk),.resetn(sys_resetn),
  .camera_enable(camera_sensor_enable_c2),
  .camera1_resetn(cmos1_reset),.camera2_resetn(cmos2_reset),
  .camera_powerdown(),.camera1_init_done(camera_cmos1_init_done_raw),
  .camera2_init_done(camera_cmos2_init_done_raw),
  .sccb_nack_seen(camera_sccb_nack_raw),
  .camera1_scl(cmos1_scl),.camera1_sda(cmos1_sda),
  .camera2_scl(cmos2_scl),.camera2_sda(cmos2_sda));

 // Asserting camera disable resets the byte-pairing stage asynchronously.
 // Deassertion is released only on CMOS2 PCLK edges after the sensor restarts.
 wire camera_capture_async_resetn=sys_resetn&&camera_sensor_enable_c2;
 reg[1:0]camera_capture_reset_pipe;
 reg[1:0]camera_writer_reset_pipe;
 reg camera_capture_init_m,camera_capture_init_s;
 always@(posedge cmos2_pclk or negedge domains_async_resetn)begin
  if(!domains_async_resetn)camera_writer_reset_pipe<=0;
  else camera_writer_reset_pipe<={camera_writer_reset_pipe[0],1'b1};
 end
 always@(posedge cmos2_pclk or negedge camera_capture_async_resetn)begin
  if(!camera_capture_async_resetn)begin
   camera_capture_reset_pipe<=0;camera_capture_init_m<=0;camera_capture_init_s<=0;
  end else begin
   camera_capture_reset_pipe<={camera_capture_reset_pipe[0],1'b1};
   camera_capture_init_m<=camera_cmos2_init_done_cpu;
   camera_capture_init_s<=camera_capture_init_m;
  end
 end
 wire camera_capture_resetn=camera_capture_reset_pipe[1];
 wire camera_writer_pixel_resetn=camera_writer_reset_pipe[1];
 wire camera_frame_vsync_pclk,camera_line_active_pclk,camera_pixel_valid_pclk;
 wire[15:0]camera_pixel_rgb565_pclk;
 ov5640_cmos2_capture u_cmos2_capture(.pclk(cmos2_pclk),
  .resetn(camera_capture_resetn),.capture_enable(camera_capture_init_s),
  .camera_vsync(cmos2_vsync),.camera_href(cmos2_href),.camera_data(cmos2_data),
  .frame_vsync(camera_frame_vsync_pclk),.line_active(camera_line_active_pclk),
  .pixel_valid(camera_pixel_valid_pclk),.pixel_rgb565(camera_pixel_rgb565_pclk));

 spi_flash_mmio u_flash(.clk(sys_clk),.resetn(sys_resetn),.addr(io_addr),.wr(io_wr),.wdata(io_wdata),.wstrb(io_wstrb),.rdata(spi_rdata),.hit(spi_hit),.spi_cs_n(spi_cs),.spi_dq0(spi_dq0),.spi_dq1(spi_dq1),.clk_enable_n(flash_clk_enable_n));
 GTP_CFGCLK u_cfgclk(.CE_N(flash_clk_enable_n),.CLKIN(sys_clk));
 wire sd_cmd_out,sd_cmd_oe;
 wire[3:0]sd_dat_in={sd_data3,sd_data2,sd_data1,sd_data0};
 assign sd_cmd=sd_cmd_oe?sd_cmd_out:1'bz;
 // Keep every DAT lane released outside an active native SD write so the
 // card exclusively drives data and DAT0 busy in native SD mode.
 wire[3:0]sd_dat_out;wire sd_dat_oe;
 assign sd_data0=sd_dat_oe?sd_dat_out[0]:1'bz;
 assign sd_data1=sd_dat_oe?sd_dat_out[1]:1'bz;
 assign sd_data2=sd_dat_oe?sd_dat_out[2]:1'bz;
 assign sd_data3=sd_dat_oe?sd_dat_out[3]:1'bz;
 sd_native_mmio u_sd(.clk(sys_clk),.resetn(sys_resetn),.addr(io_addr),.wr(io_wr),
  .wdata(io_wdata),.wstrb(io_wstrb),.rdata(sd_rdata),.hit(sd_hit),
  .sd_clk(sd_clk),.sd_cmd_in(sd_cmd),.sd_cmd_out(sd_cmd_out),
  .sd_cmd_oe(sd_cmd_oe),.sd_dat_in(sd_dat_in),.sd_dat_out(sd_dat_out),
  .sd_dat_oe(sd_dat_oe),.sd_detect_n(sd_detect_n));

 wire audio_sample_write,audio_fifo_full,audio_counter_clear;
 wire[15:0]audio_sample_data;
 wire[4:0]audio_fifo_level;
 wire[23:0]audio_microphone_sample;
 wire[31:0]audio_microphone_count,audio_playback_underflows;
 wire audio_microphone_read,audio_microphone_fifo_empty,audio_microphone_fifo_full;
 wire[23:0]audio_microphone_fifo_data;
 wire[9:0]audio_microphone_fifo_level;
 wire[31:0]audio_microphone_overflows;
 audio_mmio u_audio_regs(.clk(sys_clk),.resetn(sys_resetn),.addr(io_addr),
  .wr(io_wr),.wdata(io_wdata),.wstrb(io_wstrb),.rdata(audio_rdata),.hit(audio_hit),
  .sample_write(audio_sample_write),.sample_data(audio_sample_data),
  .fifo_full(audio_fifo_full),.fifo_level(audio_fifo_level),
  .microphone_sample(audio_microphone_sample),.microphone_count(audio_microphone_count),
  .playback_underflows(audio_playback_underflows),.counter_clear(audio_counter_clear),
  .microphone_read(audio_microphone_read),.microphone_fifo_data(audio_microphone_fifo_data),
  .microphone_fifo_empty(audio_microphone_fifo_empty),
  .microphone_fifo_full(audio_microphone_fifo_full),
  .microphone_fifo_level(audio_microphone_fifo_level),.microphone_overflows(audio_microphone_overflows));
 i2s_audio_duplex u_audio_i2s(.clk(sys_clk),.resetn(sys_resetn),
  .counter_clear(audio_counter_clear),.mic_sd(microphone_sd),
  .i2s_bclk(audio_bclk),.i2s_ws(audio_ws),.amp_sd(spk_din),
  .sample_write(audio_sample_write),.sample_data(audio_sample_data),
  .fifo_full(audio_fifo_full),.fifo_level(audio_fifo_level),
  .microphone_sample(audio_microphone_sample),.microphone_count(audio_microphone_count),
  .playback_underflows(audio_playback_underflows),.microphone_read(audio_microphone_read),
  .microphone_fifo_data(audio_microphone_fifo_data),
  .microphone_fifo_empty(audio_microphone_fifo_empty),
  .microphone_fifo_full(audio_microphone_fifo_full),
  .microphone_fifo_level(audio_microphone_fifo_level),.microphone_overflows(audio_microphone_overflows));

 // A dedicated 1 MiB region of Linux-visible DDR is reserved for accelerator staging.
 // CPU software accesses it through the uncached 0x9b00_0000 alias while the
 // DMA uses its physical 0x1b00_0000 address.
 mac_accel_ddr_kernel_top #(.DDR_BASE(32'h1b00_0000),.DDR_BYTES(1024*1024),
  .ENABLE_PFF1_GATHER(1),.ENABLE_CONV(ENABLE_CONV_CANDIDATE),
  .WEIGHT_BANK_LINES(WEIGHT_BANK_LINES),.ENABLE_FP8(ENABLE_FP8)) u_mac_accel(
  .clk(sys_clk),.resetn(sys_resetn),.reg_wr_en(io_wr&&mac_hit),
  .reg_wr_addr(io_addr[8:0]),.reg_wr_data(io_wdata),.reg_wr_strb(io_wstrb),
  .reg_rd_addr(io_addr[8:0]),.reg_rd_data(mac_reg_rdata),.irq(mac_irq),
  .m_axi_awaddr(mac_awaddr),.m_axi_awlen(mac_awlen),.m_axi_awsize(mac_awsize),
  .m_axi_awburst(mac_awburst),.m_axi_awvalid(mac_awvalid),.m_axi_awready(mac_awready),
  .m_axi_wdata(mac_wdata_axi),.m_axi_wstrb(mac_wstrb_axi),.m_axi_wlast(mac_wlast),
  .m_axi_wvalid(mac_wvalid),.m_axi_wready(mac_wready),.m_axi_bresp(mac_bresp_axi),
  .m_axi_bvalid(mac_bvalid),.m_axi_bready(mac_bready),.m_axi_araddr(mac_araddr),
  .m_axi_arlen(mac_arlen),.m_axi_arsize(mac_arsize),.m_axi_arburst(mac_arburst),
  .m_axi_arvalid(mac_arvalid),.m_axi_arready(mac_arready),.m_axi_rdata(mac_rdata_axi),
  .m_axi_rresp(mac_rresp_axi),.m_axi_rlast(mac_rlast),.m_axi_rvalid(mac_rvalid),
  .m_axi_rready(mac_rready));

 // The host and PHY are deliberately fixed at 100 Mbit/s for reliable
 // Linux-image transfers on this board/cable.  In 100M RGMII mode RXC is
 // 25 MHz, so the vendor reference GPLL (configured for a 125 MHz input)
 // must be bypassed.  The RGMII wrapper buffers RXC and reconstructs one
 // MAC byte from the two successive, duplicated DDR nibbles.
 wire eth_clk,mac_rx_error,mac_rx_valid,mac_rx_byte_valid,mac_rx_restart;wire[7:0]mac_rx_data,mac_tx_data;wire mac_tx_valid,mac_tx_ready;wire[7:0]eth_tx_delay_step,eth_rx_delay_step;
 wire rgmii_resetn=eth_resetn;
 eth_mac_mmio u_eth(.sys_clk(sys_clk),.sys_resetn(eth_resetn),.addr(io_addr),.wr(io_wr),.wdata(io_wdata),.wstrb(io_wstrb),.rdata(eth_rdata),.hit(eth_hit),.mac_clk(eth_clk),.mac_resetn(rgmii_resetn),.mac_rx_data(mac_rx_data),.mac_rx_valid(mac_rx_valid),.mac_rx_byte_valid(mac_rx_byte_valid),.mac_rx_error(mac_rx_error),.mac_tx_data(mac_tx_data),.mac_tx_valid(mac_tx_valid),.mac_tx_ready(mac_tx_ready),.mac_rx_restart(mac_rx_restart),.phy_reset_req(phy_reset_req),.eth_reset_req(eth_reset_req),.tx_delay_step(eth_tx_delay_step),.rx_delay_step(eth_rx_delay_step));
 rgmii_interface u_rgmii(.rst(~phy_rstn||~rgmii_resetn),.rx_restart(mac_rx_restart),.speed_100(1'b1),.rgmii_clk(eth_clk),.rgmii_clk_90p(1'b0),.tx_delay_step(eth_tx_delay_step),.rx_delay_step(eth_rx_delay_step),.mac_tx_data_valid(mac_tx_valid),.mac_tx_data(mac_tx_data),.mac_tx_ready(mac_tx_ready),.mac_rx_error(mac_rx_error),.mac_rx_data_valid(mac_rx_valid),.mac_rx_byte_valid(mac_rx_byte_valid),.mac_rx_data(mac_rx_data),.rgmii_rxc(rgmii_rxc),.rgmii_rx_ctl(rgmii_rx_ctl),.rgmii_rxd(rgmii_rxd),.rgmii_txc(rgmii_txc),.rgmii_tx_ctl(rgmii_tx_ctl),.rgmii_txd(rgmii_txd));

 wire ddr_clk,ddr_init_done,pll_lock,phy_pll_lock,gpll_lock,rst_gpll_lock,ddrphy_cpd_lock;
 reg [2:0] ddr_rst_pipe;
 always @(posedge ddr_clk or negedge domains_async_resetn)
  if (!domains_async_resetn) ddr_rst_pipe <= 3'b0;
  else ddr_rst_pipe <= {ddr_rst_pipe[1:0], 1'b1};
 wire ddr_resetn = ddr_rst_pipe[2];
 wire[27:0]n_awaddr,n_araddr;wire n_awap,n_arap;wire[3:0]n_awid,n_arid,n_awlen,n_arlen,n_woutid,n_rid;wire n_awvalid,n_awready,n_wready,n_wlastout,n_arvalid,n_arready,n_rlast,n_rvalid;wire[255:0]n_wdata,n_rdata;wire[31:0]n_wstrb;
 wire[27:0]bridge_awaddr;wire bridge_awap,bridge_awvalid,bridge_awready,bridge_wready,bridge_wlastout;
 wire[3:0]bridge_awid,bridge_awlen,bridge_woutid;wire[255:0]bridge_wdata;wire[31:0]bridge_wstrb;
 wire[27:0]camera_awaddr;wire camera_awvalid,camera_awready,camera_wready,camera_wlastout,camera_write_urgent;
 wire[3:0]camera_awid,camera_awlen,camera_woutid;wire[255:0]camera_wdata;wire[31:0]camera_wstrb;
 wire native_write_busy,native_write_owner_camera;
 wire camera_frame_accept_ddr,camera_write_buffer_ddr,camera_frame_valid_ddr;
 wire camera_published_buffer_ddr,camera_buffer_idle_ddr,camera_stopping_ddr;
 wire camera_snapshot_ready_ddr;
 wire camera_snapshot_buffer_ddr;
 wire[31:0]camera_snapshot_frame_count_ddr;
 wire camera_writer_started_ddr,camera_writer_complete_ddr;
 wire camera_writer_completed_buffer_ddr,camera_writer_busy_ddr,camera_writer_idle_ddr;
 wire camera_writer_ddr_error_ddr;
 wire[31:0]camera_frame_count_ddr,camera_dropped_count_ddr,camera_bad_line_count_ddr;
 reg camera_control_enable_d1,camera_control_enable_d2;
 reg camera_stop_request_d1,camera_stop_request_d2;
 reg camera_snapshot_hold_d1,camera_snapshot_hold_d2;
 reg camera_display_enable_d1,camera_display_enable_d2;
 reg camera_display_buffer_d1,camera_display_buffer_d2;
 wire[27:0]bridge_araddr,fb_araddr;wire bridge_arap,bridge_arvalid,bridge_arready,bridge_rlast,bridge_rvalid;
 wire[3:0]bridge_arid,bridge_arlen,bridge_rid,fb_arid,fb_arlen;wire[255:0]bridge_rdata;wire fb_arvalid,fb_arready,fb_urgent,fb_rlast,fb_rvalid;wire[255:0]fb_rdata;wire[3:0]fb_rid;
 axi_ddr_cdc u_ddr_bridge(.sys_clk(sys_clk),.sys_resetn(sys_resetn),.s_arid(a_arid),.s_araddr(a_araddr),.s_arlen(a_arlen),.s_arsize(a_arsize),.s_arburst(a_arburst),.s_arvalid(a_arvalid),.s_arready(a_arready),.s_rid(a_rid),.s_rdata(a_rdata),.s_rresp(a_rresp),.s_rlast(a_rlast),.s_rvalid(a_rvalid),.s_rready(a_rready),.s_awid(a_awid),.s_awaddr(a_awaddr),.s_awlen(a_awlen),.s_awsize(a_awsize),.s_awburst(a_awburst),.s_awvalid(a_awvalid),.s_awready(a_awready),.s_wid(a_wid),.s_wdata(a_wdata),.s_wstrb(a_wstrb),.s_wlast(a_wlast),.s_wvalid(a_wvalid),.s_wready(a_wready),.s_bid(a_bid),.s_bresp(a_bresp),.s_bvalid(a_bvalid),.s_bready(a_bready),.ddr_clk(ddr_clk),.ddr_resetn(ddr_resetn),.ddr_init_done(ddr_init_done),.m_awaddr(bridge_awaddr),.m_awuser_ap(bridge_awap),.m_awuser_id(bridge_awid),.m_awlen(bridge_awlen),.m_awvalid(bridge_awvalid),.m_awready(bridge_awready),.m_wdata(bridge_wdata),.m_wstrb(bridge_wstrb),.m_wready(bridge_wready),.m_wusero_id(bridge_woutid),.m_wusero_last(bridge_wlastout),.m_araddr(bridge_araddr),.m_aruser_ap(bridge_arap),.m_aruser_id(bridge_arid),.m_arlen(bridge_arlen),.m_arvalid(bridge_arvalid),.m_arready(bridge_arready),.m_rdata(bridge_rdata),.m_rid(bridge_rid),.m_rlast(bridge_rlast),.m_rvalid(bridge_rvalid));

 video_fb_dma u_fb_dma(.sys_enable(fb_dma_enable_sys),
  .sys_requested_buffer(fb_dma_requested_buffer_sys),
  .sys_clear_underflow_toggle(fb_clear_underflow_toggle_sys),
  .ddr_clk(ddr_clk),.ddr_resetn(ddr_resetn),.ddr_init_done(ddr_init_done),
  .fb_araddr(fb_araddr),.fb_arid(fb_arid),.fb_arlen(fb_arlen),
  .fb_arvalid(fb_arvalid),.fb_urgent(fb_urgent),.fb_arready(fb_arready),
  .fb_rdata(fb_rdata),.fb_rid(fb_rid),.fb_rlast(fb_rlast),
  .fb_rvalid(fb_rvalid),.dma_busy_ddr(fb_dma_busy_ddr),
  .dma_error_ddr(fb_dma_error_ddr),.pix_clk(pix_clk),
  .pix_resetn(video_resetn),.active_enable_pix(fb_active_enable_pix),
  .active_buffer_pix(fb_active_buffer_pix),.underflow_pix(fb_underflow_pix),
 .frame_count_pix(fb_frame_count_pix),
 .underflow_count_pix(fb_underflow_count_pix),.vs_out(fb_vs),
 .hs_out(fb_hs),.de_out(fb_de),.r_out(fb_r),.g_out(fb_g),.b_out(fb_b));

 // Camera control crosses from the CPU domain into the native DDR domain.
 // The active framebuffer indication crosses back from the HDMI pixel domain
 // so the writer never overwrites the bank currently being scanned out.
 always@(posedge ddr_clk or negedge ddr_resetn)begin
  if(!ddr_resetn)begin
   camera_control_enable_d1<=0;camera_control_enable_d2<=0;
   camera_stop_request_d1<=0;camera_stop_request_d2<=0;
   camera_snapshot_hold_d1<=0;camera_snapshot_hold_d2<=0;
   camera_display_enable_d1<=0;camera_display_enable_d2<=0;
   camera_display_buffer_d1<=0;camera_display_buffer_d2<=0;
  end else begin
   camera_control_enable_d1<=camera_control_enable_cpu;
   camera_control_enable_d2<=camera_control_enable_d1;
   camera_stop_request_d1<=camera_stop_request_cpu;
   camera_stop_request_d2<=camera_stop_request_d1;
   camera_snapshot_hold_d1<=camera_snapshot_hold_cpu;
   camera_snapshot_hold_d2<=camera_snapshot_hold_d1;
   camera_display_enable_d1<=fb_active_enable_pix;
   camera_display_enable_d2<=camera_display_enable_d1;
   camera_display_buffer_d1<=fb_active_buffer_pix;
   camera_display_buffer_d2<=camera_display_buffer_d1;
  end
 end

 camera_buffer_control u_camera_buffer_control(.clk(ddr_clk),.resetn(ddr_resetn),
  .control_enable(camera_control_enable_d2),.stop_request(camera_stop_request_d2),
  .snapshot_hold(camera_snapshot_hold_d2),.snapshot_ready(camera_snapshot_ready_ddr),
  .snapshot_buffer(camera_snapshot_buffer_ddr),
  .snapshot_frame_count(camera_snapshot_frame_count_ddr),
  .writer_started(camera_writer_started_ddr),.writer_complete(camera_writer_complete_ddr),
  .writer_completed_buffer(camera_writer_completed_buffer_ddr),
  .writer_idle(camera_writer_idle_ddr),.display_enable(camera_display_enable_d2),
  .display_buffer(camera_display_buffer_d2),.sensor_enable(camera_sensor_enable_ddr),
  .frame_accept_enable(camera_frame_accept_ddr),.write_buffer(camera_write_buffer_ddr),
  .frame_valid(camera_frame_valid_ddr),.published_buffer(camera_published_buffer_ddr),
  .idle(camera_buffer_idle_ddr),.stopping(camera_stopping_ddr),
  .frame_count(camera_frame_count_ddr));

 camera_frame_writer u_camera_frame_writer(
  .pixel_clk(cmos2_pclk),.pixel_resetn(camera_writer_pixel_resetn),
  .pixel_vsync(camera_frame_vsync_pclk),.pixel_line_active(camera_line_active_pclk),
  .pixel_valid(camera_pixel_valid_pclk),.pixel_rgb565(camera_pixel_rgb565_pclk),
  .ddr_clk(ddr_clk),.ddr_resetn(ddr_resetn),.enable(camera_sensor_enable_ddr),
  .frame_accept_enable(camera_frame_accept_ddr),.write_buffer(camera_write_buffer_ddr),
  .stop_request(camera_stop_request_d2||!camera_control_enable_d2),
  .cam_awaddr(camera_awaddr),.cam_awid(camera_awid),.cam_awlen(camera_awlen),
  .cam_awvalid(camera_awvalid),.cam_awready(camera_awready),
  .cam_wdata(camera_wdata),.cam_wstrb(camera_wstrb),.cam_wready(camera_wready),
  .cam_wid(camera_woutid),.cam_wlast(camera_wlastout),
  .cam_urgent(camera_write_urgent),.frame_started(camera_writer_started_ddr),
  .frame_complete(camera_writer_complete_ddr),
  .completed_buffer(camera_writer_completed_buffer_ddr),
  .busy(camera_writer_busy_ddr),.idle(camera_writer_idle_ddr),
  .bad_line_count(camera_bad_line_count_ddr),
  .drop_frame_count(camera_dropped_count_ddr),
  .ddr_error(camera_writer_ddr_error_ddr));

 wire camera_frame_error_ddr=(camera_bad_line_count_ddr!=0)||
  (camera_dropped_count_ddr!=0);
 assign camera_scanout_enable_sys=camera_control_enable_cpu&&camera_frame_valid_cpu;
 assign camera_published_buffer_sys=camera_completed_buffer_cpu;

 // Low-rate status and counters are sampled twice before software sees them.
 // The counters update only at frame/line boundaries and are diagnostic, so a
 // coherent multiword transaction is unnecessary.
 always@(posedge sys_clk or negedge sys_resetn)begin
  if(!sys_resetn)begin
   camera_frame_valid_c1<=0;camera_frame_valid_c2<=0;
   camera_frame_valid_c3<=0;camera_frame_valid_cpu<=0;
   camera_writer_busy_c1<=0;camera_writer_busy_cpu<=0;
   camera_idle_c1<=0;camera_idle_cpu<=0;
   camera_stopping_c1<=0;camera_stopping_cpu<=0;
   camera_snapshot_ready_c1<=0;camera_snapshot_ready_cpu<=0;
   camera_snapshot_buffer_c1<=0;camera_snapshot_buffer_cpu<=0;
   camera_snapshot_frame_count_c1<=0;camera_snapshot_frame_count_cpu<=0;
   camera_completed_buffer_c1<=0;camera_completed_buffer_cpu<=0;
   camera_frame_error_c1<=0;camera_frame_error_cpu<=0;
   camera_ddr_error_c1<=0;camera_ddr_error_cpu<=0;
   camera_frame_count_c1<=0;camera_frame_count_cpu<=0;
   camera_dropped_count_c1<=0;camera_dropped_count_cpu<=0;
   camera_bad_line_count_c1<=0;camera_bad_line_count_cpu<=0;
  end else begin
   camera_frame_valid_c1<=camera_frame_valid_ddr;
   camera_frame_valid_c2<=camera_frame_valid_c1;
   camera_frame_valid_c3<=camera_frame_valid_c2;
   camera_frame_valid_cpu<=camera_frame_valid_c3;
   camera_writer_busy_c1<=camera_writer_busy_ddr;
   camera_writer_busy_cpu<=camera_writer_busy_c1;
   camera_idle_c1<=camera_buffer_idle_ddr;
   camera_idle_cpu<=camera_idle_c1;
   camera_stopping_c1<=camera_stopping_ddr;
   camera_stopping_cpu<=camera_stopping_c1;
   camera_snapshot_ready_c1<=camera_snapshot_ready_ddr;
   camera_snapshot_ready_cpu<=camera_snapshot_ready_c1;
   camera_snapshot_buffer_c1<=camera_snapshot_buffer_ddr;
   camera_snapshot_buffer_cpu<=camera_snapshot_buffer_c1;
   camera_snapshot_frame_count_c1<=camera_snapshot_frame_count_ddr;
   camera_snapshot_frame_count_cpu<=camera_snapshot_frame_count_c1;
   camera_completed_buffer_c1<=camera_published_buffer_ddr;
   camera_completed_buffer_cpu<=camera_completed_buffer_c1;
   camera_frame_error_c1<=camera_frame_error_ddr;
   camera_frame_error_cpu<=camera_frame_error_c1;
   camera_ddr_error_c1<=camera_writer_ddr_error_ddr;
   camera_ddr_error_cpu<=camera_ddr_error_c1;
   camera_frame_count_c1<=camera_frame_count_ddr;
   camera_frame_count_cpu<=camera_frame_count_c1;
   camera_dropped_count_c1<=camera_dropped_count_ddr;
   camera_dropped_count_cpu<=camera_dropped_count_c1;
   camera_bad_line_count_c1<=camera_bad_line_count_ddr;
   camera_bad_line_count_cpu<=camera_bad_line_count_c1;
  end
 end

 ddr_native_write_arbiter u_native_write_arbiter(.clk(ddr_clk),.resetn(ddr_resetn),
  .s0_awaddr(bridge_awaddr),.s0_awuser_ap(bridge_awap),.s0_awid(bridge_awid),
  .s0_awlen(bridge_awlen),.s0_awvalid(bridge_awvalid),.s0_awready(bridge_awready),
  .s0_wdata(bridge_wdata),.s0_wstrb(bridge_wstrb),.s0_wready(bridge_wready),
  .s0_wusero_id(bridge_woutid),.s0_wusero_last(bridge_wlastout),
  .s1_awaddr(camera_awaddr),.s1_awid(camera_awid),.s1_awlen(camera_awlen),
  .s1_awvalid(camera_awvalid),.s1_urgent(camera_write_urgent),.s1_awready(camera_awready),
  .s1_wdata(camera_wdata),.s1_wstrb(camera_wstrb),.s1_wready(camera_wready),
  .s1_wusero_id(camera_woutid),.s1_wusero_last(camera_wlastout),
  .m_awaddr(n_awaddr),.m_awuser_ap(n_awap),.m_awid(n_awid),.m_awlen(n_awlen),
  .m_awvalid(n_awvalid),.m_awready(n_awready),.m_wdata(n_wdata),.m_wstrb(n_wstrb),
  .m_wready(n_wready),.m_wusero_id(n_woutid),.m_wusero_last(n_wlastout),
  .busy(native_write_busy),.owner_camera(native_write_owner_camera));

 ddr_native_read_arbiter u_native_read_arbiter(.clk(ddr_clk),.resetn(ddr_resetn),
  .s0_araddr(bridge_araddr),.s0_aruser_ap(bridge_arap),.s0_arid(bridge_arid),
  .s0_arlen(bridge_arlen),.s0_arvalid(bridge_arvalid),.s0_arready(bridge_arready),
  .s0_rdata(bridge_rdata),.s0_rid(bridge_rid),.s0_rlast(bridge_rlast),
  .s0_rvalid(bridge_rvalid),.s1_araddr(fb_araddr),.s1_arid(fb_arid),
  .s1_arlen(fb_arlen),.s1_arvalid(fb_arvalid),.s1_urgent(fb_urgent),
  .s1_arready(fb_arready),.s1_rdata(fb_rdata),.s1_rid(fb_rid),
  .s1_rlast(fb_rlast),.s1_rvalid(fb_rvalid),.m_araddr(n_araddr),
  .m_aruser_ap(n_arap),.m_arid(n_arid),.m_arlen(n_arlen),
  .m_arvalid(n_arvalid),.m_arready(n_arready),.m_rdata(n_rdata),
  .m_rid(n_rid),.m_rlast(n_rlast),.m_rvalid(n_rvalid));

 ddr3_test I_ips_ddr_top(.ref_clk(ref_clk),.resetn(domains_async_resetn),.core_clk(ddr_clk),.pll_lock(pll_lock),.phy_pll_lock(phy_pll_lock),.gpll_lock(gpll_lock),.rst_gpll_lock(rst_gpll_lock),.ddrphy_cpd_lock(ddrphy_cpd_lock),.ddr_init_done(ddr_init_done),.axi_awaddr(n_awaddr),.axi_awuser_ap(n_awap),.axi_awuser_id(n_awid),.axi_awlen(n_awlen),.axi_awready(n_awready),.axi_awvalid(n_awvalid),.axi_wdata(n_wdata),.axi_wstrb(n_wstrb),.axi_wready(n_wready),.axi_wusero_id(n_woutid),.axi_wusero_last(n_wlastout),.axi_araddr(n_araddr),.axi_aruser_ap(n_arap),.axi_aruser_id(n_arid),.axi_arlen(n_arlen),.axi_arready(n_arready),.axi_arvalid(n_arvalid),.axi_rdata(n_rdata),.axi_rid(n_rid),.axi_rlast(n_rlast),.axi_rvalid(n_rvalid),.apb_clk(sys_clk),.apb_rst_n(sys_resetn),.apb_sel(1'b0),.apb_enable(1'b0),.apb_addr(8'b0),.apb_write(1'b0),.apb_wdata(16'b0),.mem_cs_n(mem_cs_n),.mem_rst_n(mem_rst_n),.mem_ck(mem_ck),.mem_ck_n(mem_ck_n),.mem_cke(mem_cke),.mem_ras_n(mem_ras_n),.mem_cas_n(mem_cas_n),.mem_we_n(mem_we_n),.mem_odt(mem_odt),.mem_a(mem_a),.mem_ba(mem_ba),.mem_dqs(mem_dqs),.mem_dqs_n(mem_dqs_n),.mem_dq(mem_dq),.mem_dm(mem_dm),.dbg_gate_start(1'b0),.dbg_cpd_start(1'b0),.dbg_ddrphy_rst_n(1'b1),.dbg_gpll_scan_rst(1'b0),.samp_position_dyn_adj(1'b0),.init_samp_position_even(32'b0),.init_samp_position_odd(32'b0),.wrcal_position_dyn_adj(1'b0),.init_wrcal_position(32'b0),.force_read_clk_ctrl(1'b0),.init_slip_step(16'b0),.init_read_clk_ctrl(12'b0),.debug_cpd_offset_adj(1'b0),.debug_cpd_offset_dir(1'b0),.debug_cpd_offset(10'b0),.ck_dly_en(1'b0),.init_ck_dly_step(8'b0));
endmodule
