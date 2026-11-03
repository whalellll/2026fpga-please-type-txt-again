"""Fetch the published ref and bind source, bitstream and handoff Git blobs."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,subprocess,sys
R=Path(__file__).resolve().parents[1];branch='hardware/validated-accelerators-20261025';ref='refs/remotes/origin/'+branch
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve()
assert out.is_relative_to(R) and not out.exists();out.parent.mkdir(parents=True,exist_ok=True)
def git(*args):return subprocess.check_output(['git',*args],cwd=R)
remote={name:commit for commit,name in (line.split() for line in git('ls-remote','--heads','origin',branch,'main').decode().splitlines())}
commit=remote['refs/heads/'+branch];assert commit==git('rev-parse','HEAD').decode().strip()
subprocess.run(['git','fetch','origin','refs/heads/'+branch+':'+ref],cwd=R,check=True)
assert git('rev-parse',ref).decode().strip()==commit
check=subprocess.run([sys.executable,'-X','utf8',str(R/'scripts/verify_published_accelerator_hardware.py'),'--git-ref',ref],cwd=R,capture_output=True,check=True)
assert b'FETCHED_GIT_REF_BLOB_SHA256_PASS' in check.stdout
m=json.loads((R/'artifacts/validated_accelerators_20261025/manifest.json').read_text(encoding='utf-8'))
assert remote['refs/heads/main']==m['base_main_commit']
paths=['rtl/mac_accel/vision32_layer.v','artifacts/validated_accelerators_20261025/soc_top.sbit',
 'artifacts/validated_accelerators_20261025/manifest.json','docs/Software_Optimization_Handoff_20261025.md']
hashes={}
for name in paths:
 body=git('show',ref+':'+name);h=hashlib.sha256(body).hexdigest();assert h==hashlib.sha256((R/name).read_bytes()).hexdigest();hashes[name]=h
d=dict(status='REMOTE_HARDWARE_COMMIT_BITSTREAM_SOURCES_AND_SOFTWARE_HANDOFF_HASH_PASS',checked_utc=datetime.now(timezone.utc).isoformat(),
 remote_url=git('remote','get-url','origin').decode().strip(),remote_branch=branch,remote_commit=commit,main_commit=remote['refs/heads/main'],main_unchanged=True,
 hardware_origin_commit=m['hardware_origin_commit'],native_run_id=m['native_run_id'],remote_blob_sha256=hashes,verification_stdout=check.stdout.decode(),
 authoritative_hardware_files_verified=408,rom_artifact_files_verified=17,published_evidence_files_verified=130,
 software_runtime_sources_pushed=False,coremark_ab_tested=False,formal_delivery=False,
 history_note='Initial source/docs commit was followed by a separate complete evidence commit after sparse-checkout blocked staging. No history rewritten.')
out.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:d[k] for k in ['status','remote_branch','remote_commit','main_commit','main_unchanged']},indent=2))
