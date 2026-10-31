"""Bounded numeric actual-seam validation; no devices or audio playback."""
import argparse, hashlib, json, shlex, subprocess
from pathlib import Path
from picture_workspace import ROOT, workspace_path, wsl_path

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--rt-candidate',action='store_true',help='Explicit opt-in to the rejected-board CPU60 RT candidate seam')
    a=ap.parse_args()
    if not a.rt_candidate:ap.error('This candidate-only numeric seam requires --rt-candidate; R01 uses its original conversion')
    out=workspace_path(a.output);out.mkdir(parents=True,exist_ok=False)
    names=['linux/xinyi_board/speech_time60_test.c','linux/voice_speech/tests/test_speech_linux.c',
        'linux/voice_speech/xq_speech_linux.c','linux/voice_speech/xq_speech.h',
        'linux/voice_speech/xq_move_speech.h','linux/voice_speech/xq_whole_speech.h',
        'linux/voice_speech/xq_whole_bank.h','linux/voice_speech/xq_whole_bank.c',
        'linux/xinyi_board/gui_options.h','sw/xiangqi/xiangqi_search.h',
        'scripts/check_xinyi_speech_time60.py','scripts/picture_workspace.py',
        'linux/voice_speech/xq_speech_linux_candidate.inc','linux/voice_speech/xq_whole_bank_candidate.inc']
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    before={n:sha(ROOT/n) for n in names};result=dict(status='FAILED_PRESERVED',hardware_used=False,rt_candidate=True,source_sha256=before,runs=[])
    for n in names:
        p=out/'source'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/n).read_bytes())
    def run(name,args):
        with (out/(name+'.log')).open('xb') as f:
            p=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c','ulimit -c 0\nexec timeout --kill-after=3 60 '+shlex.join(args)],stdout=f,stderr=subprocess.STDOUT,timeout=75)
        assert p.returncode==0,(name,(out/(name+'.log')).read_text(errors='replace')[-2200:])
    try:
        for target in ['host','sanitizer','rv32']:
            cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'cc'
            flags=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align'] if target=='rv32' else []
            if target=='sanitizer':flags=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-no-pie']
            exe=out/target
            run(target+'-build',[cc,'-std=gnu11','-O2','-Wall','-Wextra','-Werror',*flags,
                '-DXINYI_COACH_MOVE_AUDIO=1','-DXINYI_BATTLE_R17=1','-I'+wsl_path(ROOT/'linux/voice_speech'),'-I'+wsl_path(ROOT/'sw/xiangqi'),
                '-DXINYI_SPEECH_RT_CANDIDATE=1',
                wsl_path(ROOT/names[0]),wsl_path(ROOT/'linux/voice_speech/xq_whole_bank.c'),'-Wl,--wrap=read,--wrap=write,--wrap=__read_chk','-o',wsl_path(exe)])
            run(target,[*(['qemu-riscv32'] if target=='rv32' else []),wsl_path(exe)])
            text=(out/(target+'.log')).read_text();assert 'R18_ACTUAL_TIME60_EXACT_PASS cases=1000040' in text
            result['runs'].append(dict(target=target,status='PASS',output=text.strip(),sha256=sha(exe)))
        run('rv32-disassembly',['/opt/toolchain/bin/riscv32-linux-musl-objdump','-d',wsl_path(out/'rv32')])
        text=(out/'rv32-disassembly.log').read_text();start=text.index('<seam60>:');block=text[start:text.index('\n\n',start)]
        assert ('mulhu' in block or 'divu' in block) and '__udivdi3' not in block and '__divdi3' not in block
        (out/'seam60-disassembly.txt').write_bytes(block.encode())
        assert before=={n:sha(ROOT/n) for n in names}
        result['status']='ACTUAL_CPU60_TIME_SEAM_MILLION_PAIRS_HOST_SAN_RV32_WRAP_NEGATIVES_U32_DIVIDE_NO_64DIV_PASS_NOT_BOARD'
    finally:(out/'result.json').write_bytes((json.dumps(result,indent=2)+'\n').encode())
    print(result['status'])

if __name__=='__main__':main()
