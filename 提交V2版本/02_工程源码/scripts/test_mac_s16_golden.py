"""Independent integer-golden S16 dot/square checks for each output profile."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess

ROOT=Path(__file__).resolve().parents[1]

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--profile',type=int,choices=[1,2],default=1)
    ap.add_argument('--icarus-bin',type=Path)
    a=ap.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
    ext='.exe' if os.name=='nt' else ''
    iv=str(a.icarus_bin/('iverilog'+ext)) if a.icarus_bin else shutil.which('iverilog')
    vvp=str(a.icarus_bin/('vvp'+ext)) if a.icarus_bin else shutil.which('vvp')
    assert iv and vvp
    env=dict(os.environ)
    if a.icarus_bin:env['PATH']=str(a.icarus_bin)+os.pathsep+env['PATH']
    sources=[ROOT/'rtl/mac_accel/MacAccelCore.v',ROOT/'sim/gtp_apm_e2_perf_sim.v',ROOT/'sim/tb_mac_half_s16_golden.sv']
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    before={p.relative_to(ROOT).as_posix():sha(p) for p in sources};logs={}
    commands=[('compile',[iv,'-g2012','-s','tb_mac_half_s16_golden',f'-Ptb_mac_half_s16_golden.OUTPUT_PROFILE={a.profile}','-o',str(out/'test.vvp'),*map(str,sources)]),('run',[vvp,str(out/'test.vvp')])]
    for name,cmd in commands:
        result=subprocess.run(cmd,capture_output=True,env=env,timeout=600)
        p=out/(name+'.log');p.write_bytes(result.stdout+result.stderr);assert result.returncode==0,p
        logs[name]=sha(p)
    assert b'MAC_HALF_S16_GOLDEN_PASS words=8394' in result.stdout
    assert before=={p.relative_to(ROOT).as_posix():sha(p) for p in sources}
    report=dict(status='S16_DOT_SQUARE_8394_INTEGER_GOLDEN_WORDS_PASS_NOT_BOARD',output_profile=a.profile,source_sha256=before,logs_sha256=logs)
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'])

if __name__=='__main__':main()
