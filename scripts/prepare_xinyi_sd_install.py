"""Prepare the exact PN03 create-only installer; never access real media."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import zlib

ROOT=Path(__file__).resolve().parents[1]
REF='127ff9a5b517f0f298ab91492d07ef2a1cf44f5b'
BOOT_MANIFEST='b6a7ad13380a0fb3e7d46b86330c1422ff978fc634abf5019b57b9c1fe42bcce'
def identity(data):return dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),crc32=f'{zlib.crc32(data):08x}')
def require(ok,message):
    if not ok:raise ValueError(message)
def prepare(bundle,out,sectors,partition):
    require(not out.exists() and out.resolve().is_relative_to((ROOT/'build').resolve()),'Fresh private build/ output required')
    raw=(bundle/'manifest.json').read_bytes();require(identity(raw)['sha256']==BOOT_MANIFEST,'Expected final-r03 boot candidate')
    manifest=json.loads(raw);inputs={};git_inputs={}
    def read(p):
        p=p.resolve();data=p.read_bytes();inputs[str(p)]=identity(data);return data
    def git(path):
        data=subprocess.check_output(['git','show',REF+':'+path],cwd=ROOT,timeout=30);git_inputs[path]=identity(data);return data
    read(Path(__file__));read(ROOT/'scripts/build_xinyi_sd_install.ps1')
    read(ROOT/'scripts/riscv_toolchain.ps1');read(bundle/'manifest.json')
    snapshot=json.loads(git('docs/validation/integrated60-linefix-functional-trial-20261024-02/build_snapshot.json'))
    support={}
    for name in ['soc.h','sd.h','fat_ro.h','fat_ro.c','runtime.c','sd_native.c','crc32_fast.h','crc32_fast.c','console_line.h','console_line.c','camera.h']:
        path='sw/bootloader/'+name;data=git(path)
        require(identity(data)['sha256']==snapshot['inputs'][path],'Original CPU60 source differs: '+path);support[name]=data
    for name in ['fat_camera.h','fat_camera.c']:
        support[name]=read(ROOT/'linux/boot/v2_1_sd/source/picture_fat_write'/name)
    namespace=read(ROOT/'artifacts/vision-model-20261020-adapter/runtime/xq_sd_namespace_fat.c')
    include=b'#include "../../../linux/boot/v2_1_sd/source/picture_fat_write/fat_camera.c"'
    require(namespace.count(include)==1,'Unknown tested namespace adapter include')
    support['install_fat.c']=namespace.replace(include,b'#include "fat_camera.c"')
    for name in ['install.c','install_xmodem.c','start.S','link.ld']:
        support[name]=read(ROOT/'linux/xinyi_board/boot'/name)
    support['link.ld']=support['link.ld'].replace(b'ORIGIN = 0x01000000',b'ORIGIN = 0x01800000')
    # The target header is itself derived from the SHA-pinned boot candidate.
    rom=git('artifacts/bootloader.bin');code=manifest['runtime_rom_code']
    require(code['start']=='0x1c000000' and code['bytes']==81108 and
            f'{zlib.crc32(rom[:code["bytes"]]):08x}'==code['crc32'],'Unexpected ROM executable interval')
    support['target.h']=(f'#define XINYI_ROM_CODE_START 0x1c000000u\n#define XINYI_ROM_CODE_BYTES {code["bytes"]}u\n'
                         f'#define XINYI_ROM_CODE_CRC 0x{code["crc32"]}u\n').encode()
    table=[
      ('PN03SBI.BIN',0x18000000,['PN02SBI.BIN','PN01SBI.BIN','fw_jump.bin']),
      ('PN03K.BIN',0x00400000,['PN02K.BIN','PN01K.BIN','Image']),
      ('PN03FS.BIN',0x03000000,['PN02FS.BIN','PN01FS.BIN','rootfs.cpio']),
      ('PN03.DTB',0x1a000000,['PN02.DTB','PN01.DTB','soc.dtb']),
      ('PN03NN.PFF',0x10000000,['PN02NN.PFF','PN01NN.PFF','pikafish.pff']),
      ('PN03ATK.BIN',0x15000000,['PN02ATK.BIN','PN01ATK.BIN','pikafish.atk']),
      ('PN03BOOT.BIN',0x01400000,[]),('PN03.JSN',0x01600000,[])]
    payloads={};records=[]
    for name,address,aliases in table:
        data=read(bundle/'payloads'/name) if name!='PN03.JSN' else raw
        if name!='PN03.JSN':require(identity(data)==manifest['files'][name],'Final payload identity mismatch: '+name)
        require(address%4==0 and len(data)>0,'Unaligned payload')
        payloads[name]=data;records.append(dict(name=name,address=address,aliases=aliases,**identity(data)))
    header='#include <stdint.h>\n'
    for i,p in enumerate(records):
        data=payloads[p['name']]
        header+=f'static const uint32_t slice_crc_{i}[]={{'+','.join(f'0x{zlib.crc32(data[n:n+65536]):08x}u' for n in range(0,len(data),65536))+'};\n'
    header+=('typedef struct {const char *name,*short_name;uint32_t address,bytes,crc;'
             'const char *aliases[4];int ready,exists;const uint32_t *slice_crc;uint32_t offset;} item_t;\nstatic item_t items[]={\n')
    for i,p in enumerate(records):
        stem,ext=p['name'].split('.');short=stem.ljust(8)+ext.ljust(3)
        aliases=','.join('"'+n+'"' for n in p['aliases'])+(',' if p['aliases'] else '')+'0'
        header+=f' {{"{p["name"]}","{short}",0x{p["address"]:08x}u,{p["bytes"]}u,0x{p["crc32"]}u,{{{aliases}}},0,0,slice_crc_{i},0}},\n'
    header+=f'}};\n#define INSTALL_COUNT 8u\n#define INSTALL_BOOT_INDEX 6u\n#define INSTALL_SECTORS {sectors}u\n#define INSTALL_PARTITION {partition}u\n'
    support['install_payloads.h']=header.encode('ascii')
    for path,value in inputs.items():require(identity(Path(path).read_bytes())==value,'Source changed: '+path)
    out.mkdir(parents=True);(out/'support').mkdir();(out/'payloads').mkdir()
    for name,data in support.items():(out/'support'/name).write_bytes(data)
    for name,data in payloads.items():(out/'payloads'/name).write_bytes(data)
    contract=dict(status='CPU60_PN03_INSTALL_INPUTS_PREPARED_NOT_INSTALLED',source_ref=REF,
        bundle_manifest_sha256=BOOT_MANIFEST,bitstream_sha256=manifest['target_bitstream_sha256'],
        media_sectors=sectors,partition_lba=partition,cluster_bytes=32768,files=records,source_inputs=inputs,git_inputs=git_inputs,
        existing_files_preserved=True,selector_modified=False,sd_written=False,flash_written=False)
    (out/'install_contract.json').write_text(json.dumps(contract,indent=2)+'\n',encoding='utf-8')
    print('PN03_INSTALL_INPUTS_PREPARED',len(records))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--media-sectors',type=int,required=True);p.add_argument('--partition-lba',type=int,required=True)
    a=p.parse_args();prepare(a.bundle.resolve(),a.output.resolve(),a.media_sectors,a.partition_lba)
