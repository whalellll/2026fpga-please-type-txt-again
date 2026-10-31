"""Check that stripping deployment copies preserves every allocated ELF section."""
import hashlib,json,struct
from pathlib import Path
R=Path(__file__).resolve().parents[2];B=R/'build/picture-merge-20261023'
def elf(p):
 data=p.read_bytes();assert data[:7]==b'\x7fELF\x01\x01\x01'
 h=struct.unpack_from('<16sHHIIIIIHHHHHH',data);assert h[2]==243 and h[7]==0
 sh=[struct.unpack_from('<10I',data,h[6]+i*h[11]) for i in range(h[12])];names=sh[h[13]];strings=data[names[4]:names[4]+names[5]];sections={}
 for s in sh:
  if not s[2]&2:continue
  name=strings[s[0]:].split(b'\0')[0].decode();body=b'' if s[1]==8 else data[s[4]:s[4]+s[5]]
  sections[name]=(s[1],s[2],s[3],s[5],hashlib.sha256(body).hexdigest())
 return h[4],h[7],sections
rows={}
for name in ('xiangqi-pikafish-gui','xq-camera-capture'):
 original=B/'gui-rv32-r02'/name;copy=B/'gui-stripped'/name
 assert elf(original)==elf(copy)
 rows[name]=dict(original_bytes=original.stat().st_size,deploy_bytes=copy.stat().st_size,original_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),deployment_sha256=hashlib.sha256(copy.read_bytes()).hexdigest(),all_allocated_sections_entry_and_flags_identical=True)
(R/'docs/validation/picture-merge-20261023/stripped-payloads.json').write_text(json.dumps(dict(status='PASS',scope='strip symbols from deployment copies only; executable sections preserved; originals retained',payloads=rows),indent=2)+'\n')
print('STRIPPED_ELF_ALLOCATED_SECTIONS_IDENTICAL')
