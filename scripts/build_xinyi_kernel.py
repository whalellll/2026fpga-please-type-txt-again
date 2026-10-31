"""Build CPU60 kernel privately; no media writes or FPGA access."""
from pathlib import Path
import argparse
import hashlib
import json
import shlex
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]

def linux(path):
    value = path.resolve().as_posix()
    assert value[1:3] == ':/'
    return '/mnt/' + value[0].lower() + value[2:]

def digest(path):
    return hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--distribution', default='Ubuntu-22.04')
    p.add_argument('--archive', type=Path, default=ROOT/'build/picture-roi-prep-20261019/downloads/linux-5.14.tar.xz')
    p.add_argument('--base-config', type=Path, default=ROOT/'build/picture-roi-prep-20261019/kernel-r01/kernel.config')
    p.add_argument('--timeout-seconds', type=int, default=900)
    a = p.parse_args()
    out = a.output.resolve()
    assert out.is_relative_to(ROOT/'build') and not out.exists()
    assert 60 <= a.timeout_seconds <= 1800
    inputs = [ROOT/'linux/mac_accel'/name for name in ['kernel/pango_mac.c',
              'kernel/pango_mac_copy_chunks.h', 'kernel/pango_mac_io32.h', 'kernel/pango_vision_io_modes.h',
              'pango_mac_uapi.h', 'linux-5.14-conv-integration.patch']]
    inputs += [ROOT/'linux/audio'/name for name in ['kernel/pango_audio.c', 'pango_audio_uapi.h']]
    inputs += [ROOT/'linux/voice_accel'/name for name in ['kernel/pango_voice.c',
               'pango_voice_uapi.h', 'kernel/Kconfig', 'kernel/Makefile']]
    inputs += [ROOT/'linux/picture_new'/name for name in ['build_kernel_cpu60.sh',
               'platform/cpu60.dts', 'platform/display.json']]
    inputs += [a.archive, a.base_config, Path(__file__)]
    before = {str(path.resolve()): digest(path) for path in inputs}
    work = '/var/tmp/xinyi-kernel-'+uuid.uuid4().hex
    log_path = out.parent/(out.name+'.build.log')
    assert not log_path.exists()
    command = ['timeout', '--kill-after=5', str(a.timeout_seconds), 'sh',
               linux(ROOT/'linux/picture_new/build_kernel_cpu60.sh'), linux(ROOT),
               linux(a.archive), linux(a.base_config), linux(out), work]
    with log_path.open('wb') as log:
        proc = subprocess.run(['wsl.exe', '-d', a.distribution, '--', *command],
                              stdout=log, stderr=subprocess.STDOUT, timeout=a.timeout_seconds+60)
    assert proc.returncode == 0, log_path.read_text(errors='replace')[-5000:]
    assert all(digest(Path(path)) == sha for path, sha in before.items()), 'source changed during build'
    record = dict(status='PASS', hardware_used=False, software_only=True, source_stable=True,
                  scope='CPU60 V321/dedicated NNUE/audio/voice drivers; DTS template, not a bound boot kit.',
                  native_work=work, inputs_sha256=before,
                  outputs_sha256={path.name: digest(path) for path in out.iterdir() if path.is_file()},
                  limitations='No board boot/recognition/timing acceptance. Rebind DT initrd end to final rootfs before deployment.')
    (out/'result.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    print('XINYI_CPU60_PRIVATE_KERNEL_BUILD_PASS_NOT_BOARD')

if __name__ == '__main__':
    main()
