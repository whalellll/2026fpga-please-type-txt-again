"""Keep a Linux build filesystem and its mount point inside the FPGA workspace."""
import argparse
import json
import os
from pathlib import Path
import subprocess

WORKSPACE = Path('/mnt/g/fpga').resolve()
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('action', choices=['prepare', 'unmount'])
parser.add_argument('--image', type=Path, required=True)
parser.add_argument('--mount', type=Path, required=True)
parser.add_argument('--mib', type=int, default=6144)
parser.add_argument('--uid', type=int, default=1000)
parser.add_argument('--gid', type=int, default=1000)
args = parser.parse_args()
image, target = args.image.resolve(), args.mount.resolve()
assert os.geteuid() == 0, 'Loop mount requires root inside WSL'
assert image.is_relative_to(WORKSPACE) and target.is_relative_to(WORKSPACE)
assert image.parent == target.parent and image.name == 'kernel.ext4' and target.name == 'kernel'
assert 64 <= args.mib <= 6144 and args.uid >= 0 and args.gid >= 0

def run(*command, check=True):
    return subprocess.run(command, check=check, capture_output=True, text=True, timeout=180)

if args.action == 'prepare':
    assert image.parent.is_dir() and not image.exists()
    assert not target.exists() or (target.is_dir() and not any(target.iterdir()))
    assert run('findmnt', '-n', '-M', str(target), check=False).returncode != 0
    with image.open('xb') as output:
        output.truncate(args.mib * 1024 * 1024)
    run('mkfs.ext4', '-q', '-F', '-m', '0', str(image))
    target.mkdir(exist_ok=True)
    run('mount', '-o', 'loop,nodev,nosuid', str(image), str(target))
    os.chown(target, args.uid, args.gid)
    record = dict(status='WORKSPACE_EXT4_MOUNTED', image=str(image), mount=str(target),
                  maximum_bytes=args.mib * 1024 * 1024, uid=args.uid, gid=args.gid)
else:
    source = run('findmnt', '-n', '-o', 'SOURCE', '-M', str(target)).stdout.strip()
    assert source.startswith('/dev/loop') and source.removeprefix('/dev/loop').isdigit()
    backing = Path('/sys/block') / Path(source).name / 'loop/backing_file'
    assert Path(backing.read_text().strip()).resolve() == image, 'Unexpected mounted filesystem owner'
    run('sync', '-f', str(target))
    run('umount', str(target))
    record = dict(status='WORKSPACE_EXT4_UNMOUNTED_PRESERVED', image=str(image), mount=str(target))
(image.parent / ('filesystem-' + args.action + '.json')).write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record))
