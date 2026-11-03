"""Strict native gate followed by the existing volatile CRAM-only programmer."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, json, os, subprocess, shutil, sys
from verify_sdboot_native import validate,sha,read,need

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--root',type=Path,required=True);p.add_argument('--work',type=Path,required=True)
p.add_argument('--output',type=Path,required=True);p.add_argument('--attempt',type=int,required=True)
p.add_argument('--jtag-server-port',type=int,default=65420)
a=p.parse_args();root=a.root.resolve();work=a.work.resolve();out=a.output.resolve()
assert 1<=a.jtag_server_port<=65535
out.mkdir(parents=True,exist_ok=True);label=f'program-{a.attempt:02d}'
receipt=out/(label+'-binding.json');need(not receipt.exists(),'Preserve previous programming attempts')
r=dict(status='PREFLIGHT_RUNNING',owner_pid=os.getpid(),started_utc=datetime.now(timezone.utc).isoformat(),
       scope='Volatile CRAM only. No Flash or SD write.',source_root=str(root),flow_root=str(work))
def save():receipt.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
save()
try:
    r['preflight']=validate(root,work)
    content_check=None
    if (root/'CPU80_CONV_CANDIDATE.json').is_file():
        from verify_cpu80_conv_candidate import validate as content_check
        r['software_preflight']=content_check(root)
    expected=r['preflight']['bitstream_sha256']
    image=out/('repaired_'+expected[:12]+'.sbit')
    if not image.exists():
        with image.open('xb') as f:f.write((root/'artifacts/soc_top.sbit').read_bytes())
    need(sha(image)==expected,'Staged programming image differs')
    r.update(status='PROGRAMMING',bitstream_sha256=expected,
             programmer_sha256=sha(root/'scripts/program_cram.ps1'),
             native_verifier_sha256=sha(Path(__file__).with_name('verify_sdboot_native.py')))
    save()
    adapter=Path(__file__).with_name('program_with_project_audit.py')
    adapter_out=out/(label+'-adapter')
    command=[sys.executable,'-B',str(adapter),'--root',str(root),'--expected-run',r['preflight']['run_id'],
             '--output',str(adapter_out),'--jtag-server-port',str(a.jtag_server_port),'--program']
    r['host_audit_adapter_sha256']=sha(adapter)
    r['command']=command;save()
    with (out/(label+'-owner.log')).open('xb') as log:
        code=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT,timeout=600).returncode
    need(code==0,'Programmer failed; inspect preserved native log')
    for original,destination in [('Program.log',label+'.log'),('Program.json',label+'.json')]:
        need(not (out/destination).exists(),'Preserve previous native programming evidence')
        shutil.copy2(adapter_out/original,out/destination)
    r['host_audit_adapter_receipt_sha256']=sha(adapter_out/'result.json')
    proof=read(out/(label+'.json'))
    need(proof['status']=='PASS' and proof['device_id']=='0x00602899' and proof['bitstream_sha256']==expected,'Programming/device confirmation failed')
    r['postflight']=validate(root,work)
    if content_check:r['software_postflight']=content_check(root)
    need(r['preflight']==r['postflight'],'Native inputs changed during programming')
    r.update(status='REPAIRED_ROM_CRAM_PROGRAM_PASS_BOARD_TESTS_PENDING',program_receipt_sha256=sha(out/(label+'.json')))
except Exception as e:
    r.update(status='FAILED_PRESERVED_ACTUAL_BOARD_STATE',error=repr(e));raise
finally:
    r['completed_utc']=datetime.now(timezone.utc).isoformat();save();print(r['status'],flush=True)
