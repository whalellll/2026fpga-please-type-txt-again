"""Extract only the verified RTL and lossless native/board evidence for push."""
from pathlib import Path
import gzip,hashlib,json,shutil,subprocess
R=Path(__file__).resolve().parents[1]
H=Path('G:/fpga/performance_soc_image_hwc_20261025')
T=Path('G:/fpga/performance_soc_transfer_reuse_20261025')
I=Path('G:/fpga/performance_soc_integer_ops_20261025')
N=H/'build/native-physical-01';O=R/'artifacts/validated_accelerators_20261025'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
summary=read(H/'docs/validation/image-hwc-20261025/summary.json')
launch=read(N/'physical-launch.json');binding=read(I/'build/integer-ops-hardware-01/result.json')
assert launch['status']=='ROUTED_FULL_STA_PASS_NOT_BOARD' and launch['pnr_complete']
assert not summary['violations'] and not summary['native_max_skew_violations']
assert summary['timing_scope']['summary_rows']==116 and summary['timing_scope']['clocks']==18
assert summary['source_commit']==launch['source_commit']=='85ed00197a199e06ecccb0bd0bc9c5184ea24c98'
assert summary['run_id']==launch['run_id']=='c8282c991f494ddc8144e35245872c02'
assert sha(N/'physical-launch.json')==summary['physical_launch_sha256']
for name,h in launch['reports'].items():assert sha(N/'pds'/name)==h,name
snapshot=read(N/'pds/build_snapshot.json')
for name,h in snapshot['inputs'].items():assert sha(N/name)==h,name
board=read(T/'docs/validation/transfer-reuse-20261025/board-models.json')
assert board['search_pass'] and board['concurrent_pass'] and not board['coremark_tested']
assert board['bitstream_sha256']==binding['bitstream_sha256']==summary['bitstream_sha256']
board_dir=T/'build/transfer-board-models-01'
assert sha(board_dir/'run.json')==board['run_receipt_sha256']
for name,h in board['evidence_sha256'].items():assert sha(board_dir/name)==h,name
base=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R).decode().strip()
changes=subprocess.check_output(['git','diff','--name-only',base,summary['source_commit'],'--','rtl','ip','config','pds','sw'],cwd=R).decode().splitlines()
assert changes==['rtl/mac_accel/vision32_layer.v'],changes
subprocess.run(['git','restore','--source='+summary['source_commit'],'--worktree',changes[0]],cwd=R,check=True)
for name,h in binding['hardware_inputs_sha256'].items():assert sha(R/name)==h,name
artifact_inputs={name:h for name,h in snapshot['inputs'].items() if name.startswith('artifacts/')}
for name,h in artifact_inputs.items():assert sha(R/name)==h,name
O.mkdir(parents=True,exist_ok=False);files={}
def copy(src,name,compress=False):
 dest=O/name;dest.parent.mkdir(parents=True,exist_ok=True);original=src.read_bytes()
 dest.write_bytes(gzip.compress(original,mtime=0) if compress else original)
 assert (gzip.decompress(dest.read_bytes()) if compress else dest.read_bytes())==original
 files[name]=dict(sha256=sha(dest),bytes=dest.stat().st_size,source_path=str(src),source_sha256=sha(src),compressed=compress)
copy(N/'pds/generate_bitstream/soc_top.sbit','soc_top.sbit')
for name in ['synthesize/soc_top.snr','place_route/soc_top.prr','report_timing/soc_top.rtr','report_timing/rtr.db']:
 copy(N/'pds'/name,'native/'+name+'.gz',True)
for src,name in [(N/'physical-launch.json','native/physical-launch.json'),(N/'pds/build_snapshot.json','native/build_snapshot.json'),
 (N/'artifacts/build_evidence.json','native/build_evidence.json'),(H/'build/image-hwc-gates.json','offline/gates.json'),
 (H/'docs/validation/image-hwc-20261025/summary.json','offline/summary.json'),(H/'docs/validation/image-hwc-20261025/sta-summary.json','native/sta-summary.json'),
 (T/'docs/validation/transfer-reuse-20261025/board-models.json','board/summary.json')]:copy(src,name)
