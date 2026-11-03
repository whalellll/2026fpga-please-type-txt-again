"""Rebuild the frozen r05 ASR using the published numerical/ABI settings."""
import argparse,hashlib,json,os,shlex,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def wsl(p):
    s=p.resolve().as_posix();assert s.startswith('G:/fpga/')
    return '/mnt/g/'+s[3:]
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--distribution',default='pikafish-verify');a=ap.parse_args()
    out=a.output.resolve();assert out.is_relative_to(R/'build') and not out.exists();out.mkdir(parents=True)
    v=R/'linux/voice3';origin=json.loads((v/'ORIGIN.json').read_text())
    for name,h in origin['source_files_sha256'].items():assert sha(v/name)==h,name
    src=v/'source/linux/voice_ctc';acc=v/'source/linux/voice_accel'
    names=['xqvoice_runtime.c','xqvoice_frontend.c','xqvoice_decode.c','xqvoice_capture.c','xqvoice_profile.c','voice_small_backend.c']
    common=['-std=c11','-D_POSIX_C_SOURCE=200809L','-O2','-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections','-pthread','-DXQV_HOP_SAMPLES=320u','-DXQV_CTC_BEAM=4u','-DXQVOICE_PROFILE_ENABLED','-I'+wsl(src),'-I'+wsl(acc)]
    script=['set -eu','export PATH=/opt/toolchain/bin:/usr/bin:/bin','export TMPDIR='+shlex.quote(wsl(out))]
    for target,cc,extra in [('asr-host','gcc',[]),('xqvoice-voice3','riscv32-linux-musl-gcc',['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align'])]:
        script.append(shlex.join([cc,*common,*extra,*[wsl(src/n) for n in names],'-Wl,--gc-sections','-lm','-o',wsl(out/target)]))
    script+=['cp '+shlex.quote(wsl(out/'xqvoice-voice3'))+' '+shlex.quote(wsl(out/'xqvoice-voice3.unstripped')),
             'riscv32-linux-musl-strip '+shlex.quote(wsl(out/'xqvoice-voice3')),
             'riscv32-linux-musl-gcc --version > '+shlex.quote(wsl(out/'compiler.txt'))]
    p=out/'build.sh';p.write_bytes(('\n'.join(script)+'\n').encode())
    with (out/'build.log').open('xb') as log:
        proc=subprocess.run(['wsl.exe','-d',a.distribution,'--','sh',wsl(p)],stdout=log,stderr=subprocess.STDOUT,timeout=600)
    assert proc.returncode==0,'See build.log'
    assert sha(out/'xqvoice-voice3')==origin['published_runtime_sha256'],'Rebuild differs from frozen publication'
    record=dict(status='VOICE3_PUBLISHED_RUNTIME_BYTE_IDENTICAL_REBUILD_PASS_NOT_BOARD',cpu_hz_detected_at_runtime=True,model_sha256=sha(v/'xqvoice_int8.bin'),runtime_sha256=sha(out/'xqvoice-voice3'),origin_sha256=sha(v/'ORIGIN.json'),source_commit=origin['source_commit'],hardware_used=False)
    (out/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(record['status'])
if __name__=='__main__':main()
