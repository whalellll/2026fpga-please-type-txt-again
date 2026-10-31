"""Actual-source CPU60 vendor waveform plus strict clock-policy mutations."""
from pathlib import Path
import argparse,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[1]
def linux(p):
 s=p.resolve().as_posix();return '/mnt/'+s[0].lower()+s[2:]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 vendor=Path('G:/fpga/PDS_2022.2-SP6.4/arch/vendor/pango/verilog/simulation')
 files=[ROOT/'rtl/video/pll_cpu.v',ROOT/'rtl/video/pll_video.v',ROOT/'sim/tb_cpu60_pll.sv',vendor/'GTP_GPLL.v',ROOT/'config/clocks.json']
 before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
 clock=json.loads(files[-1].read_text());assert clock['cpu_hz']==60000000 and clock['cpu_divisor']==36 and clock['cpu_output_divisor_eighths']==144
 cmd=f"set -eu; iverilog -g2012 -s tb_cpu60_pll -y '{linux(vendor)}' -o '{linux(out/'test.vvp')}' "+' '.join("'"+linux(p)+"'" for p in files[:3])+f"; vvp '{linux(out/'test.vvp')}'"
 r=subprocess.run(['wsl.exe','-d','pikafish-verify','--','sh','-c',cmd],capture_output=True,timeout=120)
 (out/'waveform.log').write_bytes(r.stdout+r.stderr)
 assert r.returncode==0 and b'CPU60_PLL_VENDOR_WAVEFORM_PASS' in r.stdout,(r.stdout+r.stderr).decode(errors='replace')[-2500:]
 assert before=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
 report=dict(status='CPU60_PLL_VENDOR_WAVEFORM_PASS_NOT_STA_OR_BOARD',source_sha256=before,log_sha256=hashlib.sha256(r.stdout+r.stderr).hexdigest())
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'])
if __name__=='__main__':main()
