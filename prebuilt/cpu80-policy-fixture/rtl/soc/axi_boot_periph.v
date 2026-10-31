`timescale 1ns/1ps

module axi_boot_periph #(
    parameter [31:0] BRAM_BASE=32'h1c00_0000,
    parameter integer BRAM_BYTES=128*1024,
    parameter [31:0] UART_BASE=32'h1fe0_01e0,
    parameter INIT_FILE="bootrom.hex", parameter integer UART_BAUD_DIV=234
)(
    input wire clk, input wire resetn,
    input wire [3:0] arid, input wire [31:0] araddr, input wire [7:0] arlen,
    input wire [2:0] arsize, input wire [1:0] arburst, input wire arvalid,
    output wire arready, output reg [3:0] rid, output reg [31:0] rdata,
    output reg [1:0] rresp, output reg rlast, output reg rvalid, input wire rready,
    input wire [3:0] awid, input wire [31:0] awaddr, input wire [7:0] awlen,
    input wire [2:0] awsize, input wire [1:0] awburst, input wire awvalid,
    output wire awready, input wire [3:0] wid, input wire [31:0] wdata,
    input wire [3:0] wstrb, input wire wlast, input wire wvalid, output wire wready,
    output reg [3:0] bid, output reg [1:0] bresp, output reg bvalid, input wire bready,
    input wire uart_rx, output wire uart_tx,
    input wire hid_key_valid, input wire [7:0] hid_key_data,
    output wire hid_key_ready,
    // Every accepted UART TX byte is also exported to the HDMI console
    // mirror.  This observes the bootloader, OpenSBI and Linux through the
    // same LiteUART data register without changing UART timing or software.
    output wire console_char_valid, output wire [7:0] console_char_data,
    output wire [31:0] mmio_addr, output wire mmio_wr,
    output wire [31:0] mmio_wdata, output wire [3:0] mmio_wstrb,
    input wire [31:0] mmio_rdata, input wire mmio_valid
);
    localparam WORDS=BRAM_BYTES/4; localparam OK=2'b00, DECERR=2'b11;
    reg [31:0] memory[0:WORDS-1] /* synthesis syn_ramstyle="block_ram" */;
    initial $readmemh(INIT_FILE,memory);

    wire [7:0] urx_data; wire urx_empty, urx_full, utx_full, utx_empty, utx_idle;
    reg [1:0] uart_event_enable;
    reg rd_active; reg [31:0] rd_addr; reg [7:0] rd_len,rd_beat; reg[2:0]rd_size; reg[1:0]rd_burst; reg rd_bad, rd_pop, rd_hid_pop;
    reg wr_active; reg[31:0]wr_addr; reg[7:0]wr_len,wr_beat;reg[2:0]wr_size;reg[1:0]wr_burst;reg[3:0]wr_id;reg wr_error;
    wire wr_is_bram=(wr_addr>=BRAM_BASE)&&(wr_addr<BRAM_BASE+BRAM_BYTES);
    wire wr_is_mmio=(wr_addr>=32'h1fe0_0200)&&(wr_addr<32'h1ff0_0000);
    wire[31:0]wr_next_addr=(wr_burst==2'b01)?
        wr_addr+(32'd1<<wr_size):wr_addr;
    wire wr_uart_data=((wr_addr&32'hffff_fffc)==UART_BASE);
    wire wr_uart_reg=((wr_addr&32'hffff_fffc)>=UART_BASE)&&((wr_addr&32'hffff_fffc)<=UART_BASE+20);
    wire wr_target=wr_is_bram||wr_uart_reg||(wr_is_mmio&&mmio_valid);
    wire wr_last_expected=(wr_beat==wr_len); wire wr_good=!wr_error&&wr_target&&(wid==wr_id)&&(wlast==wr_last_expected);
    wire rd_is_bram=(rd_addr>=BRAM_BASE)&&(rd_addr<BRAM_BASE+BRAM_BYTES);
    wire rd_is_mmio=(rd_addr>=32'h1fe0_0200)&&(rd_addr<32'h1ff0_0000);
    wire[31:0]rd_next_addr=(rd_burst==2'b01)?
        rd_addr+(32'd1<<rd_size):rd_addr;
    wire console_rx_empty=urx_empty&&!hid_key_valid;
    wire urx_pop=rvalid&&rready&&rd_pop&&!rd_hid_pop;
    assign hid_key_ready=rvalid&&rready&&rd_pop&&rd_hid_pop;
    // UART_BASE and UART_BASE+4 retain the original bootloader interface.
    // Bits [0] of +4 and +8 also implement the LiteUART TXFULL/RXEMPTY
    // registers used by upstream OpenSBI and Linux.  +0c/+10/+14 provide the
    // remaining harmless polling-mode LiteUART event registers.
    wire [31:0] uart_status={16'b0,1'b0,utx_idle,utx_empty,4'b0,!console_rx_empty,7'b0,utx_full};
    wire [1:0] uart_events={!console_rx_empty,!utx_full};
    // This slave has one shared external-MMIO data port.  Serialize its read
    // and write sides (write wins when AR and AW arrive together) so a read
    // can never observe rdata selected by an unrelated write address.
    assign arready=!rd_active&&!rvalid&&!wr_active&&!bvalid&&!awvalid;
    assign mmio_addr = wr_active ? wr_addr : rd_addr;
    assign mmio_wdata=wdata; assign mmio_wstrb=wstrb;
    assign mmio_wr=wr_active&&wvalid&&wready&&wr_is_mmio&&wr_good;

    always @(posedge clk) begin
      if(!resetn) begin rd_active<=0;rd_addr<=0;rd_len<=0;rd_beat<=0;rd_size<=0;rd_burst<=0;rd_bad<=0;rid<=0;rdata<=0;rresp<=OK;rlast<=0;rvalid<=0;rd_pop<=0;rd_hid_pop<=0; end
      else begin
        if(arvalid&&arready) begin rd_active<=1;rd_addr<=araddr;rd_len<=arlen;rd_beat<=0;rd_size<=arsize;rd_burst<=arburst;rd_bad<=(arlen>7)||(arsize>2)||((arburst!=0)&&(arburst!=1));rid<=arid; end
        if(rd_active&&!rvalid) begin
          rlast<=(rd_beat==rd_len); rd_pop<=0;rd_hid_pop<=0;
          if(!rd_bad&&rd_is_bram) begin rdata<=memory[(rd_addr-BRAM_BASE)>>2];rresp<=OK;end
          else if(!rd_bad&&((rd_addr&32'hffff_fffc)==UART_BASE)) begin rdata<={24'b0,urx_empty?hid_key_data:urx_data};rresp<=OK;rd_pop<=!console_rx_empty;rd_hid_pop<=urx_empty&&hid_key_valid;end
          else if(!rd_bad&&((rd_addr&32'hffff_fffc)==UART_BASE+4)) begin rdata<=uart_status;rresp<=OK;end
          else if(!rd_bad&&((rd_addr&32'hffff_fffc)==UART_BASE+8)) begin rdata<={31'b0,console_rx_empty};rresp<=OK;end
          else if(!rd_bad&&((rd_addr&32'hffff_fffc)==UART_BASE+12)) begin rdata<={30'b0,uart_events};rresp<=OK;end
          else if(!rd_bad&&((rd_addr&32'hffff_fffc)==UART_BASE+16)) begin rdata<={30'b0,uart_events};rresp<=OK;end
          else if(!rd_bad&&((rd_addr&32'hffff_fffc)==UART_BASE+20)) begin rdata<={30'b0,uart_event_enable};rresp<=OK;end
          else if(!rd_bad&&rd_is_mmio&&mmio_valid) begin rdata<=mmio_rdata;rresp<=OK;end
          else begin rdata<=0;rresp<=DECERR;end
          rvalid<=1;
        end else if(rvalid&&rready) begin rvalid<=0;rd_pop<=0;rd_hid_pop<=0;if(rlast)rd_active<=0;else begin rd_beat<=rd_beat+1;rd_addr<=rd_next_addr;end end
      end
    end

    wire uart_push=wr_active&&wvalid&&wready&&wr_uart_data&&wr_good&&(|wstrb);
    wire[7:0] uart_byte=wstrb[0]?wdata[7:0]:wstrb[1]?wdata[15:8]:wstrb[2]?wdata[23:16]:wdata[31:24];
    assign console_char_valid=uart_push;
    assign console_char_data=uart_byte;
    assign awready=!wr_active&&!bvalid&&!rd_active&&!rvalid;
    assign wready=wr_active&&(!wr_uart_data||!utx_full);
    uart_tx_fifo #(.BAUD_DIV(UART_BAUD_DIV),.FIFO_DEPTH(16),.PTR_W(4)) u_tx(.clk(clk),.resetn(resetn),.push(uart_push),.push_data(uart_byte),.full(utx_full),.empty(utx_empty),.idle(utx_idle),.tx(uart_tx));
    uart_rx_fifo #(.BAUD_DIV(UART_BAUD_DIV),.FIFO_DEPTH(16),.PTR_W(4)) u_rx(.clk(clk),.resetn(resetn),.rx(uart_rx),.pop(urx_pop),.data(urx_data),.full(urx_full),.empty(urx_empty));
    integer wi;
    always @(posedge clk) begin
      if(!resetn) begin wr_active<=0;wr_addr<=0;wr_len<=0;wr_beat<=0;wr_size<=0;wr_burst<=0;wr_id<=0;wr_error<=0;bid<=0;bresp<=OK;bvalid<=0;uart_event_enable<=0; end
      else begin
        if(awvalid&&awready)begin wr_active<=1;wr_addr<=awaddr;wr_len<=awlen;wr_beat<=0;wr_size<=awsize;wr_burst<=awburst;wr_id<=awid;wr_error<=(awlen>7)||(awsize>2)||((awburst!=0)&&(awburst!=1));end
        if(wr_active&&wvalid&&wready)begin
          if(wr_is_bram&&wr_good)begin wi=(wr_addr-BRAM_BASE)>>2;if(wstrb[0])memory[wi][7:0]<=wdata[7:0];if(wstrb[1])memory[wi][15:8]<=wdata[15:8];if(wstrb[2])memory[wi][23:16]<=wdata[23:16];if(wstrb[3])memory[wi][31:24]<=wdata[31:24];end
          if(wr_good&&((wr_addr&32'hffff_fffc)==UART_BASE+20)&&wstrb[0])uart_event_enable<=wdata[1:0];
          if(!wr_target||(wid!=wr_id)||(wlast!=wr_last_expected))wr_error<=1;
          if(wlast||wr_last_expected)begin wr_active<=0;bid<=wr_id;bresp<=(wr_error||!wr_target||(wid!=wr_id)||(wlast!=wr_last_expected))?DECERR:OK;bvalid<=1;end
          else begin wr_beat<=wr_beat+1;wr_addr<=wr_next_addr;end
        end
        if(bvalid&&bready)bvalid<=0;
      end
    end
endmodule
