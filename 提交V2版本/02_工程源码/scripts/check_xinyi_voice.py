"""Bounded software-only voice intake checks; synthetic inputs and device mocks."""
from pathlib import Path
import argparse, hashlib, json, random, shlex, subprocess, time

ROOT = Path(__file__).resolve().parents[1]
MODEL_SHA = '3e43041fd3e531ce130b56c0a460a1c7375420eea0e07afdf533012ae41da973'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def lin(p):
    s = p.resolve().as_posix()
    return '/mnt/' + s[0].lower() + s[2:]

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--distro', default='Ubuntu-22.04')
    ap.add_argument('--red', action='store_true')
    ap.add_argument('--rv32', action='store_true')
    args = ap.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    v = ROOT/'linux/voice_ctc'; s = ROOT/'linux/voice_speech'
    tracked = [p for folder in (v, s, ROOT/'linux/voice_accel') for p in folder.rglob('*') if p.is_file()]
    inputs = {p.relative_to(ROOT).as_posix(): sha(p) for p in tracked}
    assert sha(v/'balanced24.bin') == MODEL_SHA
    runs = []

    def command(name, argv, allowed=(0,), timeout=90):
        cmd = 'ulimit -c 0\nexec '+' '.join(shlex.quote(str(x)) for x in argv)
        began = time.monotonic()
        p = subprocess.run(['wsl', '-d', args.distro, '--', 'sh', '-c', cmd],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        (out/(name+'.stdout')).write_bytes(p.stdout); (out/(name+'.stderr')).write_bytes(p.stderr)
        runs.append(dict(name=name, returncode=p.returncode, elapsed_s=round(time.monotonic()-began, 3),
                         stdout_sha256=sha(out/(name+'.stdout')), stderr_sha256=sha(out/(name+'.stderr'))))
        assert p.returncode in allowed, (name, p.returncode, (p.stdout+p.stderr).decode(errors='replace')[-3000:])
        return p.stdout

    cc = '/opt/toolchain/bin/riscv32-linux-musl-gcc' if args.rv32 else 'gcc'
    flags = ['-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-pthread']
    if args.rv32: flags += ['-static', '-march=rv32ima', '-mabi=ilp32']
    includes = ['-I'+lin(p) for p in (v, s, ROOT/'linux/voice', ROOT/'sw/xiangqi')]
    common = [lin(ROOT/'linux/voice/xqvoice_notation.c'), lin(ROOT/'sw/xiangqi/xiangqi_search.c')]
    runner = ['qemu-riscv32'] if args.rv32 else []

    def build(name, files, link=()):
        exe = out/name
        command(name+'-build', [cc, *flags, *includes, *map(lin, files), *link, '-o', lin(exe)])
        return exe

    try:
        feedback = build('feedback', [v/'tests/test_feedback.c'], common)
        # The shared legal-move sources are explicit link inputs, never copied or modified.
        channel = build('channel', [v/'tests/test_worker_channel.c'], common)
        worker = build('fake-worker', [v/'tests/fake_worker.c'])
        allowed = tuple(range(1, 256)) if args.red else (0,)
        command('feedback-run', [*runner, lin(feedback)], allowed)
        # A QEMU subprocess is supplied to the real session through a tiny executable shim.
        channel_worker = worker
        if args.rv32:
            channel_worker = out/'fake-worker-qemu'
            channel_worker.write_bytes(('#!/bin/sh\nexec qemu-riscv32 '+shlex.quote(lin(worker))+' "$@"\n').encode('utf-8'))
            command('shim-mode', ['chmod', '755', lin(channel_worker)])
        command('channel-run', [*runner, lin(channel), lin(channel_worker), lin(v/'balanced24.bin')], allowed)
        if args.red:
            status = 'EXPECTED_RED_DECODE25_AND_STDERR_REPRODUCED'
        else:
            priority = build('priority', [v/'tests/test_gui_priority.c', v/'xqvoice_session.c', v/'xqvoice_gui_flow.c',
                ROOT/'sw/xiangqi/xiangqi_mouse_input.c'], common)
            command('priority-run', [*runner, lin(priority)])
            speech_common = [s/'xq_speech.c', ROOT/'sw/xiangqi/xiangqi_pikafish_link.c', ROOT/'sw/xiangqi/xiangqi_search.c']
            for name, files, link, parameters in (
                ('speech', [s/'tests/test_speech.c', *speech_common], [], []),
                ('announce', [s/'tests/test_announce.c', s/'xqvoice_announce.c', *speech_common], [], []),
                ('playback', [s/'tests/test_speech_linux.c'], ['-Wl,--wrap=read,--wrap=write'], []),
                ('pcm-cache', [s/'tests/test_pcm_cache.c', *speech_common], [],
                    [lin(ROOT/'linux/boot/v2_1_sd/rootfs_payloads/picture/pcm')]),
            ):
                exe = build(name, files, link); command(name+'-run', [*runner, lin(exe), *parameters])
            stream = build('stream', [v/'xqvoice_capture.c', v/'xqvoice_frontend.c', v/'xqvoice_profile.c',
                v/'tests/test_voice2_stream_frontend.c'], ['-DXQV_HOP_SAMPLES=320u',
                '-Wl,--wrap=open,--wrap=close,--wrap=flock,--wrap=read,--wrap=ioctl'])
            command('stream-run', [*runner, lin(stream)])
            sources = [v/n for n in ('xqvoice_runtime.c','xqvoice_frontend.c','xqvoice_decode.c',
                'xqvoice_capture.c','xqvoice_profile.c','voice_small_backend.c')]
            runtime = build('xqvoice-small-cnn', sources, ['-fwrapv','-DXQV_HOP_SAMPLES=320u','-DXQV_CTC_BEAM=8'])
            mock = build('xqvoice-device-mock', [*sources, v/'tests/voice2_device_mock.c'],
                ['-fwrapv','-DXQV_HOP_SAMPLES=320u','-DXQV_CTC_BEAM=8','-Wl,--wrap=open,--wrap=close,--wrap=ioctl'])
            command('runtime-selftest', [*runner, lin(runtime), '--selftest'])
            rng = random.Random(24075); cases=[]
            for count in (7, 33, 127, 199):
                data = count.to_bytes(4,'little')+bytes(rng.randrange(256) for _ in range(count*40))
                case = out/f'features-{count}.bin';case.write_bytes(data); traces=[]
                for backend in ('cpu','mac','mac-verify'):
                    trace = out/f'features-{count}-{backend}.trace'; traces.append(trace)
                    command(f'model-{count}-{backend}', [*runner,lin(mock),lin(v/'balanced24.bin'),lin(case),lin(trace),backend], (0,25))
                assert traces[0].read_bytes() and len({sha(t) for t in traces})==1
                cases.append(dict(frames=count, trace_sha256=sha(traces[0])))
            for variable, code in (('VOICE2_NO_CAPABILITY',6),('VOICE2_MODEL_FAIL',22),('VOICE2_TILE_TIMEOUT',22)):
                command(variable.lower(), ['env',variable+'=1',*runner,lin(mock),lin(v/'balanced24.bin'),lin(out/'features-7.bin'),'/dev/null','mac'],(code,))
            if args.rv32:
                header = command('elf-header', [cc.removesuffix('gcc')+'readelf','-h','-A',lin(runtime)])
                assert b'ELF32' in header and b'RISC-V' in header and b'Flags:                             0x0' in header
            status='VOICE_HOST_OR_RV32_SESSION_STREAM_CNN_AND_SPEECH_PASS_NOT_BOARD'
            result_extra=dict(cases=cases,runtime_sha256=sha(runtime),runtime_bytes=runtime.stat().st_size)
        assert inputs == {n:sha(ROOT/n) for n in inputs}, 'Voice inputs changed during checks'
    except BaseException as e:
        status='FAILED_PRESERVED'; result_extra=dict(error=repr(e)); raise
    finally:
        record=dict(status=status,rv32=args.rv32,model_sha256=MODEL_SHA,inputs_sha256=inputs,runs=runs,
            actual_board=False,scope='Synthetic input and explicit arithmetic/audio/process mocks; no accuracy or board latency claim',
            **locals().get('result_extra',{}))
        (out/'result.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'status':status,'checks':len(runs),'rv32':args.rv32}),flush=True)

if __name__=='__main__':main()
