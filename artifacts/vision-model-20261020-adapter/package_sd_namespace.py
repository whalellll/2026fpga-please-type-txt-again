"""Package private SD files and a command-only starter; never write media."""
import argparse
import json
from pathlib import Path
import shutil
import zipfile
from sd_namespace import REPO, PROFILE, identity, sha, verify_compiled_loader

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--candidate',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--receipt',type=Path,required=True)
a=p.parse_args()
if a.out.exists() or a.out.with_suffix('.zip').exists():p.error('Choose fresh package paths')
contract=json.loads((a.candidate/'sd_contract.json').read_text())
plan=json.loads((a.candidate/'namespace-install-plan.json').read_text())
receipt=json.loads(a.receipt.read_text())
assert receipt['status']=='PASS' and receipt['boot_from_sd_menu']
binary,descriptors=verify_compiled_loader(a.candidate,contract)
a.out.mkdir(parents=True);private=a.out/'sd-root';private.mkdir()
for name,item in contract['files'].items():shutil.copyfile(item['path'],private/name)
shutil.copyfile(binary,private/contract['deployment']['layout']['loader'])
common=a.out/'initial-menu';common.mkdir()
for name,source in [('xiangqi.bin',a.candidate/'expected-xiangqi.bin'),
                    ('XQBOOT.CFG',a.candidate/'XQBOOT.CFG'),
                    ('XQMENU.BIN',a.candidate/'xq-boot-menu.bin'),
                    ('PN00BOOT.BIN',Path(plan['original_entry']['path']))]:
    shutil.copyfile(source,common/name)
shutil.copyfile(Path(__file__).parent/'boot_sd_namespace.ps1',a.out/'Start-PictureNew.ps1')
manifest=dict(schema_version=1,format_profile=PROFILE,prefix=contract['deployment']['prefix'],
              scope='Picture_new SD namespace deployment; NOT BoardRelease or new model acceptance',
              layout=contract['deployment']['layout'],compiled_six_payload_descriptors=descriptors,
              private_files={path.name:{k:v for k,v in identity(path).items() if k!='path'} for path in private.iterdir()},
              initial_menu_files={path.name:{k:v for k,v in identity(path).items() if k!='path'} for path in common.iterdir()},
              fixed_sbit_sha256=contract['fixed_sbit_sha256'],
              boot_method='xqboot -> SD menu -> PN01BOOT.BIN -> private six SD files',
              recurring_uart_file_upload=False,sd_menu_boot_board_validated=True,
              installation_receipt_sha256=sha(a.receipt),
              stable_rom_support_files=['xiangqi.bin','xqmodel.bin','XQBOOT.CFG'],
              model_count=3,backend='rv32-driver-quantized-mac',production_ready=False,
              real_recognition_accepted=False,latency_accepted=False,flash_written=False)
(a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
readme='''# Picture_new 独立命名 SD 包 PN01

已通过串口安装到板上SD，并验证菜单及SD启动。日常不传启动器、内核或模型文件。

启动：保持匹配的E8位流，在`soc>`输入`xqboot`；菜单选择`1 Picture_new`，或直接回车。
也可在电脑运行`powershell -NoProfile -ExecutionPolicy Bypass -File .\\Start-PictureNew.ps1 -PortName COM5`，
脚本只发送控制命令，不传文件、不写SD。开始时板卡须处于`soc>`。

`sd-root/`是本分支的七个独立文件：内核、rootfs、DTB、OpenSBI、NNUE、攻击表和启动器。
下一套候选改用PN02等新前缀，保留上一套。训练原包及rootfs内的程序路径保持原样。

`initial-menu/`是首次迁移的公共菜单和备份，单独存放以避免日后更新分支时误覆盖。
xiangqi.bin为冻结ROM必读入口，现为通用选择器；xqmodel.bin为ROM所需固定载荷，未改动。
菜单从XQBOOT.CFG读最多8项，每项记录标签、独立启动器8.3文件名、字节数和CRC32。
其他分支新增自己的文件及一条菜单记录即可，不需替换Picture_new文件或通用选择器。
Native_previous使用PN00BOOT.BIN，保留迁移前的原生启动器和原载荷。

本包是部署命名调整。模型仍有现场识别错误和严重延迟，未通过真实整局或性能验收。
E8位流仍为易失CRAM，断电后须重新加载；没有写Flash。
'''
(a.out/'README.md').write_text(readme,encoding='utf-8')
all_files={path.relative_to(a.out).as_posix():identity(path) for path in a.out.rglob('*') if path.is_file()}
(a.out/'SHA256SUMS.txt').write_text(''.join(f'{item["sha256"]}  {name}\n' for name,item in all_files.items()),encoding='ascii')
archive=a.out.with_suffix('.zip')
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
    for path in a.out.rglob('*'):
        if path.is_file():z.write(path,path.relative_to(a.out).as_posix())
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for name,item in all_files.items():
        import hashlib
        assert hashlib.sha256(z.read(name)).hexdigest()==item['sha256']
print('SD_NAMESPACE_PACKAGE_PASS',archive.stat().st_size,sha(archive))
