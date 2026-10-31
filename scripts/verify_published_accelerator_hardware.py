"""Verify the published hardware and lossless evidence without original paths."""
from pathlib import Path
import argparse,gzip,hashlib,json,subprocess
R=Path(__file__).resolve().parents[1];O=R/'artifacts/validated_accelerators_20261025'
p=argparse.ArgumentParser();p.add_argument('--git-ref');a=p.parse_args()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
m=read(O/'manifest.json');assert m['status']=='HARDWARE_NATIVE_STA_AND_BOARD_FUNCTION_VERIFIED_COREMARK_AB_PENDING'
for name,h in {**m['hardware_source_sha256'],**m['build_artifact_inputs_sha256']}.items():assert sha(R/name)==h,name
for name,d in m['files'].items():
 p=O/name;assert sha(p)==d['sha256'] and p.stat().st_size==d['bytes'],name
 original=gzip.decompress(p.read_bytes()) if d['compressed'] else p.read_bytes()
 assert hashlib.sha256(original).hexdigest()==d['source_sha256'],name
assert sha(O/'soc_top.sbit')==m['bitstream_sha256']=='e42f5f1be3bc2a1a2e8f99ce428c3f9ed9762bcc685c722b03342ac746b5470b'
offline=read(O/'offline/summary.json');assert not offline['violations'] and not offline['native_max_skew_violations']
assert offline['timing_scope']['summary_rows']==116 and sum(map(len,offline['native_max_skew_tables'].values()))==20
assert offline['source_commit']==m['hardware_origin_commit'] and offline['run_id']==m['native_run_id']
assert read(O/'board/cram/program.json')['status']=='PASS'
assert read(O/'board/cram/program.json')['bitstream_sha256']==m['bitstream_sha256']
assert read(O/'board/sdboot/sdboot.result.json')['status']=='PRODUCTION_SD_BOOT_CRC_LINUX_ROOT_PASS_APPLICATIONS_PENDING'
board=read(O/'board/summary.json');assert board['search_pass'] and board['concurrent_pass'] and not board['coremark_tested']
for name,h in board['evidence_sha256'].items():assert sha(O/'board/models'/name)==h,name
assert board['bitstream_sha256']==m['bitstream_sha256']
assert not m['software_optimizations_included'] and not m['main_promoted'] and not m['coremark_ab_tested']
assert set(m['publication_checks'])=={'serial','legacy','exact'}
for key,check in m['publication_checks'].items():
 d=read(O/check['result_path']);assert d['status']==check['status'] and d['cases']==check['cases']
 sources=d.get('inputs_sha256',d.get('source_sha256',{}));assert next(h for n,h in sources.items() if n.replace('\\','/')=='rtl/mac_accel/vision32_layer.v')==m['hardware_source_sha256']['rtl/mac_accel/vision32_layer.v']
changed=subprocess.check_output(['git','diff',m['base_main_commit'],'--name-only','--','rtl','ip','config','pds','sw'],cwd=R).decode().splitlines()
assert changed==m['changed_hardware_paths']==['rtl/mac_accel/vision32_layer.v'],changed
assert not subprocess.check_output(['git','diff',m['base_main_commit'],'--name-only','--','linux'],cwd=R).strip(),'Software optimization code included'
prefix=O.relative_to(R).as_posix()+'/'
expected={prefix+n for n in m['files']}|{prefix+'manifest.json'}
tracked=set(subprocess.check_output(['git','ls-files','-z','--',prefix],cwd=R).decode().strip('\0').split('\0'))
assert expected<=tracked,'Evidence files not in Git index (check sparse-checkout rules)'
git_readback={}
if a.git_ref:
 assert '\n' not in a.git_ref and '\0' not in a.git_ref
 subprocess.run(['git','rev-parse','--verify',a.git_ref+'^{commit}'],cwd=R,stdout=subprocess.DEVNULL,check=True)
 paths=sorted(expected|set(m['hardware_source_sha256'])|set(m['build_artifact_inputs_sha256'])|{'docs/Software_Optimization_Handoff_20261025.md'})
 specs=''.join(a.git_ref+':'+n+'\n' for n in paths).encode()
 data=subprocess.check_output(['git','cat-file','--batch'],input=specs,cwd=R);at=0
 for name in paths:
  end=data.index(b'\n',at);head=data[at:end].split();assert len(head)==3 and head[1]==b'blob',name
  size=int(head[2]);at=end+1;body=data[at:at+size];at+=size+1
  assert hashlib.sha256(body).hexdigest()==sha(R/name),name
  git_readback[name]=hashlib.sha256(body).hexdigest()
 assert at==len(data)
 assert not subprocess.check_output(['git','diff',m['base_main_commit'],a.git_ref,'--name-only','--','linux'],cwd=R).strip()
print(json.dumps(dict(status='PUBLISHED_HARDWARE_SOURCES_ROM_BIT_NATIVE_STA_AND_BOARD_EVIDENCE_SHA256_PASS',hardware_inputs=len(m['hardware_source_sha256']),rom_artifact_inputs=len(m['build_artifact_inputs_sha256']),evidence_files=len(m['files']),bitstream_sha256=m['bitstream_sha256'],coremark_ab_tested=False,main_promoted=False,formal_delivery=False),indent=2))
if a.git_ref:print('FETCHED_GIT_REF_BLOB_SHA256_PASS',a.git_ref,len(git_readback))
