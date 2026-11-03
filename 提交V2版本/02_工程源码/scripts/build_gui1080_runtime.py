"""Prepare a complete1080p runtime candidate and test its real SD loader; no media access."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,re,shutil,struct,subprocess,sys
from build_cpu80_conv_sd import cpio_entries,fdt_properties,wsl_path

ROOT=Path(__file__).resolve().parents[1]
GUI='583c94b4b60e508933b18d0d267e9054a13d5ac7e84f7559e1f3b7ad5998e448'
KERNEL='3ed55853869ff00401b112d28c61687d1b22161e0518afe6d26351d03859d770'
OLD_GUI='03b4e1f78a858cc9cb9fafa113438089ec479951975062d298afa7fc6772e8a4'
INIT='etc/init.d/S95pikafish'
GUI_PATH='opt/voice-gui-display/xiangqi-gui-display-1080'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,value):p.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
def body(data,r):
 off=r['start']+110+r['fields'][11];off=(off+3)&~3
 return data[off:off+r['bytes']]
def entry(name,data,mode):
 name=name.encode()+b'\0';fields=[0,mode,0,0,1,0,len(data),0,0,0,0,len(name),0]
 raw=b'070701'+b''.join(f'{v:08x}'.encode() for v in fields)+name
 raw+=b'\0'*((-len(raw))%4);raw+=data;return raw+b'\0'*((-len(raw))%4)
def compose(data,gui):
 assert hashlib.sha256(gui).hexdigest()==GUI,'Unselected GUI binary'
 rows=cpio_entries(data);scripts=[r for r in rows if r['name'].removeprefix('./')==INIT]
 assert scripts and scripts[-1]['sha256']=='64ba014f6c4d54928a09753226fd16dca718018b01ccd5201d7ae3feb661a916','Unexpected base autostart'
 assert not any(r['name'].removeprefix('./')==GUI_PATH for r in rows),'Already modified base'
 script=body(data,scripts[-1]).decode('utf-8')
 anchor='check_hash '+OLD_GUI+' ./xiangqi-gui-display-v3'
 assert script.count(anchor)==1
 script=script.replace(anchor,'cp /'+GUI_PATH+' ./xiangqi-gui-display-v3\ncheck_hash '+GUI+' ./xiangqi-gui-display-v3\necho GUI1080_LIGHT_RUNTIME_SELECTED >/dev/console')
 trailer=rows[-1];assert trailer['name']=='TRAILER!!!'
 result=data[:trailer['start']]+entry(GUI_PATH,gui,0o100755)+entry(INIT,script.encode(),0o100755)+data[trailer['start']:trailer['end']]
 result+=b'\0'*((-len(result))%512)
 assert len(result)<0x01000000,'Rootfs exceeds reserved16MiB load window'
 new=cpio_entries(result)
 assert [(r['name'],r['fields'],r['sha256']) for r in new[:len(rows)-1]]==[(r['name'],r['fields'],r['sha256']) for r in rows[:-1]],'Base archive changed'
 assert new[-3]['name']==GUI_PATH and new[-3]['sha256']==GUI
 assert new[-2]['name']==INIT and new[-2]['fields'][1]&0o111
 return result

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--work',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--distro',default='pikafish-verify');a=ap.parse_args()
 work=a.work.resolve();out=a.output.resolve();assert not work.exists() and not out.exists();work.mkdir(parents=True)
 base=ROOT/'artifacts/cpu80_audio_service_20261022/sd-kit';manifest=read(base/'manifest.json')
 for n,item in manifest['sd_root_files'].items():assert sha(base/'sd-root'/n)==item['sha256'],n
 assert sha(base/'sd-root/Image')==KERNEL
 gui=ROOT/'artifacts/gui1080_light_20261022/xiangqi-pikafish-gui-display';assert sha(gui)==GUI
 prepared=work/'inputs';shutil.copytree(base,prepared,ignore=shutil.ignore_patterns('*.o','*.img','host-test','rv32-test','*.elf','*.map'))
 for name in ['fat_ro.c','fat_ro.h']:
  shutil.copy2(ROOT/'sw/bootloader'/name,prepared/'support/bootloader'/name)
 sd=prepared/'sd-root';rootfs=compose((sd/'rootfs.cpio').read_bytes(),gui.read_bytes());(sd/'rootfs.cpio').write_bytes(rootfs)
 source=ROOT/'linux/soc.dts';dts=source.read_text(encoding='utf-8-sig')
 dts,count=re.subn(r'linux,initrd-end\s*=\s*<0x[0-9a-fA-F]+>',f'linux,initrd-end = <0x{0x03000000+len(rootfs):08x}>',dts);assert count==1
 source.write_bytes(dts.encode('utf-8'))
 command=['wsl.exe','-d',a.distro,'--','dtc','-I','dts','-O','dtb','-o',wsl_path(sd/'soc.dtb'),wsl_path(source)]
 with (work/'dtc.log').open('xb') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
 shutil.copy2(sd/'soc.dtb',sd/'mmode.dtb');blob=(sd/'soc.dtb').read_bytes();props=fdt_properties(blob)
 get=lambda key:struct.unpack_from('>I',blob,props[key][0])[0]
 assert get('/chosen/linux,initrd-end')==0x03000000+len(rootfs)
 assert get('/cpus/timebase-frequency')==get('/cpus/cpu@0/clock-frequency')==80000000
 assert any(key.endswith('/framebuffer@1b800000/reg') and blob[off:off+size]==struct.pack('>II',0x1b800000,0x800000) for key,(off,size) in props.items())
 manifest.update(status='GUI1080_PREPARED_BOOT_INPUTS_UNTESTED',parent_candidate_run_id=manifest['candidate_run_id'],parent_candidate_bitstream_sha256=manifest['candidate_bitstream_sha256'],candidate_run_id=None,candidate_bitstream_sha256=None,display=dict(width=1920,height=1080,pixel_hz=148500000,theme='light'),gui_sha256=GUI)
 manifest['sd_root_files']={n:dict(bytes=(sd/n).stat().st_size,sha256=sha(sd/n)) for n in manifest['sd_root_files']};write(prepared/'manifest.json',manifest)
 kernel=work/'kernel-reference';kernel.mkdir();shutil.copy2(sd/'Image',kernel/'Image');shutil.copy2(ROOT/'docs/validation/cpu80-audio-service-20261022/kernel-01/build.json',kernel/'build.json')
 with (work/'loader-tests.log').open('xb') as log:subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scripts/linux/assemble_audio_service_sd.py'),'--base-kit',str(prepared),'--kernel',str(kernel),'--output',str(out),'--distro',a.distro,'--gui1080'],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1800)
 result=read(out/'manifest.json');assert result['status']=='GUI1080_CPU80_RUNTIME_18_OFFLINE_TESTS_PASS_NATIVE_BOARD_PENDING' and len(result['tests'])==18
 for n in result['sd_root_files']:shutil.copy2(out/'sd-root'/n,ROOT/'linux/boot'/n)
 write(work/'result.json',dict(status='GUI1080_RUNTIME_CPIO_DTB_18_LOADER_TESTS_PASS_NO_BOARD',utc=datetime.now(timezone.utc).isoformat(),output=str(out),gui_sha256=GUI,kernel_sha256=KERNEL,rootfs_sha256=sha(out/'sd-root/rootfs.cpio'),rootfs_bytes=len(rootfs),source_dts_sha256=sha(source),sd_manifest_sha256=sha(out/'manifest.json'),new_hardware_run=None,physical_media_written=False,board_tested=False))
 print('GUI1080_RUNTIME_CPIO_DTB_18_LOADER_TESTS_PASS_NO_BOARD',flush=True)
if __name__=='__main__':main()
