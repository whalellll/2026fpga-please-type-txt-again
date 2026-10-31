import argparse,hashlib,json,shutil
from datetime import datetime,timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--target',type=Path,required=True)
p.add_argument('--receipt',type=Path);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
paths=list((HERE/'runtime').glob('*.[ch]'))+[HERE/'build_native.sh']
paths += [HERE/'geometry_fallback/c_ref/geometry_ref.c',HERE/'geometry_fallback/c_ref/geometry_ref.h']
for name in ('xq_mac.h','xq_mac_linux.c','xq_roi.c','xq_roi.h','xq_grid.c','xq_grid.h','xq_vision.c','xq_vision.h'):
    paths.append(REPO/'linux/vision'/name)
for name in ('xiangqi_search.c','xiangqi_search.h','xiangqi_pikafish_link.c','xiangqi_pikafish_link.h'):
    paths.append(REPO/'sw/xiangqi'/name)
paths += [REPO/'linux/mac_accel/pango_mac_uapi.h',REPO/'sw/bootloader/crc32_fast.c',REPO/'sw/bootloader/crc32_fast.h',
          HERE.parent/'vision-model-20261020/geometry/geometry_reference.c']
if a.receipt:
    paths=[]
    for line in a.receipt.read_text().splitlines():
        digest,name=line.split(maxsplit=1);path=Path(name).resolve()
        assert path.is_relative_to(REPO) and hashlib.sha256(path.read_bytes()).hexdigest()==digest,name
        paths.append(path)
identity={}
for path in paths:
    name=path.relative_to(REPO).as_posix();dest=a.out/'sources'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
    identity[name]=hashlib.sha256(path.read_bytes()).hexdigest()
binary=a.target/'xq-native-worker'
(a.out/'source_binding.json').write_text(json.dumps(dict(recorded_utc=datetime.now(timezone.utc).isoformat(),
    source_sha256=identity,binary_path=str(binary),binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
    note='Exact source bytes preserved before further numerical optimization; build recipe/compiler receipt alongside target'),indent=2)+'\n')
print('NATIVE_SOURCE_SNAPSHOT',len(identity))
