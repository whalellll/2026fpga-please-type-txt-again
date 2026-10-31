"""Build one small real shared-path trace and reuse the explicit device mocks.

No device/media/audio is opened by this script. Each compiler/run is bounded.
The production diagnostic is built only, never run here.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
from picture_workspace import ROOT, workspace_path, wsl_path

SHA = lambda b: hashlib.sha256(b).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--rt-candidate', action='store_true', help='Explicitly trace the rejected-board RT candidate; default is R01')
    a = ap.parse_args()
    out = workspace_path(a.output)
    out.mkdir(parents=True, exist_ok=False)
    names = ['linux/xinyi_board/speech_rt_trace_r18.c',
        'linux/voice_speech/xq_speech_linux.c', 'linux/voice_speech/xq_speech.c',
        'linux/voice_speech/xq_speech.h', 'linux/voice_speech/xq_move_speech.h',
        'linux/voice_speech/xq_whole_speech.h', 'linux/voice_speech/xq_whole_bank.c',
        'linux/voice_speech/xq_whole_bank.h', 'linux/xinyi_board/gui_options.h',
        'sw/xiangqi/xiangqi_search.h', 'sw/xiangqi/xiangqi_pikafish_link.h',
        ('linux/voice_speech/tests/test_whole_playback.c' if a.rt_candidate else 'linux/voice_speech/tests/test_whole_playback_r01.c'),
        'linux/voice_speech/tests/test_speech_linux.c',
        'scripts/prepare_xinyi_speech_rt_trace.py', 'scripts/picture_workspace.py']
    if a.rt_candidate:
        names += ['linux/voice_speech/xq_speech_linux_candidate.inc', 'linux/voice_speech/xq_whole_bank_candidate.inc']
    before = {n: SHA((ROOT / n).read_bytes()) for n in names}
    src = out / 'source'
    for n in names:
        p = src / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes((ROOT / n).read_bytes())
    result = dict(status='FAILED_PRESERVED', hardware_used=False, rt_candidate=a.rt_candidate,
                  production_diagnostic_executed=False, source_sha256=before, runs=[])

    def run(name, args):
        log = out / (name + '.log')
        with log.open('xb') as f:
            p = subprocess.run(['wsl.exe', '-d', 'Ubuntu-22.04', '--', 'sh', '-c',
                'ulimit -c 0\nexec timeout --kill-after=3 60 ' + shlex.join(args)],
                stdout=f, stderr=subprocess.STDOUT, timeout=75)
        assert p.returncode == 0, (name, p.returncode, log.read_text(errors='replace')[-2500:])

    try:
        tests = out / 'mock-tests'
        tests.mkdir()
        text = (src / 'linux/voice_speech/tests/test_speech_linux.c').read_text()
        first = text.index('#define open fake_open')
        last = text.index('#undef syscall', first) + len('#undef syscall')
        aliases = ['OPEN', 'CLOSE', 'FLOCK', 'MMAP', 'MUNMAP', 'MLOCKALL', 'MUNLOCKALL', 'SYSCALL']
        shim = '\n'.join('#define XQRT_' + n + ' fake_' + n.lower() for n in aliases)
        shim += '\n#define malloc fake_pcm_malloc\n#define XQRT_NO_MAIN 1\n#include "speech_rt_trace_r18.c"'
        (tests / 'test_speech_linux.c').write_bytes((text[:first] + shim + text[last:]).encode())
        fixture = 'linux/voice_speech/tests/test_whole_playback.c' if a.rt_candidate else 'linux/voice_speech/tests/test_whole_playback_r01.c'
        text = (src / fixture).read_text()
        text = text.replace('"../xq_whole_speech.h"', '"xq_whole_speech.h"')
        text = text.replace(' assert(!legacy_audio_checks());', ' trace_reset();assert(!legacy_audio_checks());')
        text = text.replace(' return 0;\n}',
            ' assert(trace_stages[T_MLOCK].count && trace_stages[T_SCHED_RESTORE].count);\n'
            ' assert(trace_stages[T_RT_DISABLE_WRITE].failed || trace_stages[T_RT_RESTORE_WRITE].failed);\n'
            ' trace_emit(99,0,1,0);return 0;\n}')
        test = tests / 'test_whole_playback.c'
        test.write_bytes(text.encode())
        include = ['-I' + wsl_path(tests), '-I' + wsl_path(src / 'linux/voice_speech'),
                   '-I' + wsl_path(src / 'linux/xinyi_board'), '-I' + wsl_path(src / 'sw/xiangqi')]
        common = ['-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                  '-DXINYI_COACH_MOVE_AUDIO=1', '-DXINYI_BATTLE_R17=1', *include]
        common += ['-DXINYI_SPEECH_RT_CANDIDATE='+str(int(a.rt_candidate))]
        bank = wsl_path(src / 'linux/voice_speech/xq_whole_bank.c')
        for target in ['host', 'rv32']:
            cc = '/opt/toolchain/bin/riscv32-linux-musl-gcc' if target == 'rv32' else 'cc'
            flags = ['-static', '-march=rv32ima', '-mabi=ilp32', '-mstrict-align'] if target == 'rv32' else []
            exe = out / (target + '-mock')
            run(target + '-mock-build', [cc, *common, *flags, wsl_path(test), bank,
                '-Wl,--wrap=read,--wrap=write,--wrap=__read_chk', '-o', wsl_path(exe)])
            run(target + '-mock-run', [*(['qemu-riscv32'] if target == 'rv32' else []), wsl_path(exe)])
            log = (out / (target + '-mock-run.log')).read_text()
            assert 'R17_WHOLE_PCM_RT_CLEANUP_FORMAT_CANCEL_RECOVERY_PASS' in log
            assert 'R18_RT_STAGES' in log and 'clock_errors=0' in log
            result['runs'].append(dict(target=target, status='REAL_PATH_EXPLICIT_DEVICE_MOCK_PASS',
                                       executable_sha256=SHA(exe.read_bytes())))
        exe = out / 'speech-rt-trace.rv32.elf'
        run('production-build', ['/opt/toolchain/bin/riscv32-linux-musl-gcc', *common,
            '-static', '-march=rv32ima', '-mabi=ilp32', '-mstrict-align',
            '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections', '-s',
            wsl_path(src / 'linux/xinyi_board/speech_rt_trace_r18.c'),
            wsl_path(src / 'linux/voice_speech/xq_speech.c'), bank, '-o', wsl_path(exe)])
        data = exe.read_bytes()
        packed = gzip.compress(data, mtime=0)
        (out / 'speech-rt-trace.rv32.elf.gz').write_bytes(packed)
        assert before == {n: SHA((ROOT / n).read_bytes()) for n in names}
        result.update(status='RT_TRACE_REAL_SHARED_PATH_HOST_RV32_MOCK_RESTORE_PASS_PRODUCTION_BUILD_ONLY',
            elf_path=str(exe), elf_bytes=len(data), elf_sha256=SHA(data),
            gzip_bytes=len(packed), gzip_sha256=SHA(packed),
            command='/run/speech-rt-trace /run/new900-pcm > /run/speech-rt-trace.log 2>&1',
            runtime_bound_seconds=12, rounds=2,
            timing_scope='CLOCK_MONOTONIC wrapper boundary costs, diagnostic overhead included. No FIFO instrumentation; output after complete production cleanup; excludes helper process and IPC.')
    finally:
        (out / 'result.json').write_bytes((json.dumps(result, indent=2) + '\n').encode())
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
