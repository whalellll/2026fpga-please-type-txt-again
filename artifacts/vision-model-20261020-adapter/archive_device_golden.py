"""Bind the completed real-device 80-layer proof to immutable build inputs."""
import hashlib,json,re
from datetime import datetime,timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
OUT=REPO/'docs/validation/picture-p21-runtime-20261020'
BUILD=REPO/'build/picture-p21-native'
def identity(path):
    return dict(path=path.relative_to(REPO).as_posix(),bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())
comparison=json.loads((OUT/'golden-device-r04.json').read_text())
assert comparison['status']=='PASS' and comparison['complete'] and comparison['layers']==80
text=(OUT/'golden-device-r04.log.txt').read_text()
models=re.findall(r'XQ_GOLDEN_MODEL_DONE model=(\w+) driver=1 jobs=(\d+) cycles=(\d+) records=(\d+)',text)
assert [r[0] for r in models]==['board','detector','classifier']
assert [int(r[1]) for r in models]==[1508,34950,28499]
totals=re.search(r'XQ_GOLDEN_PROBE_DONE records=80 driver=1 jobs=(\d+) cycles=(\d+) elapsed_ms=(\d+)',text)
assert totals and int(totals[1])==64957
paths=[OUT/'golden-device-r04.json',OUT/'golden-device-r04.checks.txt',OUT/'golden-device-r04.log.txt',
       OUT/'regression-r03.json',OUT/'native-rootfs-r06.json',
       BUILD/'probe-rv32-r04/xq-golden-probe',BUILD/'probe-rv32-r04/SHA256SUMS.txt',
       BUILD/'rv32-r05/xq-native-worker',BUILD/'rv32-r05/source-before.sha256',
       BUILD/'rv32-r05/source-after.sha256',BUILD/'rv32-r05/compiler.txt',
       BUILD/'source-r05/source_binding.json',BUILD/'gui-r06/xiangqi-pikafish-gui',
       BUILD/'model-r02/native_manifest.json',BUILD/'model-r02/native_parameters.h',
       BUILD/'model-r02/refinement_rng.bin']
paths += [BUILD/'model-r02'/name for name in ('board.xqm','detector.xqm','classifier.xqm')]
record=dict(schema_version=1,status='PASS',recorded_utc=datetime.now(timezone.utc).isoformat(),
    scope='Real FPGA MAC, all 80 supplied-layer tensors; NOT M0, RGB565 full-chain or game acceptance',
    layers=80,tensors_per_layer=4,comparisons='SHA256 and CRC32, sizes, exact integer tensors',
    models=[dict(model=r[0],jobs=int(r[1]),cycles=int(r[2]),records=int(r[3]),
                 busy_seconds=int(r[2])/49500000) for r in models],
    jobs=int(totals[1]),cycles=int(totals[2]),diagnostic_elapsed_ms=int(totals[3]),
    sys_mac_hz=49500000,cpu_hz=59400000,driver_abi=1,driver_features=0x67,
    bitstream_sha256='e8a037fa676e10f31a994b2f67d35a458586a6669c61800ace53e9edacb97b45',
    kernel_sha256='55b4af36384dacd889dec87881a67b86482bf9d00747608b5d677cb3a31fa061',
    source_dump_manifest_sha256=comparison['source_dump_manifest_sha256'],
    full_integer_pipeline=False,production_ready=False,m0_accepted=False,
    native_rgb565_chain_status='RUNNING',sd_written=False,flash_written=False,
    files=[identity(p) for p in paths])
dest=OUT/'device-golden-binding.json';assert not dest.exists()
dest.write_text(json.dumps(record,indent=2)+'\n')
print('DEVICE_GOLDEN_BINDING_PASS models=3 layers=80 tensors=320 jobs=64957')
