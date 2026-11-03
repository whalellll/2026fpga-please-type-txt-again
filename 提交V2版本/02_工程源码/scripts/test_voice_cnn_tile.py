"""Independent signed-integer matrix oracle; exact all outputs, cache/reset/errors."""
from pathlib import Path
import argparse,hashlib,json,random,subprocess
R=Path(__file__).resolve().parents[1]
def wsl(p):
 s=p.resolve().as_posix();return '/mnt/'+s[0].lower()+s[2:]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--soc-mmio',action='store_true');a=ap.parse_args();o=a.output.resolve();o.mkdir(parents=True,exist_ok=False)
 rng=random.Random(20261024);cases=[(200,24,1),(120,24,3),(72,24,16),(24,22,7),(256,32,16),(4,1,1),(4,31,5)]
 cases+=[(rng.randrange(1,65)*4,rng.randrange(1,33),rng.randrange(1,17)) for _ in range(12)]
 v=[len(cases)]
 for idx,(k,co,p) in enumerate(cases):
  weights=[[rng.randrange(-128,128) for _ in range(k)] for _ in range(co)]
  inputs=[[rng.randrange(-128,128) for _ in range(k)] for _ in range(p)]
  if idx==4:weights=[[-128]*k for _ in range(co)];inputs=[[-128]*k for _ in range(p)]
  def pack(rows):return [sum((x&255)<<(8*j) for j,x in enumerate(row[i:i+4])) for row in rows for i in range(0,k,4)]
  v += [k,co,p]+pack(weights)+pack(inputs)+[sum(x*y for x,y in zip(row,w))&0xffffffff for row in inputs for w in weights]
 (o/'vectors.hex').write_text(''.join(f'{x:08x}\n' for x in v))
 sources=[R/'sim/tb_voice_cnn_tile.sv']+[R/'rtl/audio'/p for p in ['voice_cnn_tile_core.v','voice_accel_mmio.v','voice_feature_core.v','voice_classifier_core.v']]
 cmd=f"set -eu; cd '{wsl(o)}'; iverilog -g2012 -s tb_voice_cnn_tile -Ptb_voice_cnn_tile.WRAPPER={int(a.soc_mmio)} -o test.vvp "+' '.join("'"+wsl(p)+"'" for p in sources)+'; vvp test.vvp'
 p=subprocess.run(['wsl','-d','pikafish-verify','--','sh','-c',cmd],capture_output=True,timeout=180)
 (o/'rtl.log').write_bytes(p.stdout+p.stderr)
 assert p.returncode==0,(o/'rtl.log').read_text(errors='replace')[-4000:]
 assert b'VOICE_CNN_TILE_DIFFERENTIAL_PASS' in p.stdout
 r={'status':'VOICE_CNN_TILE_DIFFERENTIAL_PASS_NOT_BOARD','cases':len(cases),'soc_mmio':a.soc_mmio,'rtl_sha256':hashlib.sha256((R/'rtl/audio/voice_cnn_tile_core.v').read_bytes()).hexdigest()}
 (o/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
if __name__=='__main__':main()
