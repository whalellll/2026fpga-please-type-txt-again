"""Bind SD migration, post-install boot and focused tests to exact inputs."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
from sd_namespace import REPO, E8, sha, verify_compiled_loader

WORK=REPO/'build/picture-p21-native/sd-namespace-r01'
DEST=REPO/'docs/validation/picture-sd-namespace-20261020'

def read(path):
    raw=path.read_bytes()
    return raw.decode('utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')

def main():
    assert not DEST.exists(),'Use a fresh immutable evidence directory'
    plan=json.loads((WORK/'namespace-install-plan.json').read_text())
    contract=json.loads((WORK/'sd_contract.json').read_text())
    receipt=json.loads((WORK/'migration-r01.log.json').read_text())
    cram=json.loads((WORK/'cram-r01.json').read_text(encoding='utf-8-sig'))
    assert cram['status']=='PASS' and cram['device_count']==1 and cram['bitstream_sha256']==E8
    assert receipt['status']=='PASS' and receipt['boot_from_sd_menu']
    assert receipt['cid']==plan['expected_cid'] and not receipt['flash_written']
    log=read(WORK/'migration-r01.log')
    written=re.findall(r'^NS_READBACK_CRC_PASS name=(\S+) bytes=(\d+) crc=0x([0-9a-f]{8})',log,re.M)
    assert len(written)==10 and {row[0] for row in written}==set(plan['new_files'])
    for item in plan['source_files_and_private_copies']:
        assert (item['name'],str(item['bytes']),item['crc32']) in written
    assert len(re.findall(r'^NS_PAIR_COMMITTED ',log,re.M))==5
    assert f'NS_SHARED_MENU_ENTRY_PASS bytes=20468 crc=0x{plan["new_entry"]["crc32"]}' in log
    assert 'NS_INSTALL_PASS startup=SD_MENU uart_upload_each_boot=0 flash_written=0' in log
    boot=log.split('soc> xqboot',1)[1]
    assert 'loadx ' not in boot and 'XQ_BOOT_MENU_BEGIN sd_only=1' in boot
    assert '1 Picture_new [PN01BOOT.BIN]' in boot and '2 Native_previous [PN00BOOT.BIN]' in boot
    assert 'XQ_BOOT_MENU_PAYLOAD_PASS name=PN01BOOT.BIN' in boot
    assert 'XQ LINUX PIKAFISH READY' in boot
    binary,descriptors=verify_compiled_loader(WORK,contract)
    for name,item in descriptors.items():
        pattern='Loading '+re.escape(name)+' bytes='+str(item['bytes'])+r'[\s\S]*?CRC32=0x'+item['crc32']
        assert re.search(pattern,boot),name
    health=read(WORK/'post-boot-health-verified.log')
    assert 'XQ_NATIVE_READY models=3 backend=rv32-driver-quantized-mac' in health
    assert 'NS_GUI_AND_THREE_MODELS_READY' in health and 'XQ_ADAPTER_DONE=0' in health
    earlier=json.loads((REPO/'docs/validation/picture-native-sd-20261020/boot-r03/result.json').read_text())
    for path,digest in earlier['runtime_sha256'].items():assert digest+'  '+path in health,path
    tests=read(WORK/'host-installer-final.log')
    assert 'SD_NAMESPACE_FAT32_INSTALL_PASS' in tests and 'write_fault_cases=450' in tests
    assert 'OK' in read(WORK/'host-namespace-final.log')
    assert 'negative_cases=14' in read(WORK/'host-menu-final.log')
    compatibility=REPO/'build/picture-p21-native/sd-namespace-compat-r01/loader-picture-candidate.bin'
    assert sha(compatibility)==plan['original_entry']['sha256']
    regression_path=REPO/'docs/validation/picture-p21-runtime-20261020/regression-r06.json'
    regression=json.loads(regression_path.read_text());assert regression['status']=='PASS'
    groups={}
    for group in ('source_files_sha256','test_files_sha256','linux_files_sha256'):
        for path,digest in regression[group].items():assert sha(REPO/path)==digest,path
        groups[group]=len(regression[group])
    source_names=['sd_namespace.py','prepare_native_sd_namespace.py','prepare_sd_namespace_install.py',
                  'build_sd_namespace_tools.ps1','serial_install_sd_namespace.ps1','boot_sd_namespace.ps1',
                  'test_sd_namespace.py','archive_sd_namespace.py','package_sd_namespace.py','complete_sd_namespace_health.py',
                  'runtime/xq_boot_menu.h','runtime/xq_boot_menu.c',
                  'runtime/xq_boot_menu_contract.c','runtime/xq_boot_menu_start.S','runtime/xq_boot_menu.ld',
                  'runtime/xq_boot_strings.c','runtime/xq_sd_namespace_install.c','runtime/xq_sd_namespace_fat.c',
                  'runtime/test_boot_menu.c','runtime/test_sd_namespace_install.c']
    adapter=Path(__file__).resolve().parent
    sources={str((adapter/name).relative_to(REPO)).replace('\\','/'):sha(adapter/name) for name in source_names}
    for name in ('linux/boot/v2_1_sd/source/loader.c','sw/bootloader/fat_camera.c',
                 'sw/bootloader/fat_boot_prefix.c','sw/bootloader/fat_ro.c','scripts/build_picture_loader.ps1'):
        sources[name]=sha(REPO/name)
    result=dict(schema_version=1,status='SD_NAMESPACE_AND_RESIDENT_MENU_BOOT_PASS',
                recorded_utc=datetime.now(timezone.utc).isoformat(),prefix='PN01',
                cid=receipt['cid'],media_sectors=62333952,partition_lba=32,
                new_files_verified=10,committed_pairs=5,
                copied_existing_large_payloads_on_card=True,one_time_installer_uart_bytes=(WORK/'xq-sd-namespace-install.bin').stat().st_size,
                recurring_uart_file_upload=False,boot_method='soc> xqboot -> SD menu -> PN01BOOT.BIN -> six private SD files',
                boot_from_sd_menu=True,compiled_six_payload_descriptors=descriptors,
                private_loader_sha256=sha(binary),menu_sha256=plan['embedded']['menu']['sha256'],
                shared_rom_files_preserved=['xqmodel.bin'],shared_entry='xiangqi.bin',
                entry_size_and_chain_preserved=True,entry_tail_preserved=True,
                original_entry_backup='PN00BOOT.BIN',backup_crc32=plan['original_entry']['crc32'],
                previous_profile_registered=True,previous_profile_separately_booted=False,
                previous_loader_binary_compatibility_bit_exact=True,
                native_worker_ready=True,model_count=3,runtime_sha256=earlier['runtime_sha256'],
                kernel_and_rootfs_bytes_unchanged=True,camera_retry_attempts=2,
                camera_retry_root_cause_fixed=False,full_regression_inputs=groups,
                regression_receipt_sha256=sha(regression_path),focused_write_fault_cases=450,
                focused_parser_negative_cases=14,real_selector_relocation_emulated=True,
                flash_written=False,rtl_changed=False,hardware_rebuilt=False,
                volatile_cram_sha256=E8,power_cycle_persistence_tested=False,
                model_accuracy_accepted=False,latency_accepted=False,full_games_accepted=False,
                source_sha256=sources)
    DEST.mkdir()
    for name in ('migration-r01.log','migration-r01.log.json','migration-r01.log.load.log',
                 'cram-r01.json','cram-r01.log','cram-r01.preflight.log','cram-r01-uart.log',
                 'namespace-install-plan.json','XQBOOT.CFG','post-boot-health-r01.log','post-boot-health-r02.log',
                 'post-boot-health-verified.log','post-boot-health-collection.json',
                 'host-installer-final.log','host-namespace-final.log','host-menu-final.log'):
        shutil.copyfile(WORK/name,DEST/name)
    result['evidence_sha256']={path.name:sha(path) for path in DEST.iterdir()}
    (DEST/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('SD_NAMESPACE_AND_RESIDENT_MENU_BOOT_PASS files=10 recurring_uart_file_upload=0 runtime_hashes=5')

if __name__=='__main__':main()
