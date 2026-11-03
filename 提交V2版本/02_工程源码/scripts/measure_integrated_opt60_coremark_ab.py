"""Measure accepted CPU80 and exact P3 CPU60 in CRAM, with all samples retained."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
import threading
import time

from board_integrated_opt60 import ROOT, preflight
from verify_sdboot_native import validate as validate_control

CONTROL = Path('G:/fpga/c80audio_unpack_20261022_r3/SOC')
CONTROL_WORK = CONTROL/'docs/validation/cpu80-conv-sdboot-20261022/attempt-03'
CONTROL_BIT = '30d8f0d5ccdefcf9225780965df3efd399b9b9f27eb390d849754fcd57d526f1'
P3_COMMIT = '8aae985849f8f44e3c898dbcf31234a8df680f95'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--native-root', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--port', default='COM17')
    ap.add_argument('--jtag-server-port', type=int, default=65420)
    ap.add_argument('--initial-control-program', type=Path,
                    help='Reuse a successful local CRAM binding for control-a; verify fresh ROM info before measuring')
    ap.add_argument('--program', action='store_true')
    a = ap.parse_args()
    assert 1 <= a.jtag_server_port <= 65535
    out = a.output.resolve()
    workspace = Path('G:/fpga').resolve()
    assert ROOT.resolve().is_relative_to(workspace)
    assert out.is_relative_to((ROOT/'build').resolve()), 'New evidence must stay in the candidate build directory'
    out.mkdir(parents=True, exist_ok=False)
    scratch = out/'tmp'
    scratch.mkdir()
    for name in ['TEMP', 'TMP', 'TMPDIR']:
        os.environ[name] = str(scratch)
    try:
        bit, candidate = preflight(a.native_root.resolve(), P3_COMMIT)
        control = validate_control(CONTROL, CONTROL_WORK)
        assert control['bitstream_sha256'] == CONTROL_BIT
    except Exception as error:
        (out/'result.json').write_text(json.dumps(dict(
            status='PREFLIGHT_REJECTED_NO_BOARD_ACTION', error=repr(error),
            board_accessed=False, flash_written=False), indent=2)+'\n')
        raise
    record = dict(status='PREFLIGHT_PASS_NOT_PROGRAMMED', owner_pid=os.getpid(),
                  started_utc=datetime.now(timezone.utc).isoformat(), candidate=candidate,
                  control=control, order=['control-a', 'candidate-a', 'control-b', 'candidate-b'],
                  batches=[], per_mhz_limit=.05, total_score_gate=False,
                  workspace_root=str(workspace), temporary_directory=str(scratch),
                  workspace_paths_resolved=True,
                  jtag_server_port=a.jtag_server_port,
                  initial_control_program=str(a.initial_control_program) if a.initial_control_program else None,
                  flash_written=False, sd_written=False, formal_delivery=False)
    save = lambda: (out/'result.json').write_text(json.dumps(record, indent=2)+'\n')

    def run(command, log, timeout):
        with log.open('xb') as stream:
            child = subprocess.run(list(map(str, command)), cwd=ROOT, stdout=stream,
                                   stderr=subprocess.STDOUT, timeout=timeout)
        assert child.returncode == 0, str(log)

    def program_control(folder, previous=None):
        import serial
        from serial.tools.list_ports import comports
        assert any(p.device == a.port and p.vid == 0x10c4 and p.pid == 0xea60
                   for p in comports()), 'Fresh CP210x UART absent'
        folder.mkdir()
        if previous:
            previous = previous.resolve()
            assert previous.is_relative_to((ROOT/'build').resolve())
            receipt = read(previous)
            native_path = previous.with_name(previous.name.replace('-binding.json', '.json'))
            assert receipt['status'] == 'REPAIRED_ROM_CRAM_PROGRAM_PASS_BOARD_TESTS_PENDING'
            assert receipt['preflight'] == receipt['postflight'] == control
            assert receipt['program_receipt_sha256'] == sha(native_path)
            native = read(native_path)
            assert native['status'] == 'PASS' and native['operation'] == 'CRAM'
            assert native['device_id'] == '0x00602899' and native['device_count'] == 1
            assert native['bitstream_sha256'] == CONTROL_BIT
            (folder/'reused-program.json').write_text(json.dumps(dict(
                binding_path=str(previous), binding_sha256=sha(previous),
                native_path=str(native_path), native_sha256=sha(native_path),
                reason='Prior native programming passed; its parent capture omitted the ROM info query',
                fresh_rom_info_required=True), indent=2)+'\n')
        uart = serial.Serial(port=None, baudrate=115200, timeout=.1, write_timeout=5)
        uart.port, uart.dtr, uart.rts = a.port, False, False
        stop, errors, data = threading.Event(), [], bytearray()

        def capture():
            try:
                cancelled = False
                with (folder/'program.uart').open('xb') as stream:
                    while not stop.is_set():
                        q = uart.read(uart.in_waiting or 1)
                        if q:
                            stream.write(q); stream.flush(); data.extend(q)
                            assert len(data) < 4*1024*1024
                            if not cancelled and b'Flash autoboot in 3s' in data:
                                uart.write(b'\x1b'); cancelled = True
            except Exception as error:
                errors.append(repr(error))

        uart.open()
        thread = threading.Thread(target=capture)
        thread.start()
        try:
            if not previous:
                run([sys.executable, '-B', ROOT/'scripts/program_repaired_rom.py',
                     '--root', CONTROL, '--work', CONTROL_WORK, '--output', folder,
                     '--attempt', '1', '--jtag-server-port', a.jtag_server_port],
                    folder/'program-owner.log', 700)
                time.sleep(3)
            for command in ['', 'info']:
                uart.write((command+'\r').encode())
                time.sleep(2)
        finally:
            stop.set(); thread.join(5); uart.close()
        assert not thread.is_alive() and not errors, errors
        binding_path = previous or folder/'program-01-binding.json'
        receipt = read(binding_path)
        native = read(binding_path.with_name(binding_path.name.replace('-binding.json', '.json')))
        assert receipt['status'] == 'REPAIRED_ROM_CRAM_PROGRAM_PASS_BOARD_TESTS_PENDING'
        assert native['status'] == 'PASS' and native['operation'] == 'CRAM'
        assert native['device_id'] == '0x00602899' and native['device_count'] == 1
        assert native['bitstream_sha256'] == CONTROL_BIT
        assert b'DDR=ready' in data
        assert b'CPU_HZ=80000000' in data and b'SYS_HZ=49500000' in data
        return binding_path

    save()
    if not a.program:
        print(record['status']); return
    try:
        record['status'] = 'COREMARK_ABAB_RUNNING'
        save()
        for label in record['order']:
            is_control = label.startswith('control')
            folder = out/label
            entry = dict(label=label, status='PROGRAMMING')
            record['batches'].append(entry); save()
            if is_control:
                program = program_control(folder, a.initial_control_program if label == 'control-a' else None)
                firmware, image, hz = CONTROL/'artifacts/bootloader.bin', CONTROL/'artifacts/soc_top.sbit', 80000000
            else:
                run([sys.executable, '-B', ROOT/'scripts/board_integrated_opt60.py',
                     '--native-root', a.native_root, '--expected-commit', P3_COMMIT,
                     '--output', folder, '--port', a.port,
                     '--jtag-server-port', a.jtag_server_port, '--program'],
                    out/(label+'-program-owner.log'), 900)
                program = folder/'result.json'
                assert read(program)['status'] == 'OPT60_CRAM_DONE_AND_CPU60_ROM_INFO_PASS_MODELS_PENDING'
                firmware, image, hz = a.native_root/'artifacts/bootloader.bin', bit, 60000000
            entry.update(status='MEASURING', program_receipt=str(program),
                         program_receipt_sha256=sha(program)); save()
            measure = folder/'coremark'
            run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                 ROOT/'scripts/measure_coremark.ps1', '-Port', a.port, '-CpuHz', hz,
                 '-Optimization', 'O2', '-BitstreamPath', image, '-FirmwarePath', firmware,
                 '-OutputDirectory', measure], folder/'measure-owner.log', 900)
            result = read(measure/'result.json')
            assert result['status'] == 'PASS' and result['board_acceptance']
            assert len(result['runs']) == 4
            assert all(r['validated'] and r['duration_seconds'] >= 10 and r['cpu_hz'] == hz
                       for r in result['runs'])
            assert result['bitstream']['sha256'] == sha(image)
            assert result['firmware']['sha256'] == sha(firmware)
            assert result['log_sha256'] == sha(measure/'uart.log')
            entry.update(status='PASS', coremark_result=str(measure/'result.json'),
                         coremark_result_sha256=sha(measure/'result.json')); save()
        comparisons = {}
        for side in ['control', 'candidate']:
            runs = [r for batch in record['batches'] if batch['label'].startswith(side)
                    for r in read(Path(batch['coremark_result']))['runs'][:3]]
            assert len(runs) == 6 and all(r['mode'] == 'performance' for r in runs)
            comparisons[side] = {key: dict(all_values=[r[key] for r in runs],
                                          mean=statistics.mean(r[key] for r in runs))
                                 for key in ['iterations_per_second', 'coremark_per_mhz']}
        drop = comparisons['control']['coremark_per_mhz']['mean']-comparisons['candidate']['coremark_per_mhz']['mean']
        record.update(comparisons=comparisons, coremark_per_mhz_absolute_decrease=drop,
                      final_program_receipt=record['batches'][-1]['program_receipt'])
        assert drop <= .05, 'CoreMark/MHz exceeds user limit; retain all valid samples'
        record['status'] = 'OPT60_COREMARK_ABAB_CRC_TIME_ALL_SAMPLES_PER_MHZ_PASS_LINUX_PENDING'
    except Exception as error:
        record.update(status='FAILED_PRESERVED_INSPECT_ACTUAL_BOARD_STATE', error=repr(error))
        if record['batches'] and record['batches'][-1]['status'] != 'PASS':
            record['batches'][-1].update(status='FAILED', error=repr(error))
        raise
    finally:
        record['completed_utc'] = datetime.now(timezone.utc).isoformat()
        save(); print(record['status'], flush=True)


if __name__ == '__main__':
    main()
