from pathlib import Path
import hashlib,json,re,shutil,struct,subprocess,zlib
p=Path('G:/fpga/performance_soc_voice_hw');w=p/'build/cpu80-20261019';base=p/'artifacts/cpu75_candidate_20261018/ram-boot75';clock=w/'boot80-clock';out=w/'ram-boot80';assert not out.exists();out.mkdir()
def sha(q):return hashlib.sha256(q.read_bytes()).hexdigest()
def wp(q):s=q.resolve().as_posix();return '/mnt/'+s[0].lower()+s[2:]
old=json.loads((base/'overlay-manifest.json').read_text());cm=json.loads((clock/'boot-manifest.json').read_text());assert cm['ratio']==[99,160]
for name in ['gui-overlay.cpio','start.S','link.ld']:shutil.copyfile(base/name,out/name)
assert sha(out/'gui-overlay.cpio')=='b53fd261ee543181a3f5fb3647bd2970757b5d6de87f410b7f001975fb97e51f'
for name in ['soc.dtb','soc.dts','fw_jump.bin']:shutil.copyfile(clock/name,out/name)
shutil.copyfile(clock/'loader/opensbi_timer_bridge.inc',out/'opensbi_timer_bridge.inc')
dtb=(out/'soc.dtb').read_bytes();assert dtb.count(struct.pack('>I',0x0380e000))==1
offset=dtb.index(struct.pack('>I',0x0380e000));s=(base/'loader.c').read_text()
assert 'cpu_hz=75000000 sys_hz=49500000 ratio=33/50' in s
s=s.replace('75000000','80000000').replace('ratio=33/50','ratio=99/160')
for name in ['fw_jump.bin','soc.dtb']:
 before=zlib.crc32((base/name).read_bytes());after=zlib.crc32((out/name).read_bytes());anchor=f'0x{before:08x}u';assert s.count(anchor)==1,(name,anchor);s=s.replace(anchor,f'0x{after:08x}u')
assert s.count('+360u')==2;s=s.replace('+360u',f'+{offset}u');(out/'loader.c').write_text(s)
records=[]
for v in old['commands']:
 argv=v['argv']
 if not argv[0].startswith('/opt/toolchain/'):continue
 args=[x.replace('/mnt/g/fpga/performance_soc_voice_hw/build/cpu75-20261018/boot75-clint-bench-v2',wp(out)).replace('/mnt/g/fpga/b70r1/sw/bootloader','/mnt/g/fpga/c80p1/sw/bootloader') for x in argv]
 r=subprocess.run(['wsl.exe','-d','pikafish-verify','--',*args],capture_output=True,timeout=120);assert r.returncode==0,r.stderr[-2500:];records.append({'argv':args,'exit':r.returncode})
for node,prop in [('/cpus','timebase-frequency'),('/cpus/cpu@0','clock-frequency')]:
 r=subprocess.run(['wsl.exe','-d','pikafish-verify','--','fdtget','-t','u',wp(out/'soc.dtb'),node,prop],capture_output=True,timeout=30);assert r.returncode==0 and r.stdout.strip()==b'80000000'
record={'status':'RAM_BOOT80_BUILT_NOT_BOARD_TESTED','scope':'Read-only existing SD payloads, RAM patch only; no FPGA/SD/Flash action','cpu_hz':80000000,'sys_hz':49500000,'ratio':[99,160],'overlay_identical_to_accepted75':True,'dtb_initrd_offset':offset,'inputs_sha256':{str(q):sha(q) for q in [base/'loader.c',base/'overlay-manifest.json',clock/'loader/opensbi_timer_bridge.inc',clock/'soc.dtb',clock/'fw_jump.bin',Path(__file__)]},'outputs_sha256':{n:sha(out/n) for n in ['loader.c','loader.bin','loader.elf','opensbi_timer_bridge.inc','soc.dtb','soc.dts','fw_jump.bin','gui-overlay.cpio']},'commands':records}
(out/'overlay-manifest.json').write_text(json.dumps(record,indent=2)+'\n');print('RAM_BOOT80_BUILT_NOT_BOARD_TESTED', (out/'loader.bin').stat().st_size)
