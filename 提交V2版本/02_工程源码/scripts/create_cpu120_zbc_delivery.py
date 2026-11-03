"""Create an accepted CPU120 release only after verified main publication."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,subprocess,sys,tarfile,zipfile,shutil,tempfile,os
from verify_cpu120_zbc_board_release import verify,sha,read,BIT,RUN,CPU,IMPL
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--output',type=Path,required=True);p.add_argument('--publication',type=Path,required=True);p.add_argument('--cpu-repository',type=Path,required=True);p.add_argument('--host-gcc',required=True);a=p.parse_args()
 root=a.root.resolve();out=a.output.resolve();assert not out.exists() and out.suffix.lower()=='.zip'
 out.parent.mkdir(parents=True,exist_ok=True);pub=read(a.publication);assert pub['status']=='CPU_AND_SOC_MAIN_PUSH_READBACK_PASS' and pub['bitstream_sha256']==BIT and pub['native_run']==RUN
 def git(repo,*args):return subprocess.run(['git','-C',str(repo),*args],capture_output=True,check=True).stdout.decode().strip()
 assert git(root,'rev-parse','HEAD')==pub['soc_commit']
 assert not git(root,'diff','--name-only','HEAD')
 assert git(a.cpu_repository,'rev-parse','HEAD')==pub['cpu_commit']
 audit=out.parent/(out.stem+'-creation-checks');assert not audit.exists();audit.mkdir()
 verify(root,'docs/validation/cpu120-zbc-fc1-20261101/release-manifest.json',audit/'board-source',a.host_gcc)
 subprocess.run([sys.executable,'-B',str(root/'skills/manage.py'),'verify-delivery','--package',str(root)],check=True)
 subprocess.run([sys.executable,'-B',str(root/'scripts/update_project_index.py'),'--project-root',str(root),'--check'],check=True)
 names=git(root,'ls-files','-z').split('\0');names=[x for x in names if x]
 assert len(names)>1000 and len(names)==len(set(names))
 # Global *.log ignores must not silently drop raw accepted evidence.
 exported=read(root/'docs/validation/cpu120-zbc-fc1-20261101/source-export-index.json')
 required={x['path'] for x in exported['source_exports']}|{x['path'] for x in exported['compressed_native_logs']}
 assert required<=set(names),sorted(required-set(names))
 for directory in ['docs/validation/cpu120-zbc-fc1-20261101','software/cpu120-zbc']:
  for file in (root/directory).rglob('*'):
   if file.is_file():assert file.relative_to(root).as_posix() in names,('Untracked release evidence',str(file))
 files={};part=out.with_suffix('.zip.part');assert not part.exists()
 with zipfile.ZipFile(part,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for name in sorted(names):
   rel=PurePosixPath(name);assert not rel.is_absolute() and '..' not in rel.parts and '.git' not in rel.parts
   file=root.joinpath(*rel.parts)
   if os.name=='nt':file=Path('\\\\?\\'+str(file))
   assert file.is_file() and not file.is_symlink(),name
   data=file.read_bytes();path='SOC/'+rel.as_posix();files[path]=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest());z.writestr(path,data)
  # Exact paired CPU source; historical board archives are retained in Git,
  # while this package exports the complete build/test/generation tree.
  command=['git','-C',str(a.cpu_repository),'archive','--format=tar',pub['cpu_commit'],'VERSION','README.md','AGENTS.md','CHANGELOG.md','cpu']
  proc=subprocess.Popen(command,stdout=subprocess.PIPE)
  with tarfile.open(fileobj=proc.stdout,mode='r|') as archive:
   for member in archive:
    rel=PurePosixPath(member.name)
    if not member.isfile() or rel.parts[:2]==('cpu','handoff'):continue
    assert not rel.is_absolute() and '..' not in rel.parts
    data=archive.extractfile(member).read();path='SOC/CPU_SOURCE/'+rel.as_posix()
    if path in files:
     assert files[path]['sha256']==hashlib.sha256(data).hexdigest();continue
    files[path]=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest());z.writestr(path,data)
  assert proc.wait()==0
  data=json.dumps(pub,indent=2).encode()+b'\n';path='SOC/PUBLICATION.json';files[path]=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest());z.writestr(path,data)
  manifest=dict(schema='PDS25_CPU120_ZBC_FC1_FORMAL_ZIP_V1',status='MAIN_PUBLISHED_PACKAGE_REQUIRES_INDEPENDENT_REGRESSION_AND_MEDIA',soc_commit=pub['soc_commit'],cpu_commit=pub['cpu_commit'],implementation_commit=IMPL,cpu_implementation_commit=CPU,native_run=RUN,bitstream_sha256=BIT,cpu_hz=120000000,sys_hz=49500000,coremark_comparison_required=True,nnue_10ms_goal_met=False,formal_delivery_complete=False,files=files)
  z.writestr('SOC/DELIVERY.json',json.dumps(manifest,indent=2)+'\n')
 part.replace(out)
 with zipfile.ZipFile(out) as z:assert z.testzip() is None
 result=dict(status='CPU120_FORMAL_ZIP_CREATED_INDEPENDENT_REGRESSION_AND_MEDIA_PENDING',path=str(out),sha256=sha(out),bytes=out.stat().st_size,files=len(files)+1,native_run=RUN,bitstream_sha256=BIT)
 out.with_suffix('.zip.creation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if __name__=='__main__':main()
