"""Wait for the exact physical run, then validate/write the paired SD candidate."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,subprocess,sys,time
R=Path(__file__).resolve().parents[1];N=Path('G:/i60pnr4')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--write-sd',action='store_true');a=ap.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    record=dict(status='WAITING_FOR_NATIVE4',owner_pid=os.getpid(),started_utc=datetime.now(timezone.utc).isoformat(),actions=[],flash_written=False,formal_delivery=False)
    def save(): (out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    def run(name,cmd,timeout):
        record.update(status=name,updated_utc=datetime.now(timezone.utc).isoformat());save();print(name,flush=True)
        with (out/(name+'.log')).open('xb') as log:
            p=subprocess.run(cmd,cwd=R,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
        record['actions'].append(dict(name=name,command=cmd,exit=p.returncode,log_sha256=sha(out/(name+'.log'))));save()
        assert p.returncode==0,(name,str(out/(name+'.log')))
    try:
        save();deadline=time.monotonic()+3600;last_notice=0
        while True:
            launch=read(N/'physical-launch.json')
            assert launch['source_commit']=='e8d666add46987aec84778890b4aacda74ca6586'
            if launch['status']!='BUILDING':break
            assert time.monotonic()<deadline,'Native wait limit; leave running physical owner unchanged'
            if time.monotonic()-last_notice>=45:
                log=N/'pds/input-snapshots/dc951f8b1b7f4cf9962e5f509f165d0f/pds.stdout.log'
                if log.exists():print('NATIVE4_ACTIVE '+log.read_text(errors='replace').splitlines()[-1],flush=True)
                last_notice=time.monotonic()
            time.sleep(5)
        assert launch['status']=='ROUTED_FULL_STA_PASS_NOT_BOARD',launch
        py=sys.executable
        run('COLLECT_NATIVE',[py,'-X','utf8','scripts/collect_integrated60_linefix.py'],180)
        prepared=R/'build/integrated-sd-prepared-05';kit=R/'build/integrated-sd-kit-05'
        run('PREPARE_SD',[py,'-X','utf8','scripts/linux/prepare_integrated60_boot.py',
            '--backup','build/integrated-sd-backup-01','--assets','build/integrated-real-timing-assets-02',
            '--bench','build/integrated-picture-bench-01','--timeout-tool','build/integrated-timeout-01/timeout',
            '--voice-runtime','build/voice-stream-rv32-build-02','--candidate','artifacts/integrated60_linefix_20261024','--output',str(prepared)],180)
        run('LOADER18',[py,'-X','utf8','scripts/linux/assemble_audio_service_sd.py','--base-kit',str(prepared),
            '--kernel','build/integrated-kernel-02','--output',str(kit),'--integrated60','--local-oracle'],900)
        run('ROOTFS_EXTRACT',[py,'-X','utf8','scripts/test_integrated60_rootfs.py','--rootfs',str(kit/'sd-root/rootfs.cpio'),'--output','build/integrated-rootfs-extract-05'],180)
        if a.write_sd:
            # The card already returned by the user must still be that exact
            # FAT32 USB volume, containing all8 expected SD04 files.
            backup=R/'build/voice-stream-sd-before-write-01/manifest.json';identity=read(backup)
            ps='powershell.exe';base=[ps,'-NoProfile','-ExecutionPolicy','Bypass']
            guard="if((Get-Volume -DriveLetter E).UniqueId -cne '"+identity['volume']+"'){throw 'Returned SD volume changed'}"
            run('MEDIA_IDENTITY',base+['-Command',guard],30)
            for name,h in identity['files'].items():assert sha(Path('E:/')/name)==h,name
            deploy=base+['-File','scripts/deploy_cpu80_conv_sd.ps1','-Integrated60LineFix','-KitRoot',str(kit),'-Destination','E:/','-BackupRoot',str(R/'build/integrated-sd-write-05')]
            run('SD_READ_ONLY_PLAN',deploy,90)
            run('SD_WRITE_READBACK',deploy+['-Apply'],180)
            receipts=list((R/'build/integrated-sd-write-05').glob('*/write-result.json'));assert len(receipts)==1
            receipt=read(receipts[0]);assert receipt['Status']=='SD_FILES_WRITTEN_READBACK_HASH_PASS_BOARD_PENDING'
            assert receipt['ManifestSHA256'].lower()==sha(kit/'manifest.json')
            record.update(status='JOINT60_SD_WRITTEN_READBACK_PASS_RETURN_CARD_REQUIRED',write_receipt=str(receipts[0]),write_receipt_sha256=sha(receipts[0]))
        else:record['status']='JOINT60_SD_PREPARED_NOT_WRITTEN'
        record.update(candidate_manifest_sha256=sha(R/'artifacts/integrated60_linefix_20261024/manifest.json'),sd_manifest_sha256=sha(kit/'manifest.json'))
    except Exception as e:record.update(status='FAILED_PRESERVED_NO_BOARD_PROMOTION',error=repr(e));raise
    finally:record['updated_utc']=datetime.now(timezone.utc).isoformat();save();print(record['status'],flush=True)

if __name__=='__main__':main()
