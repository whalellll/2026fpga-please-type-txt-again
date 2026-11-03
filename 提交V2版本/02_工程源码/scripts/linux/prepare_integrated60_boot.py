"""Prepare original-model timing boot files, away from production and SD."""
from pathlib import Path
import argparse,hashlib,json,re,shutil,struct,subprocess,sys,tarfile
R=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(R/'scripts'),str(Path(__file__).resolve().parent)]
from build_cpu80_conv_sd import cpio_entries,fdt_properties,wsl_path
from prepare_voice_nnue_boot import entry
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

RUNNER='''#!/bin/sh
set -u
mkdir -p /tmp/integrated60-bench
cd /tmp/integrated60-bench
cd /opt/integrated60/assets || exit 1
failures=0
export NNUE_VECTORS=/opt/pikafish/cpu75-nnue.vectors
run_case() {
 label=$1; limit=$2; shift 2
 echo "TIMING_BEGIN $label"
 /usr/bin/timeout "$limit" "$@" >"/tmp/integrated60-bench/$label.log" 2>&1
 rc=$?
 cat "/tmp/integrated60-bench/$label.log"
 echo "TIMING_END $label rc=$rc"
 if [ "$rc" != 0 ]; then
  if [ "$label" = pikafish-hw ] && [ "$rc" = 2 ] && grep -q NNUE_LATENCY_CORRECTNESS_PASS "/tmp/integrated60-bench/$label.log"; then :
  else failures=$((failures+1)); fi
 fi
}
echo INTEGRATED60_TIMING_BEGIN cpu=60000000 sys=49500000 original_weights=1 synthetic_inputs=1
for duration in 500 1000 2000; do
 for backend in cpu mac; do
  run_case "voice-$duration-$backend" 300 /usr/bin/xqvoice-small-cnn /opt/voice2/balanced24.bin "voice-$duration.wav" /dev/null "$backend" wav
 done
done
for backend in cpu vision32; do
 run_case "classifier-$backend" 300 /usr/bin/picture-new-bench classifier classifier.xqm classifier.f32 1 "$backend" 3
 run_case "board-$backend" 600 /usr/bin/picture-new-bench board board.xqm board.f32 1 "$backend" 1
 run_case "classifier32-$backend" 600 /usr/bin/picture-new-bench classifier classifier.xqm classifier32.f32 32 "$backend" 1
done
run_case detector-vision32 1800 /usr/bin/picture-new-bench detector detector.xqm detector.f32 1 vision32 1
if [ "${XQ_DETECTOR_CPU:-1}" = 1 ]; then
 run_case detector-cpu 1800 /usr/bin/picture-new-bench detector detector.xqm detector.f32 1 cpu 1
fi
run_case pikafish-cpu 600 env PIKAFISH_STAGEA_ACCEL=0 PIKAFISH_STAGEB_ACCEL=0 PIKAFISH_NNUE_PIPELINE=0 NNUE_REQUIRE_HW=0 NNUE_SAMPLES=20 /usr/bin/pikafish-nnue-latency-clint
run_case pikafish-hw 600 env PIKAFISH_MAC_REQUIRE_DRIVER=1 PIKAFISH_STAGEA_ACCEL=1 PIKAFISH_STAGEB_ACCEL=1 PIKAFISH_NNUE_PIPELINE=1 NNUE_REQUIRE_HW=1 NNUE_SAMPLES=20 /usr/bin/pikafish-nnue-latency-clint
echo "INTEGRATED60_TIMING_DONE failures=$failures"
[ "$failures" = 0 ]
'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--backup',type=Path,required=True);p.add_argument('--assets',type=Path,required=True);p.add_argument('--bench',type=Path,required=True);p.add_argument('--timeout-tool',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 p.add_argument('--candidate',type=Path,default=R/'artifacts/integrated60_20261024')
 p.add_argument('--voice-runtime',type=Path)
 a=p.parse_args()
 a.output.mkdir(parents=True,exist_ok=False);sd=a.output/'sd-root';support=a.output/'support';sd.mkdir();support.mkdir()
 old=json.loads((a.backup/'manifest.json').read_text());assert old['status']=='SD_BASE_INPUTS_BACKED_UP_NO_SD_WRITES'
 for n,v in old['files'].items():assert sha(a.backup/'sd-root'/n)==v['sha256']
 matched=R/'artifacts/integrated60_20261024/runtime-inputs';mi=json.loads((matched/'manifest.json').read_text())
 for n,v in mi['files'].items():assert sha(matched/n)==v['sha256']
 model=json.loads((a.assets/'manifest.json').read_text());assert not model['synthetic_weights']
 bench=json.loads((a.bench/'result.json').read_text());assert bench['status']=='ORIGINAL_THREE_GRAPHS_HOST_CPU_AND_RV32_LOAD_PASS_NOT_BOARD'
 assert sha(a.bench/'picture-new-bench')==bench['outputs_sha256']['picture-new-bench']
 replacements={
  'usr/bin/xiangqi-pikafish-gui':matched/'xiangqi-pikafish-gui-display',
  'usr/bin/pikafish':matched/'pikafish-rv32',
  'usr/bin/pikafish-pipeline-search':matched/'pikafish-pipeline-search',
  'usr/bin/pikafish-nnue-latency-clint':matched/'pikafish-nnue-pipeline-latency',
  'usr/bin/xqvoice-small-cnn':matched/'xqvoice-small-cnn',
  'usr/bin/picture-new-infer':matched/'picture-new-infer',
  'usr/bin/picture-new-bench':a.bench/'picture-new-bench',
  'opt/voice2/balanced24.bin':matched/'balanced24.bin',
  'usr/bin/timeout':a.timeout_tool}
 if a.voice_runtime:
  runtime=json.loads((a.voice_runtime/'result.json').read_text());assert runtime['status']=='VOICE2_SMALL_STRICT_RV32_LINUX_BUILD_PASS_NOT_BOARD'
  for n,h in runtime['inputs_sha256'].items():assert sha(R/n)==h,n
  assert sha(a.voice_runtime/'xqvoice-small-cnn')==runtime['binary_sha256']
  for name in ['voice-stream-host-03','voice-stream-rv32-02','voice-stream-model-02','voice-stream-legacy-wav-02']:
   check=json.loads((R/'build'/name/'result.json').read_text());assert 'PASS' in check['status'],name
   for n,h in check['inputs_sha256'].items():
    f=Path(n);f=f if f.is_absolute() else R/f;assert sha(f)==h,(name,n)
  replacements['usr/bin/xqvoice-small-cnn']=a.voice_runtime/'xqvoice-small-cnn'
 base=(a.backup/'sd-root/rootfs.cpio').read_bytes();rows=cpio_entries(base);effective={r['name'].removeprefix('./'):r for r in rows if r['name']!='TRAILER!!!'}
 # Retire only these incompatible legacy clients in this derived benchmark
 # image. The original complete archive remains in the verified PC backup.
 retire={'usr/bin/pikafish-stageb-position-accept','usr/bin/pikafish-driver-soak','usr/bin/pango-mac-conv-compute-test','usr/bin/pango-mac-conv-window-test'}
 removed={n:effective[n]['sha256'] for n in retire if n in effective}
 generated={n:entry(n,f.read_bytes(),0o100755 if n.startswith('usr/bin/') else 0o100644) for n,f in replacements.items()}
 for n in ['opt/voice2','opt/integrated60','opt/integrated60/assets']:
  if n not in effective:generated[n]=entry(n,b'',0o40755)
 with tarfile.open(a.assets/'timing-assets.tar.gz') as t:
  for member in t.getmembers():
   assert member.isfile() and member.name==Path(member.name).name
   n='opt/integrated60/assets/'+member.name
   generated[n]=entry(n,t.extractfile(member).read(),0o100644)
 init='''#!/bin/sh
