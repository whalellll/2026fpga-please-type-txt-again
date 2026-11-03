"""Build the strict small-voice backend for RV32 Linux, without deploying it."""
from pathlib import Path
import argparse,hashlib,json,subprocess
R=Path(__file__).resolve().parents[1]
def lin(p):
 s=p.resolve().as_posix();return '/mnt/'+s[0].lower()+s[2:]
def main():
 global R
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--profile',action='store_true');ap.add_argument('--source-root',type=Path);a=ap.parse_args();o=a.output.resolve();o.mkdir(parents=True,exist_ok=False)
 if a.source_root:R=a.source_root.resolve()
 u=R/'linux/voice2/upstream'
 inputs=list(u.glob('*'))+[R/'linux/voice2/voice_small_backend.c',R/'linux/audio/pango_voice_uapi.h',R/'linux/voice2/balanced24.bin']
 hashes={p.relative_to(R).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
 src=[u/n for n in ['xqvoice_runtime.c','xqvoice_frontend.c','xqvoice_decode.c','xqvoice_capture.c','xqvoice_profile.c']]+[R/'linux/voice2/voice_small_backend.c']
 binary=o/'xqvoice-small-cnn'
 script=o/'build.sh'
 cmd="set -eu\n/opt/toolchain/bin/riscv32-linux-musl-gcc -std=gnu11 -O2 -fwrapv -Wall -Wextra -Werror -march=rv32ima -mabi=ilp32 -static -pthread -DXQV_HOP_SAMPLES=320u -DXQV_CTC_BEAM=8 "+('-DXQVOICE_PROFILE_ENABLED ' if a.profile else '')+' '.join("'"+lin(p)+"'" for p in src)+" -o '"+lin(binary)+"'\nreadelf -h -A '"+lin(binary)+"'\n"
 script.write_bytes(cmd.encode())
 p=subprocess.run(['wsl','-d','pikafish-verify','--','sh',lin(script)],capture_output=True,timeout=240)
 (o/'build.log').write_bytes(p.stdout+p.stderr);assert p.returncode==0,(p.stdout+p.stderr).decode(errors='replace')[-4000:]
 assert b'ELF32' in p.stdout and b'RISC-V' in p.stdout
 elf=binary.read_bytes();assert elf[:6]==b'\x7fELF\x01\x01'
 assert int.from_bytes(elf[18:20],'little')==243
 assert int.from_bytes(elf[36:40],'little')&15==0,'Compressed/float/RVE ABI forbidden'
 assert hashes=={p.relative_to(R).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
 result={'status':'VOICE2_SMALL_STRICT_RV32_LINUX_BUILD_PASS_NOT_BOARD','binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'inputs_sha256':hashes,'device':'/dev/pango-voice0','requires':'PANGO_VOICE_FEATURE_CNN_TILE','fallback':False,'profile_compiled':a.profile,'source_root':R.as_posix(),'build_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
 (o/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'binary_sha256':result['binary_sha256']}))
if __name__=='__main__':main()
