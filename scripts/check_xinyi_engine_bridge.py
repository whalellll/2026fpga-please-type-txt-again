"""Verify the new async engine adapter with an explicit protocol-only fixture."""
from pathlib import Path
import argparse, hashlib, json, shlex, subprocess
ROOT=Path(__file__).resolve().parents[1]
def linux(path):
    s=path.resolve().as_posix();return '/mnt/'+s[0].lower()+s[2:]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--battle-r17',action='store_true');a=p.parse_args()
    from picture_workspace import workspace_path
    assert a.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(a.output);assert not out.exists();out.mkdir(parents=True)
    sources=['linux/xinyi_board/engine_bridge.c','linux/xinyi_board/engine_bridge.h',
      'linux/xinyi_board/test_engine_bridge.c','linux/xinyi_board/fake_engine_service.c',
      'sw/xiangqi/xiangqi_search.c','sw/xiangqi/xiangqi_search.h','sw/xiangqi/xiangqi_pikafish_link.c',
      'sw/xiangqi/xiangqi_pikafish_link.h','linux/voice_speech/xq_speech.c','linux/voice_speech/xq_speech.h',
      'sw/bootloader/crc32_fast.c','sw/bootloader/crc32_fast.h']
    before={name:sha(ROOT/name) for name in sources}
    includes=['linux/xinyi_board','sw/xiangqi','linux/voice_speech','sw/bootloader']
    common=['-std=c11','-O2','-Wall','-Wextra','-Werror','-DXINYI_BATTLE_R17='+str(int(a.battle_r17))]+['-I'+linux(ROOT/d) for d in includes]
    link=[linux(ROOT/name) for name in [sources[0],sources[2],sources[4],sources[6],sources[8],sources[10]]]
    lines=['set -eu']
    for cc,target,extra in [('gcc','host',[]),('/opt/toolchain/bin/riscv32-linux-musl-gcc','rv32',['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align'])]:
        fixture=linux(out/('fake-engine-'+target));test=linux(out/('test-engine-'+target))
        lines.append(shlex.join([cc,*common,*extra,linux(ROOT/sources[3]),'-o',fixture]))
        lines.append(shlex.join([cc,*common,*extra,*link,'-o',test]))
        # QEMU can spawn the native host protocol fixture without registering
        # a binfmt handler or confusing nested executor setup with product IO.
        lines.append(shlex.join([*(['qemu-riscv32'] if target=='rv32' else []),test,linux(out/'fake-engine-host')]))
    script=out/'run.sh';script.write_bytes(('\n'.join(lines)+'\n').encode())
    with (out/'run.log').open('wb') as log:
        r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','timeout','--kill-after=5','120','sh',linux(script)],stdout=log,stderr=subprocess.STDOUT,timeout=150)
    body=(out/'run.log').read_text(errors='replace');assert r.returncode==0,body[-4000:]
    assert body.count('XINYI_ENGINE_BRIDGE_IDENTITY_LEGALITY_CANCEL_AND_REUSE_PASS')==2
    assert all(sha(ROOT/name)==digest for name,digest in before.items())
    (out/'result.json').write_text(json.dumps(dict(status='HOST_RV32_ENGINE_BRIDGE_PASS_NOT_REAL_ENGINE',battle_r17=a.battle_r17,hardware_used=False,
      source_stable=True,source_sha256=before,outputs_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file()},
      limitations='Protocol fixture only; official dedicated engine service must be separately linked and board-validated.'),indent=2)+'\n',encoding='utf-8')
    print('XINYI_ENGINE_BRIDGE_HOST_RV32_PASS')
if __name__=='__main__':main()
