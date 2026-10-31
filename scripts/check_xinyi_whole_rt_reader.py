"""Reuse the whole-bank reader mocks with an explicit RT candidate selection."""
from pathlib import Path
import argparse
import hashlib
import json
import shlex
import subprocess
from picture_workspace import ROOT, workspace_path, wsl_path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--rt-candidate', action='store_true')
    a = ap.parse_args()
    out = workspace_path(a.output)
    out.mkdir(parents=True, exist_ok=False)
    names = ['linux/voice_speech/xq_whole_bank.h', 'linux/voice_speech/xq_whole_bank.c',
             'linux/voice_speech/tests/test_whole_bank.c' if a.rt_candidate else
             'linux/voice_speech/tests/test_whole_bank_r01.c',
             'scripts/check_xinyi_whole_rt_reader.py']
    if a.rt_candidate:
        names.append('linux/voice_speech/xq_whole_bank_candidate.inc')
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    before = {n: sha(ROOT/n) for n in names}
    result = dict(status='FAILED_PRESERVED', hardware_used=False, rt_candidate=a.rt_candidate,
                  source_sha256=before, runs=[])
    wrap = ['open', 'open64', 'read', '__read_chk', 'close', 'mmap', 'mmap64', 'munmap', 'malloc', 'free']
    try:
        for target, cc, extra, runner in [('host','cc',[],[]),
            ('sanitizer','cc',['-fsanitize=address,undefined','-fno-sanitize-recover=all','-no-pie'],[]),
            ('rv32','/opt/toolchain/bin/riscv32-linux-musl-gcc',
             ['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align'],['qemu-riscv32'])]:
            exe = out/target
            flags = ['-std=c11','-O2','-Wall','-Wextra','-Werror', *extra,
                     '-DXINYI_BATTLE_R17=1', '-DXINYI_SPEECH_RT_CANDIDATE='+str(int(a.rt_candidate)),
                     '-I'+wsl_path(ROOT/'linux/voice_speech')]
            command = [cc,*flags,wsl_path(ROOT/names[1]),wsl_path(ROOT/names[2]),
                       '-Wl,'+','.join('--wrap='+n for n in wrap),'-o',wsl_path(exe)]
            for label, args in [('build',command),('run',[*runner,wsl_path(exe)])]:
                with (out/(target+'-'+label+'.log')).open('xb') as log:
                    q = subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                        'ulimit -c 0\nexec timeout --kill-after=3 120 '+shlex.join(args)],
                        stdout=log,stderr=subprocess.STDOUT,timeout=135)
                assert q.returncode==0,(target,label,(out/(target+'-'+label+'.log')).read_text(errors='replace')[-1800:])
            result['runs'].append(dict(target=target,executable_sha256=sha(exe)))
        assert before == {n: sha(ROOT/n) for n in names}
        result['status']='WHOLE_BANK_REAL_READER_HOST_SANITIZER_RV32_MOCK_GUARDS_ALL_KEYS_RELEASE_RECOVERY_PASS'
    finally:
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])


if __name__ == '__main__':
    main()
