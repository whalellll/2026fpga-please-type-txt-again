`timescale 1ns/1ps

module tb_axi_boot_periph;
    reg clk=0,resetn=0;always #5 clk=~clk;
    reg[3:0]arid=1;reg[31:0]araddr=0;reg[7:0]arlen=0;reg[2:0]arsize=2;reg[1:0]arburst=1;reg arvalid=0;
    wire arready;wire[3:0]rid;wire[31:0]rdata;wire[1:0]rresp;wire rlast,rvalid;reg rready=0;
    reg[3:0]awid=2;reg[31:0]awaddr=0;reg[7:0]awlen=0;reg[2:0]awsize=2;reg[1:0]awburst=1;reg awvalid=0;
    wire awready;reg[3:0]wid=2;reg[31:0]wdata=32'ha5a55a5a;reg[3:0]wstrb=4'hf;reg wlast=1,wvalid=0;wire wready;
    wire[3:0]bid;wire[1:0]bresp;wire bvalid;reg bready=0;
    wire uart_tx;wire[31:0]mmio_addr;wire mmio_wr;wire[31:0]mmio_wdata;wire[3:0]mmio_wstrb;
    reg[31:0]mmio_rdata=32'hdeadbeef;reg mmio_valid=1;
    reg hid_key_valid=0;reg[7:0]hid_key_data=0;wire hid_key_ready;

    axi_boot_periph #(.INIT_FILE("pds/bootrom.hex")) dut(
      .clk(clk),.resetn(resetn),.arid(arid),.araddr(araddr),.arlen(arlen),.arsize(arsize),.arburst(arburst),.arvalid(arvalid),.arready(arready),.rid(rid),.rdata(rdata),.rresp(rresp),.rlast(rlast),.rvalid(rvalid),.rready(rready),
      .awid(awid),.awaddr(awaddr),.awlen(awlen),.awsize(awsize),.awburst(awburst),.awvalid(awvalid),.awready(awready),.wid(wid),.wdata(wdata),.wstrb(wstrb),.wlast(wlast),.wvalid(wvalid),.wready(wready),.bid(bid),.bresp(bresp),.bvalid(bvalid),.bready(bready),
      .uart_rx(1'b1),.uart_tx(uart_tx),.hid_key_valid(hid_key_valid),.hid_key_data(hid_key_data),.hid_key_ready(hid_key_ready),.mmio_addr(mmio_addr),.mmio_wr(mmio_wr),.mmio_wdata(mmio_wdata),.mmio_wstrb(mmio_wstrb),.mmio_rdata(mmio_rdata),.mmio_valid(mmio_valid));

    task fail;input[255:0]why;begin $fatal(1,"FAIL tb_axi_boot_periph: %0s",why);end endtask
    initial begin
      repeat(3)@(posedge clk);resetn=1;
      @(negedge clk);awaddr=32'h1c00_0040;araddr=32'h1fe0_0300;awvalid=1;arvalid=1;
      #1;if(!awready||arready)fail("simultaneous AR/AW priority");
      @(posedge clk);#1;if(arready)fail("read admitted during active write");
      @(negedge clk);awvalid=0;wvalid=1;
      #1;if(!wready)fail("write data not ready");
      @(posedge clk);#1;
      @(negedge clk);wvalid=0;
      #1;if(!bvalid||bresp!=0)fail("write response");
      bready=1;@(posedge clk);#1;bready=0;
      @(negedge clk);#1;if(!arready)fail("pending read not released after write");
      @(posedge clk);#1;
      @(negedge clk);arvalid=0;
      @(posedge clk);#1;if(!rvalid||rresp!=0||rdata!=32'hdeadbeef)fail("MMIO read response");
      rready=1;@(posedge clk);#1;rready=0;

      // Exercise both branches of the explicit next-address logic.  An INCR
      // burst must visit two adjacent BRAM words.
      @(negedge clk);awaddr=32'h1c00_0080;awlen=1;awburst=1;awvalid=1;
      @(posedge clk);#1;
      @(negedge clk);awvalid=0;wdata=32'h1122_3344;wlast=0;wvalid=1;
      @(posedge clk);#1;
      @(negedge clk);wdata=32'h5566_7788;wlast=1;
      @(posedge clk);#1;
      @(negedge clk);wvalid=0;
      #1;if(!bvalid||bresp!=0)fail("INCR burst write response");
      bready=1;@(posedge clk);#1;bready=0;awlen=0;

      @(negedge clk);araddr=32'h1c00_0080;arlen=1;arburst=1;arvalid=1;
      @(posedge clk);#1;@(negedge clk);arvalid=0;
      @(posedge clk);#1;
      if(!rvalid||rresp!=0||rlast||rdata!=32'h1122_3344)
        fail("INCR burst first read beat");
      rready=1;@(posedge clk);#1;rready=0;
      @(posedge clk);#1;
      if(!rvalid||rresp!=0||!rlast||rdata!=32'h5566_7788)
        fail("INCR burst second read beat");
      rready=1;@(posedge clk);#1;rready=0;

      // A FIXED burst must retain its first address for the second beat.
      @(negedge clk);araddr=32'h1c00_0080;arburst=0;arvalid=1;
      @(posedge clk);#1;@(negedge clk);arvalid=0;
      @(posedge clk);#1;
      if(!rvalid||rresp!=0||rlast||rdata!=32'h1122_3344)
        fail("FIXED burst first read beat");
      rready=1;@(posedge clk);#1;rready=0;
      @(posedge clk);#1;
      if(!rvalid||rresp!=0||!rlast||rdata!=32'h1122_3344)
        fail("FIXED burst second read beat");
      rready=1;@(posedge clk);#1;rready=0;arlen=0;arburst=1;

      // OpenSBI/Linux LiteUART-compatible aliases: TXFULL at +4 and RXEMPTY
      // at +8.  The idle transmitter is not full and the RX FIFO is empty.
      @(negedge clk);araddr=32'h1fe0_01e4;arvalid=1;
      @(posedge clk);#1;@(negedge clk);arvalid=0;
      @(posedge clk);#1;if(!rvalid||rresp!=0||rdata[0]!=0)fail("LiteUART TXFULL");
      rready=1;@(posedge clk);#1;rready=0;
      @(negedge clk);araddr=32'h1fe0_01e8;arvalid=1;
      @(posedge clk);#1;@(negedge clk);arvalid=0;
      @(posedge clk);#1;if(!rvalid||rresp!=0||rdata[0]!=1)fail("LiteUART RXEMPTY");
      rready=1;@(posedge clk);#1;rready=0;

      // The complete SoC places the accelerator above the original 16 KiB
      // external-MMIO range.
      @(negedge clk);araddr=32'h1fe1_0000;arvalid=1;
      @(posedge clk);#1;@(negedge clk);arvalid=0;
      @(posedge clk);#1;if(!rvalid||rresp!=0||rdata!=32'hdeadbeef)
        fail("MAC MMIO window");
      rready=1;@(posedge clk);#1;

      // A translated CH9350 key is exposed through the same LiteUART RX
      // register, remains stable under backpressure and is acknowledged only
      // when the AXI read completes.
      rready=0;hid_key_data=8'h4b;hid_key_valid=1;
      @(negedge clk);araddr=32'h1fe0_01e8;arvalid=1;
      @(posedge clk);#1;@(negedge clk);arvalid=0;
      @(posedge clk);#1;if(!rvalid||rdata[0]!=0)fail("HID RXEMPTY alias");
      rready=1;@(posedge clk);#1;rready=0;
      @(negedge clk);araddr=32'h1fe0_01e0;arvalid=1;
      @(posedge clk);#1;@(negedge clk);arvalid=0;
      @(posedge clk);#1;if(!rvalid||rdata[7:0]!=8'h4b||hid_key_ready)fail("HID RBR capture");
      repeat(4)@(posedge clk);#1;if(rdata[7:0]!=8'h4b||hid_key_ready)fail("HID RBR backpressure");
      rready=1;#1;if(!hid_key_ready)fail("HID RBR handshake");
      @(posedge clk);#1;hid_key_valid=0;
      $display("PASS tb_axi_boot_periph");$finish;
    end
endmodule
