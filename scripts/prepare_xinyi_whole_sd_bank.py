"""Pack the immutable whole-phrase SD sidecar and its exact DDR descriptor.

Only fresh private output files are created. No media/device access or DTB edits.
The paired loader must verify the complete bank CRC before booting the reserved
DTB; the reader validates descriptor/header/index/clip CRC before playback.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import zlib

from picture_workspace import ROOT, workspace_path

SHA = lambda b: hashlib.sha256(b).hexdigest()
BASE, LIMIT, COUNT = 0x04000000, 0x0f000000, 5103
HEADER, RECORD, CONFIG = 128, 16, 96
DATA_AT = (HEADER + COUNT * RECORD + 4095) & ~4095


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--pcm', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--reader-proof', type=Path, required=True)
    a = ap.parse_args()
    src, out = workspace_path(a.pcm), workspace_path(a.output)
    assert out.is_relative_to((ROOT / 'build/picture-e42-20261025').resolve())
    out.mkdir(parents=True, exist_ok=False)
    result = dict(status='FAILED_PRESERVED', hardware_used=False, media_accessed=False, dtb_changed=False)
    try:
        manifest_bytes = (src / 'manifest.json').read_bytes()
        manifest_sha = SHA(manifest_bytes)
        m = json.loads(manifest_bytes)
        assert m['complete'] and len(m['files']) == COUNT and m['maximum_samples'] <= 15360
        assert m['sample_rate'] == 16000 and m['channels'] == 1 and m['format'] == 's16le'
        proof = json.loads(workspace_path(a.reader_proof).read_bytes())
        assert proof['status'] == 'WHOLE_BANK_REAL_READER_HOST_SANITIZER_RV32_MOCK_GUARDS_ALL_KEYS_RELEASE_RECOVERY_PASS'
        for n, h in proof['source_sha256'].items():
            assert SHA((ROOT / n).read_bytes()) == h, n
        for name in ['SD_ROOT', 'rootfs/opt/xq-picture/pcm', 'source', 'evidence']:
            (out / name).mkdir(parents=True)
        (out / 'evidence/whole-manifest.json').write_bytes(manifest_bytes)
        (out / 'evidence/reader-proof.json').write_bytes(workspace_path(a.reader_proof).read_bytes())
        bank = out / 'SD_ROOT/P18VOICE.BIN'
        index = bytearray()
        rows = []
        at = DATA_AT
        previous = None
        with bank.open('xb') as f:
            f.write(bytes(DATA_AT))
            for name, row in sorted(m['files'].items(), key=lambda item: item[1]['tokens']):
                key = bytes(row['tokens'])
                assert len(key) == 4 and (previous is None or previous < key)
                previous = key
                piece = 16 <= key[0] <= 24 and 1 <= key[1] <= 9
                alternate = (1 <= key[0] <= 9 or 28 <= key[0] <= 30) and 16 <= key[1] <= 24
                assert (piece or alternate) and 25 <= key[2] <= 27 and 1 <= key[3] <= 9
                data = (src / name).read_bytes()
                assert SHA(data) == row['sha256'] and len(data) == row['samples'] * 2
                assert 0 < len(data) <= 30720 and len(data) % 2 == 0
                crc = zlib.crc32(data) & 0xffffffff
                index.extend(struct.pack('<4sIII', key, at, len(data), crc))
                f.write(data)
                pad = (-len(data)) & 3
                f.write(bytes(pad))
                rows.append(dict(tokens=list(key), offset=at, bytes=len(data), samples=len(data) // 2,
                                 crc32=f'{crc:08x}', sha256=SHA(data), source=name))
                at += len(data) + pad
            span = (at + 4095) & ~4095
            assert len(index) == COUNT * RECORD and BASE + span < LIMIT
            header = bytearray(HEADER)
            header[:8] = b'XQWBANK1'
            struct.pack_into('<12I', header, 8, 1, HEADER, 16000, 1, 1, COUNT, HEADER, RECORD,
                             DATA_AT, at, zlib.crc32(index) & 0xffffffff, 0)
            header[56:88] = bytes.fromhex(manifest_sha)
            header_index_crc = zlib.crc32(header + index) & 0xffffffff
            struct.pack_into('<I', header, 52, header_index_crc)
            f.seek(0)
            f.write(header)
            f.write(index)
        assert bank.stat().st_size == at
        cfg = bytearray(CONFIG)
        cfg[:8] = b'XQWBCFG1'
        struct.pack_into('<6I', cfg, 8, 1, BASE, span, at, header_index_crc, COUNT)
        cfg[32:64] = bytes.fromhex(manifest_sha)
        struct.pack_into('<I', cfg, 64, zlib.crc32(cfg) & 0xffffffff)
        cfg_path = out / 'rootfs/opt/xq-picture/pcm/whole-bank.cfg'
        cfg_path.write_bytes(cfg)
        (out / 'reserved-memory-reg.bin').write_bytes(struct.pack('>II', BASE, span))
        (out / 'reserved-memory-no-map.bin').write_bytes(b'')
        # Independently re-read every table record and corresponding file range.
        digest, full_crc = hashlib.sha256(), 0
        with bank.open('rb') as f:
            while block := f.read(1024 * 1024):
                digest.update(block)
                full_crc = zlib.crc32(block, full_crc)
            for i, row in enumerate(rows):
                f.seek(HEADER + i * RECORD)
                key, offset, length, crc = struct.unpack('<4sIII', f.read(RECORD))
                assert list(key) == row['tokens'] and offset == row['offset'] and length == row['bytes']
                f.seek(offset)
                data = f.read(length)
                assert SHA(data) == row['sha256'] and zlib.crc32(data) & 0xffffffff == crc
        sources = {}
        for n in [*proof['source_sha256'], 'scripts/prepare_xinyi_whole_sd_bank.py', 'scripts/picture_workspace.py']:
            data = (ROOT / n).read_bytes()
            sources[n] = SHA(data)
            p = out / 'source' / n
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        replacements = {'opt/xq-picture/pcm/whole-bank.cfg': {'path': str(cfg_path), 'mode': 0o100644,
                         'bytes': CONFIG, 'sha256': SHA(cfg)}}
        (out / 'rootfs-replacements.json').write_text(json.dumps(replacements, indent=2) + '\n')
        layout = dict(schema='xinyi-whole-sd-bank/1', status='PACKED_AND_REOPENED_ALL5103_CRC_SHA_PASS_NOT_INSTALLED',
            bank_path=str(bank), filename='P18VOICE.BIN', bytes=at, crc32=f'{full_crc & 0xffffffff:08x}',
            sha256=digest.hexdigest(), physical_base=BASE, reserved_span=span,
            reserved_end=BASE + span, rom_model_start_limit=LIMIT, index_count=COUNT,
            header_bytes=HEADER, index_offset=HEADER, index_record_bytes=RECORD, data_offset=DATA_AT,
            index_crc32=f'{zlib.crc32(index) & 0xffffffff:08x}', header_index_crc32=f'{header_index_crc:08x}',
            config_path=str(cfg_path), config_bytes=CONFIG, config_sha256=SHA(cfg),
            source_manifest_sha256=manifest_sha, source_pcm_root=str(src),
            dt_node='/reserved-memory/xinyi-whole-voice@4000000',
            sysfs_dt_node='/sys/firmware/devicetree/base/reserved-memory/xinyi-whole-voice@4000000',
            dt_reg_hex=struct.pack('>II', BASE, span).hex(), dt_no_map_bytes=0,
            required_loader_action='Load exact bankbytes to base, verify full CRC before boot; use exact new DT reservation/no-map. Never load into unreserved running Linux RAM.',
            reader_mapping='Prepare temporarily maps81920B metadata. Each clip uses at most two sequential<=32768B maps, closes/unmaps then returns one owned S16 buffer before RT.',
            physical_1000ms_pass=False, installed=False, media_accessed=False, dtb_changed=False,
            source_sha256=sources, clips=rows)
        (out / 'layout.json').write_text(json.dumps(layout, indent=2) + '\n')
        assert (src / 'manifest.json').read_bytes() == manifest_bytes
        result.update(status=layout['status'], bank={k: layout[k] for k in ['bank_path', 'bytes', 'crc32', 'sha256',
                      'physical_base', 'reserved_span', 'reserved_end', 'header_index_crc32']},
                      config_sha256=SHA(cfg), source_manifest_sha256=manifest_sha,
                      rootfs_replacements=str(out / 'rootfs-replacements.json'))
    finally:
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
