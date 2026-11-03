"""Build matched boot inputs offline; no FPGA programming or physical media access."""
from pathlib import Path
import argparse,hashlib,json,re,shutil,struct,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from build_cpu80_conv_sd import cpio_entries,fdt_properties,wsl_path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def entry(name,data,mode):
 name=name.encode()+b'\0';fields=[0,mode,0,0,1,0,len(data),0,0,0,0,len(name),0]
 raw=b'070701'+b''.join(f'{v:08x}'.encode() for v in fields)+name
 raw+=b'\0'*((-len(raw))%4);raw+=data;return raw+b'\0'*((-len(raw))%4)
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
 ap.add_argument('--engine',type=Path,required=True);ap.add_argument('--voice',type=Path,required=True)
 ap.add_argument('--base-rootfs',type=Path,help='Frozen original base archive, required when rebuilding an already updated candidate')
 ap.add_argument('--base-kit',type=Path,help='Verified previous eight-file offline kit; its hashes and clock binding are checked before reuse')
 ap.add_argument('--require-pipeline-hooks',action='store_true',help='Dedicated hardware requires all three official NNUE source hooks')
 ap.add_argument('--batch60',action='store_true',help='Explicit CPU60 batch prototype with paired capability guard')
 ap.add_argument('--batch-check',type=Path,help='Matched static RV32 batch capability checker')
 a=ap.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);sd=out/'sd-root';support=out/'support';sd.mkdir();support.mkdir()
 clock=json.loads((ROOT/'config/clocks.json').read_text());cpu=clock['cpu_hz'];assert cpu in ([60000000] if a.batch60 else [75000000,70000000]) and clock['sys_hz']==49500000
 if a.batch60:
  assert a.require_pipeline_hooks and a.batch_check and a.base_kit
  assert clock['cpu_clock_source']=='dedicated1080frac' and clock['cpu_divisor']==36
 engine=a.engine.resolve();voice=a.voice.resolve()
 receipt=json.loads((engine/'result.json').read_text());assert receipt['status']=='PIKAFISH75_PIPELINE_SEARCH_AND_GUI_RV32_BUILD_PASS_NOT_BOARD'
 if a.require_pipeline_hooks:
  integration=json.loads((engine/'pipeline-integration.json').read_text())
  assert integration['status']=='ALL_THREE_NNUE_PIPELINE_HOOKS_VERIFIED' and len(integration['hooks'])==3
  assert sha(engine/'pipeline-integration.json')==receipt['pipeline_integration_sha256']
  if a.batch60:assert integration['batch_scalar_fallback_guards']==3
 for n,h in receipt['artifacts_sha256'].items():assert sha(engine/n)==h,n
 voice_receipt=json.loads((voice/'result.json').read_text())
 assert voice_receipt['status']=='VOICE_RUNTIME_RV32_CLINT_BENCH_BUILD_PASS_NOT_BOARD'
 for n,h in voice_receipt['artifacts_sha256'].items():assert sha(voice/n)==h,n
 replacements={
  'usr/bin/xiangqi-pikafish-gui':engine/'xiangqi-pikafish-gui-display',
  'usr/bin/pikafish-pipeline-search':engine/'pikafish-pipeline-search',
  'usr/bin/pikafish':engine/'pikafish-rv32',
  'usr/bin/pikafish-nnue-latency-clint':engine/'pikafish-nnue-pipeline-latency',
  'usr/bin/xqvoice':voice/'xqvoice','usr/bin/xqvoice-send':voice/'xqvoice-send',
  'usr/bin/xqaudio-capture':voice/'xqaudio-capture','usr/bin/xqvoice-accel-bench':voice/'xqvoice-accel-bench'}
 if a.batch60:replacements['usr/bin/pikafish-batch-check']=a.batch_check.resolve()
 for p in replacements.values():assert p.is_file(),p
 hashes={n:sha(p) for n,p in replacements.items()}
 extra={}
 if a.batch60:
  extra['etc/pikafish-batch.env']=(b'unset PIKAFISH_MAC_BACKEND\nexport PIKAFISH_MAC_REQUIRE_DRIVER=1\n'
   b'export PIKAFISH_STAGEA_ACCEL=${PIKAFISH_STAGEA_ACCEL:-1}\nexport PIKAFISH_STAGEB_ACCEL=${PIKAFISH_STAGEB_ACCEL:-1}\n'
   b'export PIKAFISH_NNUE_PIPELINE=${PIKAFISH_NNUE_PIPELINE:-1}\nexport PIKAFISH_NNUE_BATCH=${PIKAFISH_NNUE_BATCH:-1}\n')
  extra['usr/bin/pikafish-batch']=b'#!/bin/sh\nset -eu\n. /etc/pikafish-batch.env\n/usr/bin/pikafish-batch-check\nexec "$@"\n'
  hashes.update({n:hashlib.sha256(v).hexdigest() for n,v in extra.items()})
 checks='\n'.join('check_hash '+h+' /'+n for n,h in hashes.items())
 init=f'''#!/bin/sh
set -eu
[ "${{1:-}}" = start ] || exit 0
check_hash() {{ expected=$1; file=$2; set -- $(sha256sum "$file"); [ "$1" = "$expected" ] || {{ echo VOICE_NNUE_RUNTIME_HASH_FAIL "$file" >/dev/console; exit 1; }}; }}
{checks}
check_hash 10186411d091dc85efefc921f29300e49a1e5de7b308f6e8d49602ea349ee41a /opt/xqvoice/sd77-candidate.xqt
unset PIKAFISH_MAC_BACKEND
export PIKAFISH_MAC_REQUIRE_DRIVER=1
export PIKAFISH_STAGEA_ACCEL=${{PIKAFISH_STAGEA_ACCEL:-1}}
export PIKAFISH_STAGEB_ACCEL=${{PIKAFISH_STAGEB_ACCEL:-1}}
export PIKAFISH_NNUE_PIPELINE=${{PIKAFISH_NNUE_PIPELINE:-1}}
export XQVOICE_BACKEND=${{XQVOICE_BACKEND:-hardware}}
{'. /etc/pikafish-batch.env' if a.batch60 else ''}
{'/usr/bin/pikafish-batch-check >/dev/console' if a.batch60 else ''}
mkdir -p /tmp/voice-gui-display
cd /tmp/voice-gui-display
XQ_GUI_INPUT=/run/voice-display.in /usr/bin/xiangqi-pikafish-gui </dev/null >gui-v3.log 2>&1 &
echo $! >gui-v3.pid
tries=0
until grep -q 'XQ LINUX PIKAFISH READY' gui-v3.log; do
 tries=$((tries+1)); [ "$tries" -lt 60 ] || {{ cat gui-v3.log >/dev/console; exit 1; }}; sleep 1
done
/usr/bin/xqvoice /dev/pango-audio0 /opt/xqvoice/sd77-candidate.xqt 200 160 500 </dev/null >voice.log 2>&1 &
echo $! >voice.pid
sleep 1
kill -0 $(cat gui-v3.pid)
kill -0 $(cat voice.pid)
echo VOICE_NNUE_RUNTIME_STARTED cpu={cpu} sys=49500000 display=1080p30 >/dev/console
{'echo PIKAFISH_BATCH60_RUNTIME_STARTED batch=1 >/dev/console' if a.batch60 else ''}
tail -6 gui-v3.log >/dev/console
head -5 voice.log >/dev/console
'''
 assert not (a.base_rootfs and a.base_kit),'Choose one base source'
 parent=None
 if a.base_kit:
  parent=json.loads((a.base_kit/'manifest.json').read_text(encoding='utf-8'))
  assert parent['status']=='VOICE_NNUE_RUNTIME_18_OFFLINE_TESTS_PASS_NATIVE_BOARD_PENDING'
  assert parent['cpu_hz']==(75000000 if a.batch60 else cpu) and parent['sys_hz']==49500000
  if not a.batch60:assert parent['clock_sha256']==sha(ROOT/'config/clocks.json')
  assert set(parent['sd_root_files'])=={'Image','Image.mmode','fw_jump.bin','rootfs.cpio','soc.dtb','mmode.dtb','pikafish.pff','pikafish.atk'}
  for n,item in parent['sd_root_files'].items():
   p=a.base_kit/'sd-root'/n
   assert p.stat().st_size==item['bytes'] and sha(p)==item['sha256'],n
 base_path=a.base_kit/'sd-root/rootfs.cpio' if a.base_kit else a.base_rootfs or ROOT/'linux/boot/rootfs.cpio'
 base=base_path.read_bytes();rows=cpio_entries(base);effective={}
 for row in rows:
  if row['name']=='TRAILER!!!':continue
  effective[row['name'].removeprefix('./')]=row
 if parent is None:
  assert effective['etc/init.d/S95pikafish']['sha256']=='260ef73c60b5f548fc46028498ccf029a6e443bf0438ec106c2e30de9ac6c8dc','Unknown baseline autostart'
 generated={n:entry(n,p.read_bytes(),0o100755) for n,p in replacements.items()}
 generated.update({n:entry(n,v,0o100755 if n.startswith('usr/bin/') else 0o100644) for n,v in extra.items()})
 generated['etc/init.d/S95pikafish']=entry('etc/init.d/S95pikafish',init.encode(),0o100755)
 # Replace the superseded full GUI duplicate with an alias to the new GUI.
 alias='opt/voice-gui-display/xiangqi-gui-display-1080'
 generated[alias]=entry(alias,b'/usr/bin/xiangqi-pikafish-gui',0o120777)
 assembled=[]
 for name,row in effective.items():assembled.append(generated.pop(name,base[row['start']:row['end']]))
 assembled+=list(generated.values())+[entry('TRAILER!!!',b'',0)]
 rootfs=b''.join(assembled);rootfs+=b'\0'*((-len(rootfs))%512)
 assert len(rootfs)<0x1000000,('Rootfs exceeds reserved16MiB',len(rootfs))
 final={r['name'].removeprefix('./'):r for r in cpio_entries(rootfs)}
 assert len(final)==len(cpio_entries(rootfs)),'Duplicate archive entries'
 for name,h in hashes.items():assert final[name]['sha256']==h
 for name,row in effective.items():
  if name not in replacements and name not in ['etc/init.d/S95pikafish',alias]:assert final[name]['sha256']==row['sha256'],name
 (sd/'rootfs.cpio').write_bytes(rootfs)
 for n in ['Image','Image.mmode','fw_jump.bin','soc.dtb','mmode.dtb','pikafish.pff','pikafish.atk']:shutil.copy2(ROOT/'linux/boot'/n,sd/n)
 dts=(ROOT/'linux/soc.dts').read_text(encoding='utf-8-sig')
 dts,count=re.subn(r'linux,initrd-end\s*=\s*<0x[0-9a-fA-F]+>',f'linux,initrd-end = <0x{0x03000000+len(rootfs):08x}>',dts);assert count==1
 (support/'soc.dts').write_text(dts,newline='\n')
 subprocess.run(['wsl','-d','pikafish-verify','--','dtc','-I','dts','-O','dtb','-o',wsl_path(sd/'soc.dtb'),wsl_path(support/'soc.dts')],check=True)
 shutil.copy2(sd/'soc.dtb',sd/'mmode.dtb');blob=(sd/'soc.dtb').read_bytes();props=fdt_properties(blob)
 get=lambda key:struct.unpack_from('>I',blob,props[key][0])[0]
 assert get('/chosen/linux,initrd-end')==0x03000000+len(rootfs)
 assert get('/cpus/timebase-frequency')==get('/cpus/cpu@0/clock-frequency')==cpu
 assert any('voice-accel@1fe00800' in key for key in props)
 boot=support/'bootloader';boot.mkdir()
 for name in ['runtime.c','sd_native.c','fat_ro.c','crc32_fast.c','soc.h','sd.h','fat_ro.h','crc32_fast.h']:shutil.copy2(ROOT/'sw/bootloader'/name,boot/name)
 prefix='PIKAFISH_BATCH60' if a.batch60 else 'VOICE_NNUE'
 loader=(ROOT/'scripts/cpu80_sd/loader.c').read_text().replace('!= 80000000u','!= '+str(cpu)+'u').replace('CPU80_SD_',prefix+'_SD_')
 loader=loader.replace('cpu=80000000 sys=49500000 ratio=99/160','cpu='+str(cpu)+' sys=49500000')
 (support/'loader.c').write_text(loader,newline='\n')
 test=(ROOT/'scripts/cpu80_sd/host_test.c').read_text().replace('?75000000u:80000000u','?'+str(cpu-1000000)+'u:'+str(cpu)+'u')
 (support/'host_test.c').write_text(test,newline='\n')
 shutil.copy2(ROOT/'linux/boot/v2_1_sd/source/start.S',support/'start.S')
 (support/'link.ld').write_text((ROOT/'linux/boot/v2_1_sd/source/link.ld').read_text().replace('ORIGIN = 0x01000000','ORIGIN = 0x00000000'))
 manifest=dict(status='VOICE_NNUE_PREPARED_BOOT_INPUTS_UNTESTED',cpu_hz=cpu,sys_hz=49500000,
  clock_sha256=sha(ROOT/'config/clocks.json'),display=dict(width=1920,height=1080,pixel_hz=74250000,refresh_hz=30,theme='light'),
  candidate_run_id=None,candidate_bitstream_sha256=None,board_tested=False,
  batch60=a.batch60,batch_default=a.batch60,loader_prefix=prefix,
  rootfs_base_sha256=hashlib.sha256(base).hexdigest(),runtime_sha256=hashes,rootfs_bytes=len(rootfs),
  parent_kit_manifest_sha256=sha(a.base_kit/'manifest.json') if a.base_kit else None,
  pipeline_integration_sha256=receipt.get('pipeline_integration_sha256'),
  sd_root_files={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sd.iterdir()})
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps({'status':manifest['status'],'rootfs_bytes':len(rootfs),'headroom':0x1000000-len(rootfs)}))
if __name__=='__main__':main()
