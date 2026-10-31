"""Seal approved80MHz bytes; completion still requires independent regression/media."""
from pathlib import Path,PurePosixPath
from datetime import datetime,timezone
import argparse,json,shutil,stat
from zipfile import ZipFile,ZipInfo,ZIP_DEFLATED
from verify_cpu80_approved import validate,release_file,sha,need,RUN,BIT,IMAGE,LOADER,CPU

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--root',type=Path,required=True);ap.add_argument('--zip',type=Path,required=True)
ap.add_argument('--extract',type=Path,required=True);ap.add_argument('--receipt',type=Path,required=True)
ap.add_argument('--host-gcc',default='G:/fpga/workspace/tools/msys64/mingw64/bin/gcc.exe')
a=ap.parse_args();root=a.root.resolve();output=a.zip.resolve();extract=a.extract.resolve()
need(not output.exists() and not output.with_suffix('.part').exists() and not extract.exists() and not a.receipt.exists(),'Preserve existing seal/extraction attempts')
proof=validate(root,a.host_gcc,False)
files={p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob('*')) if release_file(root,p)}
record=dict(schema=1,status='USER_APPROVED_BOARD_TESTED_FINAL_PACKAGE_MEDIA_PENDING',created_utc=datetime.now(timezone.utc).isoformat(),
    run_id=RUN,bitstream_sha256=BIT,kernel_sha256=IMAGE,loader_sha256=LOADER,cpu_implementation_commit=CPU,
    soc_hardware_implementation_commit='3433872213649fde70106dda3f18bfd9fd7fcfce',
    software_implementation_commit='71c8c3f2ece3801b1ec6b69289bd2418c2829a7b',
    cpu_hz=80000000,sys_hz=49500000,sd_kit='artifacts/cpu80_audio_service_20261022/sd-kit',
    files_sha256=files,board_evidence='docs/validation/cpu80-audio-service-20261022/board-repair/audiofix-board-binding.json',
    user_approval='docs/validation/cpu80-audio-service-20261022/board-repair/release-approval-20261022.json',
    coremark_total_required=False,coremark_per_mhz_absolute_decrease_limit=.05,
    limitations=['Legacy dense2337.5us vs2327us,0.451% regression disclosed before version approval.',
                'NNUE10ms,full-frame YOLO30fps/accuracy and1080p not accepted.',
                'Existing external I/O delay gaps61/128 remain.'],
    publication='User explicitly requested main push before packaging on2026-10-23; approved implementation pushed and read back at a36730df867c3d4922bffb7bc72a5bba2ca28b81.',
    completion='External ZIP-hash-bound receipt must record independent full regression, card readback and final direct SD boot before declaring formal delivery complete.',
    formal_delivery_complete=False,flash_written=False)
manifest=root/'CPU80_APPROVED_DELIVERY.json'
need(not manifest.exists(),'Never rewrite a sealed manifest')
manifest.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
validate(root,a.host_gcc,True)
part=output.with_suffix('.part');output.parent.mkdir(parents=True,exist_ok=True)
with ZipFile(part,'w',compression=ZIP_DEFLATED,compresslevel=6) as z:
    for name in sorted([*files,manifest.name]):
        p=root/name;need(not p.is_symlink(),'Linked package source')
        info=ZipInfo('SOC/'+name,date_time=(1980,1,1,0,0,0));info.compress_type=ZIP_DEFLATED;info.external_attr=0o644<<16
        with p.open('rb') as source,z.open(info,'w',force_zip64=True) as target:shutil.copyfileobj(source,target,1024*1024)
with ZipFile(part) as z:
    names=z.namelist();need(len(names)==len(set(names))==len(files)+1,'ZIP entry count differs')
    for item in z.infolist():
        parts=PurePosixPath(item.filename)
        need(item.filename.startswith('SOC/') and '\\' not in item.filename and '..' not in parts.parts and
             not stat.S_ISLNK(item.external_attr>>16),'Unsafe ZIP path/type')
    need(z.testzip() is None,'ZIP CRC failure')
part.replace(output)
with ZipFile(output) as z:z.extractall(extract)
independent=validate(extract/'SOC',a.host_gcc,True)
r=dict(status='APPROVED_ZIP_EXTRACTED_CONTENT_PASS_FULL_REGRESSION_AND_MEDIA_PENDING',
    completed_utc=datetime.now(timezone.utc).isoformat(),zip=str(output),zip_sha256=sha(output),zip_bytes=output.stat().st_size,
    extraction=str(extract/'SOC'),files=len(files)+1,preseal=proof,independent_content=independent,
    full_regression=False,final_media=False,remote_pushed=True,
    approved_implementation_main='a36730df867c3d4922bffb7bc72a5bba2ca28b81')
a.receipt.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(r,ensure_ascii=False))
