"""Reject the first archive's missing models; verify actual Linux extraction."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys,tarfile,io,uuid
sys.path[:0]=[str(Path(__file__).resolve().parent)]
from build_cpu80_conv_sd import cpio_entries
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--rootfs',type=Path,default=R/'build/integrated-sd-prepared-04/sd-root/rootfs.cpio');p.add_argument('--output',type=Path,default=R/'build/integrated-rootfs-extract-04');a=p.parse_args()
out=a.output;out.mkdir(exist_ok=False)
native='/var/tmp/integrated60-rootfs-'+uuid.uuid4().hex
files={'rootfs.cpio':a.rootfs,'timeout.c':R/'linux/picture_new/bench_timeout.c'}
script=f'''set -eu
mkdir {native}/unpack
cd {native}/unpack
cpio -i --quiet --no-absolute-filenames 'opt*' < ../rootfs.cpio
gcc -std=c11 -O2 -Wall -Wextra -Werror ../timeout.c -o ../timeout-host
../timeout-host 2 /bin/true
set +e
../timeout-host 2 /bin/sh -c 'exit 7'
test "$?" = 7 || exit 70
../timeout-host 1 /bin/sleep 10
test "$?" = 124 || exit 71
../timeout-host 1 /nonexistent
test "$?" = 127 || exit 72
exit 0
'''
(out/'test.sh').write_bytes(script.encode());files['test.sh']=out/'test.sh'
payload=io.BytesIO()
with tarfile.open(fileobj=payload,mode='w') as t:
 for n,p in files.items():t.add(p,arcname=n,recursive=False)
cmd=f'mkdir {native}; tar -xf - -C {native}; sh {native}/test.sh'
r=subprocess.run(['wsl.exe','-d','pikafish-verify','--','sh','-c',cmd],input=payload.getvalue(),capture_output=True,timeout=120)
(out/'test.log').write_bytes(r.stdout+r.stderr);assert r.returncode==0,(r.stdout+r.stderr).decode(errors='replace')
names=['opt/voice2/balanced24.bin']+['opt/integrated60/assets/'+n+'.xqm' for n in ['board','detector','classifier']]
r=subprocess.run(['wsl.exe','-d','pikafish-verify','--','sha256sum',*[native+'/unpack/'+n for n in names]],capture_output=True,check=True,timeout=60)
(out/'hashes.log').write_bytes(r.stdout+r.stderr)
rows=cpio_entries(files['rootfs.cpio'].read_bytes());expected={r['name']:r['sha256'] for r in rows if r['name'] in names}
for line in r.stdout.decode().splitlines():
 h,n=line.split(None,1);assert h==expected[n[len(native+'/unpack/'):]]
old=cpio_entries((R/'build/integrated-sd-kit-01/sd-root/rootfs.cpio').read_bytes());seen={'.'};broken=[]
for r in old:
 n=r['name'].removeprefix('./')
 if n=='TRAILER!!!':continue
 if str(Path(n).parent).replace('\\','/') not in seen:broken.append(n)
 if r['fields'][1]&0o170000==0o040000:seen.add(n)
assert 'opt/voice2/balanced24.bin' in broken and 'opt/integrated60/timing-assets.tar.gz' in broken
result=dict(status='ACTUAL_LINUX_CPIO_MODEL_HASHES_AND_WATCHDOG_PASS_NOT_BOARD',native_root=native,first_archive_missing_parent_reproduced=broken,
 checked_models=expected,rootfs_sha256=hashlib.sha256(files['rootfs.cpio'].read_bytes()).hexdigest(),notes='No gzip/tar decompressor required on board; new files directly in rootfs. Normal, nonzero, timeout and missing-command watchdog cases checked.')
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
