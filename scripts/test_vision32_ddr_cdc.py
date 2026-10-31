"""Run the integer oracle through the production AXI32/DDR256 CDC bridge."""
from pathlib import Path
import argparse, hashlib, json, subprocess
from test_vision32 import ROOT, cases, fixture, linux

PREFIX = r'''`timescale 1ns/1ps
module tb_vision32_layer;
 parameter CASES=1, SOC=1;
 reg clk=0; always #5 clk=~clk;
 reg ddr_clk=0; always #3.5 ddr_clk=~ddr_clk;
 reg resetn=0,wr=0;
 reg [7:0] wa=0,ra=0; reg [31:0] wd=0; reg [3:0] ws=15;
 wire [31:0] rd;
 reg [31:0] memory[0:262143],cfg[0:15],ctl[0:5];
 reg [7:0] gold[0:131071];
 reg [31:0] rnd=32'h97531;
 integer case_id=0,clock_count=0,read_beats=0,write_beats=0,writes_seen=0;
 integer fault=0,write_started_at=0;
 wire [31:0] araddr,awaddr,wdata,rdata;
 wire [7:0] arlen,awlen;
 wire [2:0] arsize,awsize;
 wire [1:0] arburst,awburst,bresp,rresp;
 wire [3:0] wstrb,rid,bid;
 wire arvalid,arready,awvalid,awready,wvalid,wready,wlast,bvalid,bready,rvalid,rready,rlast;
 wire [27:0] na, nwa;
 wire [3:0] nid,nwid,nlen,nwlen;
 wire nav,nar,nwav,nwar,nwr;
 wire [255:0] nwd;
 wire [31:0] nws;
 reg [255:0] nrd=0; reg nrv=0;
 reg rp=0,wp=0; integer ri=0,wi=0,delay_read=0,nb;
 wire is_write=wp||awvalid||bvalid;
 wire active=rp||wp||arvalid||awvalid||rvalid||bvalid;
 wire rv=rvalid||bvalid;
 assign nar=!rp && rnd[2]; assign nwar=!wp && rnd[3];
 assign nwr=wp && rnd[4];
 always @(posedge clk)begin
  rnd<={rnd[30:0],rnd[31]^rnd[21]^rnd[1]^rnd[0]};
  if(resetn)begin
   if(rvalid && rready)read_beats<=read_beats+1;
   if(wvalid && wready)write_beats<=write_beats+1;
  end
 end
 // Native DDR has no read backpressure: one accepted address returns one256-bit beat.
 always @(posedge ddr_clk)begin
  nrv<=0;
  if(!resetn)begin rp<=0;wp<=0;end
  else begin
   if(nav && nar)begin
    if(nlen!=0)$fatal(1,"NATIVE_READ_LEN");
    ri=({2'b0,na[27:3],5'b0}-32'h1b000000)>>2;
    if(ri<0 || ri+7>=262144)$fatal(1,"NATIVE_READ_RANGE");
    rp<=1;delay_read<=2+rnd[7:5];
   end
   if(rp)begin
    if(delay_read==0)begin
     for(nb=0;nb<8;nb=nb+1)nrd[nb*32+:32]<=memory[ri+nb];
     nrv<=1;rp<=0;
    end else delay_read<=delay_read-1;
   end
   if(nwav && nwar)begin
    if(nwlen!=0)$fatal(1,"NATIVE_WRITE_LEN");
    wi=({2'b0,nwa[27:3],5'b0}-32'h1b000000)>>2;
    if(wi<0 || wi+7>=262144)$fatal(1,"NATIVE_WRITE_RANGE");
    wp<=1;
   end
   if(nwr)begin
    for(nb=0;nb<32;nb=nb+1)if(nws[nb])begin
     if((wi*4+nb)<cfg[2]-32'h1b000000 || (wi*4+nb)>=cfg[2]-32'h1b000000+ctl[0])
      $fatal(1,"NATIVE_WRITE_OUTSIDE_OUTPUT");
     memory[wi+nb/4][(nb%4)*8+:8]<=nwd[nb*8+:8];
    end
    wp<=0;
   end
  end
 end
 mac_accel_ddr_kernel_top #(.DDR_BASE(32'h1b000000),.DDR_BYTES(1048576),
  .ENABLE_H128_SPARSE(0),.ENABLE_PFF1_GATHER(1),.ENABLE_NNUE_PIPELINE(1),
  .PIKAFISH_ONLY(1),.ENABLE_CONV(1),.ENABLE_VISION32(1)) dut(
  .clk(clk),.resetn(resetn),.reg_wr_en(wr),.reg_wr_addr({1'b0,wa}),
  .reg_wr_data(wd),.reg_wr_strb(ws),.reg_rd_addr({1'b0,ra}),.reg_rd_data(rd),.irq(),
  .m_axi_awaddr(awaddr),.m_axi_awlen(awlen),.m_axi_awsize(awsize),.m_axi_awburst(awburst),
  .m_axi_awvalid(awvalid),.m_axi_awready(awready),
  .m_axi_wdata(wdata),.m_axi_wstrb(wstrb),.m_axi_wlast(wlast),.m_axi_wvalid(wvalid),.m_axi_wready(wready),
  .m_axi_bresp(bresp),.m_axi_bvalid(bvalid),.m_axi_bready(bready),
  .m_axi_araddr(araddr),.m_axi_arlen(arlen),.m_axi_arsize(arsize),.m_axi_arburst(arburst),
  .m_axi_arvalid(arvalid),.m_axi_arready(arready),
  .m_axi_rdata(rdata),.m_axi_rresp(rresp),.m_axi_rlast(rlast),.m_axi_rvalid(rvalid),.m_axi_rready(rready));
 axi_ddr_cdc bridge(
  .sys_clk(clk),.sys_resetn(resetn),.ddr_clk(ddr_clk),.ddr_resetn(resetn),.ddr_init_done(resetn),
  .s_arid(4'd1),.s_araddr(araddr),.s_arlen(arlen),.s_arsize(arsize),.s_arburst(arburst),.s_arvalid(arvalid),.s_arready(arready),
  .s_rid(rid),.s_rdata(rdata),.s_rresp(rresp),.s_rlast(rlast),.s_rvalid(rvalid),.s_rready(rready),
  .s_awid(4'd1),.s_awaddr(awaddr),.s_awlen(awlen),.s_awsize(awsize),.s_awburst(awburst),.s_awvalid(awvalid),.s_awready(awready),
  .s_wid(4'd1),.s_wdata(wdata),.s_wstrb(wstrb),.s_wlast(wlast),.s_wvalid(wvalid),.s_wready(wready),
  .s_bid(bid),.s_bresp(bresp),.s_bvalid(bvalid),.s_bready(bready),
  .m_awaddr(nwa),.m_awuser_ap(),.m_awuser_id(nwid),.m_awlen(nwlen),.m_awvalid(nwav),.m_awready(nwar),
  .m_wdata(nwd),.m_wstrb(nws),.m_wready(nwr),.m_wusero_id(4'd1),.m_wusero_last(1'b1),
  .m_araddr(na),.m_aruser_ap(),.m_aruser_id(nid),.m_arlen(nlen),.m_arvalid(nav),.m_arready(nar),
  .m_rdata(nrd),.m_rid(4'd1),.m_rlast(1'b1),.m_rvalid(nrv));
'''

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',required=True,type=Path)
    ap.add_argument('--rtl',type=Path,help='Isolated old RTL for a preserved negative reproduction')
    ap.add_argument('--quick',action='store_true')
    a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    jobs=[j for j in cases() if not j.get('fault')]
    if a.quick:jobs=jobs[:4]+jobs[-3:]
    manifest=[fixture(j,i,out) for i,j in enumerate(jobs)]
    tb=ROOT/'sim/tb_vision32_layer.sv';source=tb.read_text()
    # Reuse the identical oracle/canary/counter checks, replacing only the memory fabric.
    assert source.count(' task write_reg(')==1
    suffix=source[source.index(' task write_reg('):source.index('// Exercise the actual MAC')]
    generated=out/'tb_ddr.sv';generated.write_text(PREFIX+suffix)
    sources=sorted((ROOT/'rtl/mac_accel').glob('*.v'))+[ROOT/'rtl/soc/axi_ddr_cdc.v',ROOT/'sim/gtp_apm_e2_perf_sim.v']
    if a.rtl:sources=[a.rtl.resolve() if p.name=='vision32_layer.v' else p for p in sources]
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources+[tb]}
    cmd=f"set -eu; cd '{linux(out)}'; iverilog -g2012 -s tb_vision32_layer -Ptb_vision32_layer.CASES={len(jobs)} -o ddr.vvp "+' '.join("'"+linux(p)+"'" for p in sources+[generated])+"; vvp ddr.vvp"
    with (out/'simulation.log').open('wb') as log:
        r=subprocess.run(['wsl','-d','pikafish-verify','--','sh','-c',cmd],stdout=log,stderr=subprocess.STDOUT,timeout=1800)
    log=(out/'simulation.log').read_bytes()
    result=dict(status='VISION32_PRODUCTION_DDR_CDC_INTEGER_ORACLE_PASS_NOT_BOARD' if r.returncode==0 and b'VISION32_ALL_PASS' in log else 'FAILED_PRESERVED',
                cases=len(jobs),source_sha256=before,generated_tb_sha256=hashlib.sha256(generated.read_bytes()).hexdigest(),
                log_sha256=hashlib.sha256(log).hexdigest(),vectors=manifest)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    assert before=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources+[tb]}
    assert result['status']!='FAILED_PRESERVED',log.decode(errors='replace')[-2500:]
    print(result['status'],len(jobs),flush=True)

if __name__=='__main__':main()
