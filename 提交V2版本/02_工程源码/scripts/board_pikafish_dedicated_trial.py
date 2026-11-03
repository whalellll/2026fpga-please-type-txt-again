"""Explicit Oct24 current-version functional trial; preserves failed STA."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, subprocess, threading, time
import serial

S = Path('G:/fpga/performance_soc_pikafish_dedicated_20261024')
N = Path('G:/pfpnr4')
RUN = '6a6729f83eae4ad4bd137f3f19b3fd39'
COMMIT = '5eaddc7'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))

def preflight():
    kit=S/'build/dedicated-sd-04'
    binding=read(kit/'trial-binding.json'); manifest=read(kit/'manifest.json')
    snap=read(N/'pds/build_snapshot.json')
    physical=read(N/'pds/input-snapshots'/RUN/'physical-result.json')
    assert binding['status']=='PIKAFISH_DEDICATED_SD_OFFLINE_READY_BOARD_PENDING_STA_FAILED'
    assert binding['run_id']==snap['run_id']==physical['run_id']==RUN
    assert binding['manifest_sha256']==sha(kit/'manifest.json')
    assert physical['status']=='ROUTED_STA_FAILED_NOT_BOARD'
    assert binding['physical_receipt_sha256']==sha(N/'pds/input-snapshots'/RUN/'physical-result.json')
    for n,h in binding['checked_hardware_inputs_sha256'].items():assert sha(S/n)==sha(N/n)==snap['inputs'][n]==h,n
    assert len(manifest['tests'])==18
    for n,v in manifest['sd_root_files'].items():assert sha(kit/'sd-root'/n)==v['sha256'],n
    for n in ['report_timing/rtr.db','report_timing/soc_top.rtr','generate_bitstream/soc_top.sbit']:
        assert sha(N/'pds'/n)==physical['reports'][n],n
    bit=N/'pds/generate_bitstream/soc_top.sbit'
    assert sha(bit)==sha(kit/'soc_top.sbit')==binding['bitstream_sha256']
    deployments=[]
    for p in Path('H:/fpga_archives/Pikafish_Dedicated_Trial_20261024/sd-backups').glob('*/write-result.json'):
        entry=read(p)
        if entry['ManifestSHA256'].lower()==binding['manifest_sha256']:deployments.append((p,entry))
    assert len(deployments)==1,'Expected exact SD04 write/readback receipt'
    deployment_path,deployment=deployments[0]
    assert deployment['Status']=='SD_FILES_WRITTEN_READBACK_HASH_PASS_BOARD_PENDING'
    return bit,dict(run_id=RUN,source_commit=COMMIT,bitstream_path=str(bit),bitstream_sha256=sha(bit),
        manifest_sha256=binding['manifest_sha256'],trial_binding_sha256=sha(kit/'trial-binding.json'),sd_deployment_path=str(deployment_path),sd_deployment_sha256=sha(deployment_path),
        formal_sta_pass=False,cpu_setup_wns_ns=-0.181,
        authorization='User Oct24: no delivery; board-test this version against pure CPU and other functions. Latest instruction authorizes SD write, then board tests; card returned confirmed.',
        scope='Exact dedicated prototype CRAM trial; failed STA preserved. No Flash, main push or formal delivery.',
        programmer_sha256=sha(S/'scripts/program_cram.ps1'))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--program', action='store_true')
    ap.add_argument('--port')
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    assert not a.output.exists()
    bit, result = preflight()
    if a.program:
        assert a.port and any(p.device == a.port for p in __import__('serial.tools.list_ports', fromlist=['comports']).comports()), 'Fresh UART not present'
    a.output.mkdir(parents=True)
    result.update(status='DEDICATED_PIKAFISH_TRIAL_PREFLIGHT_PASS_NO_BOARD', started_utc=datetime.now(timezone.utc).isoformat())
    save = lambda: (a.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    save()
    if not a.program:
        print(result['status'])
        return
    stop = threading.Event(); errors = []; captured = bytearray(); thread = None; uart = None
    try:
        uart = serial.Serial(port=None, baudrate=115200, timeout=.1, write_timeout=5)
        uart.port = a.port; uart.dtr = False; uart.rts = False; uart.open()
        def capture():
            try:
                with (a.output/'program.uart').open('xb') as log:
                    cancelled = False
                    while not stop.is_set():
                        data = uart.read(uart.in_waiting or 1)
                        if data:
                            log.write(data); log.flush(); captured.extend(data)
                            assert len(captured) < 4*1024*1024
                            if not cancelled and b'Flash autoboot in 3s' in captured:
                                uart.write(b'\x1b'); cancelled = True
            except Exception as e:
                errors.append(repr(e))
        thread = threading.Thread(target=capture); thread.start()
        cmd = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(S/'scripts/program_cram.ps1'),
            '-Program', '-AllowExternalSbit', '-SbitPath', str(bit), '-PdsRoot', 'G:/fpga/PDS_2022.2-SP6.4',
            '-LogPath', str(a.output/'program.log'), '-EvidencePath', str(a.output/'program.json')]
        result.update(status='DEDICATED_PIKAFISH_TRIAL_PROGRAMMING', command=cmd, uart_port=a.port, baud=115200, dtr=False, rts=False); save()
        with (a.output/'owner.log').open('xb') as log:
            p = subprocess.run(cmd, cwd=S, stdout=log, stderr=subprocess.STDOUT, timeout=180)
        assert p.returncode == 0, 'Inspect actual programming logs'
        proof = read(a.output/'program.json')
        assert proof['status'] == 'PASS' and proof['device_id'] == '0x00602899'
        assert proof['device_count'] == 1 and proof['operation'] == 'CRAM' and proof['bitstream_sha256'] == result['bitstream_sha256']
        time.sleep(4)
        for command in ['', 'info', 'sdinfo']:
            uart.write((command+'\r').encode()); time.sleep(2)
        _, post = preflight()
        assert post['bitstream_sha256'] == result['bitstream_sha256'] and not errors
        result.update(status='DEDICATED_PIKAFISH_TRIAL_CRAM_PASS_BOOT_INSPECTION_PENDING', program_receipt_sha256=sha(a.output/'program.json'))
    except Exception as e:
        result.update(status='DEDICATED_PIKAFISH_TRIAL_FAILED_ACTUAL_BOARD_STATE_PRESERVED', error=repr(e))
        raise
    finally:
        stop.set()
        if thread:
            thread.join(5)
        if uart:
            uart.close()
        result.update(completed_utc=datetime.now(timezone.utc).isoformat(), capture_errors=errors)
        if (a.output/'program.uart').exists():
            result['uart_sha256'] = sha(a.output/'program.uart')
        save(); print(result['status'], flush=True)

if __name__ == '__main__':
    main()
