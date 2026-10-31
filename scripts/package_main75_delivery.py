"""Seal CPU75 only after verified main publication, then independently extract.

The external seal receipt remains incomplete until extracted full regression,
SD8 reread, direct SD boot and application checks are bound to this ZIP hash.
"""
from pathlib import Path,PurePosixPath
from datetime import datetime,timezone
from zipfile import ZipFile,ZipInfo,ZIP_DEFLATED
import argparse,json,shutil,stat,subprocess,sys
from workspace_paths import workspace_path
from verify_main75_release import validate,RUN,BIT
from verify_main75_delivery import verify
from verify_board_release import need,sha,read,safe

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ['root','zip','extract','receipt']:ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--host-gcc',default='G:/fpga/workspace/tools/msys64/mingw64/bin/gcc.exe')
    a=ap.parse_args();root,output,extract=map(workspace_path,[a.root,a.zip,a.extract])
    receipt=workspace_path(a.receipt);part=output.with_suffix('.part')
    need(not output.exists() and not part.exists() and not receipt.exists(),'Preserve previous package attempts')
    need(not extract.exists() or not any(extract.iterdir()),'Choose a fresh empty extraction directory')
    publication=read(root/'MAIN75_PUBLICATION.json')
    need(publication['status']=='CPU_AND_SOC_MAIN_PUSH_REMOTE_READBACK_AND_ARTIFACT_HASHES_PASS','Main publication not verified')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    remote=subprocess.check_output(['git','ls-remote','origin','refs/heads/main'],cwd=root,text=True).split()[0]
    need(head==remote==publication['soc_commit'],'Package source is not published main')
    proof=validate(root,root/'MAIN75_RELEASE.json',a.host_gcc)
    subprocess.run([sys.executable,'-B',str(root/'skills/manage.py'),'verify-delivery','--package',str(root)],check=True)
    subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(root/'scripts/audit_main75_delivery.ps1'),'-Root',str(root),'-CheckHashes'],check=True)
    inventory=root/'build/main75-package-inventory.json';need(not inventory.exists(),'Preserve previous inventory')
    subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(root/'scripts/main75_delivery_inventory.ps1'),'-Root',str(root),'-Output',str(inventory)],check=True)
    names=read(inventory);need(len(names)==len(set(x.casefold() for x in names)),'Duplicate package paths')
    files={name:sha(safe(root,name)) for name in names}
    manifest=root/'MAIN75_DELIVERY.json';need(not manifest.exists(),'Never rewrite a sealed manifest')
    record=dict(schema=1,status='MAIN75_PUBLISHED_IMPLEMENTATION_PACKAGE_FINAL_MEDIA_PENDING',
        created_utc=datetime.now(timezone.utc).isoformat(),run_id=RUN,bitstream_sha256=BIT,
        publication=publication,files_sha256=files,formal_delivery_complete=False,flash_written=False,
        completion='External ZIP-hash-bound receipt must include independent full regression, SD8 readback and direct SD boot/apps.',
        limitations=proof['limitations'])
    manifest.write_text(json.dumps(record,indent=2)+'\n')
    output.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(part,'w',compression=ZIP_DEFLATED,compresslevel=6) as archive:
        for name in sorted([*files,'MAIN75_DELIVERY.json']):
            path=safe(root,name);info=ZipInfo('SOC/'+name,date_time=(1980,1,1,0,0,0))
            info.compress_type=ZIP_DEFLATED;info.external_attr=0o644<<16
            with path.open('rb') as src,archive.open(info,'w',force_zip64=True) as dst:shutil.copyfileobj(src,dst,1024*1024)
            if name in files:need(sha(path)==files[name],'Source changed while sealing '+name)
    with ZipFile(part) as archive:
        paths=archive.namelist();need(len(paths)==len(set(paths))==len(files)+1,'ZIP entry count differs')
        for item in archive.infolist():
            path=PurePosixPath(item.filename)
            need(item.filename.startswith('SOC/') and '\\' not in item.filename and ':' not in item.filename and
                 '..' not in path.parts and not stat.S_ISLNK(item.external_attr>>16),'Unsafe ZIP entry')
        need(archive.testzip() is None,'ZIP CRC failed')
    part.replace(output)
    extract.mkdir(parents=True,exist_ok=True)
    with ZipFile(output) as archive:archive.extractall(extract)
    package=extract/'SOC';actual={p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file()}
    need(actual==set(files)|{'MAIN75_DELIVERY.json'},'Extracted file set differs')
    result=verify(package,a.host_gcc)
    final=dict(status='MAIN75_ZIP_EXTRACTION_CONTENT_PASS_FULL_REGRESSION_AND_FINAL_MEDIA_PENDING',
        zip=str(output),zip_sha256=sha(output),zip_bytes=output.stat().st_size,extraction=str(package),
        extracted_files=len(actual),independent_content=result,formal_delivery_complete=False,
        full_regression=False,final_media=False,publication=publication)
    receipt.write_text(json.dumps(final,indent=2)+'\n');print(json.dumps(final))

if __name__=='__main__':main()
