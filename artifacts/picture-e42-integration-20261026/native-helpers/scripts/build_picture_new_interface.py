"""Build and compare Picture_new interfaces; trained weights deliberately deferred."""
from pathlib import Path
import argparse,hashlib,json,subprocess,io,tarfile,struct
from workspace_paths import workspace_path,wsl_path
R=Path(__file__).resolve().parents[1]
def linux(p):
 s=Path(p).resolve().as_posix();return '/mnt/'+s[0].lower()+s[2:]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',required=True,type=Path);a=ap.parse_args()
 out=workspace_path(a.output);out.mkdir(parents=True,exist_ok=False)
 includes=['linux/picture_new/upstream/adapter/runtime','linux/picture_new/upstream/linux/vision','linux/mac_accel','sw/bootloader']
 common=['linux/picture_new/vision32_backend.c','linux/picture_new/vision32_layer.c']
 graph=common+['linux/picture_new/picture_new_infer.c','linux/picture_new/upstream/adapter/runtime/xq_native_graph.c','sw/bootloader/crc32_fast.c']
 files=set(graph+['sim/test_picture_new_vision32.c','linux/mac_accel/pango_mac_uapi.h'])
 for d in includes:files.update(p.relative_to(R).as_posix() for p in (R/d).glob('*.h'))
 files.add('linux/picture_new/upstream/adapter/runtime/xq_int8_layer.c')
 hashes={n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in files}
 flags='-std=c11 -O2 -Wall -Wextra -Werror -ffp-contract=off '
 native=wsl_path(out/'source')
 flags+=' '.join("-I'"+native+'/'+n+"'" for n in includes)
 src=lambda names:' '.join("'"+native+'/'+n+"'" for n in names)
 root=native+'/out'
 script=f'set -eu\nexport PATH=/opt/toolchain/bin:/usr/local/bin:/usr/bin:/bin\nmkdir {native}/tmp\nexport TMPDIR={native}/tmp TMP={native}/tmp TEMP={native}/tmp\n'
 for cc,suffix,extra in [('gcc','host',''),('/opt/toolchain/bin/riscv32-linux-musl-gcc','rv32','-static -march=rv32ima -mabi=ilp32 -mstrict-align')]:
  script+=f"{cc} {flags} {extra} {src(common+['sim/test_picture_new_vision32.c'])} -Wl,--wrap=ioctl -lm -o '{root}/interface-{suffix}'\n"
  script+=("qemu-riscv32 " if suffix=='rv32' else '')+f"'{root}/interface-{suffix}'\n"
  script+=f"{cc} {flags} {extra} {src(graph)} -lm -o '{root}/picture-new-infer-{suffix}'\n"
 script+=f"riscv32-linux-musl-readelf -h -A '{root}/picture-new-infer-rv32' > '{root}/elf.txt'\n"
 script+=f"test \"$(qemu-riscv32 '{root}/picture-new-infer-rv32' board /nonexistent /nonexistent '{root}/unused-output' 2>&1)\" = PICTURE_NEW_MODEL_REQUIRED_OR_INVALID\n"
 (out/'build.sh').write_bytes(script.encode())
 payload=io.BytesIO()
 with tarfile.open(fileobj=payload,mode='w') as archive:
  for n in files:archive.add(R/n,arcname=n,recursive=False)
  archive.add(out/'build.sh',arcname='build.sh',recursive=False)
 command="set -eu; test ! -e '"+native+"'; mkdir -p '"+root+"'; tar -xf - -C '"+native+"'; sh '"+native+"/build.sh'"
 with (out/'build.log').open('wb') as log:r=subprocess.run(['wsl.exe','-d','pikafish-verify','--','env','PATH=/opt/toolchain/bin:/usr/local/bin:/usr/bin:/bin','timeout','--kill-after=5','240','sh','-c',command],input=payload.getvalue(),stdout=log,stderr=subprocess.STDOUT,timeout=300)
 body=(out/'build.log').read_bytes();assert r.returncode==0,body.decode(errors='replace')[-4000:]
 assert body.count(b'PICTURE_NEW_VISION32_INTERFACE_AND_NO_FALLBACK_PASS')==2
 r=subprocess.run(['wsl.exe','-d','pikafish-verify','--','tar','-cf','-','-C',root,'.'],capture_output=True,check=True,timeout=60)
 with tarfile.open(fileobj=io.BytesIO(r.stdout)) as archive:
  for member in archive.getmembers():
   if not member.isfile():continue
   name=Path(member.name).name;assert '/' not in name and '\\' not in name
   (out/name).write_bytes(archive.extractfile(member).read())
 elf=(out/'elf.txt').read_text();binary=(out/'picture-new-infer-rv32').read_bytes()
 assert 'ELF32' in elf and 'RISC-V' in elf and binary[:6]==b'\x7fELF\x01\x01'
 assert struct.unpack_from('<H',binary,18)[0]==243 and struct.unpack_from('<I',binary,36)[0]==0,'Require RV32 soft-float/no-RVC/no-RVE ELF flags0'
 assert all(hashlib.sha256((R/n).read_bytes()).hexdigest()==h for n,h in hashes.items())
 record=dict(status='PICTURE_NEW_VISION32_HOST_RV32_INTERFACE_PASS_WEIGHTS_DEFERRED_NOT_BOARD',native_root=native,inputs_sha256=hashes,
  outputs_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()},
  scope='192/640/32 interfaces, exact raw I32 and CPU ties-even S16/LUT; whole-layer when scratch fits, hardware matrix tiling otherwise. No real trained weights, accuracy, full-frame FEN or board performance assertion.')
 (out/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(record['status'])
if __name__=='__main__':main()
