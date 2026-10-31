"""Actual product runtime/voice/engine/speech orchestration with explicit off-board fixtures."""
from pathlib import Path
import argparse
import hashlib
import io
import json
import posixpath
import shlex
import struct
import subprocess
import tarfile
import uuid

R = Path(__file__).resolve().parents[1]


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--distribution', default='Ubuntu-22.04')
    parser.add_argument('--move-only', action='store_true')
    parser.add_argument('--home-r13', action='store_true')
    parser.add_argument('--battle-r17', action='store_true')
    parser.add_argument('--preview-retry',action='store_true')
    parser.add_argument('--targets',default='host,rv32')
    args = parser.parse_args()
    assert not args.battle_r17 or (args.move_only and args.home_r13)
    assert args.targets.split(',') and set(args.targets.split(',')) <= {'host','rv32'}
    assert len(args.targets.split(',')) == len(set(args.targets.split(',')))
    from picture_workspace import workspace_path, wsl_path
    assert args.output.absolute().is_relative_to(R/'build')
    out = workspace_path(args.output)
    assert not out.exists()
    out.mkdir(parents=True)
    real = ['linux/xinyi_board/runtime.c', 'linux/xinyi_board/engine_bridge.c',
            'linux/xinyi_board/voice_bridge.c', 'linux/xinyi_board/voice_notation.c',
            'linux/xinyi_board/speech_task.c', 'linux/xinyi/xinyi_product.c',
            'linux/xinyi/coremark/process.c', 'linux/picture_new/coach_protocol.c',
            'linux/voice_ctc/xqvoice_session.c', 'linux/voice_speech/xq_speech.c',
            'sw/xiangqi/xiangqi_search.c', 'sw/xiangqi/xiangqi_pikafish_link.c',
            'sw/bootloader/crc32_fast.c']
    fixtures = ['linux/xinyi_board/runtime_test.c', 'linux/xinyi_board/runtime_fixtures.c',
                'linux/xinyi_board/fake_runtime_asr.c', 'linux/xinyi_board/fake_runtime_audio.c',
                'linux/xinyi_board/fake_engine_service.c']
    names = set(real+fixtures+['linux/xinyi_board/speech_worker.c', 'scripts/check_xinyi_runtime.py'])
    for directory in ['linux/xinyi_board', 'linux/xinyi', 'linux/vision', 'linux/voice_ctc',
                      'linux/voice', 'linux/voice_speech', 'linux/mac_accel', 'linux/picture_new',
                      'sw/xiangqi', 'sw/bootloader']:
        names.update(p.relative_to(R).as_posix() for p in (R/directory).rglob('*.h'))
    blobs = {name: (R/name).read_bytes() for name in names}
    sources = {name: sha(blob) for name, blob in blobs.items()}
    native = wsl_path(out/'source')
    includes = ['linux/xinyi_board', 'linux/xinyi', 'linux/vision', 'linux/voice_ctc',
                'linux/voice', 'linux/voice_speech', 'linux/mac_accel', 'linux/picture_new',
                'sw/xiangqi', 'sw/bootloader']
    flags = ['-std=c11', '-D_POSIX_C_SOURCE=200809L', '-O2', '-Wall', '-Wextra', '-Werror',
             '-ffunction-sections', '-fdata-sections', '-pthread']
    flags+=['-DXINYI_COACH_MOVE_AUDIO='+str(int(args.move_only))]
    flags+=['-DXINYI_HOME_R13='+str(int(args.home_r13))]
    flags+=['-DXINYI_BATTLE_R17='+str(int(args.battle_r17))]
    flags+=['-DXINYI_PREVIEW_RETRY_R19='+str(int(args.preview_retry))]
    lines = ['set -eu', 'export TMPDIR='+shlex.quote(native), 'ulimit -c 0', 'export PATH=/opt/toolchain/bin:/usr/local/bin:/usr/bin:/bin']
    for target, cc, extra in [('host', 'gcc', []), ('rv32', '/opt/toolchain/bin/riscv32-linux-musl-gcc',
                               ['-static', '-march=rv32ima', '-mabi=ilp32', '-mstrict-align'])]:
        if target not in args.targets.split(','):continue
        destination = native+'/build/'+target
        local = ['set -eu', 'mkdir -p '+shlex.quote(destination),
                 ': > '+shlex.quote(destination+'/asr.stub')]
        for fixture, name in [('linux/xinyi_board/fake_engine_service.c', 'fake-engine'),
                              ('linux/xinyi_board/fake_runtime_asr.c', 'fake-asr')]:
            local.append(shlex.join([cc, *flags, *extra, native+'/'+fixture, '-o', destination+'/'+name]))
        inc = ['-I'+native+'/'+directory for directory in includes]
        local.append(shlex.join([cc, *flags, *extra, *inc,
            *[native+'/'+name for name in real+fixtures+['linux/xinyi_board/speech_worker.c']],
            '-MM'])+' > '+shlex.quote(destination+'/dependencies.d'))
        local.append(shlex.join([cc, *flags, *extra, *inc, native+'/linux/xinyi_board/speech_worker.c',
                                native+'/linux/xinyi_board/fake_runtime_audio.c', '-o', destination+'/fake-speech']))
        local.append(shlex.join([cc, *flags, *extra, *inc,
                                *[native+'/'+name for name in real+fixtures[:2]],
                                '-Wl,--gc-sections', '-lm', '-o', destination+'/runtime-test']))
        children = [destination+'/'+name for name in ['fake-engine', 'fake-speech', 'fake-asr']]
        if target == 'rv32':
            for child in children:
                name = 'build/rv32/'+Path(child).name+'-qemu'
                blobs[name] = ('#!/bin/sh\nexec qemu-riscv32 '+shlex.quote(child)+' "$@"\n').encode()
                local.append(shlex.join(['chmod', '755', native+'/'+name]))
            children = [child+'-qemu' for child in children]
        local.append(shlex.join([*(['qemu-riscv32'] if target == 'rv32' else []),
                                destination+'/runtime-test', *children, destination]))
        script_name = 'build/run-'+target+'.sh'
        blobs[script_name] = ('\n'.join(local)+'\n').encode()
        lines.append(shlex.join(['timeout', '--kill-after=5', '240', 'sh', native+'/'+script_name]))
    blobs['build/run.sh'] = ('\n'.join(lines)+'\n').encode()
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w') as archive:
        for name, blob in blobs.items():
            item = tarfile.TarInfo(name)
            item.size = len(blob)
            item.mode = 0o644
            archive.addfile(item, io.BytesIO(blob))
    command = 'set -eu\ntest ! -e '+shlex.quote(native)+'\nmkdir -p '+shlex.quote(native)
    command += '\ntar -xf - -C '+shlex.quote(native)+'\nsh '+shlex.quote(native+'/build/run.sh')
    status = 'FAILED_PRESERVED'
    try:
        with (out/'run.log').open('wb') as log:
            result = subprocess.run(['wsl.exe', '-d', args.distribution, '--', 'sh', '-c', command],
                                    input=payload.getvalue(), stdout=log, stderr=subprocess.STDOUT, timeout=520)
        log_data = (out/'run.log').read_bytes()
        assert result.returncode == 0, log_data.decode(errors='replace')[-6000:]
        markers = ['RUNTIME_VOICE_RESTART_AFTER_ENGINE_FAILURE_OR_BUSY_DRAIN_RESETS32_AND_REJECTS_STALE_PASS',
                   'RUNTIME_COREMARK_LIVE_LOG_PROGRESS_DIRTY_QUIET_AND_STALE_GUARDS_PASS',
                   'RUNTIME_SPACE_300_DELETE_ONLY_RED_RECOMMEND_ANNOUNCE_UNTIL_SPEECH_AND_GEOMETRY_KEEP_PASS',
                   'RUNTIME_NATIVE_GEOMETRY_2_5_6_WIRE5_KEEP_BOARD_AND_NEXT_PHOTO_SUCCESS_PASS',
                   'RUNTIME_CAPTURE_CANCEL_NAVIGATION_AFTER_DRAIN_ACK_PASS',
                   'RUNTIME_COACH_CANCEL_PIN_UNTIL_CONSUMED_AND_TERMINAL_ACK_PASS',
                   'RUNTIME_ENGINE_WAITPID_BUSY1_BLOCKS_MODE_BUSY0_ACK_OLD_TOKEN_REJECT_PASS',
                   'RUNTIME_ANNOUNCE_CANCEL_NAVIGATION_AFTER_SPEECH_BYE_WAITPID_PASS',
                   'RUNTIME_REAL_VOICE_SESSION_ENGINE_SPEECH_MIC_EXCLUSIVE_LATE_ASR_CANCEL_PASS',
                   'RUNTIME_FLOAT_SCORE_SAME_PERMILLE_THREE_ROOKS_AND_DUPLICATE_DIFFERENT_CLASS_PASS',
                   'RUNTIME_REAPED_CANCEL_CONSUMED_PIN_REOPEN_ASYNC_READY_AND_NEXT_SPACE_SUCCESS_PASS',
                   'RUNTIME_FATAL_AND_UNDRAINED_NEVER_REOPEN_OR_ACK_AS_RECOVERY_PASS',
                   ('RUNTIME_R13_REFERENCE_DETAIL_NO_CHILD_NO_MEASURED_SCORE_NO_FAKE_OUTPUT_PASS' if args.home_r13 else
                    'RUNTIME_REFERENCE_10S_NO_CHILD_NO_MEASURED_SCORE_NO_FAKE_OUTPUT_CANCEL_PASS'),
                   'XINYI_RUNTIME_INTEGRATION_PASS_SYNTHETIC_HOST_OR_QEMU_NOT_BOARD']
        if args.home_r13:markers.append('RUNTIME_R13_PREVIEW_EXCLUSIVE_CANCEL_START_DRAIN_FAILURE_RECOVERY_EXIT_PASS')
        if args.battle_r17:markers += ['RUNTIME_R17_KEYBOARD_NAVIGATION_SAFE_ENTRY_PASS','RUNTIME_R17_SCANOUT_BANK_GENERATION_WRAP_CANCEL_AND_FROZEN_IMAGE_TIME_PASS','RUNTIME_R17_ASR_VISIBLE_FIRST_OPTIONAL_ONSET_AND_SPEECH_BUDGET_PASS','RUNTIME_R17_PRODUCER_READY_IPC_QUEUE_INCLUDED_LEGACY_FUTURE_OLD_ZERO_TIMERS_UNAVAILABLE_PASS','RUNTIME_R17_PRESTART_READY_NO_EMPTY_RUN_OWNER_OR_RESPAWN_AND_KEYBOARD_CLOSE_PASS']
        for marker in markers:
            assert log_data.count(marker.encode()) == len(args.targets.split(',')), marker
        archive_data = subprocess.check_output(['wsl.exe', '-d', args.distribution, '--', 'tar', '-cf', '-',
                                               '-C', native+'/build', *args.targets.split(','), 'run.sh',
                                               *['run-'+t+'.sh' for t in args.targets.split(',')]], timeout=30)
        with tarfile.open(fileobj=io.BytesIO(archive_data)) as archive:
            for item in archive.getmembers():
                if not item.isfile():
                    continue
                relative = Path(item.name)
                assert not relative.is_absolute() and '..' not in relative.parts
                target = out/relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(item).read())
        for name in (['runtime-test', 'fake-engine', 'fake-speech', 'fake-asr'] if 'rv32' in args.targets.split(',') else []):
            elf = (out/'rv32'/name).read_bytes()
            assert elf[:6] == b'\x7fELF\x01\x01' and struct.unpack_from('<H', elf, 18)[0] == 243
            assert struct.unpack_from('<I', elf, 36)[0] == 0
        inventory = sources
        compiled = set()
        for target in args.targets.split(','):
            deps = (out/target/'dependencies.d').read_text().replace('\\\n', ' ')
            compiled.update(posixpath.normpath(token[len(native)+1:]) for token in deps.split() if token.startswith(native+'/'))
        assert set(real+fixtures+['linux/xinyi_board/speech_worker.c']).issubset(compiled)
        assert compiled.issubset(inventory)
        compiled.add('scripts/check_xinyi_runtime.py')
        sources = {name: inventory[name] for name in sorted(compiled)}
        inventory_drift = [dict(path=n, original_sha256=h,current_sha256=sha((R/n).read_bytes()))
                           for n,h in inventory.items() if n not in compiled and sha((R/n).read_bytes())!=h]
        assert all(sha((R/name).read_bytes()) == expected for name, expected in sources.items()), 'Compiled sources changed during run'
        status = ('HOST_RV32' if set(args.targets.split(','))=={'host','rv32'} else args.targets.upper())+'_RUNTIME_INTEGRATION_PASS_NOT_BOARD'
    finally:
        record = dict(status=status, battle_r17=args.battle_r17,targets=args.targets,move_only=args.move_only,source_stable=status!='FAILED_PRESERVED', hardware_used=False,
                      actual_inference=False, actual_audio=False, native_root=native,
                      scope='Real runtime/product/voice_2 session/engine_bridge/speech_task/coach protocol and real fork/exec children; platform/coach/accelerator and ASR/engine/audio explicitly fake',
                      per_platform_timeout_seconds=240, source_sha256=sources,
                      source_inventory_sha256=locals().get('inventory',sources),
                      uncompiled_inventory_drift=locals().get('inventory_drift',[]),
                      tests=markers if status!='FAILED_PRESERVED' else [],
                      outputs_sha256={p.relative_to(out).as_posix(): sha(p.read_bytes()) for p in out.rglob('*') if p.is_file()})
        (out/'result.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    print(status)


if __name__ == '__main__':
    main()
