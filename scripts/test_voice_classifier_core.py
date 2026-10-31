"""Compare all121 outputs with the original C dense kernels and frozen SD77."""
from pathlib import Path
import argparse,hashlib,json,random,struct,subprocess

ROOT=Path(__file__).resolve().parents[1]
def linux(p):
 p=Path(p).resolve().as_posix();return '/mnt/'+p[0].lower()+p[2:]
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
 ap.add_argument('--model',type=Path,required=True);a=ap.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);model=a.model.resolve();b=model.read_bytes()
 assert hashlib.sha256(b).hexdigest()=='10186411d091dc85efefc921f29300e49a1e5de7b308f6e8d49602ea349ee41a'
 (out/'model.hex').write_text(''.join(f'{v:08x}\n' for v in struct.unpack('<1505I',b)))
 rng=random.Random(75);vectors=[[0]*40,[-128]*40,[127]*40]+[[rng.randrange(-128,128) for _ in range(40)] for _ in range(29)]
 raw=b''.join(struct.pack('<40b',*v) for v in vectors);(out/'input.bin').write_bytes(raw)
 (out/'input.hex').write_text(''.join(f'{v:08x}\n' for v in struct.unpack('<'+str(len(raw)//4)+'I',raw)))
 (out/'oracle.c').write_text('''#include "xqvoice_model.c"
int main(int argc,char **argv){
 xqvoice_model_t m;char error[128];int8_t x[40],h1[64],h2[32],y[25];FILE *in,*out;
 if(argc!=4 || !xqvoice_model_load(argv[1],&m,error,sizeof(error)))return 2;
 in=fopen(argv[2],"rb");out=fopen(argv[3],"wb");if(!in||!out)return 3;
 while(fread(x,1,40,in)==40){
  dense(x,40,m.weight1,m.bias1,64,m.shift1,1,h1);
  dense(h1,64,m.weight2,m.bias2,32,m.shift2,1,h2);
  dense(h2,32,m.weight3,m.bias3,25,m.shift3,0,y);
  if(fwrite(h1,1,64,out)!=64||fwrite(h2,1,32,out)!=32||fwrite(y,1,25,out)!=25)return 4;
 }
 return fclose(out)!=0;
}
''')
 cmd=f"set -eu; gcc -O2 -std=c11 -I'{linux(ROOT/'linux/voice')}' '{linux(out/'oracle.c')}' -o '{linux(out/'oracle')}'; '{linux(out/'oracle')}' '{linux(model)}' '{linux(out/'input.bin')}' '{linux(out/'golden.bin')}'"
 r=subprocess.run(['wsl','-d','pikafish-verify','--','sh','-c',cmd],capture_output=True)
 (out/'oracle.log').write_bytes(r.stdout+r.stderr);assert r.returncode==0,out/'oracle.log'
 golden=(out/'golden.bin').read_bytes();assert len(golden)==len(vectors)*121
 (out/'golden.hex').write_text(''.join(f'{v:02x}\n' for v in golden))
 core=ROOT/'rtl/audio/voice_classifier_core.v';tb=ROOT/'sim/tb_voice_classifier_core.sv'
 assert core.exists() and tb.exists(),'classifier hardware is required'
 cmd=f"set -eu; cd '{linux(out)}'; iverilog -g2012 -s tb_voice_classifier_core -Ptb_voice_classifier_core.CASES={len(vectors)} -o test.vvp '{linux(tb)}' '{linux(core)}'; vvp test.vvp"
 r=subprocess.run(['wsl','-d','pikafish-verify','--','sh','-c',cmd],capture_output=True)
 (out/'rtl.log').write_bytes(r.stdout+r.stderr);assert r.returncode==0,(out/'rtl.log').read_text(errors='replace')[-2500:]
 assert b'VOICE_CLASSIFIER_CORE_PASS' in r.stdout
 result=dict(status='VOICE_CLASSIFIER_C_ORACLE_PASS_NOT_BOARD',cases=len(vectors),outputs=len(golden),model_sha256=hashlib.sha256(b).hexdigest(),rtl_sha256=hashlib.sha256(core.read_bytes()).hexdigest())
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
