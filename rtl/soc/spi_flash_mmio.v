`timescale 1ns/1ps

// Byte-oriented SPI mode-0 port for the FPGA configuration flash.  The
// external clock is emitted by GTP_CFGCLK; clk_enable_n connects to CE_N.
// Keep CS low across command/address/data bytes by writing CTRL.CS_N=0.
module spi_flash_mmio #(
    parameter [31:0] BASE=32'h1fe0_0200
)(
    input wire clk, input wire resetn,
    input wire [31:0] addr, input wire wr,
    input wire [31:0] wdata, input wire [3:0] wstrb,
    output reg [31:0] rdata, output wire hit,
    output reg spi_cs_n, output wire spi_dq0, input wire spi_dq1,
    output wire clk_enable_n
);
    assign hit=(addr>=BASE)&&(addr<BASE+32'h20);
    reg [7:0] tx_shift,rx_shift,rx_data;
    reg [3:0] bit_count;
    reg busy,rx_valid;
    assign spi_dq0=tx_shift[7];
    assign clk_enable_n=~busy;

    always @* begin
      case(addr[4:2])
        0:rdata=32'h5350_4931; // "SPI1"
        1:rdata={31'b0,spi_cs_n};
        2:rdata={30'b0,rx_valid,busy};
        3:rdata={24'b0,rx_data};
        default:rdata=0;
      endcase
    end

    always @(posedge clk) begin
      if(!resetn) begin spi_cs_n<=1;tx_shift<=8'hff;rx_shift<=0;rx_data<=0;bit_count<=0;busy<=0;rx_valid<=0; end
      else begin
        if(wr&&hit&&(addr[4:2]==1)&&wstrb[0]&&!busy) spi_cs_n<=wdata[0];
        if(wr&&hit&&(addr[4:2]==3)&&wstrb[0]&&!busy) begin
          tx_shift<=wdata[7:0];rx_shift<=0;bit_count<=0;busy<=1;rx_valid<=0;
        end else if(busy) begin
          rx_shift<={rx_shift[6:0],spi_dq1};
          tx_shift<={tx_shift[6:0],1'b1};
          if(bit_count==7) begin busy<=0;rx_data<={rx_shift[6:0],spi_dq1};rx_valid<=1; end
          else bit_count<=bit_count+1'b1;
        end
        if(!busy&&wr&&hit&&(addr[4:2]==2)&&wstrb[0]&&wdata[1])rx_valid<=0;
      end
    end
endmodule