[ "${1:-}" = start ] || exit 0
echo INTEGRATED60_BENCH_READY cpu=60000000 sys=49500000 original_picture_weights=1 voice=balanced24 >/dev/console
echo "Timing mode: GUI and old SD77 voice service are idle. Run run-integrated60-bench." >/dev/console
'''
 generated['etc/init.d/S95pikafish']=entry('etc/init.d/S95pikafish',init.encode(),0o100755)
 generated['usr/bin/run-integrated60-bench']=entry('usr/bin/run-integrated60-bench',RUNNER.encode(),0o100755)
 if a.voice_runtime:
  voice_runner='''#!/bin/sh
set -eu
cd /opt/integrated60/assets
for ms in 500 1000 2000; do
 for mode in wav-batch wav-stream; do
  /usr/bin/timeout 30 /usr/bin/xqvoice-small-cnn /opt/voice2/balanced24.bin "voice-$ms.wav" /dev/null mac "$mode"
 done
done
'''
  generated['usr/bin/run-voice-stream-bench']=entry('usr/bin/run-voice-stream-bench',voice_runner.encode(),0o100755)
 gui='''#!/bin/sh
cd /tmp || exit 1
export PIKAFISH_MAC_REQUIRE_DRIVER=1 PIKAFISH_STAGEA_ACCEL=1 PIKAFISH_STAGEB_ACCEL=1 PIKAFISH_NNUE_PIPELINE=1
exec /usr/bin/xiangqi-pikafish-gui
'''
 generated['usr/bin/start-integrated60-gui']=entry('usr/bin/start-integrated60-gui',gui.encode(),0o100755)
 data=[]
 for n,row in effective.items():
  if n not in retire:data.append(generated.pop(n,base[row['start']:row['end']]))
 data+=list(generated.values())+[entry('TRAILER!!!',b'',0)]
 # Linux newc unpack needs parent directories before their children.
 rootfs=b''.join(data)
 ordered=cpio_entries(rootfs)
 ordered.sort(key=lambda r:(r['name']=='TRAILER!!!',r['name'].count('/'),r['name']))
 rootfs=b''.join(rootfs[r['start']:r['end']] for r in ordered)
 rootfs+=b'\0'*((-len(rootfs))%512)
 # Only extend within free DDR below official PFF1 at0x10000000. CLINT,
 # kernel, OpenSBI, model and DMA regions are disjoint from this32MiB cap.
 assert len(rootfs)<0x2000000 and 0x03000000+len(rootfs)<0x10000000,('Rootfs exceeds safe32MiB boot range',len(rootfs))
 final=cpio_entries(rootfs);names={r['name'].removeprefix('./'):r for r in final};assert len(names)==len(final)
 assert names['opt/pikafish/cpu75-nnue.vectors']['bytes']==96
 assert names['opt/pikafish/stageb-mac.bin']['bytes']==593920
 seen={'.'}
 for row in final:
  n=row['name'].removeprefix('./')
  if n=='TRAILER!!!':continue
  parent=str(Path(n).parent).replace('\\','/')
  assert parent in seen,('CPIO parent must precede child',n,parent)
  if row['fields'][1]&0o170000==0o040000:seen.add(n)
 for n,f in replacements.items():assert names[n]['sha256']==sha(f)
 (sd/'rootfs.cpio').write_bytes(rootfs)
 for n in ['Image','fw_jump.bin']:shutil.copyfile(matched/n,sd/n)
 for n in ['Image.mmode','pikafish.pff','pikafish.atk']:shutil.copyfile(a.backup/'sd-root'/n,sd/n)
 # Official models must match the retained official source copies as well.
 for n in ['pikafish.pff','pikafish.atk']:assert sha(sd/n)==sha(R/'linux/boot'/n)
 dts=(R/'linux/soc.dts').read_text(encoding='utf-8-sig');dts,c=re.subn(r'linux,initrd-end\s*=\s*<0x[0-9a-fA-F]+>',f'linux,initrd-end = <0x{0x03000000+len(rootfs):08x}>',dts);assert c==1
 (support/'soc.dts').write_bytes(dts.encode())
 subprocess.run(['wsl.exe','-d','pikafish-verify','--','dtc','-I','dts','-O','dtb','-o',wsl_path(sd/'soc.dtb'),wsl_path(support/'soc.dts')],check=True)
 shutil.copyfile(sd/'soc.dtb',sd/'mmode.dtb');blob=(sd/'soc.dtb').read_bytes();props=fdt_properties(blob)
 get=lambda key:struct.unpack_from('>I',blob,props[key][0])[0]
 assert get('/chosen/linux,initrd-end')==0x03000000+len(rootfs)
 assert get('/cpus/timebase-frequency')==get('/cpus/cpu@0/clock-frequency')==60000000
 boot=support/'bootloader';boot.mkdir()
 for n in ['runtime.c','sd_native.c','fat_ro.c','crc32_fast.c','soc.h','sd.h','fat_ro.h','crc32_fast.h']:shutil.copyfile(R/'sw/bootloader'/n,boot/n)
 loader=(R/'scripts/cpu80_sd/loader.c').read_text().replace('!= 80000000u','!= 60000000u').replace('CPU80_SD_','VOICE_NNUE_SD_').replace('cpu=80000000 sys=49500000 ratio=99/160','cpu=60000000 sys=49500000 ratio=33/40')
 (support/'loader.c').write_bytes(loader.encode())
 test=(R/'scripts/cpu80_sd/host_test.c').read_text().replace('?75000000u:80000000u','?59000000u:60000000u')
 (support/'host_test.c').write_bytes(test.encode())
 shutil.copyfile(R/'linux/boot/v2_1_sd/source/start.S',support/'start.S')
 (support/'link.ld').write_bytes((R/'linux/boot/v2_1_sd/source/link.ld').read_text().replace('ORIGIN = 0x01000000','ORIGIN = 0x00000000').encode())
 bit=json.loads((a.candidate/'manifest.json').read_text());assert bit['sta_pass'] and (bit['independent_review_pass'] or bit['strict_original_flow_pass'])
 assert sha(a.candidate/'soc_top.sbit')==bit['bitstream']['sha256']
 manifest=dict(status='INTEGRATED60_PREPARED_BOOT_INPUTS_UNTESTED',cpu_hz=60000000,sys_hz=49500000,sbi_ratio=[33,40],display=dict(width=1920,height=1080,pixel_hz=74250000,refresh_hz=30,theme='light'),
  clock_sha256=sha(R/'config/clocks.json'),candidate_run_id=bit['run_id'],candidate_bitstream_sha256=bit['bitstream']['sha256'],
  candidate_manifest_sha256=sha(a.candidate/'manifest.json'),candidate_manifest_path=a.candidate.as_posix(),original_picture_weights=True,voice_stream_enabled=bool(a.voice_runtime),
  timing_assets_manifest_sha256=sha(a.assets/'manifest.json'),timing_model_hashes=model['models'],runtime_sha256={n:sha(f) for n,f in replacements.items()},
  base_rootfs_sha256=sha(a.backup/'sd-root/rootfs.cpio'),retired_legacy_entries=removed,rootfs_bytes=len(rootfs),
  sd_root_files={f.name:dict(bytes=f.stat().st_size,sha256=sha(f)) for f in sd.iterdir()},board_tested=False,physical_media_written=False,formal_delivery=False)
 (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(dict(status=manifest['status'],rootfs_bytes=len(rootfs),headroom=0x2000000-len(rootfs))))
if __name__=='__main__':main()
