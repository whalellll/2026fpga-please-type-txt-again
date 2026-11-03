"""Live overlapping windows, chunk levels, queues and SD77 classification via MMIO."""
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
 rng=random.Random(16000);pcm=[rng.randrange(-32768,32768) for _ in range(1600)]
 (out/'pcm.bin').write_bytes(struct.pack('<1600h',*pcm));(out/'pcm.hex').write_text(''.join(f'{x&65535:04x}\n' for x in pcm))
 (out/'model.hex').write_text(''.join(f'{x:08x}\n' for x in struct.unpack('<1505I',b)))
 (out/'level.hex').write_text(''.join(f'{sum(abs(x) for x in pcm[i:i+160])//160:04x}\n' for i in range(0,1600,160)))
 (out/'oracle.c').write_text('''#include "xqvoice_model.c"
#include "xqvoice_features.h"
int main(int argc,char **argv){
 xqvoice_model_t m;char error[128];int16_t pcm[1600];int8_t f[160],pool[40],h1[64],h2[32],y[25];
 FILE *in,*out;int i,k,best=-129,second=-129;uint32_t result[2]={0,0};
 if(argc!=4 || !xqvoice_model_load(argv[1],&m,error,128))return 2;
 in=fopen(argv[2],"rb");out=fopen(argv[3],"wb");if(!in||!out||fread(pcm,2,1600,in)!=1600)return 3;
 if(xqvoice_extract_features(pcm,1600,&m,f,160)!=8)return 4;
 for(i=0;i<20;i++){int sum=0,max=-128;for(k=0;k<8;k++){int v=f[k*20+i];sum+=v;if(v>max)max=v;}pool[i]=sum/8;pool[i+20]=max;}
 dense(pool,40,m.weight1,m.bias1,64,m.shift1,1,h1);dense(h1,64,m.weight2,m.bias2,32,m.shift2,1,h2);dense(h2,32,m.weight3,m.bias3,25,m.shift3,0,y);
 for(i=0;i<25;i++){if(y[i]>best){second=best;best=y[i];result[0]=i;}else if(y[i]>second)second=y[i];}
 result[1]=(best-second)*1000u/255u;
 if(fwrite(f,1,160,out)!=160||fwrite(pool,1,40,out)!=40||fwrite(h1,1,64,out)!=64||
    fwrite(h2,1,32,out)!=32||fwrite(y,1,25,out)!=25||fwrite(result,4,2,out)!=2)return 5;
 return fclose(out)!=0;
}
''')
 cmd=f"set -eu; gcc -O2 -std=c11 -I'{linux(ROOT/'linux/voice')}' '{linux(out/'oracle.c')}' '{linux(ROOT/'linux/voice/xqvoice_features.c')}' -o '{linux(out/'oracle')}'; '{linux(out/'oracle')}' '{linux(model)}' '{linux(out/'pcm.bin')}' '{linux(out/'golden.bin')}'"
 r=subprocess.run(['wsl','-d','pikafish-verify','--','sh','-c',cmd],capture_output=True)
 (out/'oracle.log').write_bytes(r.stdout+r.stderr);assert r.returncode==0,out/'oracle.log'
 g=(out/'golden.bin').read_bytes();assert len(g)==329
 for name,data,size,digits in [('features.hex',g[:160],4,8),('pooled.hex',g[160:200],4,8),('layers.hex',g[200:321],1,2),('result.hex',g[321:],4,8)]:
  fmt='<'+str(len(data)//size)+('I' if size==4 else 'B');(out/name).write_text(''.join(f'{x:0{digits}x}\n' for x in struct.unpack(fmt,data)))
 sources=[ROOT/'sim/tb_voice_accel_mmio.sv',ROOT/'rtl/audio/voice_feature_core.v',ROOT/'rtl/audio/voice_classifier_core.v',ROOT/'rtl/audio/voice_accel_mmio.v']
 before={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
 cmd=f"set -eu; cd '{linux(out)}'; iverilog -g2012 -s tb_voice_accel_mmio -o test.vvp "+' '.join("'"+linux(p)+"'" for p in sources)+'; vvp test.vvp'
 r=subprocess.run(['wsl','-d','pikafish-verify','--','sh','-c',cmd],capture_output=True,timeout=300)
 (out/'rtl.log').write_bytes(r.stdout+r.stderr);assert r.returncode==0,(out/'rtl.log').read_text(errors='replace')[-2500:]
 assert b'VOICE_MMIO_LIVE_C_ORACLE_PASS' in r.stdout
 assert before=={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
 result=dict(status='VOICE_LIVE_MMIO_C_ORACLE_PASS_NOT_BOARD',samples=1600,windows=8,features=160,levels=10,classifier_outputs=121,source_sha256=before)
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
