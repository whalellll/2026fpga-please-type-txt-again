"""Bind native RAM software to the unchanged audited E8 hardware candidate.

Creates local candidates only. Neither SD/Flash writes nor JTAG programming.
"""
import argparse, hashlib, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
from prepare_picture_roi_candidate import prepare

p = argparse.ArgumentParser()
for key in ('hardware', 'kernel', 'dtb', 'rootfs', 'output'):
    p.add_argument('--' + key, type=Path, required=True)
a = p.parse_args()
prepare(REPO, a.hardware, a.kernel, a.dtb, a.rootfs, a.output)
manifest_path = a.output / 'sd_contract.json'
manifest = json.loads(manifest_path.read_text())
manifest.update(scope='EXPERIMENTAL native three-model UART RAM boot candidate; M0 FAIL; NOT BoardRelease',
    model_backend='rv32-driver-quantized-mac', model_count=3,
    production_ready=False, full_integer_pipeline=False,
    rootfs_build_manifest_sha256=hashlib.sha256((a.rootfs.parent / 'native-rootfs.json').read_bytes()).hexdigest(),
    cold_boot_board_validated=False)
manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
print('NATIVE_RAM_CONTRACT_PREPARED board_validated=false sd_written=false')
