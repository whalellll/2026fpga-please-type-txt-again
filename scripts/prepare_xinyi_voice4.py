"""Prepare a separate CPU60 voice_4 candidate from pinned published Git blobs.

Does not select it in the GUI/SD, read recordings, or execute upstream scripts.
All weights/tables/compiled files stay in the explicit private E build junction.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import struct
import subprocess
import zipfile

from picture_workspace import ROOT, workspace_path, wsl_path
from xinyi_voice4_timing import adapt

BASE = '2cc38efb3162eba6be8a6f77a87f99f63b4c323a'
MODEL = 'f41624fa7d2f466d693adbd9e49178feddfbd049'
MODEL_SHA = '85a1f28ee441b003b73739e5dae0faf5b9ebc4406881a23767aed6ad081e9fb9'
TABLES_SHA = '7fe9f783e0e1d9d72b00976c4ba768ad7e006ebd06d7a6b6b7d4cbc6e08d705f'
NAMES = ['xqvoice_runtime.c', 'xqvoice_frontend.c', 'xqvoice_frontend.h',
         'xqvoice_decode.c', 'xqvoice_decode.h', 'xqvoice_capture.c',
         'xqvoice_capture.h', 'xqvoice_mac.h', 'xqvoice_pipeline.inc',
         'xqvoice_stream.inc', 'xqvoice_worker.inc', 'voice_small_backend.c',
         'xqvoice_profile.c', 'xqvoice_profile.h', 'pango_audio_uapi.h']
SOURCES = ['xqvoice_runtime.c', 'xqvoice_frontend.c', 'xqvoice_decode.c',
           'xqvoice_capture.c', 'xqvoice_profile.c', 'voice_small_backend.c']
SHA = lambda b: hashlib.sha256(b).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--utterance-timing', action='store_true',
                    help='Explicit r17 live VAD-onset fields; no model/numeric changes')
    a = ap.parse_args()
    out = workspace_path(a.output)
    assert out.is_relative_to((ROOT / 'build/picture-e42-20261025').resolve())
    out.mkdir(parents=True, exist_ok=False)
    origin, files, rows = {}, {}, []
    result = dict(status='FAILED_PRESERVED', hardware_used=False, installed=False,
                  default_selected=False, recognition_quality_accepted=False)

    def write(name, data):
        q = out / name
        q.parent.mkdir(parents=True, exist_ok=True)
        with q.open('xb') as f:
            f.write(data)
        files[name] = dict(bytes=len(data), sha256=SHA(data))

    def blob(commit, path, dest):
        data = subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT, timeout=20)
        origin[dest] = dict(commit=commit, path=path, sha256=SHA(data))
        if a.utterance_timing and dest.startswith('source/linux/voice_ctc/'):
            changed = adapt(Path(dest).name, data)
            if changed != data:
                write('upstream-original/' + Path(dest).name, data)
                data = changed
                origin[dest]['timing_overlay_sha256'] = SHA(data)
        write(dest, data)
        return data

    def run(name, args, expected=(0,), limit=120, env=None):
        prefix = ['env', *(f'{k}={v}' for k, v in (env or {}).items())]
        p = subprocess.run(['wsl.exe', '-d', 'Ubuntu-22.04', '--', 'sh', '-c',
             'ulimit -c 0\nexec timeout --kill-after=3 ' + str(limit) + ' ' + shlex.join(prefix + args)],
             capture_output=True, timeout=limit + 15)
        write('evidence/' + name + '.log', p.stdout + p.stderr)
        assert p.returncode in expected, (name, p.returncode, p.stderr[-1800:])
        return p

    try:
        for name in NAMES:
            blob(BASE, 'voice/voice_3/source/linux/voice_ctc/' + name,
                 'source/linux/voice_ctc/' + name)
        uapi = blob(BASE, 'voice/voice_3/source/linux/voice_accel/pango_voice_uapi.h',
                    'source/linux/voice_accel/pango_voice_uapi.h')
        assert uapi == (ROOT / 'linux/voice_accel/pango_voice_uapi.h').read_bytes(), 'E42 UAPI changed'
        model = blob(MODEL, 'voice/voice_4/model/xqvoice_int8.bin', 'model/xqvoice_int8.bin')
        tables = blob(MODEL, 'voice/voice_4/model/include/xqvoice_tables.h',
                      'source/linux/voice_ctc/xqvoice_tables.h')
        assert SHA(model) == MODEL_SHA and len(model) == 29400 and SHA(tables) == TABLES_SHA
        blob(MODEL, 'voice/voice_4/manifest.json', 'evidence/upstream-model-manifest.json')
        blob(MODEL, 'voice/voice_4/README.md', 'evidence/upstream-readme.md')
        upstream = json.loads((out / 'evidence/upstream-model-manifest.json').read_text())
        assert upstream['replacement_eligible'] is False and upstream['actual_board'] is False
        assert upstream['deployment_config']['hop_samples'] == 320
        assert upstream['deployment_config']['ctc_beam'] == 4
        assert upstream['deployment_config']['endpoint_ms'] == 450
        mock = blob(BASE, 'voice/voice_3/source/linux/voice_ctc/tests/voice2_device_mock.c',
                    'source/linux/voice_ctc/tests/device_mock.original.c')
        needle = b'   memcpy(&t->output[p*model.cout+n],&sum,4);'
        assert mock.count(needle) == 1
        mock = mock.replace(needle, b'   if(getenv("XY_VOICE4_MOCK_BAD_DOT"))sum^=1;\n' + needle)
        write('source/linux/voice_ctc/tests/device_mock.c', mock)
        build = '''#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=${1:?fresh build directory below source/build required}
case "$out" in "$root"/build/*) ;; *) exit 2;; esac
test ! -e "$out"
mkdir -p "$out"
cc=${CC:-/opt/toolchain/bin/riscv32-linux-musl-gcc}
src="$root/linux/voice_ctc"
"$cc" -std=c11 -D_POSIX_C_SOURCE=200809L -DXQV_HOP_SAMPLES=320u -DXQV_CTC_BEAM=4u -O2 -Wall -Wextra -Werror -ffile-prefix-map="$root"=. -pthread -static -march=rv32ima -mabi=ilp32 -mstrict-align "$src/xqvoice_runtime.c" "$src/xqvoice_frontend.c" "$src/xqvoice_decode.c" "$src/xqvoice_capture.c" "$src/xqvoice_profile.c" "$src/voice_small_backend.c" -lm -o "$out/xqvoice-voice4"
"${cc%gcc}strip" --strip-all -o "$out/xqvoice-voice4.rv32.elf" "$out/xqvoice-voice4"
"$cc" --version > "$out/compiler.txt"
'''.encode()
        if a.utterance_timing:
            build = build.replace(b' -O2 ', b' -DXINYI_BATTLE_R17=${XINYI_BATTLE_R17:-1} -O2 ', 1)
        write('source/build.sh', build)
        write('source/scripts/prepare_xinyi_voice4.py', Path(__file__).read_bytes())
        write('source/scripts/xinyi_voice4_timing.py', (ROOT / 'scripts/xinyi_voice4_timing.py').read_bytes())
        write('README.md', b'''# Independent CPU60/E42 voice_4 software candidate

Not installed, not selected as product default, not accuracy-accepted. Old
balanced24 remains the fallback. Source is pinned voice_3 r05 CPU60 synchronous
/dev/pango-voice0 ABI1, with voice_4 model AND matching normalization/quantization
tables. No new RTL, driver, training or recordings. 20ms hop, CTC4, 450ms endpoint.
Do not copy voice_4 runtime_source's old MAC backend into this CPU60 build.

Run `sh source/build.sh "$PWD/source/build/rv32"` from this package root.
Model is model/xqvoice_int8.bin. Set XQVOICE_RUNTIME to the built static program
and XQVOICE_MODEL to that model only in an explicit future candidate launch.
No launch/SD script is included; this preparation does not select these values.
The GUI uses resident XQW1 protocol; synthetic layer traces test integer/packing
semantics with an explicit ioctl device mock, not speech recognition quality,
audio input, FPGA/DMA timing or real cancellation/drain.
Upstream replacement_eligible=false is preserved; new31 validation was30/31,
with no improvement over the old model. No physical 1s claim.
''')
        if a.utterance_timing:
            write('TIMING.md', b'''Optional XQW1 RESULT fields: utterance_start_us (absolute CLOCK_MONOTONIC us)
and utterance_to_result_us (finished-start). Timestamp the software observation
of the first block of the original successful consecutive VAD-start run; reset
rejected short blips and exclude waiting to speak. Not an acoustic timestamp.
Emit nonzero only for completed live input whose existing tail_valid checks
and began<=start<=last_voice ordering pass. Absent/zero fields are unavailable.
This independent candidate defaults XINYI_BATTLE_R17=1; override to0 reproduces
the untimed voice4 candidate, without selecting either as the product default.
''')
        native = wsl_path(out / 'source')
        src = native + '/linux/voice_ctc'
        common = ['-std=c11', '-D_POSIX_C_SOURCE=200809L', '-DXQV_HOP_SAMPLES=320u',
                  '-DXQV_CTC_BEAM=4u', '-O2', '-Wall', '-Wextra', '-Werror',
                  '-pthread', '-ffile-prefix-map=' + native + '=.']
        if a.utterance_timing:
            common += ['-DXINYI_BATTLE_R17=1']
            write('source/linux/voice_ctc/tests/voice4_capture_timing_test.c',
                  (ROOT / 'linux/xinyi_board/voice4_capture_timing_test.c').read_bytes())
        source_args = [src + '/' + n for n in SOURCES]
        model_path = wsl_path(out / 'model/xqvoice_int8.bin')
        for t in [1, 3, 16, 31, 64, 100]:
            data = struct.pack('<I', t) + bytes((i * 73 + t * 29) & 255 for i in range(t * 40))
            write(f'synthetic/features-{t}.bin', data)
        bad_model = bytearray(model)
        bad_model[-1] ^= 1
        write('synthetic/corrupt-model.bin', bad_model)
        old = subprocess.check_output(['git', 'show', BASE + ':voice/voice_3/bundle/model/xqvoice_int8.bin'], cwd=ROOT, timeout=20)
        write('synthetic/wrong-table-model.bin', old)
        for target, cc, extra, runner in [
            ('host', 'cc', [], []),
            ('rv32', '/opt/toolchain/bin/riscv32-linux-musl-gcc',
             ['-static', '-march=rv32ima', '-mabi=ilp32', '-mstrict-align'], ['qemu-riscv32'])]:
            exe = wsl_path(out / ('test-' + target))
            run(target + '-mock-build', [cc, *common, *extra, *source_args,
                src + '/tests/device_mock.c', '-Wl,--wrap=open,--wrap=close,--wrap=ioctl', '-lm', '-o', exe])
            run(target + '-selftest', [*runner, exe, '--selftest'])
            if a.utterance_timing:
                timing = wsl_path(out / ('timing-' + target))
                run(target + '-capture-timing-build', [cc, *common, *extra, '-I' + src,
                    src + '/tests/voice4_capture_timing_test.c', src + '/xqvoice_capture.c',
                    src + '/xqvoice_frontend.c', src + '/xqvoice_profile.c',
                    '-Wl,--wrap=open,--wrap=close,--wrap=flock,--wrap=read,--wrap=ioctl,--wrap=clock_gettime', '-lm', '-o', timing])
                run(target + '-capture-timing', [*runner, timing])
            for t in [1, 3, 16, 31, 64, 100]:
                inp = wsl_path(out / f'synthetic/features-{t}.bin')
                paths = []
                for backend in ['cpu', 'mac-verify']:
                    trace = out / f'evidence/{target}-{t}-{backend}.trace'
                    q = run(f'{target}-{t}-{backend}', [*runner, exe, model_path, inp, wsl_path(trace), backend], expected=(0, 25))
                    paths.append((trace.read_bytes(), q.returncode))
                assert paths[0] == paths[1] and paths[0][0], (target, t, 'full layer mismatch')
                rows.append(dict(target=target,frames=t,trace_bytes=len(paths[0][0]),
                                 trace_sha256=SHA(paths[0][0]),exact=True,return_code=paths[0][1]))
            inp = wsl_path(out / 'synthetic/features-31.bin')
            for label, env, backend, model_file, rc in [
                ('wrong-dot', {'XY_VOICE4_MOCK_BAD_DOT': '1'}, 'mac-verify', model_path, 23),
                ('missing-capability', {'VOICE2_NO_CAPABILITY': '1'}, 'mac', model_path, 6),
                ('model-io-failure', {'VOICE2_MODEL_FAIL': '1'}, 'mac', model_path, 22),
                ('tile-timeout', {'VOICE2_TILE_TIMEOUT': '1'}, 'mac', model_path, 22),
                ('corrupt-model', {}, 'cpu', wsl_path(out / 'synthetic/corrupt-model.bin'), 10),
                ('wrong-table', {}, 'cpu', wsl_path(out / 'synthetic/wrong-table-model.bin'), 10)]:
                run(target + '-' + label, [*runner, exe, model_file, inp,
                    wsl_path(out / ('evidence/' + target + '-' + label + '.trace')), backend], expected=(rc,), env=env)
        assert [r['trace_sha256'] for r in rows[:6]] == [r['trace_sha256'] for r in rows[6:]]
        run('production-build', ['sh', native + '/build.sh', native + '/build/production'])
        program = (out / 'source/build/production/xqvoice-voice4.rv32.elf').read_bytes()
        write('software/xqvoice-voice4.rv32.elf', program)
        if a.utterance_timing:
            run('timing-flag0-build', ['sh', native + '/build.sh', native + '/build/timing-off'], env={'XINYI_BATTLE_R17': '0'})
            flag0 = (out / 'source/build/timing-off/xqvoice-voice4.rv32.elf').read_bytes()
            assert SHA(flag0) == '07be0ddbda2716bacd47ce95cfcc8ca08c6a5eabed62fdd3242d4e8106244108', 'Timing-off differs from original independent voice4'
        write('ORIGIN.json', (json.dumps(origin, indent=2) + '\n').encode())
        manifest = dict(schema='xinyi-voice4-cpu60-candidate/1', source_commit=BASE,
            model_commit=MODEL, model_sha256=MODEL_SHA, tables_sha256=TABLES_SHA,
            program_sha256=SHA(program), program_bytes=len(program), model_promoted=False,
            hardware_used=False, installed=False, default_selected=False,
            format='XQVINT8 v1 /22 channels', hop_samples=320, ctc_beam=4,
            endpoint_ms=450, device='/dev/pango-voice0', asynchronous=False,
            optional_utterance_timing=a.utterance_timing,
            mock_full_layer_records=rows, mock_negative_cases_per_target=6,
            members=files.copy())
        write('manifest.json', (json.dumps(manifest, indent=2) + '\n').encode())
        archive = out / 'xinyi-voice4-cpu60-offline-r17-r01.zip'
        with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for n in files:
                z.writestr(n, (out / n).read_bytes())
        exported = out / 'exported'
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            for n, row in manifest['members'].items():
                assert SHA(z.read(n)) == row['sha256']
            z.extractall(exported)
        ex = wsl_path(exported / 'source')
        run('zip-source-build', ['sh', ex + '/build.sh', ex + '/build/rebuilt'])
        assert program == (exported / 'source/build/rebuilt/xqvoice-voice4.rv32.elf').read_bytes()
        result.update(status='VOICE4_CPU60_SYNTHETIC_HOST_RV32_INTEGER_CONTRACT_AND_ZIP_REBUILD_PASS_NOT_BOARD',
            program_sha256=SHA(program), model_sha256=MODEL_SHA, tables_sha256=TABLES_SHA,
            optional_utterance_timing=a.utterance_timing,
            synthetic_records=rows, negative_cases_per_target=6, zip_rebuild_exact=True,
            archive=dict(path=str(archive),bytes=archive.stat().st_size,sha256=SHA(archive.read_bytes()),members=len(files)))
    finally:
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'])


if __name__ == '__main__':
    main()
