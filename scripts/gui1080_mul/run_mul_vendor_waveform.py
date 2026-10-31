"""Replay the actual four mapped APM configurations with the vendor state model."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,re,subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from inspect_mul_signed_mapping import apms
w=Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();assert not a.output.exists();a.output.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
vm=a.root/'pds/synthesize/soc_top_syn.vm';digest=sha(vm);source=vm.read_text();body=re.search(r'(?ms)^module Mul\s.*?^endmodule',source)[0];cells=apms(body,True)
instances=[]
for c in cells:
    params=',\n'.join('.'+k+'('+v+')'for k,v in c['parameters'].items())
    ports=dict(c['ports']);ports['P']='p'+c['part']
    instances.append('GTP_APM_E2 #(\n'+params+'\n) apm'+c['part']+' (\n'+',\n'.join('.'+k+'('+v+')'for k,v in ports.items())+'\n);')
tb='''`timescale 1ns/1ps
module tb_native_mul_apms;
  reg clock=0; always #5 clock=~clock;
  reg grs_n=1; GTP_GRS GRS_INST(.GRS_N(grs_n));
  reg [31:0] io_a=0,io_b=0;
  reg io_valid=0, signed_a=0,signed_b=0;
  wire [0:0] N12,N9;
  assign N12[0]=signed_a & io_a[31];
  assign N9[0]=signed_b & io_b[31];
  wire [47:0] p00,p01,p10,p11;
'''+'\n'.join(instances)+'''
  wire [63:0] result={32'b0,p00[31:0]}+
    {{15{p01[32]}},p01[32:0],16'b0}+
    {{15{p10[32]}},p10[32:0],16'b0}+{p11[31:0],32'b0};
  reg [63:0] expected=0;
  reg signed [32:0] aa,bb;
  reg signed [65:0] whole;
  integer count=0,captures=0,held=0;
  task cycle(input [31:0] a,b,input sa,sb,en);
    begin
      @(negedge clock);io_a=a;io_b=b;signed_a=sa;signed_b=sb;io_valid=en;
      #1;
      if(result!==expected)$fatal(1,"APM held data mismatch before edge cycle=%0d",count);
      @(posedge clock);
      if(en)begin
        aa=sa?{a[31],a}:{1'b0,a};bb=sb?{b[31],b}:{1'b0,b};
        whole=aa*bb;expected=whole[63:0];captures=captures+1;
      end else held=held+1;
      #1;
      if(result!==expected)$fatal(1,"APM data mismatch cycle=%0d a=%h b=%h flags=%b%b actual=%h expected=%h",count,a,b,sa,sb,result,expected);
      count=count+1;
    end
  endtask
  reg [31:0] edges[0:17];integer i,j,f,seed,unused;
  initial begin
    edges[0]=32'h0;edges[1]=32'h1;edges[2]=32'h7fff;edges[3]=32'h8000;
    edges[4]=32'hffff;edges[5]=32'h10000;edges[6]=32'h10001;edges[7]=32'h7fff0000;
    edges[8]=32'h7fff7fff;edges[9]=32'h7fffffff;edges[10]=32'h80000000;
    edges[11]=32'h80000001;edges[12]=32'h80008000;edges[13]=32'hffff0000;
    edges[14]=32'hffff0001;edges[15]=32'hffff7fff;edges[16]=32'hfffffffe;edges[17]=32'hffffffff;
    #1;grs_n=0;#11;grs_n=1;
    for(i=0;i<18;i=i+1)for(j=0;j<18;j=j+1)for(f=0;f<4;f=f+1)
      cycle(edges[i],edges[j],f[0],f[1],1'b1);
    seed=32'h85c021;unused=$urandom(seed);
    for(i=0;i<8192;i=i+1)begin
      f=$urandom;cycle($urandom,$urandom,f[0],f[1],i%11<8);
    end
    $display("NATIVE_MUL_APM_VENDOR_WAVEFORM_PASS cycles=%0d captures=%0d held=%0d",count,captures,held);
    $finish;
  end
  initial begin #1000000;$fatal(1,"APM waveform timeout");end
endmodule
'''
high_a=next(c for c in cells if c['part']=='10')
high_b=next(c for c in cells if c['part']=='01')
sign_a=list(reversed(high_a['ports']['X'][1:-1].split(',')))[16]
sign_b=list(reversed(high_b['ports']['Y'][1:-1].split(',')))[16]
assert all(re.fullmatch(r'[A-Za-z_$][\w$]*\[0\]',x)for x in [sign_a,sign_b])
assert sign_a!=sign_b
tb=tb.replace('N12',sign_a[:-3]).replace('N9',sign_b[:-3])
bench=a.output/'tb_native_mul_apms.sv';bench.write_text(tb,encoding='utf-8')
vendor=Path('G:/fpga/PDS_2022.2-SP6.4/arch/vendor/pango/verilog/simulation')
binroot=Path('G:/fpga/workspace/tools/msys64/ucrt64/bin');image=a.output/'vendor.vvp'
env=dict(os.environ);env['PATH']=str(binroot)+';G:/fpga/workspace/tools/msys64/mingw64/bin;'+env['PATH']
commands=[('compile',[binroot/'iverilog.exe','-g2012','-s','tb_native_mul_apms','-y',vendor,'-o',image,bench]),('waveform',[binroot/'vvp.exe',image])]
logs={}
for label,cmd in commands:
    log=a.output/(label+'.log')
    with log.open('xb')as f:result=subprocess.run(list(map(str,cmd)),stdout=f,stderr=subprocess.STDOUT,env=env,timeout=180)
    assert result.returncode==0,log.read_text(errors='replace')[-2500:]
    logs[label]=sha(log)
raw=(a.output/'waveform.log').read_bytes();assert b'NATIVE_MUL_APM_VENDOR_WAVEFORM_PASS cycles=9488 captures=7256 held=2232'in raw,raw[-1500:]
assert sha(vm)==digest, 'Native VM changed'
r=dict(status='NATIVE_MUL_APM_VENDOR_WAVEFORM_PASS_NOT_STA_OR_BOARD',native_vm_sha256=sha(vm),testbench_sha256=sha(bench),actual_apm_instances=[c['name']for c in cells],cycles=9488,captures=7256,held=2232,source_sha256={str(vendor/n):sha(vendor/n)for n in ['GTP_APM_E2.v','GTP_GRS.v']},logs_sha256=logs,created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),scope='Actual four APM parameter/port configurations, excluding unused P output wire names. Their input sign/data correspondence is independently proved from the native Boolean graph. Vendor one-edge capture and held data compared with full signed multiplication over all4 sign modes. Reconstruction tested here is the specified boundary expression; actual mapped writeback is independently SAT checked. No whole CPU sequential, STA or board claim.')
(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(r['status'])
