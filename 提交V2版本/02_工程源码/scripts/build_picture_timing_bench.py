"""Build strict original-graph timing tool and validate all existing graphs."""
from pathlib import Path
import argparse,hashlib,io,json,struct,subprocess,tarfile,uuid
R=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 a.output.mkdir(parents=True,exist_ok=False);out=a.output.resolve()
 manifest=json.loads((a.assets/'manifest.json').read_text());assert not manifest['synthetic_weights']
 includes=['linux/picture_new/upstream/adapter/runtime','linux/picture_new/upstream/linux/vision','linux/mac_accel','sw/bootloader']
 sources=['linux/picture_new/vision32_backend.c','linux/picture_new/vision32_layer.c','linux/picture_new/picture_new_bench.c','linux/picture_new/upstream/adapter/runtime/xq_native_graph.c','sw/bootloader/crc32_fast.c']
 files=set(sources+['linux/picture_new/upstream/adapter/runtime/xq_int8_layer.c'])
 for d in includes:files.update(p.relative_to(R).as_posix() for p in (R/d).glob('*.h'))
 hashes={n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in files}
 native='/var/tmp/integrated60-bench-'+uuid.uuid4().hex
 flags='-std=c11 -O2 -Wall -Wextra -Werror -ffp-contract=off '+' '.join('-I'+native+'/'+n for n in includes)
 src=' '.join(native+'/'+n for n in sources)
 script='set -eu\nexport PATH=/opt/toolchain/bin:/usr/bin:/bin\n'
 script+=f'gcc {flags} {src} -lm -o {native}/out/bench-host\n'
 script+=f'riscv32-linux-musl-gcc {flags} -static -march=rv32ima -mabi=ilp32 -mstrict-align {src} -lm -o {native}/out/picture-new-bench\n'
 script+=f'mkdir {native}/assets\ntar -xzf {native}/assets.tar.gz -C {native}/assets\n'
 for model in ['board','detector','classifier']:
  script+=f'{native}/out/bench-host {model} {native}/assets/{model}.xqm {native}/assets/{model}.f32 1 load 1\n'
  script+=f'qemu-riscv32 {native}/out/picture-new-bench {model} {native}/assets/{model}.xqm {native}/assets/{model}.f32 1 load 1\n'
  script+=f'{native}/out/bench-host {model} {native}/assets/{model}.xqm {native}/assets/{model}.f32 1 cpu 1\n'
 script+=f'riscv32-linux-musl-readelf -h -A {native}/out/picture-new-bench > {native}/out/elf.txt\n'
 (out/'build.sh').write_bytes(script.encode())
 payload=io.BytesIO()
 with tarfile.open(fileobj=payload,mode='w') as t:
  for n in files:t.add(R/n,arcname=n,recursive=False)
  t.add(out/'build.sh',arcname='build.sh');t.add(a.assets/'timing-assets.tar.gz',arcname='assets.tar.gz')
 cmd=f'set -eu; mkdir -p {native}/out; tar -xf - -C {native}; timeout --kill-after=5 180 sh {native}/build.sh'
 with (out/'build.log').open('wb') as log:r=subprocess.run(['wsl.exe','-d','pikafish-verify','--','sh','-c',cmd],input=payload.getvalue(),stdout=log,stderr=subprocess.STDOUT,timeout=220)
 body=(out/'build.log').read_bytes();assert r.returncode==0,body.decode(errors='replace')[-3500:]
 assert body.count(b'PICTURE_MODEL_LOAD_PASS')==6 and body.count(b'PICTURE_TIMING')==3
 r=subprocess.run(['wsl.exe','-d','pikafish-verify','--','tar','-cf','-','-C',native+'/out','.'],capture_output=True,check=True,timeout=60)
 with tarfile.open(fileobj=io.BytesIO(r.stdout)) as t:
  for m in t.getmembers():
   if m.isfile():(out/Path(m.name).name).write_bytes(t.extractfile(m).read())
 elf=(out/'picture-new-bench').read_bytes();assert elf[:6]==b'\x7fELF\x01\x01' and struct.unpack_from('<H',elf,18)[0]==243 and struct.unpack_from('<I',elf,36)[0]==0
 assert all(hashlib.sha256((R/n).read_bytes()).hexdigest()==v for n,v in hashes.items())
 result=dict(status='ORIGINAL_THREE_GRAPHS_HOST_CPU_AND_RV32_LOAD_PASS_NOT_BOARD',native_root=native,inputs_sha256=hashes,assets_manifest_sha256=hashlib.sha256((a.assets/'manifest.json').read_bytes()).hexdigest(),outputs_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()})
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
if __name__=='__main__':main()
