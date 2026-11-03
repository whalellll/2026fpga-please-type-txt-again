"""Verify the integrated folded-word representation and544-bit store cycles."""
import argparse,os,subprocess,tempfile
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--icarus-bin',type=Path,required=True);a=ap.parse_args();root=Path(__file__).resolve().parents[1]
env=dict(os.environ);env['PATH']=str(a.icarus_bin)+os.pathsep+env['PATH']
def run(cmd):
 r=subprocess.run(list(map(str,cmd)),cwd=root,env=env,capture_output=True,timeout=180)
 assert r.returncode==0,(r.stdout+r.stderr).decode(errors='replace');return r.stdout
with tempfile.TemporaryDirectory(prefix='conv-weight-fold-') as d:
 d=Path(d);image=d/'fold.vvp'
 run([a.icarus_bin/'iverilog.exe','-g2012','-s','tb_conv_weight_fold','-o',image,root/'sim/tb_conv_weight_fold.sv',root/'rtl/mac_accel/mac_conv_weight_dma.v',root/'rtl/mac_accel/mac_weight_double_buffer.v'])
 assert b'CONV_WEIGHT_FOLD_RTL_PASS' in run([a.icarus_bin/'vvp.exe',image])
 t=(root/'sim/tb_mac_weight_lutram_equivalence.sv').read_text().replace('module tb_mac_weight_lutram_equivalence','module tb_conv_weight_store544')
 t=t.replace('mac_weight_double_buffer #(.DEPTH(DEPTH),.ADDR_WIDTH(AW)) candidate','mac_weight_double_buffer #(.DEPTH(DEPTH),.ADDR_WIDTH(AW),.DATA_WIDTH(544)) candidate')
 t=t.replace("random_bits^(32'h9e3779b9*lane)^cycle","lane<17 ? random_bits^(32'h9e3779b9*lane)^cycle : 32'b0")
 tb=d/'tb.sv';tb.write_text(t)
 for depth,aw in [(4,2),(27,5),(32,5)]:
  run([a.icarus_bin/'iverilog.exe','-g2012','-s','tb_conv_weight_store544','-Ptb_conv_weight_store544.DEPTH='+str(depth),'-Ptb_conv_weight_store544.AW='+str(aw),'-o',image,tb,root/'sim/reference/mac_weight_double_buffer_cpu80.v',root/'rtl/mac_accel/mac_weight_double_buffer.v'])
  assert b'CONV_WEIGHT_PUBLIC_CYCLE_EQUIVALENCE_PASS' in run([a.icarus_bin/'vvp.exe',image])
print('CONV_WEIGHT_FOLD_AND_544BIT_STORE_CYCLES_PASS basis1024 random4096 cycles60000')
