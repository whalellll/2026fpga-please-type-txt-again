"""Make a RAM-only native candidate; immutable models were already losslessly packed."""
import argparse,gzip,hashlib,io,json,tarfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--models',type=Path,required=True);p.add_argument('--worker',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if a.out.exists():raise FileExistsError(a.out)
files={name:(a.models/name).read_bytes() for name in ('board.xqm','detector.xqm','classifier.xqm','refinement_rng.bin','native_manifest.json')}
files['xq-native-worker']=a.worker.read_bytes()
manifest=dict(scope='EXPERIMENTAL native RAM deployment; M0 FAIL; no production/full-integer claim',files={name:dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest()) for name,data in files.items()})
files['ram_manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
stream=io.BytesIO()
with tarfile.open(fileobj=stream,mode='w',format=tarfile.USTAR_FORMAT) as tf:
    for name,data in files.items():
        t=tarfile.TarInfo('xq-native/'+name);t.size=len(data);t.mtime=0;t.uid=t.gid=0;t.mode=0o755 if name=='xq-native-worker' else 0o644
        tf.addfile(t,io.BytesIO(data))
a.out.write_bytes(gzip.compress(stream.getvalue(),compresslevel=9,mtime=0))
a.out.with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('NATIVE_RAM_PACKAGE',a.out.stat().st_size,hashlib.sha256(a.out.read_bytes()).hexdigest(),flush=True)
