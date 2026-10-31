"""Image-backed regression for the VOICE-only FAT writer; never accesses a card."""
from pathlib import Path
import json
import struct
import subprocess
import sys
import tempfile
import wave
import zlib

exe = Path(sys.argv[1]).resolve()

def run(*args, ok=True):
    result = subprocess.run([str(exe), *map(str, args)], capture_output=True, text=True)
    if ok and result.returncode: raise AssertionError(result.stderr + result.stdout)
    if not ok and not result.returncode: raise AssertionError('Expected rejection')
    return json.loads(result.stdout) if ok else result

with tempfile.TemporaryDirectory(prefix='voice-sd-regression-') as directory:
    root = Path(directory); disk = root / 'disk.img'
    with disk.open('wb') as f: f.truncate(40 * 1024 * 1024)
    subprocess.run(['mkfs.fat', '-F', '32', '-i', '1234abcd', str(disk)], check=True, capture_output=True)
    raw = bytearray(disk.read_bytes())
    reserved = struct.unpack_from('<H', raw, 14)[0]; fats = raw[16]; fat_size = struct.unpack_from('<I', raw, 36)[0]
    data = (reserved + fats * fat_size) * 512; cluster_bytes = raw[13] * 512
    boot = [('IMAGE', b'kernel-original'), ('ROOTFS  CPI', b'rootfs-original'),
            ('FW_JUMP BIN', b'firmware-original'), ('SOC     DTB', b'dtb-original')]
    slots = [0, 2, 3, 4]
    for index, (name, payload) in enumerate(boot):
        cluster = index + 3
        for copy in range(fats): struct.pack_into('<I', raw, (reserved + copy * fat_size) * 512 + cluster * 4, 0x0fffffff)
        entry = data + slots[index] * 32
        raw[entry:entry + 11] = name.ljust(11).encode(); raw[entry + 11] = 0x20
        struct.pack_into('<H', raw, entry + 26, cluster); struct.pack_into('<I', raw, entry + 28, len(payload))
        start = data + (cluster - 2) * cluster_bytes; raw[start:start + len(payload)] = payload
    # Valid single-entry VFAT name for the four-character CPIO extension.
    short = b'ROOTFS  CPI'; checksum = 0
    for byte in short: checksum = (((checksum & 1) << 7) + (checksum >> 1) + byte) & 255
    lfn = data + 32; raw[lfn] = 0x41; raw[lfn + 11] = 0x0f; raw[lfn + 13] = checksum
    long_name = [ord(c) for c in 'rootfs.cpio'] + [0, 0xffff]
    for offset, code in zip([1,3,5,7,9,14,16,18,20,22,24,28,30], long_name): struct.pack_into('<H', raw, lfn + offset, code)
    disk.write_bytes(raw)
    wav = root / 'capture.wav'
    with wave.open(str(wav), 'wb') as f:
        f.setparams((1, 2, 16000, 0, 'NONE', 'not compressed')); f.writeframes(b'\x20\x00' * 960000)
    meta = root / 'capture.json'; meta.write_text('{"planned_tokens":["ma","liu"],"labels_confirmed":false}\n')
    info = run('--image', disk, '--info')
    original = disk.read_bytes()
    assert info['partition_lba'] == 0 and info['volume_serial'] == 0x1234abcd
    args = ['--image', disk, '--expect-cid', info['cid'], '--expect-partition', '0',
            '--expect-volume', str(info['volume_serial']), '--save', wav, '--metadata', meta]
    run(*[('0' * 32 if str(a) == info['cid'] else a) for a in args], ok=False)
    assert disk.read_bytes() == original
    for option in ['--expect-partition', '--expect-volume']:
        wrong = list(args); position = wrong.index(option) + 1; wrong[position] = str(int(wrong[position]) + 1)
        run(*wrong, ok=False); assert disk.read_bytes() == original
    valid_wav = wav.read_bytes(); invalid_wav = bytearray(valid_wav); struct.pack_into('<I', invalid_wav, 24, 44100)
    wav.write_bytes(invalid_wav); run(*args, ok=False); assert disk.read_bytes() == original; wav.write_bytes(valid_wav)
    with wave.open(str(wav), 'wb') as f:
        f.setparams((1, 2, 16000, 0, 'NONE', 'not compressed')); f.writeframes(b'\x20\x00' * (61 * 16000))
    run(*args, ok=False); assert disk.read_bytes() == original; wav.write_bytes(valid_wav)
    first = run(*args); second = run(*args)
    assert first['wav'] == 'VOICE/REC00001.WAV' and second['wav'] == 'VOICE/REC00002.WAV'
    final = disk.read_bytes()
    assert final[:512] == original[:512]
    assert final[data:data + 5 * 32] == original[data:data + 5 * 32]
    for index, (_, payload) in enumerate(boot):
        slot = slots[index]; assert final[data + slot * 32:data + (slot + 1) * 32] == original[data + slot * 32:data + (slot + 1) * 32]
        start = data + (index + 1) * cluster_bytes
        assert final[start:start + len(payload)] == payload
        for copy in range(fats):
            offset = (reserved + copy * fat_size) * 512 + (index + 3) * 4
            assert final[offset:offset + 4] == original[offset:offset + 4]
    voice = next(final[data + i:data + i + 32] for i in range(0, cluster_bytes, 32) if final[data + i:data + i + 11] == b'VOICE      ')
    directory_cluster = (struct.unpack_from('<H', voice, 20)[0] << 16) | struct.unpack_from('<H', voice, 26)[0]
    directory = data + (directory_cluster - 2) * cluster_bytes
    entries = [final[directory + i:directory + i + 32] for i in range(0, cluster_bytes, 32)]
    file_entry = next(e for e in entries if e[:11] == b'REC00001WAV')
    cluster = (struct.unpack_from('<H', file_entry, 20)[0] << 16) | struct.unpack_from('<H', file_entry, 26)[0]
    length = struct.unpack_from('<I', file_entry, 28)[0]; loaded = bytearray()
    while cluster < 0x0ffffff8:
        start = data + (cluster - 2) * cluster_bytes; loaded.extend(final[start:start + cluster_bytes])
        cluster = struct.unpack_from('<I', final, reserved * 512 + cluster * 4)[0] & 0x0fffffff
    assert bytes(loaded[:length]) == wav.read_bytes()
    assert first['wav_crc32'] == '%08x' % (zlib.crc32(wav.read_bytes()) & 0xffffffff)
    json_entry = next(e for e in entries if e[:11] == b'REC00001JSN')
    cluster = (struct.unpack_from('<H', json_entry, 20)[0] << 16) | struct.unpack_from('<H', json_entry, 26)[0]
    json_length = struct.unpack_from('<I', json_entry, 28)[0]; loaded_json = bytearray()
    while cluster < 0x0ffffff8:
        start = data + (cluster - 2) * cluster_bytes; loaded_json.extend(final[start:start + cluster_bytes])
        cluster = struct.unpack_from('<I', final, reserved * 512 + cluster * 4)[0] & 0x0fffffff
    paired = json.loads(bytes(loaded_json[:json_length]))
    assert paired['request']['planned_tokens'] == ['ma', 'liu'] and paired['wav_crc32'] == first['wav_crc32']
    assert not paired['labels_confirmed']
    # Corrupt media and wrong geometry must be rejected without further writes.
    dirty = bytearray(final)
    for copy in range(fats):
        offset = (reserved + copy * fat_size) * 512 + 4
        struct.pack_into('<I', dirty, offset, struct.unpack_from('<I', dirty, offset)[0] & ~0x08000000)
    disk.write_bytes(dirty); run(*args, ok=False); assert disk.read_bytes() == dirty
    print('VOICE_SD_IMAGE_PASS 60s WAV append/readback, 61s rejection, wrong-CID/partition/volume/format no-write, append2, boot-protection, dirty-FAT rejection')
