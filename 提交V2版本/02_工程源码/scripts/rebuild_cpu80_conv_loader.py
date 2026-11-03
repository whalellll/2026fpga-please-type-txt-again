"""Independently rebuild the packaged SD loader into a new directory."""
import argparse,hashlib,json,struct,subprocess,zlib
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--kit',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--distro',default='pikafish-verify');a=ap.parse_args()
kit=a.kit.resolve();out=a.output.resolve();assert not out.exists();out.mkdir(parents=True)
support=kit/'support';boot=support/'bootloader';sd=kit/'sd-root'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def linux(p):
 s=p.resolve().as_posix();assert s[1:3]==':/';return '/mnt/'+s[0].lower()+s[2:]
header='#ifndef CPU80_PAYLOADS_H\n#define CPU80_PAYLOADS_H\n#include "fat_ro.h"\n'
header+='typedef struct { const char *name; uint32_t address, bytes, crc32; fat_ro_file_t file; } payload_t;\nstatic payload_t payloads[] = {\n'
for name,address in {'fw_jump.bin':0x18000000,'Image':0x00400000,'rootfs.cpio':0x03000000,'soc.dtb':0x1a000000,'pikafish.pff':0x10000000,'pikafish.atk':0x15000000}.items():
 data=(sd/name).read_bytes();header+=' {"%s",0x%08xu,%du,0x%08xu,{0}},\n'%(name,address,len(data),zlib.crc32(data))
header+='};\n#define PAYLOAD_COUNT (sizeof(payloads)/sizeof(payloads[0]))\n#endif\n'
assert (support/'payloads.h').read_text(encoding='ascii')==header,'Packaged loader headers do not bind current SD files'
cc='/opt/toolchain/bin/riscv32-linux-musl-gcc';tools='/opt/toolchain/bin/riscv32-linux-musl-'
flags=['-march=rv32ima','-Wa,-march=rv32ima_zicsr_zifencei','-mabi=ilp32','-mcmodel=medany','-mno-relax','-msmall-data-limit=0','-mstrict-align','-ffreestanding','-fno-builtin','-fno-common','-ffunction-sections','-fdata-sections','-Os','-Wall','-Wextra','-Werror','-I',linux(boot),'-I',linux(support)]
commands=[]
def run(label,cmd):
 result=subprocess.run(['wsl.exe','-d',a.distro,'--',*cmd],capture_output=True,timeout=180)
 (out/(label+'.log')).write_bytes(result.stdout+result.stderr);assert result.returncode==0,(label,result.stderr[-2000:]);commands.append(cmd)
objects=[]
for name in ['start.S','loader.c','runtime.c','sd_native.c','fat_ro.c','crc32_fast.c']:
 source=support/name if name in ('start.S','loader.c') else boot/name;obj=out/(source.stem+'.o')
 run(source.stem,[cc,*flags,'-c',linux(source),'-o',linux(obj)]);objects.append(linux(obj))
elf=out/'loader.elf'
run('link',[cc,'-march=rv32ima','-mabi=ilp32','-nostdlib','-static','-Wl,--gc-sections,--no-relax,--build-id=none','-T',linux(support/'link.ld'),'-Wl,-Map,'+linux(out/'loader.map'),*objects,'-lgcc','-o',linux(elf)])
run('objcopy',[tools+'objcopy','-O','binary',linux(elf),linux(out/'Image.mmode')])
assert (out/'Image.mmode').read_bytes()==(sd/'Image.mmode').read_bytes(),'Relocated SD loader differs from delivered bytes'
(out/'result.json').write_text(json.dumps(dict(status='RELOCATED_CONV_SD_LOADER_BYTE_IDENTICAL_PASS_NOT_BOARD',loader_sha256=sha(out/'Image.mmode'),commands=commands,kit=str(kit)),indent=2)+'\n');print('RELOCATED_CONV_SD_LOADER_BYTE_IDENTICAL_PASS_NOT_BOARD')
