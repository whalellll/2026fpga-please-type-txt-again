"""Load only the verified1080p image into volatile CRAM, capturing UART before programming."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,subprocess,threading,time,shutil,sys
from verify_gui1080_native import validate,read,sha

ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True);ap.add_argument('--work',type=Path,required=True)
ap.add_argument('--output',type=Path,required=True);ap.add_argument('--port',default='COM17');ap.add_argument('--program',action='store_true');a=ap.parse_args()
root=a.root.resolve();work=a.work.resolve();out=a.output.resolve();assert not out.exists();out.mkdir(parents=True)
r=dict(status='GUI1080_PREFLIGHT_RUNNING',started_utc=datetime.now(timezone.utc).isoformat(),source_root=str(root),scope='Volatile CRAM only; no Flash or SD write')
save=lambda:(out/'result.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
save();stop=threading.Event();thread=None;s=None;errors=[]
try:
    r['native']=validate(root,work);save()
    if not a.program:
        r['status']='GUI1080_NATIVE_PREFLIGHT_PASS_NO_BOARD_ACCESS'
    else:
        import serial
        image=out/('gui1080_'+r['native']['bitstream_sha256'][:12]+'.sbit')
        with image.open('xb') as f:f.write((root/'artifacts/soc_top.sbit').read_bytes())
        assert sha(image)==r['native']['bitstream_sha256']
        s=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=5);s.port=a.port;s.dtr=False;s.rts=False;s.open()
        log=out/'program.uart';captured=bytearray()
        def capture():
            try:
                with log.open('xb') as stream:
                    cancelled=False
                    while not stop.is_set():
                        data=s.read(s.in_waiting or 1)
                        if data:
                            stream.write(data);stream.flush();captured.extend(data)
                            assert len(captured)<4*1024*1024,'UART capture exceeds bound'
                            if not cancelled and b'Flash autoboot in 3s' in captured:
                                s.write(b'\x1b');cancelled=True
            except Exception as error:errors.append(repr(error))
        thread=threading.Thread(target=capture);thread.start()
        r.update(status='GUI1080_CRAM_PROGRAMMING',uart_port=a.port,baud=115200,dtr=False,rts=False,programmer_sha256=sha(root/'scripts/program_cram.ps1'));save()
        adapter=Path(__file__).with_name('program_with_project_audit.py')
        command=[sys.executable,'-B',str(adapter),'--root',str(root),'--expected-run',r['native']['run_id'],'--output',str(out/'program-adapter'),'--program']
        r['host_audit_adapter_sha256']=sha(adapter)
        r['command']=command;save()
        with (out/'owner.log').open('xb') as stream:p=subprocess.run(command,cwd=root,stdout=stream,stderr=subprocess.STDOUT,timeout=600)
        assert p.returncode==0,'Inspect preserved native programming logs'
        for original,destination in [('Program.log','program.log'),('Program.json','program.json')]:
            assert not (out/destination).exists();shutil.copy2(out/'program-adapter'/original,out/destination)
        r['host_audit_adapter_receipt_sha256']=sha(out/'program-adapter/result.json')
        proof=read(out/'program.json')
        assert proof['status']=='PASS' and proof['device_id']=='0x00602899' and proof['bitstream_sha256']==r['native']['bitstream_sha256']
        time.sleep(3);stop.set();thread.join(timeout=5);s.close();assert not thread.is_alive() and not errors,errors
        r['postflight']=validate(root,work);assert r['native']==r['postflight']
        r.update(status='GUI1080_CRAM_PROGRAM_PASS_RUNTIME_BOOT_PENDING',program_receipt_sha256=sha(out/'program.json'),uart_sha256=sha(log),console_prompt_observed=b'soc> ' in captured)
except Exception as error:
    r.update(status='FAILED_GUI1080_PROGRAM_ATTEMPT_PRESERVED_ACTUAL_BOARD_STATE',error=repr(error));raise
finally:
    stop.set()
    if thread:thread.join(timeout=5)
    if s and s.is_open:s.close()
    r['completed_utc']=datetime.now(timezone.utc).isoformat();save();print(json.dumps(r),flush=True)
