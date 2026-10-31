from pathlib import Path
import argparse,hashlib,json,re,shutil,struct,subprocess,zlib
ap=argparse.ArgumentParser();ap.add_argument('--hz',type=int,choices=[70875000,75000000],required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
p=Path('G:/fpga/performance_soc_voice_hw');work=p/'build/cpu75-20261018';base=work/'boot70875-clint-fixed'
clock=work/'boot75-clock' if a.hz==75000000 else base
out=work/a.output;assert out.parent==work and not out.exists();out.mkdir()
def sha(q):return hashlib.sha256(q.read_bytes()).hexdigest()
def wp(q):
    s=q.resolve().as_posix();return '/mnt/'+s[0].lower()+s[2:]
records=[]
def run(argv):
    r=subprocess.run(['wsl','-d','pikafish-verify','--',*argv],capture_output=True);r.check_returncode()
    records.append({'argv':argv,'exit':r.returncode,'stdout':r.stdout.decode('utf-8','replace')});return r.stdout.strip()
blob=(base/'gui-overlay.cpio').read_bytes();entries=[];i=0
while blob[i:i+6]==b'070701':
    h=blob[i:i+110];n=int(h[94:102],16);size=int(h[54:62],16)
    name=blob[i+110:i+110+n-1].decode();start=(i+110+n+3)&~3
    if name=='TRAILER!!!':break
    entries.append((name,blob[start:start+size],int(h[14:22],16)));i=(start+size+3)&~3
tools=['pikafish-driver-soak','pikafish-stageb-word-accept','pikafish-nnue-latency-clint']
for n in tools:entries.append(('usr/bin/'+n,(work/n).read_bytes(),0o100700))
entries.append(('opt/pikafish/cpu75-nnue.vectors',(work/'cpu75-nnue.vectors').read_bytes(),0o100600))
entries.append(('TRAILER!!!',b'',0));payload=bytearray()
for ino,(name,data,mode) in enumerate(entries,1):
    name=name.encode()+b'\0';fields=[ino,mode,0,0,1,0,len(data),0,0,0,0,len(name),0]
    payload+=b'070701'+''.join(f'{x:08x}' for x in fields).encode()+name
    payload+=bytes((-len(payload))%4);payload+=data;payload+=bytes((-len(payload))%4)
payload+=bytes((-len(payload))%512)
assert len(payload)%4==0 and 0x03000000+8445624+len(payload)<0x04000000
(out/'gui-overlay.cpio').write_bytes(payload)
oldinc=(base/'opensbi_timer_bridge.inc').read_text();oldfw=bytes(int(v,16) for v in re.findall(r'0x([0-9a-f]{2})',re.search(r'fw_jump_bin\[\] = \{(.*?)\};',oldinc,re.S)[1]))
dtb=(clock/'soc.dtb').read_bytes();fw=(clock/'fw_jump.bin').read_bytes() if a.hz==75000000 else oldfw
assert dtb.count(struct.pack('>I',0x0380e000))==1
offset=dtb.index(struct.pack('>I',0x0380e000));end=0x03000000+8445624+len(payload);newle=int.from_bytes(struct.pack('>I',end),'little')
old=json.loads((base/'overlay-manifest.json').read_text());s=(base/'loader.c').read_text()
s=s.replace('70875000',str(a.hz))
if a.hz==75000000:s=s.replace('ratio=44/63','ratio=33/50')
for before,after in [(zlib.crc32(oldfw),zlib.crc32(fw)),(int(old['dtb_crc32'],16),zlib.crc32(dtb)),(0x3276ae7f,zlib.crc32(payload)),(0xb8b68503,newle)]:
    assert f'0x{before:08x}u' in s;s=s.replace(f'0x{before:08x}u',f'0x{after:08x}u')
s=s.replace('317440u',str(len(payload))+'u').replace('79360u',str(len(payload)//4)+'u').replace('+360u',f'+{offset}u')
(out/'loader.c').write_text(s)
inc=(work/'boot75-clock/loader/opensbi_timer_bridge.inc').read_text() if a.hz==75000000 else oldinc
(out/'opensbi_timer_bridge.inc').write_text(inc)
for n in ['start.S','link.ld']:shutil.copyfile(base/n,out/n)
for n in ['soc.dtb','soc.dts']:shutil.copyfile(clock/n,out/n)
(out/'fw_jump.bin').write_bytes(fw)
for entry in old['commands']:
    if entry['argv'][0].startswith('/opt/toolchain/'):run([v.replace(wp(base),wp(out)) for v in entry['argv']])
for node,prop in [('/cpus','timebase-frequency'),('/cpus/cpu@0','clock-frequency')]:assert run(['fdtget','-t','u',wp(out/'soc.dtb'),node,prop])==str(a.hz).encode()
assert run(['fdtget','-t','x',wp(out/'soc.dtb'),'/reserved-memory/clint-mmio@2000000','reg'])==b'2000000 10000'
record={'scope':'RAM-only benchmark overlay; same kernel, official PFF1, GUI and SD77 display-only',
 'cpu_hz':a.hz,'sys_hz':49500000,'ratio':[33,50] if a.hz==75000000 else [44,63],
 'overlay_bytes':len(payload),'initrd_end':hex(end),'overlay_crc32':f'{zlib.crc32(payload):08x}','dtb_crc32':f'{zlib.crc32(dtb):08x}',
 'source_sha256':{str(q):sha(q) for q in [base/'loader.c',base/'gui-overlay.cpio',clock/'soc.dtb',Path(__file__),*[work/n for n in tools]]},
 'outputs_sha256':{n:sha(out/n) for n in ['loader.bin','loader.c','gui-overlay.cpio','opensbi_timer_bridge.inc','soc.dtb','fw_jump.bin']},'commands':records}
(out/'overlay-manifest.json').write_text(json.dumps(record,indent=2));print('BENCHMARK_GUI_BOOT_BUILT',a.hz,len(payload))
