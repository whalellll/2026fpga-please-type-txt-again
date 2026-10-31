"""Archive boot evidence only; camera captures and their identifiers stay in build/."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / 'build/picture-p21-native'
DEST = REPO / 'docs/validation/picture-native-sd-20261020/boot-r03'

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def main():
    assert not DEST.exists(), 'Archive is immutable: choose a new revision'
    program = json.loads((SOURCE/'sd-cram-r03.json').read_text())
    recovery = json.loads((SOURCE/'uart-native-r07-after-user-reconnect.json').read_text())
    boot = (SOURCE/'sd-boot-20261020-r03.log').read_text()
    prior = (SOURCE/'sd-boot-20261020-r02.log').read_text()
    health = (SOURCE/'sd-health-r04.log').read_text()
    assert recovery['received_bytes'] > 0 and 'soc> ' in recovery['text']
    assert program['status'] == 'PASS' and program['device_count'] == 1
    assert program['device_id'] == '0x00602899'
    assert program['bitstream_sha256'] == 'e8a037fa676e10f31a994b2f67d35a458586a6669c61800ace53e9edacb97b45'
    assert 'CPU_HZ=63642857' in prior and 'SD_LOADER_FAIL camera preinit' in prior
    assert 'CPU_HZ=59400000' in boot and 'PIKAFISH_SD_LOADER_PASS' in boot
    assert 'XQ LINUX PIKAFISH READY' in boot
    assert 'rv32-driver-quantized-mac abi=1 threshold=50 DEVELOPMENT_ONLY camera=background' in boot
    expected = {'brfw.bin':'8072b5c4','N20K.BIN':'57aec2e7','N20FS.BIN':'fd08270c',
                'N20.DTB':'4fb3265f','pikafish.pff':'80322636','pikafish.atk':'cba1dd72'}
    for name, crc in expected.items():
        assert re.search(r'Loading '+re.escape(name)+r' bytes=\d+.*?CRC32=0x'+crc, boot, re.S), name
    assert 'XQ_NATIVE_READY models=3 backend=rv32-driver-quantized-mac' in health
    assert 'features=00000067' in health and 'XQ_ADAPTER_DONE=0' in health
    identities = {
        '/usr/bin/xiangqi-pikafish-gui':'ab1528db2b7af429e63f0db4872f9df889b3116462610eedae57e7d36d8052a3',
        '/run/xq-native/xq-native-worker':'e2836949c3f9a9dde4e84fc685aa4ff0827924f061dc8a3684245075495c1913',
        '/run/xq-native/board.xqm':'fbd8a4e8bcd78918a44674eb69225f7d82ac4547ac24a777ea4b4b11cf495efe',
        '/run/xq-native/detector.xqm':'d65b4b8686520ae1546d0a207c1bcb9f30efe0d40e7f5c8245c4dd11ff9ca09d',
        '/run/xq-native/classifier.xqm':'b49c730c939dc5f9d6f3850af772ef24a5216e603da34362b0b21ca5f8cbfa3c',
    }
    for path, digest in identities.items():
        assert digest+'  '+path in health, path
    attempts = re.findall(r'PICTURE_CAMERA_START attempt=(\d+) result=(-?\d+) status=(0x[0-9a-f]+)', boot)
    assert attempts and attempts[-1][1] == '0'
    DEST.mkdir()
    evidence = {}
    for name in ('sd-cram-r03.json','sd-cram-r03.log','sd-cram-r03.preflight.log',
                 'sd-cram-r03-uart.log','uart-native-r07-after-user-reconnect.json',
                 'sd-boot-20261020-r02.log','sd-boot-20261020-r03.log','sd-health-r04.log'):
        source = SOURCE/name
        shutil.copyfile(source, DEST/name)
        evidence[name] = sha(source)
    result = dict(schema_version=1, recorded_utc=datetime.now(timezone.utc).isoformat(),
                  status='SD_BOOT_AND_THREE_MODEL_DEPLOYMENT_PASS',
                  uart_bidirectional=True, uart_recovery_root_cause='Not established; recovered following user reconnection',
                  prior_boot_failure='Non-E8 63.642857 MHz configuration; six SD CRCs passed, background-camera preinit rejected',
                  cram_program=program['bitstream_sha256'], flash_written=False, new_sd_write=False,
                  sd_boot_with_volatile_e8=True, power_cycle_persistence_tested=False,
                  boot_crc32=expected, camera_initialization_attempts=attempts,
                  kernel_driver_features='0x67', model_count=3, runtime_sha256=identities,
                  fresh_live_camera_recognition_accepted=False, latency_accepted=False,
                  full_games_accepted=False, production_ready=False, evidence_sha256=evidence)
    (DEST/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('NATIVE_SD_BOOT_EVIDENCE_PASS')

if __name__ == '__main__':
    main()
