"""Collect immutable offline evidence before the fresh physical build."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil,gzip
R=Path(__file__).resolve().parents[1];out=R/'docs/validation/integrated60-20261024'
out.mkdir(parents=True,exist_ok=True);assert not (out/'summary.json').exists();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
names=['integrated-full-regression-02','integrated-picture-interface-05','integrated-vision-driver-01','integrated-voice-model-02','integrated-voice-mmio-01','integrated-vision-soc-01','integrated-vision-nnue-01','integrated-pikafish-runtime-02','integrated-voice-rv32-01','integrated-voice-wav-01','integrated-boot60-01','integrated-pikafish-rv32-01','integrated-pll60-01']
records={}
for name in names:
 p=R/'build'/name/'result.json';d=json.loads(p.read_text());assert 'PASS' in d['status'] or d['status']=='BOOT_CANDIDATE_BUILT_NOT_BOARD_TESTED',(name,d['status'])
 for field in ['inputs_sha256','source_sha256','sources_sha256','source_inputs_sha256']:
  for n,h in d.get(field,{}).items():
   if n.startswith('/var/tmp/'):
    assert d.get('source_inputs_sha256'),'Require source bindings for Linux-native inputs'
    continue
   if n.startswith('/mnt/') and len(n)>7 and n[6]=='/':n=n[5].upper()+':/'+n[7:]
   f=Path(n);f=f if f.is_absolute() else R/f;assert sha(f)==h,(name,n)
 shutil.copyfile(p,out/(name+'.json'));records[name]=dict(status=d['status'],receipt_sha256=sha(p))
for label,rel in [('kernel','build/integrated-kernel-02/build.json'),('resources','build/integrated-resources-01.json'),('native_clock','build/integrated-native-clock-01.json'),('clock_policy','build/cpu60-clock-policy.json')]:
 p=R/rel;d=json.loads(p.read_text());assert 'PASS' in d['status'];shutil.copyfile(p,out/(label+'.json'));records[label]=dict(status=d['status'],receipt_sha256=sha(p))
for rel,label in [('build/integrated-full-regression-01/result.json','regression-first-failed.json'),('build/integrated-full-regression-01/run.log','regression-first-failed.log'),('build/integrated-full-regression-02/run.log','regression-pass.log')]:shutil.copyfile(R/rel,out/label)
n=Path('G:/i60syn1');snr=n/'pds/synthesize/soc_top.snr';(out/'resource-native.snr.gz').write_bytes(gzip.compress(snr.read_bytes(),mtime=0))
shutil.copyfile(n/'resource-evidence/result.json',out/'resource-native.json')
summary=dict(status='INTEGRATED60_OFFLINE_AND_RESOURCE_GATES_PASS_PHYSICAL_PENDING',created_utc=datetime.now(timezone.utc).isoformat(),source_root=R.as_posix(),cpu_hz=60000000,sys_hz=49500000,display='1080p30',vision_weights='DEFERRED_BY_USER_INTERFACE_ONLY',checks=records,files_sha256={p.name:sha(p) for p in out.iterdir()},native_resource_root=n.as_posix(),native_snr_sha256=sha(snr),pnr=False,board=False,push=False,delivery=False)
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(summary['status'])
