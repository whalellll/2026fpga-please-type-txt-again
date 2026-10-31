"""Boot the exact GUI1080 runtime over bundled TFTP; no SD or Flash operation."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,ipaddress,json,re,time
from verify_gui1080_native import validate,read,sha
from tftp_gui1080_candidate import validate as runtime_validate

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ['root','work','kit','program-receipt','output']:ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--port',default='COM17');ap.add_argument('--server',required=True);ap.add_argument('--board',required=True)
    ap.add_argument('--transfer-timeout',type=int,default=3600);a=ap.parse_args()
    server=ipaddress.IPv4Address(a.server);board=ipaddress.IPv4Address(a.board)
    assert server!=board and not server.is_loopback and not board.is_multicast
    out=a.output.resolve();assert not out.exists();out.mkdir(parents=True)
    result=dict(status='GUI1080_NETBOOT_PREFLIGHT',started_utc=datetime.now(timezone.utc).isoformat(),transport='ROM TFTP hexcrc to DDR; no runtime patch',physical_sd_used=False,flash_written=False,server=str(server),board=str(board),commands=[])
    def save():(out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    s=None;stream=None;save()
    try:
        result['native']=validate(a.root,a.work);result['runtime']=runtime_validate(a.kit)
        program=read(a.program_receipt)
        assert program['status']=='GUI1080_CRAM_PROGRAM_PASS_RUNTIME_BOOT_PENDING'
        assert program['native']==result['native'] and program['uart_port']==a.port
        result['program_receipt_sha256']=sha(a.program_receipt)
        manifest=read(a.kit/'manifest.json');assert sha(a.kit/'manifest.json')==result['native']['runtime_manifest_sha256']
        import serial
        s=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=5);s.port=a.port;s.dtr=False;s.rts=False;s.open()
        stream=(out/'netboot.uart').open('xb')
        def send(command):
            result['commands'].append(command);save()
            data=(command+'\r').encode('ascii')
            for i in range(0,len(data),4):s.write(data[i:i+4]);time.sleep(.008)
        def until(pattern,timeout):
            start=time.monotonic();data=bytearray()
            while time.monotonic()-start<timeout:
                part=s.read(s.in_waiting or 1)
                if part:
                    stream.write(part);stream.flush();data.extend(part)
                    assert len(data)<8*1024*1024,'Capture exceeds bound'
                    if re.search(pattern,data[-16384:]):return bytes(data)
            raise TimeoutError(f'UART timeout {timeout}s for {pattern!r}')
        prompt=rb'(?m)^soc> ?$'
        send('');until(prompt,20)
        send('info');info=until(prompt,30)
        for marker in [b'DDR=ready',b'SYS_HZ=49500000',b'CPU_HZ=80000000',b'TIMEBASE_HZ=49500000']:assert marker in info,marker
        send('netcfg '+str(board));data=until(prompt,30)
        assert ('board IP set to 0x'+format(int(board),'08X')).encode() in data
        result['status']='GUI1080_NETBOOT_MODEL_TRANSFERS';save()
        for name,address in [('pikafish.pff','0x10000000'),('pikafish.atk','0x15000000')]:
            send(f'tftp {server} {name} {address}');start=time.monotonic();data=until(prompt,a.transfer_timeout)
            assert b'TFTP failed' not in data and b'TFTP error' not in data
            assert re.search(rb'(?m)^downloaded '+str(manifest['sd_root_files'][name]['bytes']).encode()+rb'\r?$',data)
            result.setdefault('model_transfers',{})[name]=dict(bytes=manifest['sd_root_files'][name]['bytes'],sha256=manifest['sd_root_files'][name]['sha256'],host_elapsed_seconds=time.monotonic()-start,board_memory_sha256_pending=True);save()
        result['status']='GUI1080_NETBOOT_LINUX_STARTING';save();send('netboot '+str(server))
        data=until(rb'(?m)^/ # |netboot failed, error|Kernel panic',a.transfer_timeout)
        assert b'Starting OpenSBI at 0x18000000' in data and b'GUI1080_LIGHT_RUNTIME_SELECTED' in data
        assert re.search(rb'(?m)^/ # ',data) and b'Kernel panic' not in data and b'netboot failed' not in data
        # The rootfs pins the selected binary at startup. Read it back before functional tests.
        command='sha256sum /opt/voice-gui-display/xiangqi-gui-display-1080; printf "\\n__GUI1080_HASH_END__:%s\\n" "$?"'
        result['commands'].append(command);save()
        wire=(command+'\n').encode()
        for i in range(0,len(wire),4):s.write(wire[i:i+4]);time.sleep(.008)
        data=until(rb'\r?\n__GUI1080_HASH_END__:([0-9]+)\r?\n',120)
        assert b'\n__GUI1080_HASH_END__:0' in data.replace(b'\r',b'') and manifest['gui_sha256'].encode()+b'  /opt/voice-gui-display/xiangqi-gui-display-1080' in data
        result.update(status='GUI1080_TFTP_LINUX_ROOT_SELECTED_GUI_HASH_PASS_FUNCTIONAL_PENDING',postflight=validate(a.root,a.work))
        assert result['postflight']==result['native']
    except Exception as error:
        result.update(status='FAILED_GUI1080_NETBOOT_PRESERVED',error=repr(error));raise
    finally:
        if stream:stream.close()
        if s:s.close()
        if (out/'netboot.uart').is_file():result['uart_sha256']=sha(out/'netboot.uart')
        result['completed_utc']=datetime.now(timezone.utc).isoformat();save();print(json.dumps(result),flush=True)
if __name__=='__main__':main()
