"""Rebuild a software-only kernel candidate, retaining its native tree and logs."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,subprocess,traceback

root=Path(__file__).resolve().parents[2]
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--output',type=Path,required=True)
ap.add_argument('--archive',type=Path,required=True)
ap.add_argument('--base-image',type=Path,required=True)
ap.add_argument('--distro',default='pikafish-verify')
ap.add_argument('--jobs',type=int,default=2)
a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
assert 1<=a.jobs<=4
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def linux(p):
    s=p.resolve().as_posix();assert s[1:3]==':/';return '/mnt/'+s[0].lower()+s[2:]
inputs=[a.archive,a.base_image,root/'linux/mac_accel/kernel/pango_mac.c',
        root/'linux/mac_accel/kernel/pango_mac_copy_chunks.h',root/'linux/mac_accel/pango_mac_uapi.h',
        root/'linux/mac_accel/linux-5.14-integration.patch',root/'linux/audio/kernel/pango_audio.c',
        root/'linux/audio/pango_audio_uapi.h',Path(__file__)]
assert sha(a.base_image)=='1e5580a8b63f83723a8d1c4f2017df6d2010b776a7e1c01a17bcdc67a4eeb360','Use the currently booted SD kernel as configuration reference'
record=dict(status='KERNEL_SOFTWARE_BUILD_RUNNING_NOT_BOARD',started_utc=datetime.now(timezone.utc).isoformat(),
            source_root=str(root),distro=a.distro,jobs=a.jobs,inputs_sha256={str(p.resolve()):sha(p) for p in inputs},
            native_tree='/tmp/cpu80-audio-service-20261022-k1',hardware_changed=False,pnr_started=False,board_accessed=False)
def save():(out/'build.json').write_text(json.dumps(record,indent=2)+'\n')
script=r'''#!/bin/bash
set -eu
repo=$1
output=$2
archive=$3
base_image=$4
jobs=$5
build=/tmp/cpu80-audio-service-20261022-k1
test ! -e "$build"
mkdir "$build"
tar -xJf "$archive" -C "$build"
tree="$build/linux-5.14"
printf '%s\n' "$tree" > "$output/native-tree.txt"
cp "$repo/linux/mac_accel/kernel/pango_mac.c" "$tree/drivers/misc/pango_mac.c"
cp "$repo/linux/mac_accel/kernel/pango_mac_copy_chunks.h" "$tree/drivers/misc/pango_mac_copy_chunks.h"
cp "$repo/linux/mac_accel/pango_mac_uapi.h" "$tree/include/uapi/linux/pango_mac.h"
cp "$repo/linux/audio/kernel/pango_audio.c" "$tree/drivers/misc/pango_audio.c"
cp "$repo/linux/audio/pango_audio_uapi.h" "$tree/include/uapi/linux/pango_audio.h"
patch -d "$tree" -p1 < "$repo/linux/mac_accel/linux-5.14-integration.patch"
"$tree/scripts/extract-ikconfig" "$base_image" > "$output/base.config"
test -s "$output/base.config"
cp "$output/base.config" "$tree/.config"
riscv64-linux-gnu-gcc --version > "$output/compiler-version.txt"
export KBUILD_BUILD_USER=yuu KBUILD_BUILD_HOST=yuu KBUILD_BUILD_VERSION=1
export KBUILD_BUILD_TIMESTAMP='Thu Oct 22 14:00:00 UTC 2026'
make -C "$tree" ARCH=riscv CROSS_COMPILE=riscv64-linux-gnu- olddefconfig
cp "$tree/.config" "$output/kernel.config"
cmp "$output/base.config" "$output/kernel.config"
grep -q '^CONFIG_PANGO_MAC_ACCEL=y$' "$tree/.config"
grep -q '^CONFIG_PANGO_AUDIO_CAPTURE=y$' "$tree/.config"
grep -q '^CONFIG_PREEMPT_NONE=y$' "$tree/.config"
grep -q '^CONFIG_HZ=250$' "$tree/.config"
grep -q '^CONFIG_32BIT=y$' "$tree/.config"
grep -q '^# CONFIG_RISCV_ISA_C is not set$' "$tree/.config"
grep -q '^# CONFIG_FPU is not set$' "$tree/.config"
make -C "$tree" -j"$jobs" ARCH=riscv CROSS_COMPILE=riscv64-linux-gnu- Image
cp "$tree/arch/riscv/boot/Image" "$output/Image"
cp "$tree/vmlinux" "$output/vmlinux"
cp "$tree/System.map" "$output/System.map"
"$tree/scripts/extract-ikconfig" "$output/Image" > "$output/embedded.config"
cmp "$output/kernel.config" "$output/embedded.config"
sha256sum "$tree/drivers/misc/pango_mac.c" "$tree/drivers/misc/pango_audio.c" > "$output/native-driver-sha256.txt"
printf '%s\n' AUDIO_SERVICE_KERNEL_BUILD_CONFIG_IDENTICAL_PASS_NOT_BOARD
'''
(out/'build.sh').write_text(script,encoding='utf-8',newline='\n')
save()
try:
    command=['wsl.exe','-d',a.distro,'--','bash',linux(out/'build.sh'),linux(root),linux(out),linux(a.archive),linux(a.base_image),str(a.jobs)]
    record['command']=command;save()
    with (out/'kernel.log').open('xb') as f:
        process=subprocess.Popen(command,stdout=f,stderr=subprocess.STDOUT)
        record['pid']=process.pid;save()
        try:code=process.wait(10800)
        except subprocess.TimeoutExpired:
            # Stop only the exact WSL build tree selected above; retain files.
            subprocess.run(['wsl.exe','-d',a.distro,'--','pkill','-TERM','-f','^make -C /tmp/cpu80-audio-service-20261022-k1/linux-5.14'],capture_output=True)
            raise
    assert code==0,(out/'kernel.log').read_text(errors='replace')[-2500:]
    assert b'AUDIO_SERVICE_KERNEL_BUILD_CONFIG_IDENTICAL_PASS_NOT_BOARD' in (out/'kernel.log').read_bytes()
    assert (out/'Image').stat().st_size<=a.base_image.stat().st_size+1048576
    for p,h in record['inputs_sha256'].items():assert sha(Path(p))==h,p
    record.update(status='AUDIO_SERVICE_KERNEL_CONFIG_IDENTICAL_BUILD_PASS_BOARD_PENDING',outputs_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='build.json'})
except Exception:
    record.update(status='FAILED_PRESERVED_SOFTWARE_KERNEL_NOT_PROMOTED',error=traceback.format_exc())
    raise
finally:
    record['updated_utc']=datetime.now(timezone.utc).isoformat();save();print(record['status'],flush=True)
