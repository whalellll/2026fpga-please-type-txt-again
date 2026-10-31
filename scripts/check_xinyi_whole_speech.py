"""Actual whole-phrase loading/RT cleanup with synthetic audio and device mocks."""
from pathlib import Path
import argparse
import hashlib
import json
import shlex
import subprocess
from picture_workspace import ROOT, workspace_path, wsl_path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', required=True, type=Path)
    ap.add_argument('--targets', default='host,sanitizer,rv32')
    ap.add_argument('--rt-candidate', action='store_true', help='Explicitly exercise the rejected-board RT candidate; default validates R01')
    a = ap.parse_args()
    out = workspace_path(a.output)
    assert out.is_relative_to((ROOT / 'build/picture-e42-20261025').resolve())
    out.mkdir(parents=True, exist_ok=False)
    names = [('linux/voice_speech/tests/test_whole_playback.c' if a.rt_candidate else 'linux/voice_speech/tests/test_whole_playback_r01.c'),
        'linux/voice_speech/tests/test_speech_linux.c', 'linux/voice_speech/xq_speech_linux.c',
        'linux/voice_speech/xq_speech.h', 'linux/voice_speech/xq_move_speech.h',
        'linux/voice_speech/xq_whole_speech.h', 'linux/xinyi_board/gui_options.h',
        'sw/xiangqi/xiangqi_search.h', 'scripts/check_xinyi_whole_speech.py',
        'linux/voice_speech/xq_whole_bank.c', 'linux/voice_speech/xq_whole_bank.h']
    if a.rt_candidate:
        names += ['linux/voice_speech/xq_speech_linux_candidate.inc', 'linux/voice_speech/xq_whole_bank_candidate.inc']
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    before = {n: sha(ROOT/n) for n in names}
    result = dict(status='FAILED_PRESERVED', hardware_used=False, rt_candidate=a.rt_candidate, runs=[], source_sha256=before)
    try:
        for target in a.targets.split(','):
            assert target in ['host', 'sanitizer', 'rv32']
            exe = out/target
            flags = ['-static', '-march=rv32ima', '-mabi=ilp32', '-mstrict-align'] if target=='rv32' else []
            if target=='sanitizer':
                flags = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-no-pie']
            cc = '/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'cc'
            cmd = [cc, '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-DXINYI_COACH_MOVE_AUDIO=1', '-DXINYI_BATTLE_R17=1', *flags,
                '-DXINYI_SPEECH_RT_CANDIDATE='+str(int(a.rt_candidate)),
                '-I'+wsl_path(ROOT/'linux/voice_speech'), '-I'+wsl_path(ROOT/'sw/xiangqi'),
                wsl_path(ROOT/names[0]), wsl_path(ROOT/'linux/voice_speech/xq_whole_bank.c'),
                '-Wl,--wrap=read,--wrap=write,--wrap=__read_chk', '-o', wsl_path(exe)]
            for phase, args in [('build', cmd), ('run', [*(['qemu-riscv32'] if target=='rv32' else []), wsl_path(exe)])]:
                log = out/(target+'-'+phase+'.log')
                with log.open('xb') as f:
                    q = subprocess.run(['wsl.exe', '-d', 'Ubuntu-22.04', '--', 'sh', '-c',
                        'ulimit -c 0\nexec timeout --kill-after=3 120 '+shlex.join(args)],
                        stdout=f, stderr=subprocess.STDOUT, timeout=135)
                assert not q.returncode, (target, phase, log.read_text(errors='replace')[-2200:])
            text = (out/(target+'-run.log')).read_text()
            assert 'R17_WHOLE_PCM_RT_CLEANUP_FORMAT_CANCEL_RECOVERY_PASS' in text
            result['runs'].append(dict(target=target, status='PASS', executable_sha256=sha(exe)))
        assert before == {n: sha(ROOT/n) for n in names}
        result['status'] = 'R17_WHOLE_PCM_ACTUAL_PATH_SYNTHETIC_RT_CLEANUP_HOST_RV32_PASS_NOT_BOARD'
    finally:
        (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(result['status'])


if __name__ == '__main__':
    main()
