"""Build/source-reproduce the offline r17 GUI, helper and matching ASR/audio kit.

This is deliberately not a boot/SD installer. The full whole-phrase bank does
not fit PN15's existing 16 MiB initrd aperture; retain that measured boundary.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shlex
import subprocess
import zipfile
from picture_workspace import ROOT, workspace_path, wsl_path
from verify_xinyi_elf import inspect

BASE_GUI = 'eb7f7c7a599b82ffe9402f297a6f00a0fcfc47ab2dde1ed0e5662491048b3208'
BASE_HELPER = 'b0f27d0679a36c07944575add15cf8b33872dbc45a5304a27827d2a0415b3211'
FLAGS = ['XINYI_CPU_HZ=60000000', 'XINYI_HOME_R13=1', 'XINYI_HOME_R15=1',
    'XINYI_GUI_DOUBLE_BUFFER=1', 'XINYI_GUI_RAM_RENDER=0', 'XINYI_GUI_PAGE_DELTAS=1',
    'XINYI_GUI_PAIR_DELTAS=1', 'XINYI_UI_FEEDBACK=1', 'XINYI_COACH_MOVE_AUDIO=1',
    'XINYI_UI_NAV_DIAG=0']


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--evidence-root', required=True, type=Path)
    ap.add_argument('--output', required=True, type=Path)
    a = ap.parse_args()
    logical = a.output.absolute()
    assert logical.is_relative_to(ROOT/'build')
    out = workspace_path(logical)
    p = workspace_path(a.evidence_root)
    assert p.is_relative_to((ROOT/'build/picture-e42-20261025').resolve())
    out.mkdir(parents=True, exist_ok=False)
    sha = lambda b: hashlib.sha256(b).hexdigest()
    payload, sources, programs, proofs = {}, {}, {}, {}
    result = dict(status='FAILED_PRESERVED', installed=False, board_used=False)

    def run(name, args, limit=120):
        with (out/(name+'.log')).open('xb') as log:
            q = subprocess.run(['wsl.exe', '-d', 'Ubuntu-22.04', '--', 'sh', '-c',
                'ulimit -c 0\nexec timeout --kill-after=3 '+str(limit)+' '+shlex.join(args)],
                stdout=log, stderr=subprocess.STDOUT, timeout=limit+15)
        assert not q.returncode, (name, (out/(name+'.log')).read_text(errors='replace')[-2400:])

    def lexical(path):
        s = path.absolute().as_posix()
        return '/mnt/'+s[0].lower()+s[2:]

    def bind(n, h=None):
        n = n.replace('\\', '/')
        assert not Path(n).is_absolute() and '..' not in Path(n).parts, n
        b = (ROOT/n).read_bytes()
        assert h is None or sha(b)==h, n
        assert n not in sources or sources[n]==sha(b), n
        sources[n] = sha(b)

    def bind_build(folder):
        b = (folder/'source-before.sha256').read_bytes()
        assert b==(folder/'source-after.sha256').read_bytes()
        prefix = wsl_path(ROOT)+'/'
        for line in b.decode().splitlines():
            h, name = line.split(None, 1)
            assert name.startswith(prefix)
            bind(name[len(prefix):], h)

    def archive_input(folder, package_name):
        proof = json.loads((p/folder/'result.json').read_text())
        assert 'PASS_NOT_BOARD' in proof['status']
        zpath = Path(proof['archive']['path'])
        raw = zpath.read_bytes()
        assert sha(raw)==proof['archive']['sha256']
        with zipfile.ZipFile(zpath) as z:
            assert z.testzip() is None
            members = {n: z.read(n) for n in z.namelist()}
        payload['asr/'+package_name] = raw
        payload['evidence/'+folder+'.json'] = (p/folder/'result.json').read_bytes()
        return proof, members

    try:
        proof_folders = ['render-final-tray-r09', 'render-voice4-final-tray-r03', 'render-final-closeout-r10',
            'runtime-dependency-audit-r02', 'whole-playback-final-r04',
            'model-metrics-frozen-r01', 'model-metrics-voice-r01',
            'whole-yaoyao-adaptive-validation-r02']
        for name in proof_folders:
            raw = (p/name/'result.json').read_bytes()
            proof = json.loads(raw)
            assert 'PASS' in proof['status'], name
            # The voice metrics proof includes externally extracted Git blobs
            # in its private input manifest, not in this checkout's namespace.
            if name not in ['model-metrics-voice-r01','render-final-tray-r09','render-voice4-final-tray-r03']:
                for n, h in proof.get('source_sha256', {}).items():
                    bind(n, h)
            proofs[name] = proof
            payload['evidence/'+name+'.json'] = raw
        assert {r['target'] for r in proofs['render-final-tray-r09']['runs']}=={'host','sanitizer','rv32','scalar-oracle'}
        assert all(r['full_pixel_hash_records']==300 for r in proofs['render-final-tray-r09']['runs'])
        assert proofs['render-final-closeout-r10']['old_font_header_byte_identical']
        for name in ['runtime-final-r03','runtime-main-r02','runtime-timing-r02','runtime-platform-r01']:
            filename = 'platform-validation.json' if name=='runtime-platform-r01' else 'result.json'
            payload['evidence/'+name+'.json'] = (p/name/filename).read_bytes()

        for name, battle, voice4 in [('baseline',0,0),('balanced',1,0),('voice4',1,1)]:
            dest = lexical(logical/('build-'+name))
            run(name+'-build', ['env', *FLAGS, 'XINYI_BATTLE_R17='+str(battle),
                'XINYI_ASR_VOICE4='+str(voice4), 'sh', wsl_path(ROOT/'linux/xinyi_board/build.sh'), dest])
            folder = out/('build-'+name)
            bind_build(folder)
            elf = out/('gui-'+name+'.elf')
            run(name+'-strip', ['/opt/toolchain/bin/riscv32-linux-musl-strip', '--strip-all',
                '-o', wsl_path(elf), dest+'/xinyi-one'], 30)
            b = elf.read_bytes()
            assert b'XINYI_NAV_DIAG_' not in b
            assert inspect(elf)['allocated']==inspect(folder/'xinyi-one')['allocated']
            if not battle: assert sha(b)==BASE_GUI
            programs['gui-'+name] = dict(bytes=len(b), sha256=sha(b), battle_r17=battle, asr_voice4=voice4)
            payload['software/gui-'+name+'.rv32.elf'] = b
        for flag in [0,1]:
            name = 'speech-flag'+str(flag)
            dest = lexical(logical/name)
            run(name+'-build', ['env', 'XINYI_COACH_MOVE_AUDIO=1', 'XINYI_BATTLE_R17='+str(flag),
                'sh', wsl_path(ROOT/'linux/xinyi_board/build_speech.sh'), dest])
            bind_build(out/name)
            elf = out/(name+'.elf')
            run(name+'-strip', ['/opt/toolchain/bin/riscv32-linux-musl-strip','--strip-all',
                '-o',wsl_path(elf),dest+'/xinyi-speech-worker'],30)
            b = elf.read_bytes()
            if not flag: assert sha(b)==BASE_HELPER
            programs[name] = dict(bytes=len(b),sha256=sha(b),battle_r17=flag)
            payload['software/'+name+'.rv32.elf'] = b
        balanced, bm = archive_input('balanced-worker-delivery-r01','balanced24-source-candidate.zip')
        voice4, vm = archive_input('voice-candidate-timing-r02','voice4-source-candidate.zip')
        payload['software/asr-balanced24.rv32.elf'] = bm['software/asr-balanced24-flag1.rv32.elf']
        payload['models/asr-balanced24.bin'] = bm['source/linux/voice_ctc/balanced24.bin']
        payload['software/asr-voice4.rv32.elf'] = vm['software/xqvoice-voice4.rv32.elf']
        payload['models/asr-voice4.bin'] = vm['model/xqvoice_int8.bin']
        assert sha(payload['software/asr-balanced24.rv32.elf'])==balanced['programs']['flag1']['sha256']
        assert sha(payload['software/asr-voice4.rv32.elf'])==voice4['program_sha256']
        assert sha(payload['models/asr-voice4.bin'])==voice4['model_sha256']

        pcm = p/'whole-yaoyao-adaptive-r02'
        raw = (pcm/'manifest.json').read_bytes()
        m = json.loads(raw)
        assert m['complete'] and m['expected_entries']==5103
        expected = set()
        for first in [*range(16,25),*range(28,31),*range(1,10)]:
            seconds = range(1,10) if first in range(16,25) else range(16,25)
            for second in seconds:
                for action in range(25,28):
                    for last in range(1,10):
                        expected.add('whole/%02d-%02d-%02d-%02d.pcm'%(first,second,action,last))
        assert set(m['files'])==expected and len(expected)==5103
        for n, row in m['files'].items():
            b = (pcm/n).read_bytes()
            assert sha(b)==row['sha256'] and len(b)==2*row['samples'] and 0<row['samples']<=15360
            payload['pcm/'+n] = b
        payload['pcm/manifest.json'] = raw
        for f in sorted((pcm/'audition-pairs').glob('*.wav')):
            payload['audition/'+f.name] = f.read_bytes()
        for mode in range(3):
            f = p/'previews-final-r02'/('mode-'+str(mode)+'.png')
            payload['preview/synthetic-mode-'+str(mode)+'.png'] = f.read_bytes()
        for n in ['scripts/prepare_xinyi_battle_r17.py','scripts/picture_workspace.py',
            'scripts/verify_xinyi_elf.py','scripts/check_xinyi_battle_r17.py',
            'scripts/check_xinyi_runtime.py','scripts/check_xinyi_main_loop.py',
            'scripts/check_xinyi_battle_timing.py','scripts/check_xinyi_whole_speech.py',
            'linux/xinyi/gen_battle_font.py','linux/xinyi/fonts/battle-r17.json',
            'linux/xinyi/fonts/OFL.txt']:
            bind(n)
        for n,h in sources.items():
            b = (ROOT/n).read_bytes();assert sha(b)==h
            payload['source/'+n] = b
        payload['README.md'] = '''# r17 offline native battle/voice candidate

Not installed, not a full SD image, and no physical one-second/clarity acceptance.
PN15 full SD remains the last tested baseline. No board access was performed.

Three battle modes, four chess-disc navigation buttons and one shared status
tray. Keyboard/mouse is silent and mic-off; voice/mouse share a preserved game;
image remains an independent physical board. Esc uses actual safe cancellation.
Image and utterance latency lock on actual matching-bank scan acknowledgement;
old ASR without onset metadata reports --. AI time is separate. Red win rate is
pure engine WDL win probability, with missing data shown as --.

LUTs are labeled E42 subtree references, include LUTRAM, exclude shared fabric.
Speedups without matching CPU60 measurements are pending. Parameter counts are
frozen inference weights+bias; full NNUE includes feature/PSQT tables, excludes
repacked duplicates. See evidence for exact per-layer/static counts.

gui-balanced pairs only with asr-balanced24 and models/asr-balanced24.bin.
gui-voice4 pairs only with asr-voice4 and models/asr-voice4.bin. Voice4 remains
an independent quality candidate, not a promoted default model. The nested ASR
ZIPs contain their exact sources and independent byte-rebuild proofs.

Both new GUIs require speech-flag1 and pcm/whole (kind9). Never combine new GUI
with old helper/bank. Legacy helper rejects kind9; kind8/old240ms contract stays.
Yaoyao is synthesized as full four-token phrases at finite native rates1.2..1.4;
no resampling or clipping phonemes. All5103 files <=960ms; plus4ms prime <=964ms.
The runtime additionally measures scheduling/startup/drain; this PCM bound alone
does not prove result-to-complete <=1s. Audition WAVs were not automatically played.

The complete bank is ~150MB raw/~87MB even when concatenated and gzipped. PN15's
entire initrd aperture is16MiB. These resources cannot be appended to its current
overlay or called a working SD update. Standalone SD storage/loading integration,
real clarity/underflow and physical latency remain open; no SD/Flash/selector writes.
The selected frozen vision worker/models, engine and rest of PN15 are not changed
or redistributed here. Source/binaries/resources form a reviewable offline kit.

Build GUI from source/ using its linux/xinyi_board/build.sh with CPU60000000,
HOME_R13=1 HOME_R15=1 GUI_DOUBLE_BUFFER=1 GUI_RAM_RENDER=0 GUI_PAGE_DELTAS=1
GUI_PAIR_DELTAS=1 UI_FEEDBACK=1 COACH_MOVE_AUDIO=1 UI_NAV_DIAG=0 BATTLE_R17=1;
all names have XINYI_ prefix. ASR_VOICE4=0/1 selects matching label/variant.
For exact r16 rollback use BATTLE_R17=0 ASR_VOICE4=0. Output must be $PWD/build/… .
Build helper with XINYI_COACH_MOVE_AUDIO=1 XINYI_BATTLE_R17=1 and build_speech.sh.
Strip each ELF with riscv32-linux-musl-strip --strip-all. No model/board is used
for those builds. Final packager independently rebuilds all five binaries from ZIP.
All preview boards/numbers are synthetic fixture states, not physical evidence.
'''.encode()
        manifest = dict(schema='xinyi-battle-r17-offline/1',installed=False,board_used=False,
            physical_one_second_pass=False,full_sd_image=False,programs=programs,
            source_sha256=sources,members={n:dict(bytes=len(b),sha256=sha(b)) for n,b in payload.items()})
        payload['manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
        archive=out/'xinyi-battle-voice-offline-r17-r01.zip'
        with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for n,b in sorted(payload.items()):z.writestr(n,b)
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            for n,row in manifest['members'].items():assert sha(z.read(n))==row['sha256']
            exported=out/'exported';exported.mkdir()
            for n in z.namelist():
                if n.startswith('source/'):z.extract(n,exported)
        native=wsl_path(exported/'source')
        for name,battle,v4 in [('baseline',0,0),('balanced',1,0),('voice4',1,1)]:
            dest=native+'/build/'+name
            run('zip-'+name,['env',*FLAGS,'XINYI_BATTLE_R17='+str(battle),'XINYI_ASR_VOICE4='+str(v4),
                'sh',native+'/linux/xinyi_board/build.sh',dest])
            elf=out/('zip-'+name+'.elf')
            run('zip-'+name+'-strip',['/opt/toolchain/bin/riscv32-linux-musl-strip','--strip-all','-o',wsl_path(elf),dest+'/xinyi-one'],30)
            assert elf.read_bytes()==payload['software/gui-'+name+'.rv32.elf']
        for flag in [0,1]:
            dest=native+'/build/speech'+str(flag)
            run('zip-speech'+str(flag),['env','XINYI_COACH_MOVE_AUDIO=1','XINYI_BATTLE_R17='+str(flag),
                'sh',native+'/linux/xinyi_board/build_speech.sh',dest])
            elf=out/('zip-speech'+str(flag)+'.elf')
            run('zip-speech'+str(flag)+'-strip',['/opt/toolchain/bin/riscv32-linux-musl-strip','--strip-all','-o',wsl_path(elf),dest+'/xinyi-speech-worker'],30)
            assert elf.read_bytes()==payload['software/speech-flag'+str(flag)+'.rv32.elf']
        assert all(sha((ROOT/n).read_bytes())==h for n,h in sources.items())
        result.update(status='R17_FULL_OFFLINE_KIT_SHA_CRC_FIVE_ZIP_ELF_REBUILDS_PASS_NOT_BOARD',
            programs=programs,source_sha256=sources,archive=dict(path=str(archive),bytes=archive.stat().st_size,
            sha256=sha(archive.read_bytes()),members=len(payload),sha_crc_pass=True,zip_binary_rebuilds=5))
    finally:
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])


if __name__=='__main__':main()
