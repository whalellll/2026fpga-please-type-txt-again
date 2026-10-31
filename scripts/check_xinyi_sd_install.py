"""Exercise the exact PN03 installer and original FAT logic on synthetic SD.

Fixtures are sparse Linux files with an all-zero mock CID, never media images
for deployment. The RV32 run links the same GCC16 production installer/FAT
objects; only main is renamed for the host-owned entry point.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def wsl(path):
    s=path.resolve().as_posix();return '/mnt/'+s[0].lower()+s[2:]

FIXTURE=r'''
import json,os,struct,sys
from pathlib import Path
candidate=Path(sys.argv[1]);directory=Path(sys.argv[2]);directory.mkdir()
c=json.loads((candidate/'install_contract.json').read_text())
sectors=c['media_sectors'];partition=c['partition_lba'];reserved=32;spc=64;total=sectors-partition;fatsize=1
while True:
 needed=(((total-reserved-2*fatsize)//spc+2)*4+511)//512
 if needed<=fatsize:break
 fatsize=needed
data=partition+reserved+2*fatsize
boot=bytearray(512);boot[:11]=b'\xeb\x58\x90MSDOS5.0'
struct.pack_into('<HBHBHHBHHHII',boot,11,512,spc,reserved,2,0,0,0xf8,0,63,255,partition,total)
struct.pack_into('<IHHIHH',boot,36,fatsize,0,0,2,1,6)
boot[64]=0x80;boot[66]=0x29;struct.pack_into('<I',boot,67,0x504e3033)
boot[71:82]=b'HOSTONLY   ';boot[82:90]=b'FAT32   ';boot[510:512]=b'\x55\xaa'
mbr=bytearray(512);mbr[446+4]=0x0c;struct.pack_into('<II',mbr,446+8,partition,total);mbr[510:512]=b'\x55\xaa'
fat=bytearray(fatsize*512);struct.pack_into('<3I',fat,0,0x0ffffff8,0x0fffffff,0x0fffffff)
root=bytearray(32768);cluster=3;entry=0;locations={}
files=[(n,('KEEP '+n+'\n').encode()) for n in ['xiangqi.bin','xqmodel.bin','XQBOOT.CFG','PN00BOOT.BIN','PN01BOOT.BIN','PN02BOOT.BIN']]
if c.get('prefix') in ['PN06','PN07','PN08','PN15']:
 for prefix in ['PN03','PN04','PN05']+(['PN06'] if c['prefix'] in ['PN07','PN08','PN15'] else [])+(['PN07'] if c['prefix'] in ['PN08','PN15'] else [])+(['PN08','PN09'] if c['prefix']=='PN15' else []):
  for suffix in ['BOOT.BIN','SBI.BIN','K.BIN','FS.BIN','NN.PFF','ATK.BIN','.DTB','UPD.GZ','.JSN']:
   name=prefix+suffix;files.append((name,('KEEP '+name+'\n').encode()))
 if c['prefix'] in ['PN07','PN08','PN15']:files.append(('PN06.SHA',b'KEEP PN06.SHA\n'))
 if c['prefix'] in ['PN08','PN15']:files.append(('PN07.SHA',b'KEEP PN07.SHA\n'))
 if c['prefix']=='PN15':
  files.extend((p+'.SHA',('KEEP '+p+'.SHA\n').encode()) for p in ['PN08','PN09'])
aliases={'PN03SBI.BIN':'fw_jump.bin','PN03K.BIN':'Image','PN03.DTB':'soc.dtb','PN03NN.PFF':'PN02NN.PFF','PN03ATK.BIN':'PN02ATK.BIN'}
for source,name in aliases.items():
 if (candidate/'payloads'/source).is_file():files.append((name,(candidate/'payloads'/source).read_bytes()))
disk=directory/'baseline.img'
with disk.open('wb') as f:
 f.truncate(sectors*512);f.seek(0);f.write(mbr);f.seek(partition*512);f.write(boot);f.seek((partition+6)*512);f.write(boot)
 for name,payload in files:
  parts=name.split('.',1);stem=parts[0];ext=parts[1] if len(parts)>1 else '';short=(stem.upper().ljust(8)+ext.upper().ljust(3)).encode();assert len(short)==11
  e=bytearray(32);e[:11]=short;e[11]=0x20;struct.pack_into('<H',e,20,cluster>>16);struct.pack_into('<H',e,26,cluster&65535);struct.pack_into('<I',e,28,len(payload))
  root[entry:entry+32]=e;locations[name]=dict(entry=data*512+entry,cluster=cluster);entry+=32
  count=(len(payload)+32767)//32768
  for index in range(count):struct.pack_into('<I',fat,(cluster+index)*4,cluster+index+1 if index+1<count else 0x0fffffff)
  f.seek((data+(cluster-2)*spc)*512);f.write(payload);cluster+=count
 for index in range(2):f.seek((partition+reserved+index*fatsize)*512);f.write(fat)
 f.seek(data*512);f.write(root)
metadata=dict(media_sectors=sectors,partition_lba=partition,data_lba=data,fatsize=fatsize,root_entries=entry//32,locations=locations)
(directory/'geometry.json').write_text(json.dumps(metadata))
print('SYNTHETIC_SPARSE_FAT32_READY_ZERO_CID_NEVER_DEPLOY',entry//32,flush=True)
'''

def run(candidate,out,distro):
    from picture_workspace import workspace_path
    workspace_path(out)
    if out.exists():raise ValueError('Fresh build/ output required')
    out.mkdir(parents=True);support=candidate/'support';commands=[];tests=[]
    current=[Path(__file__).resolve(),ROOT/'linux/xinyi_board/boot/install.c',ROOT/'linux/xinyi_board/boot/install_test.c',ROOT/'linux/xinyi_board/boot/install_xmodem.c',ROOT/'linux/xinyi_board/boot/install_xmodem_test.c',ROOT/'scripts/prepare_xinyi_sd_install.py',ROOT/'scripts/build_xinyi_sd_install.ps1']
    source_before={str(p):sha(p) for p in current}
    contract=json.loads((candidate/'install_contract.json').read_text())
    for p,v in contract['source_inputs'].items():
        if sha(Path(p))!=v['sha256']:raise ValueError('Stale candidate source: '+p)
    (out/'fixture.py').write_text(FIXTURE,encoding='utf-8')
    temp='/tmp/pn03-'+out.name
    def call(argv,name,timeout=180):
        proc=subprocess.run(['wsl.exe','-d',distro,'--',*argv],cwd=ROOT,capture_output=True,timeout=timeout)
        raw=proc.stdout+proc.stderr;(out/(name+'.log')).write_bytes(raw)
        commands.append(dict(name=name,exit=proc.returncode,log_sha256=hashlib.sha256(raw).hexdigest()))
        if proc.returncode:raise ValueError(name+': '+raw.decode(errors='replace')[-2200:])
        return raw
    call(['python3',wsl(out/'fixture.py'),wsl(candidate),temp],'fixture')
    common=['-std=gnu99','-O2','-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections','-I',wsl(support)]
    harness=wsl(ROOT/'linux/xinyi_board/boot/install_test.c')
    call(['gcc',*common,'-Dmain=pn03_install_main','-c',wsl(support/'install.c'),'-o',wsl(out/'host-install.o')],'host-object')
    call(['gcc',*common,harness,wsl(out/'host-install.o'),wsl(support/'install_fat.c'),wsl(support/'fat_ro.c'),wsl(support/'crc32_fast.c'),'-Wl,--gc-sections','-o',wsl(out/'host-test')],'host-link')
    cc='/opt/toolchain/bin/riscv32-linux-musl-gcc'
    objects=[candidate/'rv32-install-test.o',candidate/'obj/07_install_fat.c.o',candidate/'obj/04_fat_ro.c.o',candidate/'obj/05_crc32_fast.c.o']
    call([cc,'-march=rv32ima','-Wa,-march=rv32ima_zicsr_zifencei','-mabi=ilp32','-static',*common,harness,*map(wsl,objects),'-Wl,--gc-sections','-o',wsl(out/'rv32-test')],'rv32-same-production-objects-link')
    legacy=(support/'runtime.c').read_text()
    legacy=legacy[legacy.index('static uint16_t crc16('):]
    (out/'legacy_xmodem.c').write_text('#include "soc.h"\n'+legacy,encoding='utf-8')
    for platform,compiler,prefix in [('host','gcc',[]),('rv32',cc,['-march=rv32ima','-Wa,-march=rv32ima_zicsr_zifencei','-mabi=ilp32','-static'])]:
        legacy_object=out/(platform+'-legacy.o')
        call([compiler,*prefix,*common,'-Dxmodem_receive=legacy_xmodem_receive','-c',wsl(out/'legacy_xmodem.c'),'-o',wsl(legacy_object)],platform+'-legacy-object')
        receiver=[wsl(candidate/'obj/08_install_xmodem.c.o')] if platform=='rv32' else [wsl(support/'install_xmodem.c')]
        call([compiler,*prefix,*common,wsl(ROOT/'linux/xinyi_board/boot/install_xmodem_test.c'),*receiver,wsl(legacy_object),'-o',wsl(out/(platform+'-xmodem-test'))],platform+'-xmodem-link')
        for scenario in ['pass','64k','gap300','legacy-gap300','crc-once','duplicate','bad-crc','cancel','timeout']:
            raw=call([*(['qemu-riscv32'] if platform=='rv32' else []),wsl(out/(platform+'-xmodem-test')),scenario],platform+'-xmodem-'+scenario)
            if ('XMODEM_TEST_PASS '+scenario).encode() not in raw:raise ValueError('Missing XMODEM test completion')
            tests.append(dict(scenario='xmodem-'+scenario,platform=platform,status='PASS',same_production_gcc16_objects=platform=='rv32'))
    rom=ROOT/'build/xinyi-one-20261024/boot-cpu60-final-r03/support/target-rom.bin'
    def test(scenario,platform='host',fixture=None):
        fixture=fixture or temp+'/'+scenario+'-'+platform+'.img'
        if scenario!='existing':call(['cp','--sparse=always',temp+'/baseline.img',fixture],'copy-'+scenario+'-'+platform)
        prefix=['qemu-riscv32'] if platform=='rv32' else []
        raw=call([*prefix,wsl(out/(platform+'-test')),scenario,fixture,wsl(candidate/'payloads'),wsl(rom)],scenario+'-'+platform,240)
        if ('INSTALL_TEST_PASS '+scenario).encode() not in raw:raise ValueError('Missing test completion')
        tests.append(dict(scenario=scenario,platform=platform,status='PASS',same_production_gcc16_objects=platform=='rv32'))
        return fixture
    for platform in ['host','rv32']:
        fixture=test('pass',platform);test('existing',platform,fixture)
        test('ram-reuse',platform)
        if len(contract['files'])==8:
            test('slow-big-pair',platform);test('stalled-big-file',platform)
    for scenario in ['clock','rom','camera-busy','wrong-cid','cid-swap','uart-corrupt','ram-corrupt','write-fail','write-swap']:
        test(scenario)
    for scenario in ['camera-busy','wrong-cid','ram-corrupt','write-swap']:test(scenario,'rv32')
    if contract.get('prefix') in ['PN06','PN07','PN08','PN15']:
        for platform in ['host','rv32']:
            for scenario in ['old-exact','wrong-exact',*[f'engine-busy-{i}' for i in range(5)]]:
                test(scenario,platform)
    after={str(p):sha(p) for p in current}
    if after!=source_before:raise ValueError('Test sources changed')
    result=dict(status='PASS',hardware_used=False,sd_written=False,flash_written=False,
        installer_sha256=sha(candidate/'PN03INST.BIN'),source_stable=True,source_sha256=after,
        same_gcc16_object_sha256={str(p):sha(p) for p in objects},
        install_contract_sha256=sha(candidate/'install_contract.json'),tests=tests,commands=commands,
        synthetic_fat=dict(path=temp+'/baseline.img',cid='0'*32,deployable=False,sparse=True),
        limitations=['All SD/UART transports and MMIO are synthetic.','Actual SD write requires fresh matching card CID, exact program receipt and this passed binary proof.'])
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('PN03_INSTALL_HOST_AND_SAME_GCC16_RV32_FAULT_TESTS_PASS',len(tests))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--distro',default='Ubuntu-22.04')
    a=p.parse_args();run(a.candidate.resolve(),a.output.resolve(),a.distro)
