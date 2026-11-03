"""Validate compiled payload descriptors and package a manual-copy SD candidate."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import zipfile

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--candidate',type=Path,required=True)
p.add_argument('--regression',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
if a.out.exists() or a.out.with_suffix('.zip').exists():p.error('choose fresh output paths')
m=json.loads((a.candidate/'sd_contract.json').read_text())
r=json.loads(a.regression.read_text())
assert r['status']=='PASS' and r['working_tree_and_isolation_inputs_match_after_execution']
assert r['linux_files_sha256']['linux/boot/v2_1_sd/source/loader.c']==sha(REPO/'linux/boot/v2_1_sd/source/loader.c')
elf=(a.candidate/'loader-picture-candidate.elf').read_bytes()
assert elf[:7]==b'\x7fELF\x01\x01\x01'
assert struct.unpack_from('<H',elf,18)[0]==243
assert struct.unpack_from('<I',elf,24)[0]==0x01000000 and struct.unpack_from('<I',elf,36)[0]==0
binary=a.candidate/'loader-picture-candidate.bin';raw=binary.read_bytes()
addresses={'brfw.bin':0x18000000,'N20K.BIN':0x00400000,'N20FS.BIN':0x03000000,
           'N20.DTB':0x1a000000,'pikafish.pff':0x10000000,'pikafish.atk':0x15000000}
# The binary's actual descriptor pointers, lengths and CRCs must bind all six inputs.
descriptors={}
for name,address in addresses.items():
    item=m['files'][name];source=Path(item['path'])
    assert source.stat().st_size==item['bytes'] and sha(source)==item['sha256'],name
    needle=struct.pack('<III',address,item['bytes'],int(item['crc32'],16))
    assert raw.count(needle)==1,(name,'descriptor absent/ambiguous')
    at=raw.index(needle);pointer=struct.unpack_from('<I',raw,at-4)[0]
    offset=pointer-0x01000000
    assert 0<=offset<len(raw) and raw[offset:offset+len(name)+1]==name.encode()+b'\0',name
    descriptors[name]=dict(address=hex(address),bytes=item['bytes'],crc32=item['crc32'])
a.out.mkdir(parents=True);sd=a.out/'sd-root';sd.mkdir()
for name in ('N20K.BIN','N20FS.BIN','N20.DTB'):
    shutil.copyfile(Path(m['files'][name]['path']),sd/name)
shutil.copyfile(binary,sd/'xiangqi.bin')
manifest=dict(schema_version=1,scope='Native three-model experimental manual-copy SD candidate; NOT BoardRelease',
    model_count=3,backend='rv32-driver-quantized-mac',production_ready=False,
    cold_sd_boot_validated=False,sd_written_by_agent=False,flash_written=False,
    fixed_sbit_sha256=m['fixed_sbit_sha256'],required_bitstream='E8 background-capture candidate already loaded in volatile CRAM',
    compiled_six_payload_descriptors=descriptors,
    regression_receipt_sha256=sha(a.regression),loader_source_sha256=sha(REPO/'linux/boot/v2_1_sd/source/loader.c'),
    loader_builder_sha256=sha(REPO/'scripts/build_picture_loader.ps1'),
    files={path.name:dict(bytes=path.stat().st_size,sha256=sha(path)) for path in sd.iterdir()},
    unchanged_sd_dependencies={name:m['files'][name] for name in ('brfw.bin','pikafish.pff','pikafish.atk')},
    preserve_other_files=['Image','P19FS.BIN','P19.DTB','P19BOOT.BIN','xqmodel.bin'],
    rollback='Restore the original xiangqi.bin from the PC backup; old Image and P19 files are preserved')
(a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
instructions='''# Picture_new 三模型 SD 实验候选（2026-10-20）

本包由已验证的 GUI r07、原生 worker r05 和三模型组成，保持严格 FPGA 驱动后端。
离线板端全链路约35分41秒，实时相机识别及完整对局尚未通过；这是实验候选。
此 SD 启动组合已完成编译、六载荷契约校验和完整功能回归，整卡冷启动仍需返板验证。

复制步骤：
1. 当前板已停在 soc>，UART 大文件传输已取消，可以取下 SD 卡；保持板卡上电以保留 E8 CRAM。
2. 先把 SD 根目录现有的 xiangqi.bin 完整复制到电脑另一目录备份。
3. 将本包 sd-root 内的四个文件直接复制到 SD 根目录：N20K.BIN、N20FS.BIN、N20.DTB、xiangqi.bin。
   三个 N20 文件是新增；仅 xiangqi.bin 替换原入口。不是把 sd-root 文件夹整个复制进去。
4. 保留卡上原有 Image、P19*、brfw.bin、pikafish.pff、pikafish.atk、xqmodel.bin 及其他文件。
5. 核对四个文件与 manifest.json 的字节数/SHA256，安全弹出并插回板卡，告知工程 AI。
   工程 AI 会通过 UART 执行 xqboot、检查六载荷 CRC、驱动能力与三模型 READY，再重新拍摄。

回退：将电脑备份的原 xiangqi.bin 放回卡根目录；原 Image/P19 文件未被本包替换。
若板卡断电，E8 易失 CRAM 需由工程 AI 重新扫描并加载后再验本包。
不需要写 FPGA Flash，也不需要格式化卡。训练权重未修改。
'''
(a.out/'README.md').write_text(instructions,encoding='utf-8')
(a.out/'SHA256SUMS.txt').write_text(''.join(f'{entry["sha256"]}  sd-root/{name}\n' for name,entry in manifest['files'].items()),encoding='ascii')
archive=a.out.with_suffix('.zip')
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
    for path in a.out.rglob('*'):
        if path.is_file():z.write(path,path.relative_to(a.out).as_posix())
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for name,item in manifest['files'].items():
        assert hashlib.sha256(z.read('sd-root/'+name)).hexdigest()==item['sha256']
print('NATIVE_SD_MANUAL_COPY_PACKAGE_PASS',archive.stat().st_size,sha(archive))
