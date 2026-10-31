"""Verify sealed r13-r17 deliveries, extract only to build/, archive intake metadata."""
import argparse,hashlib,json,stat,zipfile
from pathlib import Path,PurePosixPath
from receive_r08 import unique_object
REPO=Path(__file__).resolve().parents[2]
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path);p.add_argument('--sha256',required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args()
 root=a.out.resolve();assert root.is_relative_to(REPO/'build') and not root.exists() and not a.receipt.exists()
 assert sha(a.archive.read_bytes())==a.sha256,'archive SHA mismatch'
 with zipfile.ZipFile(a.archive) as z:
  entries={};seen=set()
  for i in z.infolist():
   n=i.filename;path=PurePosixPath(n)
   assert not path.is_absolute() and '..' not in path.parts and '\\' not in n and ':' not in n and not stat.S_ISLNK(i.external_attr>>16) and n.casefold() not in seen,'unsafe ZIP'
   seen.add(n.casefold())
   if not i.is_dir():entries[n]=i
  candidates=[n for n in entries if n.endswith('/manifest.json') and n.count('/')==1];assert len(candidates)==1
  mn=candidates[0];prefix=mn.removesuffix('manifest.json');raw=z.read(mn);m=json.loads(raw,object_pairs_hook=unique_object)
  assert set(entries)=={prefix+n for n in m['files']}|{mn},'full manifest coverage required'
  for n,item in m['files'].items():
   data=z.read(prefix+n);assert sha(data)==item['sha256'] and len(data)==item['bytes'],n
  root.mkdir(parents=True)
  for n in entries:
   target=root/n.removeprefix(prefix);assert target.resolve().is_relative_to(root)
   target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(n))
 a.receipt.parent.mkdir(parents=True,exist_ok=True)
 result=dict(status='PASS',archive=a.archive.name,archive_sha256=a.sha256,manifest_sha256=sha(raw),schema=m.get('schema'),payloads=len(m['files']),full_manifest_coverage=True,game2_images_opened=0,game2_inference_runs=0,training_executed=False,hardware_used=False,production_ready=False)
 a.receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('SEALED_DELIVERY_INTAKE_PASS',a.archive.name,len(m['files']))
if __name__=='__main__':main()
