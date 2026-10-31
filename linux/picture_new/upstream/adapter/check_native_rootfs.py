"""Check the complete cold-RAM initrd contents without deploying/rebooting."""
import argparse, gzip, hashlib, io, json, struct, tarfile
from pathlib import Path, PurePosixPath

p = argparse.ArgumentParser()
p.add_argument('--rootfs', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
assert not a.out.exists()
raw = a.rootfs.read_bytes()
assert len(raw) <= 0x1000000
entries = {}
at = 0
while True:
    assert raw[at:at+6] == b'070701'
    fields = [int(raw[at+6+i*8:at+14+i*8], 16) for i in range(13)]
    namesize, size = fields[11], fields[6]
    name = raw[at+110:at+110+namesize-1].decode()
    start = (at+110+namesize+3) & ~3
    assert start+size <= len(raw)
    if name == 'TRAILER!!!':
        break
    entries[name.lstrip('./')] = (raw[start:start+size], fields[1])
    at = (start+size+3) & ~3
for name in ('usr/bin/xiangqi-pikafish', 'usr/bin/xiangqi-pikafish-gui', 'usr/bin/xq-camera-exec'):
    assert entries[name][1] & 0o111
for name in ('usr/bin/xiangqi-pikafish-gui', 'usr/bin/xq-camera-exec'):
    data = entries[name][0]
    assert data[:6] == b'\x7fELF\x01\x01'
    assert struct.unpack_from('<H', data, 18)[0] == 243
    assert struct.unpack_from('<I', data, 36)[0] == 0
config = entries['etc/xq-picture.conf'][0].decode()
assert 'XQ_MODEL_BACKEND=rv32-driver-quantized-mac\n' in config
assert 'XQ_MODEL_WORKER=/run/xq-native/xq-native-worker\n' in config
assert 'PIKAFISH_MAC_REQUIRE_DRIVER=1\n' in config
assert 'XQ_PICTURE_MODE=stub' not in config
launcher = entries['usr/bin/xiangqi-pikafish'][0].decode()
assert 'exec /usr/bin/xq-camera-exec' in launcher
assert any(b'/usr/bin/xiangqi-pikafish' in data for name,(data,mode) in entries.items()
           if name.startswith('etc/init.d/'))
files = {}
with tarfile.open(fileobj=io.BytesIO(entries['opt/xq-native/native-models.tar.gz'][0]),mode='r:gz') as tf:
    for member in tf.getmembers():
        path = PurePosixPath(member.name)
        assert member.isfile() and not path.is_absolute() and '..' not in path.parts
        files[member.name] = tf.extractfile(member).read()
manifest = json.loads(files['xq-native/ram_manifest.json'])
assert set(files) == {'xq-native/'+name for name in manifest['files']} | {'xq-native/ram_manifest.json'}
for name, item in manifest['files'].items():
    data = files['xq-native/'+name]
    assert len(data) == item['bytes'] and hashlib.sha256(data).hexdigest() == item['sha256']
worker = files['xq-native/xq-native-worker']
assert worker[:6] == b'\x7fELF\x01\x01' and struct.unpack_from('<I',worker,36)[0] == 0
result = dict(status='PASS', scope='Complete native initrd packaging; NOT cold-boot/device/M0 acceptance',
    raw_bytes=len(raw), rootfs_sha256=hashlib.sha256(raw).hexdigest(),
    files=manifest['files'], gui_sha256=hashlib.sha256(entries['usr/bin/xiangqi-pikafish-gui'][0]).hexdigest(),
    model_count=3, strict_driver=True, sd_written=False)
a.out.write_text(json.dumps(result,indent=2)+'\n')
print('NATIVE_ROOTFS_CONTENTS_PASS models=3 strict_driver=true cold_boot_validated=false')
