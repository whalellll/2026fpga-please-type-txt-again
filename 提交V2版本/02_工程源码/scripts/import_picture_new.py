"""Import pinned Picture_new technical sources without inheriting remote instructions."""
from pathlib import Path
import hashlib,json,subprocess,io,tarfile
ROOT=Path(__file__).resolve().parents[1]
REF='80622e3f982332b25a83d9cc63f1ac5ed3f75bbd'
PREFIX='artifacts/vision-model-20261020-adapter/'
blob=subprocess.check_output(['git','archive','--format=tar',REF,PREFIX,'linux/vision','artifacts/vision-model-20261020/manifest.json','artifacts/board_detect_v2_round1/manifest.json'],cwd=ROOT)
archive=tarfile.open(fileobj=io.BytesIO(blob))
files=[m.name for m in archive.getmembers() if m.isfile()]
copied={}
for name in files:
 if not (name.startswith(PREFIX) or name.startswith('linux/vision/') or name in ('artifacts/vision-model-20261020/manifest.json','artifacts/board_detect_v2_round1/manifest.json')):continue
 if name.endswith('AGENTS.md') or '/evaluation/' in name or '/label-policy-' in name:continue
 rel='adapter/'+name[len(PREFIX):] if name.startswith(PREFIX) else name
 out=ROOT/'linux/picture_new/upstream'/rel
 out.parent.mkdir(parents=True,exist_ok=True)
 data=archive.extractfile(name).read();out.write_bytes(data)
 copied[name]=dict(path=out.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(data).hexdigest())
(ROOT/'linux/picture_new/SOURCE.json').write_text(json.dumps(dict(repository='whalellll/performance_soc',branch='Picture_new',commit=REF,files=copied,weights_in_git=False),indent=2)+'\n')
print('PICTURE_NEW_SOURCE_IMPORTED',len(copied))
