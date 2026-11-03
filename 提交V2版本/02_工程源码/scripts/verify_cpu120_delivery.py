"""Safely unpack the immutable CPU120 ZIP and run independent regression."""
from pathlib import Path,PurePosixPath
from datetime import datetime,timezone
import argparse,hashlib,json,os,subprocess,sys,zipfile
from verify_cpu120_board_release import verify,sha,BIT,RUN
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--zip',type=Path,required=True);p.add_argument('--extract',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--cpu-cache',type=Path,required=True);p.add_argument('--host-gcc',required=True);p.add_argument('--pds',type=Path,required=True);p.add_argument('--tools',type=Path,default=Path('G:/fpga/workspace/tools'));a=p.parse_args()
 assert not a.extract.exists() and not a.output.exists();a.output.mkdir(parents=True);digest=sha(a.zip)
 record=dict(status='RUNNING_INDEPENDENT_ZIP_VERIFICATION',owner_pid=os.getpid(),started_utc=datetime.now(timezone.utc).isoformat(),archive=str(a.zip.resolve()),archive_sha256=digest,extraction=str(a.extract.resolve()),bitstream_sha256=BIT,native_run=RUN,formal_delivery_complete=False)
 def save():(a.output/'result.json').write_text(json.dumps(record,indent=2)+'\n')
 save()
 try:
  with zipfile.ZipFile(a.zip) as z:
   names=z.namelist();assert len(names)==len(set(n.casefold() for n in names)) and len(names)<20000
   assert sum(x.file_size for x in z.infolist())<10*1024**3
   manifest=json.loads(z.read('SOC/DELIVERY.json'));assert manifest['schema']=='PDS25_CPU120_FORMAL_ZIP_V1' and manifest['bitstream_sha256']==BIT and manifest['native_run']==RUN
   assert set(names)==set(manifest['files'])|{'SOC/DELIVERY.json'}
   for name in names:
    rel=PurePosixPath(name);assert rel.parts[0]=='SOC' and '..' not in rel.parts and '.git' not in rel.parts and '\\' not in name and not rel.is_absolute()
    info=z.getinfo(name);assert (info.external_attr>>16)&0o170000!=0o120000
    raw=z.read(name)
    if name!='SOC/DELIVERY.json':assert len(raw)==manifest['files'][name]['bytes'] and hashlib.sha256(raw).hexdigest()==manifest['files'][name]['sha256'],name
   a.extract.mkdir(parents=True);z.extractall(a.extract)
  root=a.extract/'SOC';record['soc_commit']=manifest['soc_commit'];record['cpu_commit']=manifest['cpu_commit'];record['source_static']=verify(root,'docs/validation/cpu120-20261101/release-manifest.json',a.output/'static-before',a.host_gcc);save()
  env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1');tmp=a.output/'tmp';tmp.mkdir();env.update(TEMP=str(tmp),TMP=str(tmp),TMPDIR=str(tmp))
  def run(name,command,timeout):
   path=a.output/(name+'.log')
   with path.open('xb') as stream:code=subprocess.run(list(map(str,command)),cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=timeout).returncode
   assert code==0,name+' failed: '+str(path)
  run('skills',[sys.executable,'-B',root/'skills/manage.py','verify-delivery','--package',root],300)
  run('index',[sys.executable,'-B',root/'scripts/update_project_index.py','--project-root',root,'--check'],300)
  run('negative-bounds',[sys.executable,'-B',root/'scripts/test_cpu120_delivery_guards.py','--root',root,'--output',a.output/'bounds-negatives'],300)
  run('regression',[sys.executable,'-B',root/'scripts/run_cpu120_package_regression.py','--root',root,'--output',a.output/'regression','--cpu-cache',a.cpu_cache,'--tools',a.tools,'--pds',a.pds],18000)
  for name,info in manifest['files'].items():assert sha(a.extract/name)==info['sha256'],name
  assert sha(a.zip)==digest
  record.update(status='CPU120_ZIP_INDEPENDENT_UNPACK_CPU131_ARCH8_SOC_FC1_38_REGRESSION_PASS_MEDIA_PENDING',completed_utc=datetime.now(timezone.utc).isoformat(),all_packaged_files_unchanged=True,regression_receipt_sha256=sha(a.output/'regression/result.json'));save();print(record['status'],flush=True)
 except Exception as error:record.update(status='FAILED_PRESERVED',error=repr(error));save();raise
if __name__=='__main__':main()
