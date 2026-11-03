"""Deploy only nine named files to the user-selected, identity-checked E card."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,subprocess
from workspace_paths import workspace_path
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
NAMES={'Image','Image.mmode','fw_jump.bin','rootfs.cpio','soc.dtb','mmode.dtb','pikafish.pff','pikafish.atk'}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--kit',type=Path,required=True);ap.add_argument('--backup',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--volume-id',required=True)
    a=ap.parse_args();kit=workspace_path(a.kit);out=workspace_path(a.output);assert not out.exists();out.mkdir(parents=True)
    info_cmd=['powershell.exe','-NoProfile','-Command',"$ErrorActionPreference='Stop'; $v=Get-Volume -DriveLetter E; $d=Get-Partition -DriveLetter E | Get-Disk; [ordered]@{volume=$v.UniqueId;filesystem=$v.FileSystem;bytes=$v.Size;disk=$d.Number;bus=[string]$d.BusType;device_bytes=$d.Size}|ConvertTo-Json -Compress"]
    q=subprocess.run(info_cmd,capture_output=True,timeout=30);assert q.returncode==0,q.stderr
    info=json.loads(q.stdout.decode('utf-8-sig'));assert a.volume_id.lower() in info['volume'].lower()
    assert info['filesystem']=='FAT32' and info['bus']=='USB' and info['disk']==2
    assert 31_000_000_000<info['device_bytes']<33_000_000_000
    manifest=read(kit/'manifest.json');backup=read(a.backup/'manifest.json')
    assert manifest['status']=='MAIN_FREQUENCY_RUNTIME_18_OFFLINE_TESTS_PASS_BOARD_PENDING'
    assert manifest['cpu_hz']==70000000 and manifest['sbi_ratio']==[99,140] and len(manifest['tests'])==18
    assert manifest['gui_coremark_has_observed_program_receipt'] and manifest['program_assignment_receipt_sha256']
    assert set(manifest['sd_root_files'])==NAMES
    assert backup['status']=='SD_E_PREWRITE_ROOT_MANIFEST_AND_REPLACED_FILES_BACKUP_READBACK_PASS'
    assert backup['volume_id'].lower()==a.volume_id.lower()
    card=Path('E:/');targets=NAMES|{'SHA256SUMS.txt'}
    for row in backup['files']:
        assert sha(card/row['name'])==row['sha256'],'Card changed since backup: '+row['name']
        if row['replaced']:assert sha(Path(row['backup']))==row['sha256']
    for name,row in manifest['sd_root_files'].items():assert sha(kit/'sd-root'/name)==row['sha256']
    record=dict(status='WRITING_SD_E',started_utc=datetime.now(timezone.utc).isoformat(),volume=info,kit_manifest_sha256=sha(kit/'manifest.json'),backup_manifest_sha256=sha(a.backup/'manifest.json'),files=[],flash_written=False,card_formatted=False)
    def save():(out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    save()
    try:
        for name in sorted(targets):
            source=kit/'sd-root'/name;target=card/name;h=sha(source)
            with source.open('rb') as src,target.open('wb') as dst:
                while True:
                    chunk=src.read(1024*1024)
                    if not chunk:break
                    dst.write(chunk)
                dst.flush();os.fsync(dst.fileno())
            assert sha(target)==h,name
            record['files'].append(dict(name=name,bytes=source.stat().st_size,sha256=h,readback_sha256=sha(target)));save()
        flush=subprocess.run(['powershell.exe','-NoProfile','-Command',"$ErrorActionPreference='Stop'; Write-VolumeCache -DriveLetter E; Write-Output CACHE_FLUSH_PASS"],capture_output=True,timeout=60)
        (out/'volume-flush.log').write_bytes(flush.stdout+flush.stderr)
        assert flush.returncode==0 and b'CACHE_FLUSH_PASS' in flush.stdout,'Volume cache flush failed'
        for row in record['files']:assert sha(card/row['name'])==row['sha256']
        for row in backup['files']:
            if row['name'] not in targets:assert sha(card/row['name'])==row['sha256'],'Unrelated root file changed: '+row['name']
        assert sorted(p.name for p in card.iterdir() if p.is_dir())==sorted(backup['untouched_user_directories'])
        record.update(status='MAIN70_SD8_AND_HASH_MANIFEST_WRITE_VOLUME_FLUSH_READBACK_PASS',unrelated_root_files_unchanged=len(backup['files'])-len(targets),user_directories_preserved=True,ready_for_safe_removal=True)
    except Exception as e:
        record.update(status='SD_E_WRITE_INCOMPLETE_PRESERVED',error=repr(e));raise
    finally:record['completed_utc']=datetime.now(timezone.utc).isoformat();save()
    print(record['status'])

if __name__=='__main__':main()
