"""Extract the paired rootfs with its actual RV32 BusyBox; no media access."""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import argparse
import hashlib
import io
import json
import subprocess
import tarfile
import uuid

from build_cpu80_conv_sd import cpio_entries

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--kit', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    manifest_path = a.kit/'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    assert manifest['status'] == 'INTEGRATED60_RUNTIME_18_OFFLINE_TESTS_PASS_NATIVE_BOARD_PENDING'
    rootfs = a.kit/'sd-root/rootfs.cpio'
    data = rootfs.read_bytes()
    rows = cpio_entries(data)
    seen, entries = {'.'}, {}
    for row in rows:
        name = row['name'].removeprefix('./')
        if name == 'TRAILER!!!':
            continue
        path = PurePosixPath(name)
        assert not path.is_absolute() and '..' not in path.parts, name
        assert name not in entries, name
        assert str(path.parent) in seen, ('Missing prior parent', name)
        if row['fields'][1] & 0o170000 == 0o040000:
            seen.add(name)
        entries[name] = row
    expected = dict(manifest['runtime_sha256'])
    expected.update({
        'opt/voice2/balanced24.bin': '3e43041fd3e531ce130b56c0a460a1c7375420eea0e07afdf533012ae41da973',
        'opt/integrated60/assets/board.xqm': 'fbd8a4e8bcd78918a44674eb69225f7d82ac4547ac24a777ea4b4b11cf495efe',
        'opt/integrated60/assets/detector.xqm': 'd65b4b8686520ae1546d0a207c1bcb9f30efe0d40e7f5c8245c4dd11ff9ca09d',
        'opt/integrated60/assets/classifier.xqm': 'fc03674b9f73f8c0d0fffd1cbdd10b4edebccd2056740d8aeec7e472b522697f',
    })
    for name, digest in expected.items():
        assert entries[name]['sha256'] == digest, name
        if name.startswith('usr/bin/'):
            assert entries[name]['fields'][1] & 0o111 == 0o111, name
    busybox = entries['bin/busybox']
    start = busybox['end'] - ((busybox['bytes'] + 3) & ~3)
    body = data[start:start+busybox['bytes']]
    assert hashlib.sha256(body).hexdigest() == busybox['sha256']
    native = '/var/tmp/opt60-rootfs-' + uuid.uuid4().hex
    script = '''set -eu
cd "$(dirname "$0")"
chmod 755 busybox-rv32
mkdir bootstrap unpack
cd bootstrap
cpio -id --quiet --no-absolute-filenames 'lib*' 'usr/lib*' < ../rootfs.cpio
cd ..
cd unpack
/usr/bin/qemu-riscv32 -L ../bootstrap ../busybox-rv32 cpio -i 'bin*' 'etc*' 'lib*' 'opt*' 'sbin*' 'usr*' 'var*' 'tmp*' 'root*' < ../rootfs.cpio
sha256sum -c ../expected.sha256
/usr/bin/qemu-riscv32 -L ../bootstrap ../busybox-rv32 sh -n usr/bin/start-integrated60-gui
/usr/bin/qemu-riscv32 -L ../bootstrap ../busybox-rv32 sh -n etc/pikafish-batch.env
'''
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w') as tar:
        for name, content, mode in [
            ('rootfs.cpio', data, 0o644), ('busybox-rv32', body, 0o755),
            ('test.sh', script.encode(), 0o644),
            ('expected.sha256', ''.join(f'{h}  {n}\n' for n, h in expected.items()).encode(), 0o644),
        ]:
            entry = tarfile.TarInfo(name)
            entry.size, entry.mode = len(content), mode
            tar.addfile(entry, io.BytesIO(content))
    child = subprocess.run(['wsl.exe', '-d', 'pikafish-verify', '--', 'sh', '-c',
                            f'mkdir {native} && tar -xf - -C {native} && sh {native}/test.sh'],
                           input=payload.getvalue(), capture_output=True, timeout=180)
    (a.output/'test.log').write_bytes(child.stdout+child.stderr)
    assert child.returncode == 0, (child.stdout+child.stderr).decode(errors='replace')
    result = dict(status='OPT60_ACTUAL_RV32_BUSYBOX_EXTRACTION_MODELS_AND_AB_TOOLS_PASS_NOT_BOARD',
                  created_utc=datetime.now(timezone.utc).isoformat(), native_root=native,
                  rootfs_sha256=hashlib.sha256(data).hexdigest(),
                  manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                  busybox_sha256=busybox['sha256'], checked_files=expected,
                  parent_order_checked=len(entries), gui_shell_syntax=True,
                  no_physical_media_access=True, board_tested=False)
    (a.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(result['status'])


if __name__ == '__main__':
    main()
