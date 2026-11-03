`timescale 1ns/1ps
module tb_eth_tx_byte_diff;
reg cc=0,mc=0,cr=0,mr=0,wr=0;
always #10.101 cc=~cc;
always #20 mc=~mc;
reg[31:0] addr=0,wd=0;reg[3:0] ws=0;
reg[7:0] rxd=0;reg rxv=0,rxb=0,rxe=0,ready=0;
wire[31:0] rd0,rd1;wire h0,h1;wire[7:0] td0,td1,ts0,ts1,rs0,rs1;
wire tv0,tv1,re0,re1,pr0,pr1,er0,er1;
eth_mac_mmio_reference old(.sys_clk(cc),.sys_resetn(cr),.addr(addr),.wr(wr),.wdata(wd),.wstrb(ws),.rdata(rd0),.hit(h0),.mac_clk(mc),.mac_resetn(mr),.mac_rx_data(rxd),.mac_rx_valid(rxv),.mac_rx_byte_valid(rxb),.mac_rx_error(rxe),.mac_tx_data(td0),.mac_tx_valid(tv0),.mac_tx_ready(ready),.mac_rx_restart(re0),.phy_reset_req(pr0),.eth_reset_req(er0),.tx_delay_step(ts0),.rx_delay_step(rs0));
eth_mac_mmio dut(.sys_clk(cc),.sys_resetn(cr),.addr(addr),.wr(wr),.wdata(wd),.wstrb(ws),.rdata(rd1),.hit(h1),.mac_clk(mc),.mac_resetn(mr),.mac_rx_data(rxd),.mac_rx_valid(rxv),.mac_rx_byte_valid(rxb),.mac_rx_error(rxe),.mac_tx_data(td1),.mac_tx_valid(tv1),.mac_tx_ready(ready),.mac_rx_restart(re1),.phy_reset_req(pr1),.eth_reset_req(er1),.tx_delay_step(ts1),.rx_delay_step(rs1));
integer seed=1,i,j,k,cycles=0,checks=0;reg[31:0] val;reg active=0;
always @(posedge cc or posedge mc)begin
 #1;
 if(active)begin
  if({rd0,h0,td0,tv0,re0,pr0,er0,ts0,rs0}!=={rd1,h1,td1,tv1,re1,pr1,er1,ts1,rs1})$fatal(1,"public differential mismatch time=%t addr=%h ws=%h rd=%h/%h",$time,addr,ws,rd0,rd1);
  for(k=0;k<512;k=k+1)if(old.tx_mem[k]!==dut.tx_mem[k]||old.rx_mem[k]!==dut.rx_mem[k])$fatal(1,"memory differential mismatch word=%d",k);
  checks=checks+1;
 end
end
initial begin
 if(!$value$plusargs("SEED=%d",seed))seed=1;
 for(i=0;i<512;i=i+1)begin val=$random(seed);old.tx_mem[i]=val;dut.tx_mem[i]=val;val=$random(seed);old.rx_mem[i]=val;dut.rx_mem[i]=val;end
 repeat(5)@(negedge cc);cr=1;mr=1;active=1;
 for(j=0;j<16;j=j+1)for(i=0;i<512;i=i+1)begin @(negedge cc);addr=32'h1fe03000+i*4;wd=$random(seed);ws=j;wr=1;end
 @(negedge cc);wr=0;
 for(i=0;i<6000;i=i+1)begin
  @(negedge cc);val=$random(seed);wd=$random(seed);ws=val[3:0];wr=val[4];
  case(i%8)
   0,1,2:addr=32'h1fe03000+{val[8:0],2'b00};
   3:addr=32'h1fe02000+{val[8:0],2'b00};
   4:addr=32'h1fe0100c;
   5:begin addr=32'h1fe01010;wd=val&32'h3f;end
   6:addr=32'h1fe0101c;
   7:addr=32'h1fe01004;
  endcase
  cr=(i%997>4);mr=(i%733>3);ready=val[5];rxd=val[15:8];rxv=(i%83<72);rxb=val[6];rxe=(i%137==0);
 end
 @(negedge cc);wr=0;cr=1;mr=1;ready=1;rxv=0;rxb=0;rxe=0;
 repeat(3000)@(negedge cc);
 $display("ETH_TX_BYTE_WRITE_FULL_INTERFACE_AND_MEMORY_DIFF_PASS checks=%0d all16masks/all512words random_cycles=6000",checks);$finish;
end
initial begin #2000000;$fatal(1,"timeout");end
endmodule
