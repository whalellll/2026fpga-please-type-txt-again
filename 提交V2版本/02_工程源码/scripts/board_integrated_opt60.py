"""Program only the exact full-STA-pass optimization candidate into CRAM."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import subprocess
import threading
import time

import serial
from serial.tools.list_ports import comports

ROOT = Path(__file__).resolve().parents[1]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))


def preflight(native, expected_commit):
    launch_path = native/'physical-launch.json'
    launch = read(launch_path)
    assert launch['status'] == 'ROUTED_FULL_STA_PASS_NOT_BOARD', launch['status']
    assert launch['pnr_complete'] and launch['source_commit'] == expected_commit
    assert launch['cpu_hz'] == 60000000 and launch['sys_hz'] == 49500000
    snapshot_path = native/'pds/build_snapshot.json'
    snapshot = read(snapshot_path)
    proof_path = native/'artifacts/build_evidence.json'
    proof = read(proof_path)
    assert launch['run_id'] == snapshot['run_id'] == proof['run_id']
    assert launch['snapshot_sha256'] == proof['input_snapshot_sha256'] == sha(snapshot_path)
    assert proof['device'] == 'PG2L100H-6-FBG676' and proof['timing'] == 'All Constraints Met'
    assert proof['timing_summary_source'] == 'final report_timing'
    assert proof['max_skew_verified'] and proof['max_skew_rows'] == 20
    assert proof['timing_scope_verified'] and proof['timing_scope']['clocks'] == 18
    assert proof['timing_scope']['summary_rows'] == 116
    assert proof['latches'] == 0
    for rel, digest in snapshot['inputs'].items():
        assert sha(native/rel) == digest, ('Frozen native input changed', rel)
        assert sha(ROOT/rel) == digest, ('Paired source input changed', rel)
    for group in ['inputs', 'outputs', 'report_hashes']:
        for rel, digest in proof[group].items():
            assert sha(native/rel) == digest, (group, rel)
    for rel, digest in launch['reports'].items():
        assert sha(native/'pds'/rel) == digest, rel
    gate_path = Path(launch.get('gate_path', ROOT/'build/opt60-gates-01.json'))
    assert gate_path.resolve().is_relative_to(ROOT/'build')
    assert sha(gate_path) == launch['gate_sha256']
    gate = read(gate_path)
    assert gate['status'] == 'INTEGRATED_OPT60_CORRECTNESS_SOFTWARE_RESOURCE_GATES_PASS_NOT_STA_OR_BOARD'
    for rel, digest in gate['files'].items():
        assert sha(ROOT/rel) == digest, ('Candidate gate changed', rel)
    bit = native/'pds/generate_bitstream/soc_top.sbit'
    assert sha(bit) == proof['outputs']['artifacts/soc_top.sbit'] == sha(native/'artifacts/soc_top.sbit')
    assert 'Design Summary : All Constraints Met.' in (native/'pds/report_timing/soc_top.rtr').read_text()
    return bit, dict(native_root=native.as_posix(), run_id=launch['run_id'],
                     source_commit=expected_commit, bitstream_path=bit.as_posix(),
                     bitstream_sha256=sha(bit), launch_sha256=sha(launch_path),
                     snapshot_sha256=sha(snapshot_path), build_evidence_sha256=sha(proof_path),
                     correctness_gate_sha256=sha(gate_path),
                     cpu_hz=60000000, sys_hz=49500000, display='1080p30',
                     final_sta_pass=True, flash_written=False, sd_written=False,
                     model_tests_passed=False, formal_delivery=False,
                     board_controller_sha256=sha(Path(__file__)),
                     programmer_sha256=sha(ROOT/'scripts/program_cram.ps1'))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--native-root', type=Path, required=True)
    ap.add_argument('--expected-commit', required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--port')
    ap.add_argument('--jtag-server-port', type=int, default=65420)
    ap.add_argument('--program', action='store_true')
    a = ap.parse_args()
    assert 1 <= a.jtag_server_port <= 65535
    assert not a.output.exists(), 'Preserve previous board evidence'
    bit, result = preflight(a.native_root.resolve(), a.expected_commit)
    if a.program:
        assert any(p.device == a.port and p.vid == 0x10c4 and p.pid == 0xea60
                   for p in comports()), 'Fresh CP210x UART absent'
    a.output.mkdir(parents=True)
    result.update(status='OPT60_EXACT_NATIVE_STA_PREFLIGHT_PASS_NOT_PROGRAMMED',
                  started_utc=datetime.now(timezone.utc).isoformat())
    save = lambda: (a.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    save()
    if not a.program:
        print(result['status'])
        return
    stop, errors, captured = threading.Event(), [], bytearray()
    uart, thread = None, None
    try:
        uart = serial.Serial(port=None, baudrate=115200, timeout=.1, write_timeout=5)
        uart.port, uart.dtr, uart.rts = a.port, False, False
        uart.open()
        uart.reset_input_buffer()

        def capture():
            try:
                with (a.output/'program.uart').open('xb') as log:
                    cancelled = False
                    while not stop.is_set():
                        data = uart.read(uart.in_waiting or 1)
                        if data:
                            log.write(data)
                            log.flush()
                            captured.extend(data)
                            assert len(captured) < 4*1024*1024
                            if not cancelled and b'Flash autoboot in 3s' in captured:
                                uart.write(b'\x1b')
                                cancelled = True
            except Exception as error:
                errors.append(repr(error))

        thread = threading.Thread(target=capture)
        thread.start()
        command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                   str(ROOT/'scripts/program_cram.ps1'), '-Program', '-AllowExternalSbit',
                   '-SbitPath', str(bit), '-PdsRoot', 'G:/fpga/PDS_2022.2-SP6.4',
                   '-JtagServerPort', str(a.jtag_server_port),
                   '-LogPath', str(a.output/'program.log'),
                   '-EvidencePath', str(a.output/'program.json')]
        result.update(status='OPT60_PROGRAMMING_ACTUAL_STATE_PENDING', command=command,
                      uart_port=a.port, baud=115200, dtr=False, rts=False)
        save()
        with (a.output/'owner.log').open('xb') as log:
            child = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                   timeout=180)
        assert child.returncode == 0, 'Inspect native programming log and actual device state'
        programmed = read(a.output/'program.json')
        assert programmed['status'] == 'PASS' and programmed['operation'] == 'CRAM'
        assert programmed['device_id'] == '0x00602899' and programmed['device_count'] == 1
        assert programmed['bitstream_sha256'] == result['bitstream_sha256']
        result.update(status='OPT60_CRAM_DONE_PASS_ROM_CHECK_PENDING', cram_programmed=True,
                      program_receipt_sha256=sha(a.output/'program.json'))
        save()
        time.sleep(4)
        for command in ['', 'info']:
            uart.write((command+'\r').encode())
            time.sleep(2)
        assert not errors, errors
        assert b'DDR=ready' in captured and b'CPU_HZ=60000000' in captured
        assert b'SYS_HZ=49500000' in captured
        assert sha(bit) == result['bitstream_sha256']
        result['status'] = 'OPT60_CRAM_DONE_AND_CPU60_ROM_INFO_PASS_MODELS_PENDING'
    except Exception as error:
        result['error'] = repr(error)
        result['status'] = ('OPT60_CRAM_DONE_PASS_ROM_CHECK_FAILED' if result.get('cram_programmed')
                            else 'OPT60_PROGRAM_ATTEMPT_FAILED_INSPECT_ACTUAL_STATE')
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
        save()
        print(result['status'], flush=True)


if __name__ == '__main__':
    main()
