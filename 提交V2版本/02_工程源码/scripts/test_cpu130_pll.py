"""Check CPU80/SYS/video periods using the installed vendor PLL model."""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--icarus-bin',type=Path)
p.add_argument('--vendor-models',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--timeout-seconds',type=int,default=90)
p.add_argument('--fractional',action='store_true')
p.add_argument('--cpu130',action='store_true')
p.add_argument('--cpu60',action='store_true')
p.add_argument('--wsl-distro',help='Explicitly run this same check using Linux Icarus in a Windows WSL distribution')
a=p.parse_args();root=Path(__file__).resolve().parents[1]
if not 10 <= a.timeout_seconds <= 900:p.error('--timeout-seconds must be 10..900')

if a.wsl_distro:
    assert os.name=='nt','--wsl-distro requires a Windows host'
    def linux(path):
        value=path.resolve().as_posix()
        assert len(value)>2 and value[1:3]==':/', 'Expected a local drive path: '+value
        return '/mnt/'+value[0].lower()+value[2:]
    cmd=['wsl.exe','-d',a.wsl_distro,'--','python3',linux(Path(__file__)),
         '--vendor-models',linux(a.vendor_models),'--output',linux(a.output),
         '--timeout-seconds',str(a.timeout_seconds)]
    if a.fractional:cmd.append('--fractional')
    if a.cpu130:cmd.append('--cpu130')
    if a.cpu60:cmd.append('--cpu60')
    subprocess.run(cmd,check=True,timeout=2*a.timeout_seconds+30)
    record=json.loads((a.output/'result.json').read_text())
    expected='CPU60_PLL_VENDOR_WAVEFORM_PASS' if a.cpu60 else 'CPU130_FRAC_PLL_VENDOR_WAVEFORM_PASS' if a.cpu130 else 'CPU80_FRAC_PLL_VENDOR_WAVEFORM_PASS' if a.fractional else 'CPU80_PLL_VENDOR_WAVEFORM_PASS'
    assert record['status']==expected
    record['execution_platform']='WSL '+a.wsl_distro
    record['host_command']=cmd
    (a.output/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    print(expected+' platform=WSL:'+a.wsl_distro)
    raise SystemExit(0)
a.output.mkdir(parents=True,exist_ok=False)
suffix='.exe' if os.name=='nt' else ''
def executable(name):
    return str(a.icarus_bin/(name+suffix)) if a.icarus_bin else shutil.which(name)
env=dict(os.environ)
if a.icarus_bin:env['PATH']=str(a.icarus_bin)+os.pathsep+env['PATH']
top='tb_cpu60_pll' if a.cpu60 else 'tb_cpu130_pll' if a.cpu130 else 'tb_cpu80_frac_pll' if a.fractional else 'tb_cpu80_pll'
marker='CPU60_PLL_VENDOR_WAVEFORM_PASS' if a.cpu60 else 'CPU130_FRAC_PLL_VENDOR_WAVEFORM_PASS' if a.cpu130 else 'CPU80_FRAC_PLL_VENDOR_WAVEFORM_PASS' if a.fractional else 'CPU80_PLL_VENDOR_WAVEFORM_PASS'
sources=[root/'rtl/video/pll_cpu.v',root/'rtl/video/pll_video.v',root/('sim/'+top+'.sv')]
image=a.output/'pll.vvp'
commands=[('compile',[executable('iverilog'),'-g2012','-s',top,'-y',str(a.vendor_models),'-o',str(image),*map(str,sources)]),('waveform',[executable('vvp'),str(image)])]
for name,cmd in commands:
    r=subprocess.run(cmd,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=a.timeout_seconds)
    (a.output/(name+'.txt')).write_bytes(r.stdout)
    assert r.returncode==0 and b'ERROR:' not in r.stdout and b'FATAL:' not in r.stdout,(name,r.stdout[-2500:])
    if name=='waveform':assert marker.encode() in r.stdout,r.stdout[-2500:]
record={'status':marker,'scope':'Digital vendor model only; not physical STA or board lock proof','source_sha256':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in sources+[a.vendor_models/'GTP_GPLL.v']},'tools':{'compiler':executable('iverilog'),'simulator':executable('vvp')},'checker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
(a.output/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(record['status'])
