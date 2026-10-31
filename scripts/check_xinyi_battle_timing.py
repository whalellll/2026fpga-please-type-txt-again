"""Synthetic-only actual VAD start/optional ASR protocol checks; no audio/model."""
from pathlib import Path
import argparse,hashlib,json,shlex,subprocess
from picture_workspace import ROOT,workspace_path,wsl_path

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path);a=parser.parse_args()
    out=workspace_path(a.output);assert out.is_relative_to((ROOT/'build/picture-e42-20261025').resolve())
    out.mkdir(parents=True,exist_ok=False)
    names=['linux/xinyi_board/battle_timing_test.c','linux/voice_ctc/xqvoice_capture.c',
           'linux/voice_ctc/xqvoice_capture.h','linux/voice_ctc/xqvoice_stream.inc',
           'linux/voice_ctc/xqvoice_session.c','linux/voice_ctc/xqvoice_session.h',
           'linux/voice_ctc/xqvoice_frontend.h','linux/voice_ctc/xqvoice_profile.h',
           'scripts/check_xinyi_battle_timing.py']
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    before={n:sha(ROOT/n) for n in names};result=dict(status='FAILED_PRESERVED',hardware_used=False,runs=[])
    def run(name,args):
        with (out/(name+'.log')).open('xb') as log:
            q=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                'ulimit -c 0\nexec timeout --kill-after=3 60 '+shlex.join(args)],stdout=log,stderr=subprocess.STDOUT,timeout=70)
        assert not q.returncode,(name,(out/(name+'.log')).read_text(errors='replace')[-2000:])
    try:
        for target,cc,extra in [('host','cc',[]),('rv32','/opt/toolchain/bin/riscv32-linux-musl-gcc',['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align']),('sanitizer','cc',['-fsanitize=address,undefined','-fno-sanitize-recover=all','-no-pie'])]:
            exe=out/target
            run(target+'-build',[cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-pthread','-ffunction-sections','-fdata-sections',
                '-DXINYI_BATTLE_R17=1',*extra,*['-I'+wsl_path(ROOT/n) for n in ['linux/voice_ctc','linux/voice','linux/voice_speech','linux/vision','linux/mac_accel','sw/xiangqi','sw/bootloader']],wsl_path(ROOT/names[0]),'-Wl,--gc-sections','-lm','-o',wsl_path(exe)])
            run(target,[*(['qemu-riscv32'] if target=='rv32' else []),wsl_path(exe)])
            assert 'R17_REAL_VAD_FIRST_CONSECUTIVE_BLOCK_NO_LISTENING_OR_NOISE_START_AND_OPTIONAL_WIRE_NEGATIVES_PASS' in (out/(target+'.log')).read_text()
            result['runs'].append(dict(target=target,pass_=True,exe_sha256=sha(exe)))
        assert before=={n:sha(ROOT/n) for n in names}
        result.update(status='R17_REAL_VAD_AND_OPTIONAL_START_PROTOCOL_HOST_RV32_SANITIZER_PASS_NOT_BOARD',source_sha256=before)
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])
if __name__=='__main__':main()
