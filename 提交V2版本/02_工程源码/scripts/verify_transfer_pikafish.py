"""Check actual compiled port sources/ELF and original PFF1 integer scores."""
from pathlib import Path
import argparse,hashlib,json,subprocess
from workspace_paths import workspace_path,wsl_path
from build_cpu80_conv_sd import cpio_entries
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--build',type=Path,default=R/'build/transfer-pikafish-02');p.add_argument('--output',type=Path,default=R/'build/transfer-pikafish-verify-02');p.add_argument('--vectors',type=Path);a=p.parse_args()
o=workspace_path(a.output);o.mkdir(parents=True,exist_ok=False)
b=workspace_path(a.build);sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
receipt=json.loads((b/'result.json').read_text());assert 'PASS' in receipt['status']
ports=['pikafish_mac_runtime.cpp','pikafish_mac_runtime.h','pikafish_stagea_accel.cpp','pikafish_stagea_accel.h','pikafish_feature_updates.h','pikafish_stageb_accel.cpp','pikafish_stageb_accel.h']
for name in ports:assert sha(R/'linux/pikafish'/name)==sha(b/'source/src'/name),name
assert sha(R/'linux/mac_accel/pango_mac_uapi.h')==sha(b/'source/src/pango_mac_uapi.h')
for name,h in receipt['pipeline_integration']['patched_sources_sha256'].items():
 assert sha(b/'source'/name)==h,name
direct=json.loads((b/'feature-updates-integration.json').read_text())
assert direct['source_sha256']==sha(b/'source/src/nnue/nnue_accumulator.cpp')
for name,h in receipt['artifacts_sha256'].items():
 p=b/name;data=p.read_bytes();assert sha(p)==h
 assert data[:6]==b'\x7fELF\x01\x01' and int.from_bytes(data[18:20],'little')==243 and int.from_bytes(data[36:40],'little')==0
if a.vectors:
 raw=workspace_path(a.vectors).read_bytes()
 assert hashlib.sha256(raw).hexdigest()=='f74b6cd2c98af3170253fab0d3644f0076be3de6a5b56646cd052a7f85e94d89'
 (o/'official.vectors').write_bytes(raw)
else:
 base=Path('G:/fpga/performance_soc_image_hwc_20261025/build/hwc-sd-kit-01/sd-root/rootfs.cpio').read_bytes()
 v=next(x for x in cpio_entries(base) if x['name'].removeprefix('./')=='opt/pikafish/cpu75-nnue.vectors')
 at=v['end']-((v['bytes']+3)&~3);(o/'official.vectors').write_bytes(base[at:at+v['bytes']])
q=subprocess.run(['wsl.exe','-d','pikafish-verify','--','env','NNUE_CLOCKSOURCE=linux','NNUE_REQUIRE_HW=0','PIKAFISH_STAGEA_ACCEL=0','PIKAFISH_STAGEB_ACCEL=0','PIKAFISH_NNUE_PIPELINE=0','PIKAFISH_NNUE_BATCH=0',
 'NNUE_MODEL='+wsl_path(R/'linux/boot/pikafish.pff'),'NNUE_VECTORS='+wsl_path(o/'official.vectors'),'NNUE_SAMPLES=20','qemu-riscv32',wsl_path(b/'pikafish-nnue-pipeline-latency')],capture_output=True,timeout=240)
(o/'cpu-vectors.log').write_bytes(q.stdout+q.stderr)
assert q.returncode==0 and b'NNUE_LATENCY_CORRECTNESS_PASS' in q.stdout,(q.stdout+q.stderr)[-2000:]
d=dict(status='PIKAFISH_SW_STATIC_RV32_COMPILED_PORT_AND_ORIGINAL_INTEGER_VECTORS_PASS_NOT_BOARD',
 build_receipt_sha256=sha(b/'result.json'),compiled_port_sha256={n:sha(b/'source/src'/n) for n in ports+['pango_mac_uapi.h']},
 model_sha256=sha(R/'linux/boot/pikafish.pff'),vectors_sha256=sha(o/'official.vectors'),log_sha256=sha(o/'cpu-vectors.log'),board_tested=False)
(o/'result.json').write_text(json.dumps(d,indent=2)+'\n');print(d['status'])
