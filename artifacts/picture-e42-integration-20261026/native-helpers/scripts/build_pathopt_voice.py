"""Build bounded-memory voice candidate from an immutable native source copy."""
from pathlib import Path
import argparse,hashlib,io,json,subprocess,tarfile
from workspace_paths import workspace_path,wsl_path
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
o=workspace_path(a.output);o.mkdir(parents=True,exist_ok=False)
files=[f for f in (R/'linux/voice2').rglob('*') if f.is_file()]+[R/'linux/audio/pango_voice_uapi.h']
hashes={f.relative_to(R).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
native=wsl_path(o/'source')
sources=['xqvoice_runtime.c','xqvoice_frontend.c','xqvoice_decode.c','xqvoice_capture.c','xqvoice_profile.c']
src=' '.join('linux/voice2/upstream/'+n for n in sources)+' linux/voice2/voice_small_backend.c'
script=f'''set -eu
export PATH=/opt/toolchain/bin:/usr/bin:/bin
mkdir out
mkdir tmp
export TMPDIR="$PWD/tmp" TMP="$PWD/tmp" TEMP="$PWD/tmp"
for variant in plain profile; do
 flags=''
 if [ "$variant" = profile ]; then flags=-DXQVOICE_PROFILE_ENABLED; fi
 riscv32-linux-musl-gcc -std=gnu11 -O2 -fwrapv -Wall -Wextra -Werror -march=rv32ima -mabi=ilp32 -static -pthread -DXQV_HOP_SAMPLES=320u -DXQV_CTC_BEAM=8 $flags {src} -o out/xqvoice-$variant
 riscv32-linux-musl-readelf -h -A out/xqvoice-$variant > out/$variant.elf.txt
 qemu-riscv32 out/xqvoice-$variant --selftest
done
'''
payload=io.BytesIO()
with tarfile.open(fileobj=payload,mode='w') as t:
 for f in files:t.add(f,arcname=f.relative_to(R).as_posix(),recursive=False)
 b=script.encode();info=tarfile.TarInfo('build.sh');info.size=len(b);t.addfile(info,io.BytesIO(b))
with (o/'build.log').open('wb') as log:
 r=subprocess.run(['wsl.exe','-d','pikafish-verify','--','sh','-c',f"set -eu; mkdir '{native}'; tar -xf - -C '{native}'; cd '{native}'; timeout --kill-after=5 180 sh build.sh"],input=payload.getvalue(),stdout=log,stderr=subprocess.STDOUT,timeout=210)
assert r.returncode==0,(o/'build.log').read_text(errors='replace')[-3000:]
result=subprocess.run(['wsl.exe','-d','pikafish-verify','--','tar','-cf','-','-C',native+'/out','.'],capture_output=True,check=True,timeout=60)
with tarfile.open(fileobj=io.BytesIO(result.stdout)) as t:
 for member in t.getmembers():
  if member.isfile():
   name=Path(member.name).name;assert '/' not in name and '\\' not in name
   (o/name).write_bytes(t.extractfile(member).read())
for name in ['xqvoice-plain','xqvoice-profile']:
 b=(o/name).read_bytes();assert b[:6]==b'\x7fELF\x01\x01' and int.from_bytes(b[18:20],'little')==243 and int.from_bytes(b[36:40],'little')==0
assert hashes=={f.relative_to(R).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
(o/'result.json').write_text(json.dumps(dict(status='PATHOPT_VOICE_PLAIN_PROFILE_STATIC_RV32_BUILD_SELFTEST_PASS_NOT_BOARD',native_root=native,inputs_sha256=hashes,outputs_sha256={n:hashlib.sha256((o/n).read_bytes()).hexdigest() for n in ['xqvoice-plain','xqvoice-profile','plain.elf.txt','profile.elf.txt']},board_tested=False),indent=2)+'\n')
print('PATHOPT_VOICE_PLAIN_PROFILE_STATIC_RV32_BUILD_SELFTEST_PASS_NOT_BOARD')
