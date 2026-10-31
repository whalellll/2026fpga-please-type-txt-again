"""Bind the first SD-menu migration to one exact card and the current entry."""
import argparse
import json
from pathlib import Path
import struct
import zlib
from sd_namespace import REPO, ROLES, identity, verify_compiled_loader

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--candidate',type=Path,required=True)
p.add_argument('--old-entry',type=Path,required=True)
p.add_argument('--cid',required=True)
a=p.parse_args()
candidate=a.candidate.resolve()
if not candidate.is_relative_to((REPO/'build').resolve()):p.error('Use build/ candidate')
if len(a.cid)!=32 or any(c not in '0123456789abcdef' for c in a.cid):p.error('Exact lowercase 128-bit CID required')
header=candidate/'sd_namespace_install.h'
plan_path=candidate/'namespace-install-plan.json'
if header.exists() or plan_path.exists():p.error('Use a fresh install plan')
contract=json.loads((candidate/'sd_contract.json').read_text())
if contract['deployment']['prefix']!='PN01':p.error('This initial migration is reserved for PN01')
loader,_=verify_compiled_loader(candidate,contract)
old=a.old_entry.read_bytes();menu=(candidate/'xq-boot-menu.bin').read_bytes()
assert len(old)==20468 and identity(a.old_entry)['sha256']=='24561e13bcc8c9466a038e76944384b62d5beacddc460d8d50e111ba581502ba'
assert len(menu)%4==0 and 0<len(menu)<=len(old)//512*512
old_crc=zlib.crc32(old);loader_info=identity(loader)
config=(f'XQ_BOOT_MENU_V1\nPicture_new PN01BOOT.BIN {loader_info["bytes"]} {loader_info["crc32"]}\n'
        f'Native_previous PN00BOOT.BIN {len(old)} {old_crc:08x}\n').encode('ascii')
(candidate/'XQBOOT.CFG').write_bytes(config)
patched=menu+old[len(menu):]
(candidate/'expected-xiangqi.bin').write_bytes(patched)
layout=contract['deployment']['layout']
source_names={'sbi':'brfw.bin','kernel':'N20K.BIN','rootfs':'N20FS.BIN',
              'dtb':'N20.DTB','nnue':'pikafish.pff','attack':'pikafish.atk'}
addresses=[0x04000000,0x05000000,0x04000000,0x05000000,0x04000000,0x09000000]
items=[]
for (role,fields),address in zip(ROLES.items(),addresses):
    item=contract['files'][layout[role]]
    items.append(dict(source=source_names[role],name=layout[role],address=address,
                      bytes=item['bytes'],crc32=item['crc32'],sha256=item['sha256']))
text='/* Exact first-install CID, private file contracts and small embedded payloads. */\n'
text+='#define NS_EXPECTED_CID {'+','.join('0x'+a.cid[i:i+8]+'u' for i in range(0,32,8))+'}\n'
text+=f'#define NS_OLD_BYTES {len(old)}u\n#define NS_OLD_CRC 0x{old_crc:08x}u\n'
text+=f'#define NS_NEW_ENTRY_CRC 0x{zlib.crc32(patched):08x}u\n'
text+='#define NS_COPY_ITEMS { \\\n'
for item in items:
    stem,ext=item['name'].split('.')
    short=stem.ljust(8)+ext.ljust(3)
    text+=f' {{"{item["source"]}","{item["name"]}","{short}",{item["bytes"]}u,0x{item["crc32"]}u,0x{item["address"]:08x}u}}, \\\n'
text+='}\n'
for name,data in [('loader',loader.read_bytes()),('menu',menu),('config',config)]:
    text+=f'#define NS_{name.upper()}_BYTES {len(data)}u\n#define NS_{name.upper()}_CRC 0x{zlib.crc32(data):08x}u\n'
    padded=data+b'\0'*(-len(data)%4)
    words=struct.unpack('<'+str(len(padded)//4)+'I',padded)
    text+=f'static const uint32_t ns_{name}[]={{\n'
    for at in range(0,len(words),8):text+=','.join(f'0x{x:08x}u' for x in words[at:at+8])+',\n'
    text+='};\n'
header.write_text(text,encoding='ascii')
plan=dict(schema_version=1,scope='One-time exact-CID SD selector migration; no recurring UART file upload',
          expected_cid=a.cid,media_sectors=62333952,partition_lba=32,
          source_files_and_private_copies=items,original_entry=identity(a.old_entry),
          new_entry=identity(candidate/'expected-xiangqi.bin'),
          embedded=dict(loader=identity(loader),menu=identity(candidate/'xq-boot-menu.bin'),config=identity(candidate/'XQBOOT.CFG')),
          new_files=[item['name'] for item in items]+['PN01BOOT.BIN','XQBOOT.CFG','PN00BOOT.BIN','XQMENU.BIN'],
          only_existing_file_patched='xiangqi.bin',backup_name='PN00BOOT.BIN',
          preserves_entry_size_chain_and_tail=True,flash_written=False,sd_written=False,
          boot_rom_support_files=['xiangqi.bin','xqmodel.bin','XQBOOT.CFG'],
          note='xqboot ROM carrier xqmodel.bin stays unchanged; branch-private kernel/rootfs/DTB/SBI/NNUE/attack files do not share names')
plan_path.write_text(json.dumps(plan,indent=2)+'\n')
print('SD_NAMESPACE_INSTALL_PLAN_PASS files=10 CID='+a.cid+' sd_written=0')
