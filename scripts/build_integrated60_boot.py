"""Build exact CPU60 timer firmware on Linux storage; no SD/board writes."""
from pathlib import Path
import argparse,hashlib,json,subprocess,tarfile,io,uuid
R=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--output',required=True,type=Path);a=ap.parse_args()
out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
native='/var/tmp/integrated60-boot-'+uuid.uuid4().hex
files=[R/'config/clocks.json',R/'linux/sources/opensbi-1.3.1.tar.gz']
for d in ['linux/opensbi','sw/bootloader','artifacts/voice_hw_candidate_20261016/loader','artifacts/voice_hw_candidate_20261016/boot']:
 files+=sorted(p for p in (R/d).rglob('*') if p.is_file() and p.suffix in ['.py','.h','.c','.S','.ld','.patch','.dts'])
hashes={p.relative_to(R).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
payload=io.BytesIO()
with tarfile.open(fileobj=payload,mode='w') as archive:
 for p in files:archive.add(p,arcname=p.relative_to(R).as_posix(),recursive=False)
command=f"set -eu; test ! -e '{native}'; mkdir '{native}'; tar -xf - -C '{native}'; python3 '{native}/linux/opensbi/build_clock_candidate.py' --output '{native}/out' --archive '{native}/linux/sources/opensbi-1.3.1.tar.gz' --clock-config '{native}/config/clocks.json'"
with (out/'build.log').open('wb') as log:r=subprocess.run(['wsl.exe','-d','pikafish-verify','--','env','PATH=/opt/toolchain/bin:/usr/local/bin:/usr/bin:/bin','timeout','--kill-after=10','1200','sh','-c',command],input=payload.getvalue(),stdout=log,stderr=subprocess.STDOUT,timeout=1240)
assert r.returncode==0,(out/'build.log').read_text(errors='replace')[-3000:]
names=['fw_jump.bin','fw_jump.elf','soc.dtb','soc.dts','loader-cpu-clock.bin','loader-cpu-clock.elf','pg2l_clock_ratio.h','boot-manifest.json']
receipt=subprocess.run(['wsl.exe','-d','pikafish-verify','--','tar','-cf','-','-C',native+'/out',*names],capture_output=True,check=True,timeout=60)
with tarfile.open(fileobj=io.BytesIO(receipt.stdout)) as archive:
 for n in names:(out/n).write_bytes(archive.extractfile(n).read())
record=json.loads((out/'boot-manifest.json').read_text());assert record['status']=='BOOT_CANDIDATE_BUILT_NOT_BOARD_TESTED' and record['ratio']==[33,40]
assert all(hashlib.sha256((R/n).read_bytes()).hexdigest()==h for n,h in hashes.items())
record.update(native_root=native,source_inputs_sha256=hashes)
(out/'result.json').write_text(json.dumps(record,indent=2)+'\n');print('CPU60_OPEN_SBI_TIMER_33_40_BUILD_PASS_NOT_BOARD')
