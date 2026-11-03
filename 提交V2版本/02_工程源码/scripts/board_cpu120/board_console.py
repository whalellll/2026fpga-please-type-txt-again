"""Bounded production SD boot and command capture; no upload or Flash path."""
import argparse, hashlib, json, re, time
from datetime import datetime, timezone
from pathlib import Path
import serial
from board_boot_contract import contract,validate

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('mode',choices=['sdboot','commands'])
p.add_argument('--port',required=True)
p.add_argument('--log',type=Path,required=True)
p.add_argument('--spec',type=Path)
p.add_argument('--timeout',type=int,default=600)
p.add_argument('--pace-bytes',type=int,choices=[1,2,4],default=4)
p.add_argument('--cpu-hz',type=int,choices=[120000000,80000000,75000000,70000000,60000000],default=80000000)
p.add_argument('--loader-prefix',choices=['CPU120','CPU80','VOICE_NNUE','MAIN70','MAIN75'],default='CPU80')
a=p.parse_args()
assert not a.log.exists() and not a.log.with_suffix('.result.json').exists()
if a.mode=='commands':
    assert a.spec
    spec=json.loads(a.spec.read_text(encoding='utf-8-sig'))
    for i,item in enumerate(spec):
        # Leave room for the completion marker within BusyBox's line buffer.
        assert len(item['command'].encode())+80<=900,'Command exceeds bounded UART shell line; split the spec before opening UART'
record=dict(status='RUNNING',mode=a.mode,port=a.port,baud=115200,dtr=False,rts=False,
            started_utc=datetime.now(timezone.utc).isoformat(),commands=[])
s=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=5)
s.port=a.port;s.dtr=False;s.rts=False
f=None
def read_until(pattern,seconds):
    data=bytearray();deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        q=s.read(s.in_waiting or 1)
        if q:
            f.write(q);f.flush();data+=q
            print(q.decode('utf-8','replace'),end='',flush=True)
            assert len(data)<4*1024*1024,'UART capture bound exceeded'
            if re.search(pattern,data):return bytes(data)
    raise TimeoutError(f'UART timeout={seconds} pattern={pattern!r}')
def write(text,pace=.008):
    data=text.encode()
    for i in range(0,len(data),a.pace_bytes):s.write(data[i:i+a.pace_bytes]);time.sleep(pace)
try:
    s.open();f=a.log.open('xb')
    if a.mode=='sdboot':
        _,_,stop_pattern=contract(a.loader_prefix,a.cpu_hz)
        record.update(cpu_hz=a.cpu_hz,loader_prefix=a.loader_prefix)
        s.write(b'\r');read_until(rb'(?m)^soc> ?$',15)
        for cmd in ['info','sdinfo']:
            write(cmd+'\r');read_until(rb'(?m)^soc> ?$',30)
        start=time.monotonic();write('sdboot\r')
        data=read_until(stop_pattern,a.timeout)
        validate(data,a.loader_prefix,a.cpu_hz)
        record.update(status='PRODUCTION_SD_BOOT_CRC_LINUX_ROOT_PASS_APPLICATIONS_PENDING',host_elapsed_seconds=time.monotonic()-start)
    else:
        record['spec_sha256']=hashlib.sha256(a.spec.read_bytes()).hexdigest()
        s.write(b'\n');read_until(rb'/[^\r\n]* #\s*$',15)
        for i,item in enumerate(spec):
            marker=f'__CVB_END_{i}__'
            command=item['command']+f'; printf "\\n{marker}:%s\\n" "$?"\n'
            write(command)
            start=time.monotonic()
            data=read_until(rb'\r?\n'+marker.encode()+rb':([0-9]+)\r?\n',item.get('timeout',90))
            code=int(re.search(rb'\r?\n'+marker.encode()+rb':([0-9]+)\r?\n',data)[1])
            result=dict(command=item['command'],exit=code,host_response_seconds=time.monotonic()-start,
                        required_markers=item.get('markers',[]))
            record['commands'].append(result)
            assert code in item.get('allowed_exit',[0]),f'Command{i} exit={code}'
            for marker in item.get('markers',[]):assert marker.encode() in data,f'Command{i} missing {marker}'
        record['status']='BOARD_COMMAND_SPEC_PASS'
except Exception as e:
    record.update(status='FAILED_PRESERVED',error=repr(e))
    raise
finally:
    s.close()
    if f:f.close()
    if a.log.exists():record['uart_sha256']=hashlib.sha256(a.log.read_bytes()).hexdigest()
    record['completed_utc']=datetime.now(timezone.utc).isoformat()
    a.log.with_suffix('.result.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print('\n'+record['status'],flush=True)
