"""Prepare an exact-CID, backed-up frozen-ROM xqboot entry update."""
from pathlib import Path
import argparse,json,struct
from picture_workspace import ROOT,workspace_path
from prepare_xinyi_cpu60_kit import identity,require


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ['candidate','original-installer','inventory','original-entry','program-receipt','output']:
        ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();out=workspace_path(a.output);require(not out.exists(),'Fresh output required')
    inputs={}
    def read(p):
        p=p.resolve();data=p.read_bytes();inputs[str(p)]=identity(data);return data
    read(Path(__file__));m=json.loads(read(a.candidate/'manifest.json'))
    inventory=json.loads(read(a.inventory));program=json.loads(read(a.program_receipt))
    require(inventory['status']=='PASS_READ_ONLY_COMPLETE_ORIGINAL_EXPORTED','Complete read-only backup required')
    require(program['status']=='PASS' and program['operation']=='CRAM' and program['audit_profile']=='PublishedE42'
        and program['device_count']==1 and program['bitstream_sha256']==m['target_bitstream_sha256'],'Fresh exact E42 receipt required')
    require(inventory['sectors']==62333952 and inventory['partition']==32 and inventory['cluster_bytes']==32768,'Exact tested media geometry required')
    for name in ['PN04SBI.BIN','PN04FS.BIN','PN04NN.PFF','PN04ATK.BIN','PN08K.BIN']:
        v=m['full_sd_files'][name];require(all(inventory['files'][name][k]==v[k] for k in ['bytes','crc32']),'Existing SD payload mismatch: '+name)
    original=read(a.original_entry);old=inventory['files']['xiangqi.bin']
    require(identity(original)['sha256']==inventory['original_sha256'] and len(original)==old['bytes']
        and identity(original)['crc32']==old['crc32'],'Original backup mismatch')
    require(inventory['files']['xqmodel.bin']==dict(bytes=207792,crc32='51f2d900'),'Frozen ROM compatibility model mismatch')
    loader=read(a.candidate/'sd-update/PN15BOOT.BIN')
    require(len(loader)%4==0 and len(loader)<=min(32768,len(original)),'Loader prefix bounds')
    patched=loader+original[len(loader):]
    out.mkdir(parents=True);support=out/'support';support.mkdir()
    for name in ['start.S','link.ld','runtime.c','sd_native.c','fat_ro.c','crc32_fast.c','console_line.c',
                 'soc.h','sd.h','fat_ro.h','crc32_fast.h','console_line.h','camera.h','target.h','fat_camera.c','fat_camera.h']:
        (support/name).write_bytes(read(a.original_installer/'support'/name))
    for name in ['fat_boot_prefix.c','fat_boot_prefix.h']:
        (support/name).write_bytes(read(ROOT/'linux/boot/v2_1_sd/source/picture_fat_write'/name))
    source=read(ROOT/'linux/boot/v2_1_sd/source/install_sd_console.c').decode()
    source=source.replace('#include "picture_console_boot.h"','#include "picture_console_boot.h"\n#include "target.h"\n#include "camera.h"')
    at=source.index('static int mount(void)')
    target='''static int exact_target(void)
{
 return REG32(SYS_BASE)==SYS_ID_VALUE && REG32(CPU_HZ_REG)==60000000u &&
 REG32(SYS_HZ_REG)==49500000u && REG32(TIMEBASE_HZ_REG)==49500000u &&
 REG32(0x1fe1006cu)==XINYI_REQUIRE_EXACT_VERSION &&
 !((REG32(0x1fe1000cu)|REG32(0x1fe10044u)|REG32(0x1fe1010cu)|REG32(0x1fe1018cu)|REG32(0x1fe1008cu))&1u) &&
 !(REG32(CAMERA_BASE+CAMERA_REG_CONTROL)&CAMERA_CONTROL_ENABLE) &&
 (REG32(CAMERA_BASE+CAMERA_REG_STATUS)&112u)==CAMERA_STATUS_IDLE &&
 (crc32_fast(0xffffffffu,(const void *)XINYI_ROM_CODE_START,XINYI_ROM_CODE_BYTES)^0xffffffffu)==XINYI_ROM_CODE_CRC;
}
'''
    source=source[:at]+target+source[at:]
    source=source.replace('const sd_card_info_t *info;int r;start=','const sd_card_info_t *info;int r;if(!exact_target())return FC_CORRUPT;start=')
    begin=source.index('static int ensure_model(void)');end=source.index('static int install(void)',begin)
    source=source[:begin]+'''static int ensure_model(void)
{
 fat_ro_file_t file;int r=load("xqmodel.bin",&file,0x0f000000u,207792u);if(r)return r;
 if(crc((const void *)0x0f000000u,file.size)!=0x51f2d900u)return FC_CORRUPT;
 console_puts("SD_CONSOLE_ROM_MODEL_PASS crc=0x51f2d900\\n");return 0;
}
'''+source[end:]
    source=source.replace('42648u','CONSOLE_ORIGINAL_BYTES')
    source=source.replace('original=crc(image,file.size);boot_crc=',
        'original=crc(image,file.size);if(original!=CONSOLE_ORIGINAL_CRC)return FC_CORRUPT;boot_crc=')
    begin=source.index('static int restore(');end=source.index('static int equal(',begin)
    source=source[:begin]+'''static int restore(uint32_t expected)
{
 fat_ro_file_t backup,file;int r=mount();if(r)return r;
 if(expected!=CONSOLE_ORIGINAL_CRC)return FC_CORRUPT;
 r=load(CONSOLE_BACKUP_NAME,&backup,0x04000000u,CONSOLE_ORIGINAL_BYTES);if(r)return r;
 if(crc((const void *)0x04000000u,backup.size)!=expected)return FC_CORRUPT;
 r=fat_ro_find(&card.volume,"xiangqi.bin",&file);if(r||file.size!=backup.size)return FC_CORRUPT;
 r=replace("xiangqi.bin",&file,(const uint8_t *)0x04000000u,expected);if(r)return r;
 console_puts("SD_CONSOLE_RESTORE_PASS\\n");return 0;
}
'''+source[end:]
    source=source.replace('restore[-mmode]','restore')
    source='\n'.join(line for line in source.splitlines() if 'else if(!memcmp(line,"restore-mmode ' not in line)+'\n'
    source=source.replace('restore(value,0)','restore(value)')
    require('Image.mmode' not in source and 'restore-mmode' not in source,'Entry updater must only patch Xiangqi alias')
    (support/'install_sd_console.c').write_text(source,newline='\n')
    header='/* Fresh read-only inventory, exact backup and PN15 loader. */\n'
    for k,v in dict(CONSOLE_BACKUP_NAME='U15XOLD.BIN',CONSOLE_LOADER_NAME='U15XBOOT.BIN',
                    CONSOLE_BACKUP_SHORT='U15XOLD BIN',CONSOLE_LOADER_SHORT='U15XBOOTBIN').items():header+=f'#define {k} "{v}"\n'
    cid=inventory['cid'];require(len(cid)==32,'CID width')
    header+='#define CONSOLE_CARD_CID {'+','.join('0x'+cid[i:i+8]+'u' for i in range(0,32,8))+'}\n'
    header+=f'#define CONSOLE_BOOT_BYTES {len(loader)}u\n#define CONSOLE_ORIGINAL_BYTES {len(original)}u\n#define CONSOLE_ORIGINAL_CRC 0x{old["crc32"]}u\n'
    words=struct.unpack('<%dI'%(len(loader)//4),loader)
    header+='static const uint32_t console_boot[]={\n'+'\n'.join(','.join('0x%08xu'%v for v in words[i:i+8])+',' for i in range(0,len(words),8))+'\n};\n'
    (support/'picture_console_boot.h').write_text(header,newline='\n')
    (out/'expected-patched-xiangqi.bin').write_bytes(patched)
    for p in sorted(support.iterdir()):read(p)
    require(all(identity(Path(n).read_bytes())==v for n,v in inputs.items()),'Inputs drifted')
    record=dict(status='EXACT_CARD_ENTRY_PREPARED_NOT_INSTALLED',cid=cid,original=identity(original),
        expected_patched=identity(patched),loader=identity(loader),backup_name='U15XOLD.BIN',loader_name='U15XBOOT.BIN',
        bitstream_sha256=m['target_bitstream_sha256'],source_inputs=inputs,sd_written=False,flash_written=False,
        only_existing_file_modified='xiangqi.bin prefix',original_tail_preserved=True)
    (out/'entry_contract.json').write_text(json.dumps(record,indent=2)+'\n')
    print('EXACT_CID_ORIGINAL_CRC_BOUND_ENTRY_PREPARED')


if __name__=='__main__':main()
