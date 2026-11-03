"""Freeze and hash every kernel integration input across the actual build."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,shutil,subprocess
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--archive-wsl');ap.add_argument('--jobs',type=int,default=2);a=ap.parse_args()
 out=a.output.resolve();assert not out.exists();out.mkdir(parents=True)
 files=[ROOT/'linux/boot/Image',ROOT/'linux/soc.dts',ROOT/'config/clocks.json',ROOT/'scripts/build_linux_mac_kernel.ps1',ROOT/'scripts/wsl_build_profile.sh']
 for sub in ['linux/audio','linux/mac_accel']:
  files+=sorted(p for p in (ROOT/sub).rglob('*') if p.is_file() and p.suffix in ['.h','.c','.patch'])
 hashes={str(p):sha(p) for p in files}
 (out/'inputs.json').write_text(json.dumps(hashes,indent=2)+'\n')
 cmd=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'scripts/build_linux_mac_kernel.ps1'),
      '-Distro','pikafish-verify','-Jobs',str(a.jobs),'-IncludeAudio','-IncludeVoice','-LinuxArchivePath','G:/fpga/performance_soc_linux/linux/sources/linux-5.14.tar.xz','-OutputPath',str(out/'outputs')]
 if a.archive_wsl:cmd+=['-LinuxArchiveWslPath',a.archive_wsl]
 with (out/'launcher.log').open('wb') as f:p=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
 assert p.returncode==0,p.returncode
 assert all(sha(Path(n))==h for n,h in hashes.items()),'Kernel input changed during compilation'
 assert b'LINUX_MAC_SCHEDULER_KERNEL_BUILD_PASS' in (out/'launcher.log').read_bytes()
 for name in ['Image','soc.dtb','kernel.config']:shutil.copy2(out/'outputs'/name,out/name)
 config=(out/'kernel.config').read_text()
 for flag in ['CONFIG_32BIT=y','CONFIG_PREEMPT_NONE=y','CONFIG_PANGO_MAC_ACCEL=y','CONFIG_PANGO_AUDIO_CAPTURE=y','CONFIG_PANGO_VOICE_ACCEL=y']:
  assert flag in config
 receipt=dict(status='VOICE_NNUE_FROZEN_KERNEL_BUILD_PASS_NOT_BOARD',completed_utc=datetime.now(timezone.utc).isoformat(),
  commands=cmd,inputs_sha256=hashes,outputs_sha256={n:sha(out/n) for n in ['Image','soc.dtb','kernel.config']},
  log_sha256=sha(out/'launcher.log'),board_tested=False)
 (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n');print(receipt['status'])
if __name__=='__main__':main()
