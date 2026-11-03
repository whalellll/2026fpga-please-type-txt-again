"""Check private HWC product integration against the immutable CPU graph.

Only fixed synthetic inputs are generated. No board, photos or dataset scan.
Full output equality, bad packs, allocation/cancellation/ioctl failure, explicit
capability checks, independent quantization/operators and RV32 ABI are covered.
"""
from pathlib import Path
import argparse
import array
import hashlib
import json
import math
import os
import shlex
import struct
import subprocess
import zlib

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = 'artifacts/vision-model-20261020-adapter/runtime'
HWC = 'linux/picture_new/hwc_fast'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def linux(path):
    value = path.resolve().as_posix()
    assert value[1:3] == ':/'
    return '/mnt/' + value[0].lower() + value[2:]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--model-dir', type=Path, required=True)
    ap.add_argument('--distribution', default='Ubuntu-22.04')
    ap.add_argument('--rgb-quant',action='store_true')
    ap.add_argument('--profile',action='store_true')
    a = ap.parse_args()
    logical = a.output.absolute()
    assert logical.is_relative_to(ROOT / 'build') and not logical.exists()
    out = logical.resolve()
    out.mkdir(parents=True)
    model_dir = a.model_dir.resolve()
    assert sha(model_dir / 'detector.xqi') == 'd72d039041b41310f037344772eb75ce895ec6fe678bbb31ed547a7ad7453942'
    assert sha(model_dir / 'reference.xqm') == 'd65b4b8686520ae1546d0a207c1bcb9f30efe0d40e7f5c8245c4dd11ff9ca09d'
    common = ['linux/picture_new/vision32_backend.c', 'linux/picture_new/graph_profile.c',
              'sw/bootloader/crc32_fast.c']
    product = [HWC + '/tests/product_adapter.c', HWC + '/adapter.c',
               HWC + '/tests/picture_new_graph_mock.c', 'linux/picture_new/graph_runtime.c',
               'linux/picture_new/graph_tensor.c', 'linux/picture_new/graph_ops.c',
               'linux/picture_new/vision32_layer.c', ADAPTER + '/xq_sha256.c', *common]
    reference = [HWC + '/tests/frozen_graph_reference.c', ADAPTER + '/xq_native_graph.c',
                 'linux/picture_new/vision32_layer.c', *common]
    quant = [HWC + '/tests/test_integer_quant.c', HWC + '/integer_hwc.c',
             'linux/picture_new/vision32_layer.c', *common]
    operators = [HWC + '/tests/test_integer_ops.c', *common]
    includes = [HWC, ADAPTER, 'linux/picture_new', 'linux/vision', 'linux/mac_accel', 'sw/bootloader']
    files = set(product + reference + quant + operators)
    files.update(p.relative_to(ROOT).as_posix() for p in (ROOT / HWC).rglob('*')
                 if p.is_file() and p.suffix in {'.h', '.c'})
    files.update(p.relative_to(ROOT).as_posix() for d in includes
                 for p in (ROOT / d).glob('*.h'))
    files.update(['linux/picture_new/vision32_locality.c',
                  'linux/picture_new/whole_layer_fast/vision32_layer.c',
                  'linux/picture_new/upstream/adapter/runtime/xq_int8_layer.c',
                  'linux/picture_new/upstream/adapter/runtime/xq_int8_layer.h',
                  'scripts/check_picture_hwc_intake.py'])
    before = {name: sha(ROOT / name) for name in sorted(files)}
    flags = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-misleading-indentation',
             '-ffp-contract=off', '-ffunction-sections', '-fdata-sections']
    inc = ['-I' + linux(ROOT / name) for name in includes]
    runs = []

    def run(name, command, seconds=240, expected=(0,)):
        log = out / (name + '.log')
        full = ['wsl.exe', '-d', a.distribution, '--', 'sh', '-c',
                'ulimit -c 0\nexec timeout --kill-after=5 ' + str(seconds) + ' ' + shlex.join(command)]
        with log.open('xb') as stream:
            result = subprocess.run(full, stdout=stream, stderr=subprocess.STDOUT, timeout=seconds + 20)
        runs.append({'name': name, 'exit': result.returncode, 'seconds_bound': seconds})
        assert result.returncode in expected, (name, log.read_text(errors='replace')[-3500:])
        return log.read_text(errors='replace')

    def build(name, source, extra=(), rv32=False):
        cc = '/opt/toolchain/bin/riscv32-linux-musl-gcc' if rv32 else 'gcc'
        target = ['-static', '-march=rv32ima', '-mabi=ilp32', '-mstrict-align'] if rv32 else []
        binary = out / name
        run(name + '-build', [cc, *flags, *target, *extra, *inc,
                              *[linux(ROOT / p) for p in source],
                              '-Wl,--gc-sections', '-lm', '-o', linux(binary)], 90)
        return binary

    result = {'status': 'FAILED_PRESERVED', 'hardware_used': False,
              'photos_or_game2_accessed': False, 'source_sha256': before, 'runs': runs,
              'model_sha256': sha(model_dir / 'detector.xqi'), 'cases': {}}
    result.update(rgb_quant=a.rgb_quant,profile=a.profile)
    try:
        wrap = ['-Wl,--wrap=open,--wrap=close,--wrap=mmap,--wrap=munmap,--wrap=ioctl,--wrap=malloc,--wrap=calloc',
                '-DXQ_HWC_DETECTOR=1', '-DXQ_CLASSIFIER_S16=1', '-DXQ_FAST_REQUANT=1']
        if a.rgb_quant:wrap+=['-DXQ_HWC_RGB_QUANT=1']
        if a.profile:wrap+=['-DXQ_GRAPH_PROFILE']
        product_binary = build('product-host', product, wrap)
        reference_binary = build('reference-host', reference)
        q = build('quant-host', quant, ['-DXI8_TEST'])
        assert 'INTEGER_QUANT_EXHAUSTIVE_S16_AND_S24_REFERENCE_PASS' in run('quant-host-run', [linux(q)], 120)
        ops = build('operators-sanitized', operators,
                    ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer'])
        assert 'INTEGER_OPS_POOL_NARROW_PACK_ADD_ALIAS_REFERENCE_PASS' in run('operators-sanitized-run', [linux(ops)], 120)
        models = out / 'models'
        models.mkdir()
        (models / 'detector.xqm').write_bytes((model_dir / 'reference.xqm').read_bytes())
        (models / 'detector.xqi').write_bytes((model_dir / 'detector.xqi').read_bytes())
        input_exp = struct.unpack_from('<i', (model_dir / 'detector.xqi').read_bytes(), 48 + 18 * 4)[0]
        for case in ['fixed', 'zero', 'signed']+(['rgb'] if a.rgb_quant else []):
            inp = out / (case + '.f32')
            if case == 'fixed':
                inp.write_bytes((model_dir / 'reference.f32').read_bytes())
            elif case=='rgb':
                values=array.array('f',[(i%256)/255. for i in range(3*640*640)])
                inp.write_bytes(values.tobytes())
            else:
                palette = [0] * 256 if case == 'zero' else [((i * 61 + 13) % 256) - 128 for i in range(256)]
                values = array.array('f', [math.ldexp(palette[i % 256], input_exp) for i in range(3 * 640 * 640)])
                assert values.itemsize == 4
                inp.write_bytes(values.tobytes())
            new, old = out / (case + '-new.f32'), out / (case + '-reference.f32')
            text = run(case + '-product', [linux(product_binary), linux(models / 'detector.xqm'), linux(inp), linux(new)])
            assert 'HWC_PRODUCT_BOUNDARY_NO_CPU_FALLBACK_NO_RAW2_OBSERVER_OOM_CANCEL_IOCTL_INVALIDATE_PASS' in text
            assert 'jobs=166' in text
            run(case + '-reference', [linux(reference_binary), linux(models / 'detector.xqm'), linux(inp), linux(old)])
            assert new.read_bytes() == old.read_bytes(), case + ' full output differs from immutable CPU graph'
            result['cases'][case] = {'full_output_equal': True, 'full_output_sha256': sha(new),
                                      'fixed_shape_jobs': 166, 'failure_paths_invalidate_output': True}
            if case == 'fixed':
                assert 'crc=97265de4' in text
            if a.profile:
                line=next(v for v in text.splitlines() if v.startswith('XQ_HWC_PROFILE okay=1 '))
                fields={k:int(v) for k,v in [v.split('=') for v in line.split()[1:]]}
                assert abs(fields['input_us']+fields['graph_us']+fields['heads_us']-fields['total_us'])<=2
                assert abs(fields['same_output_us']-fields['graph_us']-fields['export_core_us'])<=1
                assert fields['jobs']==166
                result['cases'][case]['profile_boundaries_close']=True
        binary = (models / 'detector.xqi').read_bytes()
        bad = {'truncated': binary[:100], 'crc': binary[:-1] + bytes([binary[-1] ^ 1])}
        v = bytearray(binary);struct.pack_into('<I', v, 8, 2);bad['version'] = bytes(v)
        for name, index, value in [('opcode', 0, 3), ('input_parent', 5, 0), ('dtype', 27, 7), ('refcount', 26, 0)]:
            v = bytearray(binary);struct.pack_into('<i', v, 48 + index * 4, value)
            struct.pack_into('<I', v, 44, zlib.crc32(v[48:]));bad[name] = bytes(v)
        v = bytearray(binary);v[-1] ^= 1;struct.pack_into('<I', v, 44, zlib.crc32(v[48:]));bad['different_valid_crc'] = bytes(v)
        for name, payload in bad.items():
            (models / 'detector.xqi').write_bytes(payload)
            text = run('bad-' + name, [linux(product_binary), linux(models / 'detector.xqm'),
                       linux(out / 'zero.f32'), linux(out / ('bad-' + name + '.f32'))], 15, (2,))
            assert 'HWC_PRODUCT_MODEL_REJECTED_BEFORE_DEVICE' in text
            assert 'PICTURE_GRAPH_MOCK_JOBS' not in text, 'Bad pack reached device'
        (models / 'detector.xqi').write_bytes(binary)
        result['bad_models_rejected_before_device'] = sorted(bad)
        rv = build('product-rv32', product, wrap, True)
        data = rv.read_bytes()
        assert data[:6] == b'\x7fELF\x01\x01' and struct.unpack_from('<H', data, 18)[0] == 243
        assert struct.unpack_from('<I', data, 36)[0] == 0
        if a.rgb_quant:
            rv_output=out/'rgb-rv32-new.f32'
            run('rgb-rv32-product',['qemu-riscv32',linux(rv),linux(models/'detector.xqm'),linux(out/'rgb.f32'),linux(rv_output)],240)
            assert rv_output.read_bytes()==(out/'rgb-reference.f32').read_bytes()
            result['rgb_full_output_rv32_equal_reference']=True
        for name, sources, extra in [('quant-rv32', quant, ['-DXI8_TEST']), ('operators-rv32', operators, [])]:
            binary_path = build(name, sources, extra, True)
            run(name + '-run', ['qemu-riscv32', linux(binary_path)], 120)
        result['rv32_soft_float_abi_flags_zero'] = True
        result['qemu_quant_and_operator_references'] = True
        assert all(sha(ROOT / name) == h for name, h in before.items()), 'Source changed during tests'
        result['status'] = ('HWC_RGB_FOUR_INPUTS_FULL_HEADS_REFERENCE_FAILURE_PROFILE_HOST_RV32_PASS_NOT_BOARD' if a.rgb_quant else
            'HWC_THREE_FULL_HEADS_IMMUTABLE_CPU_REFERENCE_FAILURE_GUARDS_HOST_RV32_PASS_NOT_BOARD')
    finally:
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(result['status'])


if __name__ == '__main__':
    main()
