"""Exact loader identity/clock and SD payload validation; no device access."""
import re


def contract(prefix='CPU80', cpu_hz=80000000):
    if prefix == 'CPU120':
        assert cpu_hz == 120000000, 'CPU120 loader requires exact120MHz'
        success = b'CPU120_SD_PAYLOADS_CRC_PASS cpu=120000000 sys=49500000 ratio=33/80'
    elif prefix == 'CPU80':
        assert cpu_hz == 80000000, 'CPU80 loader requires exact80MHz'
        success = b'CPU80_SD_PAYLOADS_CRC_PASS cpu=80000000 sys=49500000 ratio=99/160'
    elif prefix == 'MAIN75':
        assert cpu_hz == 75000000, 'Merged-main loader requires exact75MHz'
        success = b'MAIN75_SD_PAYLOADS_CRC_PASS cpu=75000000 sys=49500000 ratio=33/50'
    elif prefix == 'MAIN70':
        assert cpu_hz == 70000000, 'Merged-main loader requires exact70MHz'
        success = b'MAIN70_SD_PAYLOADS_CRC_PASS cpu=70000000 sys=49500000 ratio=99/140'
    elif prefix == 'PIKAFISH_BATCH60':
        assert cpu_hz == 60000000, 'Batch60 loader requires exact60MHz'
        success = b'PIKAFISH_BATCH60_SD_PAYLOADS_CRC_PASS cpu=60000000 sys=49500000'
    else:
        assert prefix == 'VOICE_NNUE' and cpu_hz in (75000000, 70000000, 60000000)
        success = (f'VOICE_NNUE_SD_PAYLOADS_CRC_PASS cpu={cpu_hz} sys=49500000' +
                   (' ratio=33/40' if cpu_hz == 60000000 else '')).encode()
    tag = prefix.encode() + b'_SD_'
    stop = (rb'(?m)^/ # |' + re.escape(tag)
            + rb'(?:CLOCK_MISMATCH|INIT_FAIL|FAT_FAIL|FILE_INVALID|LOAD_OR_CRC_FAIL)'
            + rb'|Kernel panic|sdboot returned, error')
    return tag, success, stop


def validate(data, prefix='CPU80', cpu_hz=80000000):
    tag, success, _ = contract(prefix, cpu_hz)
    # Native SD loader prints sector progress dots without a trailing newline.
    assert re.search(rb'(?m)^\.*' + re.escape(success) + rb'\r?$', data), 'Missing exact loader CRC/clock success'
    assert re.search(rb'(?m)^/ # ', data), 'No Linux root shell'
    for name in (b'fw_jump.bin', b'Image', b'rootfs.cpio', b'soc.dtb', b'pikafish.pff', b'pikafish.atk'):
        assert b'Loading ' + name in data, 'Missing SD payload load: ' + str(name)
    assert not re.search(re.escape(tag) + rb'\w*(?:FAIL|MISMATCH|INVALID)|Kernel panic', data), 'SD boot failure'
