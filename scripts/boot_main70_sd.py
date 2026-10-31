"""Arm serial capture, then boot only after the user's explicit return/reset signal."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,re,time,serial
from board_boot_contract import contract,validate
from workspace_paths import workspace_path

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--work',type=Path,required=True)
    a=ap.parse_args();work=workspace_path(a.work);out=work/'boot-01';assert not out.exists();out.mkdir()
    read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
    assert read(work/'coremark-abab-02/result.json')['status']=='MAIN70_COREMARK_ABAB_ALL_SAMPLES_CRC_TIME_PER_MHZ_PASS_LINUX_PENDING'
    assert read(work/'sd-write-01/result.json')['status']=='MAIN70_SD8_AND_HASH_MANIFEST_WRITE_VOLUME_FLUSH_READBACK_PASS'
    assigned=read(Path(read(work/'coremark-abab-02/result.json')['final_program_receipt']))
    assert assigned['status']=='PASS' and assigned['bitstream_sha256']=='24226a3a2cf41e96554e4f4ea677f133964cbf942993cb1f751c60c5928a8a02'
    record=dict(status='ARMED_WAITING_EXPLICIT_USER_CARD_RETURN_AND_CPU_RESET',started_utc=datetime.now(timezone.utc).isoformat(),port='COM17',baud=115200,dtr=False,rts=False,bitstream_sha256=assigned['bitstream_sha256'],sd_write_receipt_sha256=hashlib.sha256((work/'sd-write-01/result.json').read_bytes()).hexdigest())
    def save():(out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    s=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=3);s.port='COM17';s.dtr=False;s.rts=False
    save();s.open()
    with (out/'uart.log').open('xb') as log:
        def receive(pattern,seconds):
            data=bytearray();end=time.monotonic()+seconds
            while time.monotonic()<end:
                chunk=s.read(s.in_waiting or 1)
                if chunk:log.write(chunk);log.flush();data+=chunk
                assert len(data)<8*1024*1024
                if re.search(pattern,data):return bytes(data)
            raise TimeoutError('Serial receive: '+str(pattern))
        def send(command):
            for char in (command+'\r').encode():s.write(bytes([char]));time.sleep(.008)
        try:
            s.write(b'\r');receive(rb'(?m)^soc> ?$',15)
            deadline=time.monotonic()+1800
            while not (work/'user-card-returned.json').exists():
                assert time.monotonic()<deadline,'User card-return wait exceeded30min'
                chunk=s.read(s.in_waiting or 1)
                if chunk:log.write(chunk);log.flush()
            trigger=read(work/'user-card-returned.json');assert trigger['user_confirmed_card_return_and_cpu_reset'] is True
            record['trigger']=trigger;record['status']='BOOTING_FROM_SD';save()
            s.write(b'\r');receive(rb'(?m)^soc> ?$',15)
            for command in ['info','sdinfo']:send(command);receive(rb'(?m)^soc> ?$',45)
            _,_,stop=contract('MAIN70',70000000)
            began=time.monotonic();send('sdboot');data=receive(stop,900)
            validate(data,'MAIN70',70000000)
            record.update(status='MAIN70_DIRECT_SD6_PAYLOAD_CRC_LINUX_ROOT_PASS_APPLICATIONS_PENDING',boot_host_elapsed_seconds=time.monotonic()-began)
        except Exception as e:record.update(status='FAILED_PRESERVED',error=repr(e));raise
        finally:
            s.close();log.flush();record['completed_utc']=datetime.now(timezone.utc).isoformat();record['uart_sha256']=hashlib.sha256((out/'uart.log').read_bytes()).hexdigest();save()
    print(record['status'])

if __name__=='__main__':main()
