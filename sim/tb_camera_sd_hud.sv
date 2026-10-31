`timescale 1ns/1ps
module tb_camera_sd_hud;
 reg cpu_clk=0,pix_clk=0,resetn=0;
 always #7 cpu_clk=~cpu_clk;always #5 pix_clk=~pix_clk;
 reg [31:0] addr=0,wdata=0;reg wr=0;wire [31:0] rdata;wire hit;
 wire [255:0] text_cpu;wire [2:0] style_cpu;wire toggle_cpu,ack;
 camera_mmio regs(.clk(cpu_clk),.resetn(resetn),.addr(addr),.wr(wr),.wdata(wdata),.wstrb(4'hf),
  .rdata(rdata),.hit(hit),.hud_text(text_cpu),.hud_style(style_cpu),.hud_toggle(toggle_cpu),.hud_ack(ack),
  .cmos1_init_done(1'b0),.cmos2_init_done(1'b0),.frame_valid(1'b0),.writer_busy(1'b0),
  .idle(1'b1),.stopping(1'b0),.snapshot_ready(1'b0),.snapshot_buffer(1'b0),.snapshot_frame_count(32'b0),
  .completed_buffer(1'b0),.sccb_nack(1'b0),.frame_error(1'b0),.ddr_error(1'b0),
  .frame_count(32'b0),.dropped_count(32'b0),.bad_line_count(32'b0));
 reg vs=0,hs=0,de=0;reg [7:0] r=0,g=0,b=0;
 wire ov,oh,od;wire [7:0] rr,gg,bb;
 camera_sd_hud hud(.clk(pix_clk),.resetn(resetn),.text_cpu(text_cpu),.style_cpu(style_cpu),
  .toggle_cpu(toggle_cpu),.ack_pix(ack),.vs_in(vs),.hs_in(hs),.de_in(de),
  .r_in(r),.g_in(g),.b_in(b),.vs_out(ov),.hs_out(oh),.de_out(od),.r_out(rr),.g_out(gg),.b_out(bb));
 task write_reg(input [31:0] a,input [31:0] d);
 begin @(negedge cpu_clk);addr=a;wdata=d;wr=1;@(negedge cpu_clk);wr=0;end endtask
 integer x,y,i,ink_count;reg [2:0] style=0;
 task pixel(input integer px,input integer py);
 reg [7:0] er,eg,eb;reg expected_ink;
 begin
  @(negedge pix_clk);de=1;hs=0;vs=0;r=px[7:0];g=py[7:0];b=8'h5a;
  er=r;eg=g;eb=b;
  if(style[0]&&px<256&&py<16)begin
   expected_ink=px<8&&(px==0||px==7);
   er=expected_ink?(style[2:1]==1?0:255):0;
   eg=expected_ink?(style[2:1]==2?0:255):0;eb=0;
   if(expected_ink)ink_count=ink_count+1;
  end
  @(posedge pix_clk);@(posedge pix_clk);#1;
  if(!od||oh||ov||rr!==er||gg!==eg||bb!==eb)$fatal(1,"HUD pixel/timing mismatch at %0d,%0d got %h%h%h expected %h%h%h",px,py,rr,gg,bb,er,eg,eb);
 end endtask
 // Drive full-rate scanlines. Expected source coordinates are independent of
 // the DUT counters and checked against its two-cycle output pipeline.
 reg [26:0] expect1=0,expect2=0;integer sx=0,sy=0;reg de_prev=0,vs_prev=0;reg checking=0;
 reg [7:0] er,eg,eb;reg ink;
 always @(posedge pix_clk)begin
  expect2=expect1;er=r;eg=g;eb=b;
  if(checking&&de&&style[0]&&sx<256&&sy<16)begin
   ink=sx<8&&(sx==0||sx==7);
   er=ink?(style[2:1]==1?0:255):0;eg=ink?(style[2:1]==2?0:255):0;eb=0;
   if(ink)ink_count=ink_count+1;
  end
  expect1={vs,hs,de,er,eg,eb};
  if(vs&&!vs_prev)sy=0;else if(de_prev&&!de)sy=sy+1;
  if(de)sx=sx+1;else sx=0;
  de_prev=de;vs_prev=vs;
  #1;if(checking&&{ov,oh,od,rr,gg,bb}!==expect2)$fatal(1,"HUD scanline pipeline mismatch x=%0d y=%0d got=%h expected=%h style=%d active=%d text=%h xy=%d,%d",sx,sy,{ov,oh,od,rr,gg,bb},expect2,style,hud.style_active,hud.text_active[31:0],hud.x,hud.y);
 end
 task frame;
 begin
  repeat(6)@(negedge pix_clk); // allow request synchronizer before next VSYNC
  @(negedge pix_clk);vs=1;de=0;repeat(12)@(negedge pix_clk);vs=0;
  repeat(4)@(negedge pix_clk);
  for(y=0;y<20;y=y+1)begin
   for(x=0;x<320;x=x+1)begin de=1;r=x[7:0];g=y[7:0];b=8'h5a;@(negedge pix_clk);end
   de=0;hs=1;repeat(8)@(negedge pix_clk);hs=0;repeat(8)@(negedge pix_clk);
  end
 end endtask
 initial begin
  // Use a deterministic glyph independent of workstation fonts.
  #1;for(i=0;i<2048;i=i+1)hud.u_font.rom[i]=0;
  for(i=0;i<16;i=i+1)hud.u_font.rom[65*16+i]=8'h81;
  repeat(5)@(negedge cpu_clk);resetn=1;ink_count=0;
  write_reg(32'h1fe12030,32'h20202041);
  write_reg(32'h1fe12020,1);addr=32'h1fe12020;#1;
  if(!rdata[31])$fatal(1,"HUD missing pending handshake");
  write_reg(32'h1fe12030,32'h42424242);
  if(text_cpu[31:0]!=32'h20202041)$fatal(1,"pending payload overwritten");
  style=1;checking=1;frame();
  if(ack!=toggle_cpu||ink_count!=32)$fatal(1,"yellow/VSYNC commit failed");
  write_reg(32'h1fe12020,3);style=3;ink_count=0;frame();if(ink_count!=32)$fatal(1,"green failed");
  write_reg(32'h1fe12020,5);style=5;ink_count=0;frame();if(ink_count!=32)$fatal(1,"red failed");
  write_reg(32'h1fe12020,0);style=0;ink_count=0;frame();if(ink_count)$fatal(1,"HUD disable failed");
  $display("CAMERA_SD_HUD_CDC_COLOR_TIMING_SOURCE_ISOLATION_PASS");$finish;
 end
 initial begin #2000000;$fatal(1,"HUD timeout");end
endmodule
