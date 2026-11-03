"""QEMU/PTY interoperability tests of the actual RV32 Linux RAM receiver.

Run inside WSL as root solely to create fresh synthetic /run/xinyi-rx-test-*
files. No board, camera, MMIO, SD or real model inputs are used.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pty
import select
import signal
import subprocess
import termios
import time

def crc16(data):
    c=0
    for b in data:
        c^=b<<8
        for _ in range(8):c=((c<<1)^0x1021 if c&32768 else c<<1)&65535
    return c

class Link:
    def __init__(self,fd):self.fd=fd;self.pending=bytearray()
    def until(self,marker,seconds=8):
        end=time.monotonic()+seconds
        while marker not in self.pending:
            if time.monotonic()>=end:raise TimeoutError(repr(marker))
            if select.select([self.fd],[],[],.1)[0]:self.pending.extend(os.read(self.fd,8192))
        pos=self.pending.index(marker)+len(marker)
        answer=bytes(self.pending[:pos]);del self.pending[:pos];return answer
    def control(self):
        end=time.monotonic()+8
        while time.monotonic()<end:
            for i,b in enumerate(self.pending):
                if b in (6,21,24,67):del self.pending[:i+1];return b
            self.pending.clear()
            if select.select([self.fd],[],[],.1)[0]:self.pending.extend(os.read(self.fd,8192))
        raise TimeoutError('XMODEM control')
    def write(self,data):
        while data:data=data[os.write(self.fd,data):]

def run(binary,scenario):
    target=Path('/run/fake') if scenario=='bad-path' else Path('/run/xinyi-rx-test-%d-%s'%(os.getpid(),scenario))
    part=Path(str(target)+'.part')
    assert not target.exists() and not part.exists()
    payload=bytes((i*37+11)%256 for i in range(70001))
    if scenario=='overwrite':target.write_bytes(b'KEEP_EXISTING')
    master,slave=pty.openpty();original=termios.tcgetattr(slave)
    child=subprocess.Popen(['qemu-riscv32',str(binary),str(target),str(len(payload))],
                           stdin=slave,stdout=slave,stderr=slave,close_fds=True)
    link=Link(master)
    try:
        failure=scenario in ('cancel','bad-crc','signal','timeout','overwrite','publish-race','bad-path')
        if scenario not in ('overwrite','bad-path'):
            for offset in range(0,len(payload),65536):
                n=min(65536,len(payload)-offset)
                link.until(('XINYI_LINUX_RX_CHUNK offset=%d bytes=%d\n'%(offset,n)).encode())
                link.until(b'Start PN03 XMODEM-CRC slice...\n')
                assert link.control()==67
                if scenario=='cancel':link.write(b'\x18');break
                if scenario=='signal':child.send_signal(signal.SIGTERM);break
                if scenario=='timeout':break
                if scenario=='publish-race' and offset==0:target.write_bytes(b'KEEP_EXISTING')
                for at in range(0,n,1024):
                    block=at//1024+1
                    data=payload[offset+at:offset+min(at+1024,n)].ljust(1024,b'\x1a')
                    c=crc16(data);packet=bytes((2,block&255,255-(block&255)))+data+c.to_bytes(2,'big')
                    if at==0 and offset==0 and scenario in ('crc-once','bad-crc'):
                        bad=packet[:-1]+bytes((packet[-1]^1,))
                        for _ in range(8 if scenario=='bad-crc' else 1):
                            link.write(bad);assert link.control()==21
                        if scenario=='bad-crc':break
                    if at==0 and offset==0 and scenario=='gap300':
                        link.write(packet[:3]);time.sleep(.3);link.write(packet[3:])
                    else:link.write(packet)
                    assert link.control()==6
                    if at==0 and offset==0 and scenario=='duplicate':
                        link.write(packet);assert link.control()==6
                if scenario=='bad-crc':break
                link.write(b'\x04');assert link.control()==6
            link.until(b'XINYI_LINUX_RAM_RX_FAIL' if failure else b'XINYI_LINUX_RAM_RX_PASS',12)
        child.wait(timeout=5)
        assert child.returncode==(2 if failure else 0),(scenario,child.returncode)
        assert termios.tcgetattr(slave)==original,'Terminal was not restored'
        assert not part.exists(),'Partial file remains'
        if scenario in ('overwrite','publish-race'):assert target.read_bytes()==b'KEEP_EXISTING'
        elif failure:assert not target.exists()
        else:assert target.read_bytes()==payload
        return dict(scenario=scenario,status='PASS',terminal_restored=True)
    finally:
        if child.poll() is None:
            child.terminate()
            try:child.wait(timeout=3)
            except subprocess.TimeoutExpired:child.kill();child.wait()
        os.close(master);os.close(slave)
        if scenario!='bad-path':
            target.unlink(missing_ok=True);part.unlink(missing_ok=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('binary',type=Path);p.add_argument('report',type=Path)
    a=p.parse_args()
    if a.report.exists():raise ValueError('Preserve previous report')
    before=hashlib.sha256(a.binary.read_bytes()).hexdigest()
    cases=['pass','gap300','crc-once','duplicate','cancel','bad-crc','signal','timeout','overwrite','publish-race','bad-path']
    tests=[]
    for case in cases:
        tests.append(run(a.binary.resolve(),case));print('LINUX_RAM_RX_QEMU_PTY_PASS',case,flush=True)
    assert hashlib.sha256(a.binary.read_bytes()).hexdigest()==before
    a.report.write_text(json.dumps(dict(status='PASS',hardware_used=False,sd_written=False,flash_written=False,
        binary_sha256=before,tests=tests),indent=2)+'\n')
