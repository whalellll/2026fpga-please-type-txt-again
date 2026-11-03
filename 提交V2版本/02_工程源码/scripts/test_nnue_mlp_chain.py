"""Full FC0/dual activation/FC1/FC2 chain using the real PE and C reference."""
from pathlib import Path
import argparse,hashlib,json,random,struct,subprocess,zlib
ROOT=Path(__file__).resolve().parents[1]
def linux(p):
 p=Path(p).resolve().as_posix();return '/mnt/'+p[0].lower()+p[2:]
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--official-half',type=int,choices=[0,1]);ap.add_argument('--dense-profile',type=int,choices=[0,1,2],default=1);a=ap.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);rng=random.Random(750495)
 count=6 if a.official_half is None else 16
 memory=bytearray(count*65536);features=[];raw=[];official=[];bindings={}
 if a.official_half is not None:
  for name in ['pikafish-stageb-mac.bin','pikafish-stageb-position-golden.bin']:
   bindings[name]=hashlib.sha256((ROOT/'artifacts'/name).read_bytes()).hexdigest()
  pfsb=(ROOT/'artifacts/pikafish-stageb-mac.bin').read_bytes();pfg=(ROOT/'artifacts/pikafish-stageb-position-golden.bin').read_bytes()
  assert len(pfsb)==593920 and len(pfg)==38176
  assert struct.unpack_from('<I',pfg,48)[0]==struct.unpack_from('<I',pfsb,44)[0]==zlib.crc32(pfsb[4096:])
  assert struct.unpack_from('<I',pfsb,120)[0]==zlib.crc32(pfsb[:120])
  assert struct.unpack_from('<I',pfg,36)[0]==zlib.crc32(pfg[160:])
  assert pfg[56:120]==pfsb[48:112]
 for c in range(count):
  x=[0 if c==0 else 127 if c==1 else rng.randrange(128) for _ in range(1024)]
  w0=[[rng.randrange(-8,9) for _ in range(1024)] for _ in range(32)]
  w1=[[rng.randrange(-64,64) for _ in range(64)] for _ in range(32)]
  w2=[rng.randrange(-128,128) for _ in range(128)]
  b0=[rng.randrange(-30000,30000) for _ in range(32)];b1=[rng.randrange(-10000,10000) for _ in range(32)];b2=[rng.randrange(-10000,10000)]
  if c==0:b0[:12]=[-32769,-32768,-16384,-1,0,1,16320,16384,32767,32768,100000,-100000]
  if a.official_half is not None:
   case=c+a.official_half*16;record=pfg[160+case*1188:160+(case+1)*1188]
   bucket=struct.unpack_from('<I',record)[0];slot=pfsb[4096+bucket*0x9000:4096+(bucket+1)*0x9000]
   x=list(record[36:1060]);w0=[[0]*1024 for _ in range(32)]
   for co in range(32):
    for ci in range(1024):
     at=0x100+(ci//256)*8192+(ci%256//4)*128+(co//2)*8+(ci%4)*2+co%2
     w0[co][ci]=struct.unpack_from('<b',slot,at)[0]
   b0=list(struct.unpack_from('<32i',slot,0x8100));b1=list(struct.unpack_from('<32i',slot,0x8980));b2=list(struct.unpack_from('<i',slot,0x8a80))
   w1=[list(struct.unpack_from('<64b',slot,0x8180+row*64)) for row in range(32)]
   w2=list(struct.unpack_from('<128b',slot,0x8a00))
   official.append((struct.unpack_from('<32i',record,1060),struct.unpack_from('<i',record,16)[0]))
  base=c*65536
  for co in range(32):
   for i in range(1024):
    at=base+0x100+(i//256)*8192+(i%256//4)*128+(co//2)*8+(i%4)*2+(co%2)
    memory[at]=w0[co][i]&255
  for off,data in [(0x8100,struct.pack('<32i',*b0)),(0x8180,struct.pack('<2048b',*(v for row in w1 for v in row))),
                   (0x8980,struct.pack('<32i',*b1)),(0x8a00,struct.pack('<128b',*w2)),(0x8a80,struct.pack('<i',*b2))]:
   memory[base+off:base+off+len(data)]=data
  features.extend(x[i]|(x[i+1]<<8) for i in range(0,1024,2))
  raw.append(bytes(x)+struct.pack('<32768b',*(v for row in w0 for v in row))+struct.pack('<32i',*b0)+
             struct.pack('<2048b',*(v for row in w1 for v in row))+struct.pack('<32i',*b1)+struct.pack('<128b',*w2)+struct.pack('<i',*b2))
 (out/'model.hex').write_text(''.join(f'{v:08x}\n' for v in struct.unpack('<'+str(len(memory)//4)+'I',memory)))
 (out/'features.hex').write_text(''.join(f'{v:04x}\n' for v in features));(out/'oracle-input.bin').write_bytes(b''.join(raw))
 (out/'oracle.c').write_text('''#include "pf_mlp_stage_b.h"
#include <stdio.h>
#include <string.h>
int main(int argc,char **argv){
 FILE *in,*out;unsigned char x[1024],a0[64],a1[128];
 int8_t w0[32768],w1[2048],w2[128];int32_t b0[32],b1[32],b2[1],f0[32],f1[32],f2,score;
 pf_mlp_model_t m={0};
 if(argc!=3 || !(in=fopen(argv[1],"rb")) || !(out=fopen(argv[2],"wb")))return 2;
 while(fread(x,1,1024,in)==1024){
  if(fread(w0,1,32768,in)!=32768||fread(b0,4,32,in)!=32||fread(w1,1,2048,in)!=2048||
     fread(b1,4,32,in)!=32||fread(w2,1,128,in)!=128||fread(b2,4,1,in)!=1)return 3;
  m.fc0_w=w0;m.fc0_b=b0;m.fc1_w=w1;m.fc1_b=b1;m.fc2_w=w2;m.fc2_b=b2;
  pf_mlp_affine_u8_i8(x,1024,w0,b0,32,f0);
  pf_mlp_sqr_clipped_relu_i32(f0,a0,32,7);pf_mlp_clipped_relu_i32(f0,a0+32,32,7);
  pf_mlp_affine_u8_i8(a0,64,w1,b1,32,f1);
  memcpy(a1,a0,64);pf_mlp_sqr_clipped_relu_i32(f1,a1+64,32,6);pf_mlp_clipped_relu_i32(f1,a1+96,32,6);
  pf_mlp_affine_u8_i8(a1,128,w2,b2,1,&f2);
  if(!pf_mlp_propagate(&m,x,0,0,&score))return 4;
  if(fwrite(f0,4,32,out)!=32||fwrite(f1,4,32,out)!=32||fwrite(&f2,4,1,out)!=1||fwrite(&score,4,1,out)!=1)return 5;
 }
 return fclose(out)!=0;
}
''')
 ref=ROOT/'sw/pikafish_mlp_stage_b'
 cmd=f"set -eu; gcc -O2 -std=c11 -I'{linux(ref)}' '{linux(out/'oracle.c')}' '{linux(ref/'pf_mlp_stage_b_ref.c')}' -o '{linux(out/'oracle')}'; '{linux(out/'oracle')}' '{linux(out/'oracle-input.bin')}' '{linux(out/'golden.bin')}'"
 r=subprocess.run(['wsl','-d','pikafish-verify','--','sh','-c',cmd],capture_output=True)
 (out/'oracle.log').write_bytes(r.stdout+r.stderr);assert r.returncode==0,(out/'oracle.log').read_text(errors='replace')
 golden=(out/'golden.bin').read_bytes();assert len(golden)==count*66*4
 for c,(fc0,score) in enumerate(official):
  assert struct.unpack_from('<32i',golden,c*264)==fc0
  assert struct.unpack_from('<i',golden,c*264+260)[0]==score
 (out/'golden.hex').write_text(''.join(f'{v:08x}\n' for v in struct.unpack('<'+str(count*66)+'I',golden)))
 sources=[ROOT/'sim/tb_nnue_mlp_chain.sv',ROOT/'sim/gtp_apm_e2_perf_sim.v',ROOT/'rtl/mac_accel/MacAccelCore.v',ROOT/'rtl/mac_accel/mac_accel_dma_kernel.v',ROOT/'rtl/mac_accel/nnue_mlp_chain.v']
 src=' '.join("'"+linux(p)+"'" for p in sources)
 before={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
 cmd=f"set -eu; cd '{linux(out)}'; iverilog -g2012 -DPIKAFISH_BOOT_MIN_DRM -s tb_nnue_mlp_chain -Ptb_nnue_mlp_chain.CASES={count} -Ptb_nnue_mlp_chain.DENSE_PROFILE={a.dense_profile} -o test.vvp {src}; vvp test.vvp"
 r=subprocess.run(['wsl','-d','pikafish-verify','--','sh','-c',cmd],capture_output=True,timeout=300)
 (out/'rtl.log').write_bytes(r.stdout+r.stderr);assert r.returncode==0,(out/'rtl.log').read_text(errors='replace')[-3000:]
 assert b'NNUE_MLP_CHAIN_PASS' in r.stdout
 assert before=={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},'RTL changed during simulation'
 result=dict(status='NNUE_MLP_CHAIN_C_REFERENCE_REAL_PE_PASS_NOT_BOARD',cases=count,layers=3,affine_values=count*65,score_values=count,official_half=a.official_half,model_sha256=bindings,
             dense_profile=a.dense_profile,source_sha256=before)
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
