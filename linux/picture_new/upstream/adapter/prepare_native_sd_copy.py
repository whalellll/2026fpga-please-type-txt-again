"""Stage a matched, namespaced SD candidate locally; never write removable media."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--ram', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
if a.out.exists() or not a.out.resolve().is_relative_to((REPO/'build').resolve()):
    p.error('choose a fresh build/ directory')
manifest = json.loads((a.ram/'sd_contract.json').read_text())
assert manifest['fixed_sbit_sha256']=='e8a037fa676e10f31a994b2f67d35a458586a6669c61800ace53e9edacb97b45'
for name, item in manifest['files'].items():
    source = Path(item['path'])
    assert source.stat().st_size == item['bytes'] and sha(source)==item['sha256'], name
a.out.mkdir(parents=True)
header = '/* Native SD candidate: no UART-preloaded large payloads. */\n'
renames = {'Image':('N20K.BIN','PICTURE_KERNEL'),
           'brfs2.bin':('N20FS.BIN','PICTURE_INITRD'),
           'br.dtb':('N20.DTB','PICTURE_DTB')}
for old, (new, prefix) in renames.items():
    item = manifest['files'].pop(old)
    destination = a.out/new
    shutil.copyfile(Path(item['path']), destination)
    assert sha(destination)==item['sha256']
    item['path'] = str(destination.resolve())
    manifest['files'][new] = item
    header += f'#define {prefix}_NAME "{new}"\n#define {prefix}_BYTES {item["bytes"]}u\n#define {prefix}_CRC 0x{item["crc32"]}u\n'
(a.out/'picture_payloads.h').write_text(header, encoding='ascii')
manifest.update(scope='EXPERIMENTAL native three-model manual SD copy candidate; NOT BoardRelease',
                uart_kernel=False, sd_written=False, flash_written=False,
                cold_boot_board_validated=False, loader_entry=0x01000000,
                manual_copy=dict(new_files=['N20K.BIN','N20FS.BIN','N20.DTB'],
                    replace_after_pc_backup=['xiangqi.bin'], original_Image_preserved=True,
                    unchanged_dependencies=['brfw.bin','pikafish.pff','pikafish.atk','xqmodel.bin']))
(a.out/'sd_contract.json').write_text(json.dumps(manifest, indent=2)+'\n')
print('NATIVE_SD_COPY_STAGED no_media_written=1')
