`timescale 1ns/1ps

// Minimal polled Ethernet MAC for a bootloader.  It deliberately implements
// complete-frame buffers instead of DMA: software writes one frame, starts TX,
// and pops one received frame. Hardware handles preamble, padding, FCS and IFG.
module eth_mac_mmio #(
    parameter [31:0] BASE=32'h1fe0_1000,
    parameter [47:0] MAC_ADDR=48'h02_50_47_32_00_01
)(
    input wire sys_clk,input wire sys_resetn,
    input wire [31:0] addr,input wire wr,input wire[31:0]wdata,input wire[3:0]wstrb,
    output reg[31:0]rdata,output wire hit,
    input wire mac_clk,input wire mac_resetn,
    input wire[7:0]mac_rx_data,input wire mac_rx_valid,input wire mac_rx_byte_valid,input wire mac_rx_error,
    output reg[7:0]mac_tx_data,output reg mac_tx_valid,input wire mac_tx_ready,
    output wire mac_rx_restart,
    output reg phy_reset_req,
    output reg eth_reset_req,
    output reg[7:0]tx_delay_step,output reg[7:0]rx_delay_step
);
    localparam BUF=2048;
    reg[31:0]rx_mem[0:(BUF/4)-1] /* synthesis syn_ramstyle="distributed_ram" */;
    reg[31:0]tx_mem[0:(BUF/4)-1] /* synthesis syn_ramstyle="distributed_ram" */;
    reg[10:0] rx_len_mac;
    reg rx_frame_toggle, tx_done_toggle;
    reg[1:0] rx_err_sync;
    assign hit=(addr>=BASE)&&(addr<BASE+32'h3000);
    wire rx_window=(addr>=BASE+32'h1000)&&(addr<BASE+32'h1800);
    wire tx_window=(addr>=BASE+32'h2000)&&(addr<BASE+32'h2800);

    reg[10:0]tx_len_sys; reg tx_req_toggle,rx_ack_toggle,rx_restart_toggle;
    reg[1:0]tx_done_sync,rx_toggle_sync; reg[10:0]rx_len_sync1,rx_len_sys;
    reg clear_err_toggle;
    wire rx_ready=(rx_toggle_sync[1]!=rx_ack_toggle);
    wire tx_busy=(tx_done_sync[1]!=tx_req_toggle);
    integer ti;wire[31:0]cpu_byte_mask={{8{wstrb[3]}},{8{wstrb[2]}},{8{wstrb[1]}},{8{wstrb[0]}}};
    always @(posedge sys_clk) begin
      if(!sys_resetn)begin tx_len_sys<=0;tx_req_toggle<=0;rx_ack_toggle<=0;rx_restart_toggle<=0;phy_reset_req<=0;eth_reset_req<=0;tx_done_sync<=0;rx_toggle_sync<=0;rx_len_sync1<=0;rx_len_sys<=0;clear_err_toggle<=0;tx_delay_step<=8'd100;rx_delay_step<=8'd247;end
      else begin
        phy_reset_req<=1'b0;
        eth_reset_req<=1'b0;
        tx_done_sync<={tx_done_sync[0],tx_done_toggle};
        rx_toggle_sync<={rx_toggle_sync[0],rx_frame_toggle};
        rx_len_sync1<=rx_len_mac;
        if(rx_toggle_sync[1]!=rx_ack_toggle)rx_len_sys<=rx_len_sync1;
        if(wr&&hit&&!tx_window&&!rx_window)case(addr[7:2])
          3:if(wstrb[0]|wstrb[1])tx_len_sys<=wdata[10:0];
          4:begin
              if(wdata[0]&&rx_ready)rx_ack_toggle<=rx_toggle_sync[1];
              if(wdata[1]&&!tx_busy&&tx_len_sys>=14&&tx_len_sys<=BUF)tx_req_toggle<=~tx_req_toggle;
              if(wdata[2])clear_err_toggle<=~clear_err_toggle;
              if(wdata[3])rx_restart_toggle<=~rx_restart_toggle;
              if(wdata[4])phy_reset_req<=1'b1;
              if(wdata[5])eth_reset_req<=1'b1;
            end
          7:begin
              if(wstrb[0])tx_delay_step<=wdata[7:0];
              if(wstrb[1])rx_delay_step<=wdata[15:8];
            end
        endcase
        if(wr&&tx_window)begin ti=(addr-(BASE+32'h2000))>>2;tx_mem[ti]<=(tx_mem[ti]&~cpu_byte_mask)|(wdata&cpu_byte_mask);end
      end
    end
    integer ri;
    always @* begin
      if(rx_window)begin ri=(addr-(BASE+32'h1000))>>2;rdata=rx_mem[ri];end
      else if(tx_window)begin ri=(addr-(BASE+32'h2000))>>2;rdata=tx_mem[ri];end
      else case(addr[7:2])
        0:rdata=32'h4554_4831; // ETH1
        1:rdata={28'b0,rx_err_sync[1],1'b0,tx_busy,rx_ready};
        2:rdata={21'b0,rx_len_sys};
        3:rdata={21'b0,tx_len_sys};
        5:rdata=MAC_ADDR[31:0];
        6:rdata={16'b0,MAC_ADDR[47:32]};
        7:rdata={16'b0,rx_delay_step,tx_delay_step};
        default:rdata=0;
      endcase
    end

    // Receive side: discard 7x55+D5 and retain the complete frame, including
    // its four FCS bytes.  The bootloader validates FCS in software.  This
    // keeps the active 25 MHz capture path shallow and avoids a data-pattern-
    // dependent decision on the parallel CRC result at the frame boundary.
    reg prev_dv,rx_receiving,rx_blocked; reg[3:0]rx_skip;reg[10:0]rx_count;
    reg rx_err_latch; reg[1:0]rx_ack_sync,clear_sync,rx_restart_sync;
    assign mac_rx_restart=rx_restart_sync[1]^rx_restart_sync[0];
    always @(posedge sys_clk) begin
      if(!sys_resetn)rx_err_sync<=0;else rx_err_sync<={rx_err_sync[0],rx_err_latch};
    end
    always @(posedge mac_clk) begin
      if(!mac_resetn)begin prev_dv<=0;rx_receiving<=0;rx_blocked<=0;rx_skip<=0;rx_count<=0;rx_len_mac<=0;rx_frame_toggle<=0;rx_err_latch<=0;rx_ack_sync<=0;clear_sync<=0;rx_restart_sync<=0;end
      else begin
        rx_ack_sync<={rx_ack_sync[0],rx_ack_toggle};clear_sync<={clear_sync[0],clear_err_toggle};rx_restart_sync<={rx_restart_sync[0],rx_restart_toggle};
        if(clear_sync[1]!=clear_sync[0])rx_err_latch<=0;
        if(mac_rx_restart)begin
          prev_dv<=0;rx_receiving<=0;rx_blocked<=0;rx_skip<=0;rx_count<=0;
        end else begin
          prev_dv<=mac_rx_valid;
          if(mac_rx_valid&&!prev_dv)begin rx_receiving<=1;rx_skip<=1;rx_count<=0;rx_blocked<=(rx_frame_toggle!=rx_ack_sync[1]);end
          if(mac_rx_valid&&rx_receiving&&mac_rx_byte_valid)begin
            if(mac_rx_error)rx_err_latch<=1;
            if(rx_skip<8)rx_skip<=rx_skip+1'b1;
            else if(!rx_blocked)begin if(rx_count<BUF)begin case(rx_count[1:0])0:rx_mem[rx_count>>2][7:0]<=mac_rx_data;1:rx_mem[rx_count>>2][15:8]<=mac_rx_data;2:rx_mem[rx_count>>2][23:16]<=mac_rx_data;3:rx_mem[rx_count>>2][31:24]<=mac_rx_data;endcase rx_count<=rx_count+1'b1;end else begin rx_blocked<=1;rx_err_latch<=1;end end
          end
          if(!mac_rx_valid&&prev_dv&&rx_receiving)begin
            rx_receiving<=0;
            if(!rx_blocked&&rx_count>=18)begin
              rx_len_mac<=rx_count;
              rx_frame_toggle<=~rx_frame_toggle;
            end else rx_err_latch<=1;
          end
        end
      end
    end

    localparam T_IDLE=0,T_PRE=1,T_DATA=2,T_FCS=3,T_IFG=4;
    reg[2:0]tx_state;reg[3:0]pre_count,ifg_count;reg[10:0]tx_pos,tx_len_mac;
    reg[31:0]tx_crc,tx_fcs;reg[1:0]fcs_pos;reg[1:0]tx_req_sync;
    wire[7:0]payload_byte=(tx_pos<tx_len_mac)?tx_mem[tx_pos>>2][tx_pos[1:0]*8+:8]:8'h00;
    wire[10:0]padded_len=(tx_len_mac<60)?60:tx_len_mac;
    // Unrolled reflected Ethernet CRC-32 update for one payload byte.  Each
    // stage is a fixed bit position, avoiding both a helper subroutine and a
    // variable-indexed procedural loop in the 25 MHz transmit datapath.
    wire[31:0]tx_crc_step1=(tx_crc[0]^payload_byte[0])?((tx_crc>>1)^32'hedb8_8320):(tx_crc>>1);
    wire[31:0]tx_crc_step2=(tx_crc_step1[0]^payload_byte[1])?((tx_crc_step1>>1)^32'hedb8_8320):(tx_crc_step1>>1);
    wire[31:0]tx_crc_step3=(tx_crc_step2[0]^payload_byte[2])?((tx_crc_step2>>1)^32'hedb8_8320):(tx_crc_step2>>1);
    wire[31:0]tx_crc_step4=(tx_crc_step3[0]^payload_byte[3])?((tx_crc_step3>>1)^32'hedb8_8320):(tx_crc_step3>>1);
    wire[31:0]tx_crc_step5=(tx_crc_step4[0]^payload_byte[4])?((tx_crc_step4>>1)^32'hedb8_8320):(tx_crc_step4>>1);
    wire[31:0]tx_crc_step6=(tx_crc_step5[0]^payload_byte[5])?((tx_crc_step5>>1)^32'hedb8_8320):(tx_crc_step5>>1);
    wire[31:0]tx_crc_step7=(tx_crc_step6[0]^payload_byte[6])?((tx_crc_step6>>1)^32'hedb8_8320):(tx_crc_step6>>1);
    wire[31:0]tx_crc_next =(tx_crc_step7[0]^payload_byte[7])?((tx_crc_step7>>1)^32'hedb8_8320):(tx_crc_step7>>1);
    always @(posedge mac_clk) begin
      if(!mac_resetn)begin tx_state<=T_IDLE;mac_tx_data<=0;mac_tx_valid<=0;pre_count<=0;ifg_count<=0;tx_pos<=0;tx_len_mac<=0;tx_crc<=32'hffff_ffff;tx_fcs<=0;fcs_pos<=0;tx_req_sync<=0;tx_done_toggle<=0;end
      else begin
        tx_req_sync<={tx_req_sync[0],tx_req_toggle};mac_tx_valid<=0;
        case(tx_state)
          T_IDLE:if(tx_req_sync[1]!=tx_done_toggle)begin tx_len_mac<=tx_len_sys;pre_count<=0;tx_state<=T_PRE;end
          T_PRE:begin mac_tx_valid<=1;mac_tx_data<=(pre_count==7)?8'hd5:8'h55;if(mac_tx_ready)begin if(pre_count==7)begin tx_pos<=0;tx_crc<=32'hffff_ffff;tx_state<=T_DATA;end else pre_count<=pre_count+1'b1;end end
          T_DATA:begin mac_tx_valid<=1;mac_tx_data<=payload_byte;if(mac_tx_ready)begin tx_crc<=tx_crc_next;if(tx_pos+1>=padded_len)begin tx_fcs<=~tx_crc_next;fcs_pos<=0;tx_state<=T_FCS;end else tx_pos<=tx_pos+1'b1;end end
          T_FCS:begin mac_tx_valid<=1;case(fcs_pos)0:mac_tx_data<=tx_fcs[7:0];1:mac_tx_data<=tx_fcs[15:8];2:mac_tx_data<=tx_fcs[23:16];3:mac_tx_data<=tx_fcs[31:24];endcase if(mac_tx_ready)begin if(fcs_pos==3)begin ifg_count<=0;tx_state<=T_IFG;end else fcs_pos<=fcs_pos+1'b1;end end
          T_IFG:if(ifg_count==11)begin tx_done_toggle<=tx_req_sync[1];tx_state<=T_IDLE;end else ifg_count<=ifg_count+1'b1;
          default:tx_state<=T_IDLE;
        endcase
      end
    end
endmodule
