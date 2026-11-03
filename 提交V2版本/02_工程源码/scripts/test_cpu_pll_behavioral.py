"""Compare all supported active CPU clock profiles in behavioral/vendor models."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--icarus-bin',type=Path);p.add_argument('--vendor-models',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--wsl-distro')
    a=p.parse_args();root=Path(__file__).resolve().parents[1]
    if a.wsl_distro:
        assert os.name=='nt'
        def linux(path):
            value=path.resolve().as_posix();assert value[1:3]==':/'
            return '/mnt/'+value[0].lower()+value[2:]
        cmd=['wsl.exe','-d',a.wsl_distro,'--','python3','-B',linux(Path(__file__)),'--icarus-bin','/usr/bin','--vendor-models',linux(a.vendor_models),'--output',linux(a.output)]
        subprocess.run(cmd,check=True,timeout=240)
        record=json.loads((a.output/'result.json').read_text());assert record['status']=='CPU_PLL_BEHAVIORAL_AND_VENDOR_PERIOD_DUTY_PASS'
        print(record['status']+' platform=WSL:'+a.wsl_distro);return
    a.output.mkdir(parents=True,exist_ok=False);env=dict(os.environ)
    if a.icarus_bin:env['PATH']=str(a.icarus_bin)+os.pathsep+env['PATH']
    suffix='.exe' if os.name=='nt' else ''
    exe=lambda name:str(a.icarus_bin/(name+suffix)) if a.icarus_bin else shutil.which(name)
    sources=[root/'rtl/video/pll_cpu.v',root/'sim/tb_cpu_pll_profiles.sv']
    for model in ('behavioral','vendor'):
        image=a.output/(model+'.vvp');args=['-DSOC_VIDEO_SIM'] if model=='behavioral' else ['-y',str(a.vendor_models)]
        cmd=[exe('iverilog'),'-g2012','-s','tb_cpu_profiles',*args,'-o',str(image),*map(str,sources)]
        for phase,command in [('compile',cmd),('waveform',[exe('vvp'),str(image)])]:
            r=subprocess.run(command,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
            (a.output/(model+'-'+phase+'.log')).write_bytes(r.stdout)
            assert not r.returncode and b'ERROR:' not in r.stdout and b'FATAL:' not in r.stdout,(model,phase,r.returncode,r.stdout[-1500:])
            if phase=='waveform':assert b'CPU_ALL13_ACTIVE_PERIOD_DUTY_PASS' in r.stdout
    sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
    record=dict(status='CPU_PLL_BEHAVIORAL_AND_VENDOR_PERIOD_DUTY_PASS',profiles=13,samples_per_profile=32,source_sha256={str(f):sha(f) for f in sources+[Path(__file__),a.vendor_models/'GTP_GPLL.v']},scope='Nominal active output period and high-time comparison after lock; no physical jitter, phase matching, STA or board proof.')
    (a.output/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(record['status'])
if __name__=='__main__':main()
