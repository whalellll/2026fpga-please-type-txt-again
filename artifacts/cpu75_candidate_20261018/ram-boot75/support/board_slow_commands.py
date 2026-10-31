import argparse, base64, binascii, hashlib, json, re, sys, time
from pathlib import Path
import serial

ap=argparse.ArgumentParser()
ap.add_argument('mode',choices=['boot','commands'])
ap.add_argument('--spec',type=Path)
ap.add_argument('--boot-root',type=Path,default=Path('G:/fpga/b70r1/artifacts/cpu70_candidate_20261017/gui-restore'))
ap.add_argument('--log',type=Path,required=True)
a=ap.parse_args()
if a.log.exists(): raise SystemExit('Refusing existing evidence log')
s=serial.Serial(port=None,baudrate=115200,timeout=0.1,write_timeout=5)
s.port='COM17'; s.dtr=False; s.rts=False
s.open()
f=a.log.open('xb')
def read_until(pattern,seconds):
    data=b''; end=time.monotonic()+seconds
    while time.monotonic()<end:
        q=s.read(s.in_waiting or 1)
        if q:
            f.write(q); f.flush(); data+=q
            if len(data)>2*1024*1024: raise RuntimeError('Capture bound exceeded')
            print(q.decode('utf-8','replace'),end='',flush=True)
            if re.search(pattern,data): return data
    raise TimeoutError(f'UART wait {seconds}s: {pattern!r}')
def control(allowed):
    end=time.monotonic()+8
    while time.monotonic()<end:
        q=s.read(1)
        if q and q[0] in allowed: return q[0]
    raise TimeoutError('XMODEM control timeout')
def upload(path,address):
    content=path.read_bytes()
    print(f'\nUPLOAD {path.name} bytes={len(content)} sha256={hashlib.sha256(content).hexdigest()}',flush=True)
    s.write(f'loadx {address}\r'.encode())
    read_until(b'Start XMODEM-CRC transfer now',10)
    control([0x43])
    for i,offset in enumerate(range(0,len(content),1024)):
        block=content[offset:offset+1024].ljust(1024,b'\x1a')
        n=(i+1)&255
        packet=bytes([2,n,255-n])+block+binascii.crc_hqx(block,0).to_bytes(2,'big')
        for retry in range(5):
            s.write(packet)
            c=control([6,21,24])
            if c==6: break
            if c==24: raise RuntimeError('Board cancelled upload')
        else: raise RuntimeError('Upload retries exhausted')
        if i%64==0: print(f'UPLOAD_ACK block={i+1}',flush=True)
    s.write(b'\x04')
    if control([6,24])!=6: raise RuntimeError('EOT rejected')
    read_until(b'soc> ',10)
def linux_command(command, marker, timeout=60, pace=0.025):
    command += f'; printf "\\n{marker}:%s\\n" "$?"\n'
    encoded=command.encode()
    width=1
    for offset in range(0,len(encoded),width):
        s.write(encoded[offset:offset+width]); time.sleep(pace)
    started=time.monotonic()
    data=read_until(rb'\r?\n'+marker.encode()+rb':(\d+)\r?\n',timeout)
    print(f'HOST_RESPONSE_ELAPSED marker={marker} seconds={time.monotonic()-started:.6f}',flush=True)
    code=int(re.search(rb'\r?\n'+marker.encode()+rb':(\d+)\r?\n',data)[1])
    return code,data
try:
    if a.mode=='boot':
        root=a.boot_root
        manifest=json.loads((root/'overlay-manifest.json').read_text())
        for name in ['gui-overlay.cpio','loader.bin']:
            if hashlib.sha256((root/name).read_bytes()).hexdigest()!=manifest['outputs_sha256'][name]:
                raise RuntimeError('Host payload hash mismatch: '+name)
        s.write(b'\n'); read_until(b'soc> ',10)
        for cmd in ['info','sdinfo']:
            s.write((cmd+'\r').encode()); read_until(b'soc> ',20)
        upload(root/'gui-overlay.cpio','0x1a100000')
        upload(root/'loader.bin','0x01000000')
        s.write(b'boot 0x01000000\r')
        data=read_until(b'VOICE_GUI_OVERLAY_STARTED|Kernel panic|SD payload invalid|SD payload CRC mismatch|VOICE_GUI_RAM_OVERLAY_FAIL|SD init failed|FAT mount failed|Console ready. Type help.',420)
        if b'VOICE_GUI_OVERLAY_STARTED' not in data: raise RuntimeError('Boot failure marker')
        if not re.search(rb'/ #\s*$',data): read_until(rb'/ #\s*$',30)
    else:
        s.write(b'\n')
        read_until(rb'/[^\r\n]* #\s*$',8)
        results=[]
        for i,item in enumerate(json.loads(a.spec.read_text(encoding='utf-8'))):
            if 'upload' in item:
                local=Path(item['upload']); remote=item['remote']
                code,_=linux_command(f'stty -echo; test ! -e {remote} && : > {remote}',f'__UP_BEGIN_{i}')
                if code: raise RuntimeError('Upload destination exists')
                encoded=base64.b64encode(local.read_bytes()).decode()
                for k,offset in enumerate(range(0,len(encoded),768)):
                    part=encoded[offset:offset+768]
                    code,_=linux_command(f"printf '%s' '{part}' | base64 -d >> {remote}",f'__UP_{i}_{k}')
                    if code: raise RuntimeError('Upload chunk failed')
                    if k%8==0: print(f'UPLOAD_LINUX_ACK chunk={k+1}',flush=True)
                code,data=linux_command(f'stty echo; sha256sum {remote}',f'__UP_HASH_{i}')
                if code or hashlib.sha256(local.read_bytes()).hexdigest().encode() not in data:
                    raise RuntimeError('Uploaded hash mismatch')
                results.append({'upload':str(local),'remote':remote,'sha256':hashlib.sha256(local.read_bytes()).hexdigest()})
                continue
            marker=f'__BOARD_END_{i}'
            code,data=linux_command(item['command'],marker,item.get('timeout',60))
            results.append({'command':item['command'],'exit':code})
            if code and item.get('required',True): raise RuntimeError('Board command returned '+str(code))
        a.log.with_suffix('.results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print('\nBOARD_IO_PASS',flush=True)
finally:
    s.close(); f.close()
    a.log.with_suffix('.log').write_text(a.log.read_bytes().decode('utf-8','replace'),encoding='utf-8')
