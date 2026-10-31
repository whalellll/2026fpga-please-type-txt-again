"""Compile and QEMU-check additive CPU80 convolution user tools; no devices."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--distro',default='pikafish-verify');a=ap.parse_args()
root=Path(__file__).resolve().parents[1];out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def wsl(p):
 s=p.resolve().as_posix();return '/mnt/'+s[0].lower()+s[2:]
logs=out/'evidence';logs.mkdir();bin=out/'usr/bin';bin.mkdir(parents=True)
records={};sources={};commands=[]
for tool in ['pango_mac_conv_window_test','pango_mac_conv_compute_test']:
 source=root/'linux/mac_accel'/(tool+'.c');binary=bin/tool.replace('_','-')
 cc='/opt/toolchain/bin/riscv32-linux-musl-gcc'
 args=[cc,'-std=gnu11','-march=rv32ima','-mabi=ilp32','-Os','-static','-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-Wall','-Wextra','-Werror',wsl(source),'-o',wsl(binary)]
 result=subprocess.run(['wsl.exe','-d',a.distro,'--',*args],capture_output=True,timeout=180)
 (logs/(tool+'-compile.log')).write_bytes(result.stdout+result.stderr);assert result.returncode==0,(tool,result.stderr[-1500:])
 commands.append(args)
 if tool=='pango_mac_conv_compute_test':
  for mode in ['--oracle-only','--oracle-shapes']:
   args=['qemu-riscv32',wsl(binary),mode]
   result=subprocess.run(['wsl.exe','-d',a.distro,'--',*args],capture_output=True,timeout=90)
   (logs/(tool+mode+'.log')).write_bytes(result.stdout+result.stderr);assert result.returncode==0,(tool,result.stderr[-1500:])
   assert b'PASS' in result.stdout,(tool,result.stdout[-1500:])
   commands.append(args)
 records[binary.relative_to(out).as_posix()]=sha(binary);sources[source.relative_to(root).as_posix()]=sha(source)
sources['linux/mac_accel/pango_mac_uapi.h']=sha(root/'linux/mac_accel/pango_mac_uapi.h')
(out/'manifest.json').write_text(json.dumps(dict(status='RV32_CONV_TOOLS_COMPILED_COMPUTE_QEMU_ORACLES_PASS_NOT_BOARD',window_scope='Compiled RV32 only: the window tool requires a real device and has no oracle-only option.',files_sha256=records,source_sha256=sources,commands=commands),indent=2)+'\n')
print('RV32_CONV_TOOLS_COMPILED_COMPUTE_QEMU_ORACLES_PASS_NOT_BOARD')
