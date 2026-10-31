"""Independent Python arbitrary-precision requant oracle for the real voice RTL."""
from pathlib import Path
import argparse, hashlib, json, random, subprocess
R=Path(__file__).resolve().parents[1]
def lin(p):
    s=p.resolve().as_posix();return '/mnt/'+s[0].lower()+s[2:]
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    o=a.output.resolve();o.mkdir(parents=True,exist_ok=False)
    rng=random.Random(60241024);values=[]
    cases=[(8,32,3),(256,32,16),(72,24,7),(24,22,1),(4,1,1)]
    for index,(k,co,p) in enumerate(cases):
        lo,hi=(0,127) if index%2 else (-32768,32767)
        biases=[[-2147483648,2147483647,-1,0,1,3,-3][i%7] for i in range(co)]
        multipliers=[[1,1073741824,3,4194304][i%4] for i in range(co)]
        shifts=[[1,2,15,30,31,32,59,60][i%8] for i in range(co)]
        weights=[[rng.randrange(-128,128) for _ in range(k)] for _ in range(co)]
        inputs=[[rng.randrange(-128,128) for _ in range(k)] for _ in range(p)]
        if index==4:weights=[[0]*k];inputs=[[0]*k];biases=[-3];multipliers=[1];shifts=[1]
        values += [k,co,p,lo,hi]
        for b,m,s in zip(biases,multipliers,shifts):values += [b,m,s]
        for rows in [weights,inputs]:
            values += [sum((x&255)<<(8*j) for j,x in enumerate(row[i:i+4])) for row in rows for i in range(0,k,4)]
        for row in inputs:
            for w,b,m,s in zip(weights,biases,multipliers,shifts):
                prod=(sum(x*y for x,y in zip(row,w))+b)*m
                q=(abs(prod)+(1<<(s-1)))>>s
                if prod<0:q=-q
                values.append(max(lo,min(hi,q)))
    (o/'quant.hex').write_text(f'{len(cases):08x}\n'+''.join(f'{v&0xffffffff:08x}\n' for v in values))
    sources=[R/'sim/tb_voice_cnn_quant.sv',R/'rtl/audio/voice_cnn_tile_core.v']
    cmd=f"set -eu; cd '{lin(o)}'; iverilog -g2012 -s tb_voice_cnn_quant -o quant.vvp "+' '.join("'"+lin(p)+"'" for p in sources)+'; vvp quant.vvp'
    r=subprocess.run(['wsl','-d','pikafish-verify','--','sh','-c',cmd],capture_output=True,timeout=180)
    (o/'rtl.log').write_bytes(r.stdout+r.stderr)
    assert r.returncode==0 and b'VOICE_CNN_QUANT_EXACT_AND_CANCEL_PASS' in r.stdout,(r.stdout+r.stderr).decode(errors='replace')[-2500:]
    record=dict(status='VOICE_CNN_QUANT_INDEPENDENT_INTEGER_ORACLE_PASS_NOT_BOARD',cases=len(cases),
                source_sha256={p.relative_to(R).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    (o/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(record['status'])
if __name__=='__main__':main()
