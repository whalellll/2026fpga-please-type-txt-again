`timescale 1ns/1ps
// HDMI-only annotation. The input pixels/DDR framebuffer are never modified.
// Stable bundled CPU text is copied at VSYNC and acknowledged afterwards.
// Exactly two pixel clocks latency, matching the existing HID overlay path.
module camera_sd_hud(
 input wire clk,resetn,
 input wire [255:0] text_cpu,input wire [2:0] style_cpu,
 input wire toggle_cpu,output reg ack_pix,
 input wire vs_in,hs_in,de_in,input wire [7:0] r_in,g_in,b_in,
 output reg vs_out,hs_out,de_out,output reg [7:0] r_out,g_out,b_out
);
 reg toggle_s1,toggle_s2,toggle_s3,vs_d,de_d;
 reg [255:0] text_active;
 reg [2:0] style_active;
 reg [10:0] x;reg [9:0] y;
 reg [7:0] character;
 // Constant-indexed selection keeps PDS's control synthesis predictable.
 always @* begin
  case(x[7:3])
   0:character=text_active[7:0];1:character=text_active[15:8];
   2:character=text_active[23:16];3:character=text_active[31:24];
   4:character=text_active[39:32];5:character=text_active[47:40];
   6:character=text_active[55:48];7:character=text_active[63:56];
   8:character=text_active[71:64];9:character=text_active[79:72];
   10:character=text_active[87:80];11:character=text_active[95:88];
   12:character=text_active[103:96];13:character=text_active[111:104];
   14:character=text_active[119:112];15:character=text_active[127:120];
   16:character=text_active[135:128];17:character=text_active[143:136];
   18:character=text_active[151:144];19:character=text_active[159:152];
   20:character=text_active[167:160];21:character=text_active[175:168];
   22:character=text_active[183:176];23:character=text_active[191:184];
   24:character=text_active[199:192];25:character=text_active[207:200];
   26:character=text_active[215:208];27:character=text_active[223:216];
   28:character=text_active[231:224];29:character=text_active[239:232];
   30:character=text_active[247:240];31:character=text_active[255:248];
   default:character=8'h20;
  endcase
 end
 wire [7:0] glyph;
 font_rom u_font(.clk(clk),.addr({character[6:0],y[3:0]}),.bits(glyph));
 reg s1_vs,s1_hs,s1_de,s1_area;reg [7:0] s1_r,s1_g,s1_b;
 reg [2:0] s1_column,s1_style;
 wire ink=glyph[3'd7-s1_column];
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin
   toggle_s1<=0;toggle_s2<=0;toggle_s3<=0;ack_pix<=0;
   text_active<={32{8'h20}};style_active<=0;vs_d<=0;de_d<=0;x<=0;y<=0;
   s1_vs<=0;s1_hs<=0;s1_de<=0;s1_area<=0;s1_r<=0;s1_g<=0;s1_b<=0;s1_column<=0;s1_style<=0;
   vs_out<=0;hs_out<=0;de_out<=0;r_out<=0;g_out<=0;b_out<=0;
  end else begin
   toggle_s1<=toggle_cpu;toggle_s2<=toggle_s1;toggle_s3<=toggle_s2;
   vs_d<=vs_in;de_d<=de_in;
   if(vs_in&&!vs_d)begin
    y<=0;
    if(toggle_s3!=ack_pix)begin
     text_active<=text_cpu;style_active<=style_cpu;ack_pix<=toggle_s3;
    end
   end else if(de_d&&!de_in)y<=y+1'b1;
   if(de_in)x<=x+1'b1;else x<=0;
   s1_vs<=vs_in;s1_hs<=hs_in;s1_de<=de_in;
   s1_r<=r_in;s1_g<=g_in;s1_b<=b_in;
   s1_area<=de_in&&style_active[0]&&(x<11'd256)&&(y<10'd16);
   s1_column<=x[2:0];s1_style<=style_active;
   vs_out<=s1_vs;hs_out<=s1_hs;de_out<=s1_de;
   if(s1_area)begin
    // style2:1: 0/yellow saving, 1/green success, 2/red failure.
    r_out<=ink?(s1_style[2:1]==1?8'd0:8'd255):8'd0;
    g_out<=ink?(s1_style[2:1]==2?8'd0:8'd255):8'd0;
    b_out<=0;
   end else begin r_out<=s1_r;g_out<=s1_g;b_out<=s1_b;end
  end
 end
endmodule
