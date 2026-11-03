"""Pinned model, real CPU runtime vs new backend; replay all tiles against RTL."""
from pathlib import Path
import argparse,hashlib,json,os,random,struct,subprocess
R=Path(__file__).resolve().parents[1]
def lin(p):
 s=p.resolve().as_posix();return '/mnt/'+s[0].lower()+s[2:]
def command(cmd,o,name):
 script=o/(name+'.sh');script.write_bytes(('set -eu\n'+cmd+'\n').encode())
 p=subprocess.run(['wsl','-d','pikafish-verify','--','sh',lin(script)],capture_output=True,timeout=240)
 (o/(name+'.log')).write_bytes(p.stdout+p.stderr)
 assert p.returncode==0,(name,(p.stdout+p.stderr).decode(errors='replace')[-2500:])
 return p.stdout
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--rv32',action='store_true');a=ap.parse_args();o=a.output.resolve();o.mkdir(parents=True,exist_ok=False)
 src=R/'linux/voice2/upstream';model=R/'linux/voice2/balanced24.bin';assert hashlib.sha256(model.read_bytes()).hexdigest()=='3e43041fd3e531ce130b56c0a460a1c7375420eea0e07afdf533012ae41da973'
 sources=[src/f for f in ['xqvoice_runtime.c','xqvoice_frontend.c','xqvoice_decode.c','xqvoice_capture.c','xqvoice_profile.c']]+[R/'linux/voice2/voice_small_backend.c']
 bound=sources+list(src.glob('*.h'))+[src/'xqvoice_stream.inc',src/'xqvoice_worker.inc',R/'sim/voice2_device_mock.c',R/'rtl/audio/voice_cnn_tile_core.v',R/'sim/tb_voice_cnn_tile.sv']
 hashes={p.relative_to(R).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in bound}
 cc='/opt/toolchain/bin/riscv32-linux-musl-gcc -static -march=rv32ima -mabi=ilp32' if a.rv32 else 'gcc'
 runner='qemu-riscv32 ' if a.rv32 else ''
 cmd=cc+" -std=gnu11 -O2 -Wall -Wextra -Werror -DXQV_HOP_SAMPLES=320u -DXQV_CTC_BEAM=8 -pthread "+' '.join("'"+lin(p)+"'" for p in sources)+" '"+lin(R/'sim/voice2_device_mock.c')+"' -Wl,--wrap=open,--wrap=close,--wrap=ioctl -o '"+lin(o/'runtime')+"'"
 command(cmd,o,'build');allwords=[];jobs=0;rng=random.Random(24075);cases=[]
 for index,frames in enumerate([7,33,127,199]):
  data=struct.pack('<I',frames)+bytes(rng.randrange(256) for _ in range(frames*40));f=o/f'input-{index}.bin';f.write_bytes(data)
  for backend in ['cpu','mac','mac-verify']:
   trace=o/f'{index}-{backend}.trace';dump=o/f'{index}-{backend}.rtl.bin'
   cmd=f"VOICE2_RTL_DUMP='{lin(dump)}' {runner}'{lin(o/'runtime')}' '{lin(model)}' '{lin(f)}' '{lin(trace)}' {backend}; rc=$?; test $rc = 0 -o $rc = 25"
   # Runtime may reject random logits as no legal CTC phrase; this is expected.
   command('set +e; '+cmd,o,f'{index}-{backend}')
  reference=(o/f'{index}-cpu.trace').read_bytes()
  assert reference and all((o/f'{index}-{b}.trace').read_bytes()==reference for b in ['mac','mac-verify'])
  # Fused hardware path emits no raw trace, but every quantized value is checked
  # by the independent mock against the original CPU trace for all five layers.
  command(f"set +e; VOICE2_HW_QUANT=1 VOICE2_REQUIRE_QUANT=1 VOICE2_EXPECT_QUANT_TRACE='{lin(o/f'{index}-cpu.trace')}' {runner}'{lin(o/'runtime')}' '{lin(model)}' '{lin(f)}' /dev/null mac; rc=$?; test $rc = 0 -o $rc = 25",o,f'{index}-quant')
  assert b'VOICE2_MOCK_QUANT_JOBS=' in (o/f'{index}-quant.log').read_bytes()
  raw=(o/f'{index}-mac.rtl.bin').read_bytes();words=list(struct.unpack('<'+'I'*(len(raw)//4),raw));jobs+=words[0];allwords+=words[1:]
  cases.append({'frames':frames,'trace_sha256':hashlib.sha256(reference).hexdigest()})
 (o/'vectors.hex').write_text(f'{jobs:08x}\n'+''.join(f'{x:08x}\n' for x in allwords))
 if not a.rv32:command(f"cd '{lin(o)}'; iverilog -g2012 -s tb_voice_cnn_tile -o model.vvp '{lin(R/'sim/tb_voice_cnn_tile.sv')}' '{lin(R/'rtl/audio/voice_cnn_tile_core.v')}'; vvp model.vvp",o,'model-rtl')
 # Old SD77 firmware must be rejected rather than silently using CPU.
 command(f"set +e; VOICE2_NO_CAPABILITY=1 {runner}'{lin(o/'runtime')}' '{lin(model)}' '{lin(o/'input-0.bin')}' /dev/null mac; rc=$?; test $rc = 6",o,'capability-reject')
 command(f"set +e; VOICE2_REQUIRE_QUANT=1 {runner}'{lin(o/'runtime')}' '{lin(model)}' '{lin(o/'input-0.bin')}' /dev/null mac; rc=$?; test $rc = 6",o,'quant-capability-reject')
 command(f"set +e; VOICE2_HW_QUANT=1 VOICE2_QUANT_MODEL_FAIL=1 {runner}'{lin(o/'runtime')}' '{lin(model)}' '{lin(o/'input-0.bin')}' /dev/null mac; rc=$?; test $rc = 22",o,'quant-setup-reject')
 assert hashes=={p.relative_to(R).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in bound}
 result={'status':'VOICE2_BALANCED24_RV32_MOCK_PASS_NOT_BOARD' if a.rv32 else 'VOICE2_BALANCED24_FULL_MODEL_BACKEND_AND_RTL_PASS_NOT_BOARD','cases':cases,'rtl_tiles':0 if a.rv32 else jobs,'model_sha256':hashlib.sha256(model.read_bytes()).hexdigest(),'inputs_sha256':hashes,'scope':'All5 raw/requant layer traces exact CPU vs device mock; host run additionally replays real-model tile inputs/weights against RTL. Synthetic feature input, not speech accuracy or board speedup.'}
 (o/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
