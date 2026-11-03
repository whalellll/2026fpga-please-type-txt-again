"""Use the unchanged C extractor as an oracle for complete hardware frames."""
from pathlib import Path
import argparse
import json
import math
import random
import subprocess
import hashlib

ROOT=Path(__file__).resolve().parents[1]

def linux(p):
    p=Path(p).resolve().as_posix()
    return '/mnt/'+p[0].lower()+p[2:]

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    rng=random.Random(20261023)
    samples=[[0]*400,[32767]*400,[-32768]*400,[32767 if x%2 else -32768 for x in range(400)]]
    for frequency in (80,200,440,1000,4000,7000):
        samples.append([int(18000*math.sin(2*math.pi*frequency*i/16000)) for i in range(400)])
    samples += [[rng.randrange(-32768,32768) for _ in range(400)] for _ in range(14)]
    # Several normalization contracts exercise negative rounding and both saturations.
    cases=[(s,offset,scale) for offset,scale in ((6000,1024),(0,32768),(16000,255)) for s in samples]
    (out/'oracle.c').write_text('''#include "xqvoice_features.h"
#include <stdio.h>
#include <stdint.h>
int main(int argc,char **argv){
 FILE *in,*output;int32_t off,scale;int16_t pcm[400];int8_t f[20];
 xqvoice_model_t m={0};
 if(argc!=3 || !(in=fopen(argv[1],"rb")) || !(output=fopen(argv[2],"wb")))return 2;
 while(fread(&off,4,1,in)==1){
  if(fread(&scale,4,1,in)!=1 || fread(pcm,2,400,in)!=400)return 3;
  m.feature_offset_q8=off;m.feature_scale_q15=scale;
  if(xqvoice_extract_features(pcm,400,&m,f,20)!=1 || fwrite(f,1,20,output)!=20)return 4;
 }
 return fclose(output)!=0;
}
''')
    import struct
    (out/'vectors.bin').write_bytes(b''.join(struct.pack('<ii400h',off,scale,*s) for s,off,scale in cases))
    (out/'pcm.hex').write_text(''.join(f'{v&65535:04x}\n' for s,_,_ in cases for v in s))
    (out/'params.hex').write_text(''.join(f'{v&0xffffffff:08x}\n' for _,off,scale in cases for v in (off,scale)))
    command=['wsl','-d','pikafish-verify','--','/bin/sh','-c',
             f"set -eu; gcc -std=c11 -O2 -fwrapv -I'{linux(ROOT/'linux/voice')}' '{linux(out/'oracle.c')}' "
             f"'{linux(ROOT/'linux/voice/xqvoice_features.c')}' -o '{linux(out/'oracle')}'; "
             f"'{linux(out/'oracle')}' '{linux(out/'vectors.bin')}' '{linux(out/'golden.bin')}'"]
    r=subprocess.run(command,capture_output=True);(out/'oracle.log').write_bytes(r.stdout+r.stderr)
    assert r.returncode==0,(out/'oracle.log')
    golden=(out/'golden.bin').read_bytes();assert len(golden)==len(cases)*20
    (out/'golden.hex').write_text(''.join(f'{x:02x}\n' for x in golden))
    tb=ROOT/'sim/tb_voice_feature_core.sv'
    core=ROOT/'rtl/audio/voice_feature_core.v'
    assert core.exists() and tb.exists(),'hardware core and independent oracle testbench required'
    command=['wsl','-d','pikafish-verify','--','/bin/sh','-c',
        f"set -eu; cd '{linux(out)}'; iverilog -g2012 -s tb_voice_feature_core -Ptb_voice_feature_core.CASES={len(cases)} "
        f"-o test.vvp '{linux(tb)}' '{linux(core)}'; vvp test.vvp"]
    r=subprocess.run(command,capture_output=True);(out/'rtl.log').write_bytes(r.stdout+r.stderr)
    assert r.returncode==0,(out/'rtl.log').read_text(errors='replace')[-3000:]
    assert b'VOICE_FEATURE_CORE_PASS' in r.stdout
    report=dict(status='VOICE_FEATURE_CORE_C_ORACLE_PASS_NOT_BOARD',cases=len(cases),outputs=len(golden),
        golden_sha256=hashlib.sha256(golden).hexdigest(),
        input_sha256=hashlib.sha256((out/'vectors.bin').read_bytes()).hexdigest(),
        rtl_sha256=hashlib.sha256(core.read_bytes()).hexdigest())
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':main()
