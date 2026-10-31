"""Stream prepared engine sources into a new WSL-local directory, avoiding DrvFS stat latency."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,tarfile,time
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--baseline',type=Path,required=True)
ap.add_argument('--target',required=True);ap.add_argument('--receipt',type=Path,required=True);a=ap.parse_args()
assert a.target.startswith('/var/tmp/pikafish-dedicated-source-') and '..' not in a.target
assert not a.receipt.exists()
cmd=['wsl.exe','-d','pikafish-verify','--','sh','-c','set -eu; test ! -e "'+a.target+'"; mkdir "'+a.target+'"; tar -xf - -C "'+a.target+'"']
files=[]
for sub in ('src','scripts'):
 for directory,dirs,names in os.walk(a.baseline/sub):
  dirs[:]=[n for n in dirs if n not in ['.git','__pycache__']]
  for name in sorted(names):
   p=Path(directory)/name
   if p.suffix in ['.o','.d','.a','.pyc'] or name in ['pikafish']:continue
   files.append(p)
process=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
hashes={};start=time.monotonic()
try:
 with tarfile.open(fileobj=process.stdin,mode='w|') as tar:
  for p in files:
   rel=p.relative_to(a.baseline).as_posix();hashes[rel]=hashlib.sha256(p.read_bytes()).hexdigest();tar.add(p,arcname=rel,recursive=False)
 process.stdin.close();process.stdin=None
 stdout,stderr=process.communicate(timeout=120)
 assert process.returncode==0,(stdout+stderr).decode(errors='replace')
finally:
 if process.poll() is None:process.terminate();process.wait(timeout=20)
a.receipt.parent.mkdir(parents=True,exist_ok=True)
a.receipt.write_text(json.dumps(dict(status='WSL_LOCAL_PREPARED_SOURCE_STREAM_COMPLETE',target=a.target,files_sha256=hashes,seconds=time.monotonic()-start),indent=2)+'\n')
print('WSL_LOCAL_SOURCE_STREAM_PASS',len(files),round(time.monotonic()-start,2),a.target)
