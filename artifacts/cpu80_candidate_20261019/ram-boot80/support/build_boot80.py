from pathlib import Path
import subprocess,json,hashlib,datetime
p=Path('G:/fpga/performance_soc_voice_hw');w=p/'build/cpu80-20261019';log=w/'boot80-build.log';assert not log.exists()
cmd=['wsl.exe','-d','pikafish-verify','--','python3','/mnt/g/fpga/performance_soc_voice_hw/linux/opensbi/build_clock_candidate.py','--output','/mnt/g/fpga/performance_soc_voice_hw/build/cpu80-20261019/boot80-clock','--archive','/mnt/g/fpga/performance_soc_voice_hw/linux/sources/opensbi-1.3.1.tar.gz','--clock-config','/mnt/g/fpga/c80r1/config/clocks.json']
with log.open('wb') as f:r=subprocess.run(cmd,cwd=p,stdout=f,stderr=subprocess.STDOUT,timeout=1800)
assert r.returncode==0,(r.returncode,log.read_text(errors='replace')[-2500:])
m=json.loads((w/'boot80-clock/boot-manifest.json').read_text());assert m['ratio']==[99,160]
print('CPU80_CLOCK_BOOT_BUILT_NOT_BOARD_TESTED')