for key,d in summary['offline_checks'].items():
 src=H/d['path'];assert sha(src)==d['sha256'];copy(src,'offline/checks/'+key+'.json')
for name in board['evidence_sha256']:copy(board_dir/name,'board/models/'+name)
copy(board_dir/'run.json','board/models/run.json') if 'run.json' not in board['evidence_sha256'] else None
for directory,names,prefix in [
 (I/'build/integer-ops-program-02',['result.json','program.json','program.log','program.preflight.log','program.uart'],'board/cram'),
 (I/'build/integer-ops-boot-01',['sdboot.result.json','sdboot.uart'],'board/sdboot')]:
 for name in names:copy(directory/name,prefix+'/'+name)
assert read(I/'build/integer-ops-program-02/program.json')['status']=='PASS'
assert read(I/'build/integer-ops-boot-01/sdboot.result.json')['status']=='PRODUCTION_SD_BOOT_CRC_LINUX_ROOT_PASS_APPLICATIONS_PENDING'
# Readable software evidence is documentation only; no runtime/driver/model source.
for directory,names,prefix in [
 (I/'docs/validation/integer-ops-20261025',['offline.json','board.json','sd.json','final.json'],'software-reference/integer-ops'),
 (Path('G:/fpga/performance_soc_integer_hwc_20261025/docs/validation/integer-hwc-20261025'),['board.json'],'software-reference/integer-graph')]:
 for name in names:copy(directory/name,prefix+'/'+name)
manifest=dict(schema=1,status='HARDWARE_NATIVE_STA_AND_BOARD_FUNCTION_VERIFIED_COREMARK_AB_PENDING',
 authorization='User2026-10-25 explicitly requested pushing verified hardware optimizations; software optimization directions documented separately.',
 base_main_commit=base,hardware_origin_commit=summary['source_commit'],native_run_id=summary['run_id'],
 bitstream_sha256=summary['bitstream_sha256'],hardware_source_sha256=binding['hardware_inputs_sha256'],changed_hardware_paths=changes,
 build_artifact_inputs_sha256=artifact_inputs,
 cpu_hz=60000000,sys_hz=49500000,cpu_source_changed=False,sta_focus=summary['sta_focus'],timing_scope=summary['timing_scope'],
 native_resource_totals=summary['routed_resources']['total'],resource_comparison_reference='Preceding exact-epilogue routed implementation; not a main/P3 resource delta.',
 native_resource_delta_vs_preceding_exact=summary['routed_resource_delta'],
 board_verified=dict(image_three_original_crcs=True,voice_fixed_wav=True,official_pikafish=True,search=True,concurrent=True),
 board_environment='Board tests use separately frozen kernel02 and software15c0baa; published Linux sources/boot remain the remote main baseline.',
 coremark_ab_tested=False,software_optimizations_included=False,main_promoted=False,formal_delivery=False,flash_written=False,
 legacy_quantization_tradeoff='Serial legacy modes0/1 multiplication adds31 cycles per value; active raw/exact modes2/4/5 bypass the serial path.',
 files=files)
(O/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for name in ['test_vision32.py','test_vision32_exact.py','test_serial_legacy_multiply.py','workspace_paths.py']:
 shutil.copyfile(H/'scripts'/name,R/'scripts'/name)
# Test temporaries must stay in this workspace, including iverilog's own files.
for name in ['test_vision32.py','test_serial_legacy_multiply.py']:
 p=R/'scripts'/name;s=p.read_text(encoding='utf-8')
 if name=='test_vision32.py':
  needle='    cmd = "set -eu; cd '
  replacement='    temporary=out/"tmp";temporary.mkdir()\n    cmd = "set -eu; export TMPDIR=\''+"\"+linux(temporary)+\""+'\'; cd '
 else:
  needle="cmd='set -eu; cd '"
  replacement="temporary=o/'tmp';temporary.mkdir()\ncmd='set -eu; export TMPDIR='+wsl_path(temporary)+'; cd '"
 assert needle in s,name;s=s.replace(needle,replacement,1);p.write_text(s,encoding='utf-8',newline='\n')
print(json.dumps(dict(status=manifest['status'],files=len(files),source_files=len(binding['hardware_inputs_sha256']),bitstream_sha256=manifest['bitstream_sha256']),indent=2))
