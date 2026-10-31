"""Bounded synthetic arithmetic/operator smoke from the exported source only."""
from pathlib import Path
import argparse
import json
import subprocess
import sys

sys.dont_write_bytecode = True
from verify_handoff import verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    verify(root)
    out = args.output.resolve()
    if out.is_relative_to(root):
        parser.error('Use an output directory outside the immutable handoff')
    out.mkdir(parents=True, exist_ok=False)
    source = root/'current-source'
    flags = ['-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
             '-ffp-contract=off','-ffunction-sections','-fdata-sections']
    includes = ['linux/picture_new/hwc_fast','linux/picture_new','linux/vision','linux/mac_accel',
                'artifacts/vision-model-20261020-adapter/runtime','sw/bootloader']
    flags += ['-I'+str(source/name) for name in includes]
    rows = []

    def run(name, argv):
        with (out/(name+'.log')).open('xb') as f:
            result = subprocess.run(['timeout','--kill-after=3','60',*argv], stdout=f,
                stderr=subprocess.STDOUT, timeout=75)
        assert result.returncode == 0, (name, result.returncode)
        return (out/(name+'.log')).read_text()

    try:
        for name, files, extra, marker in [
            ('quant', ['linux/picture_new/hwc_fast/tests/test_integer_quant.c',
                       'linux/picture_new/hwc_fast/integer_hwc.c',
                       'linux/picture_new/upstream/adapter/runtime/xq_int8_layer.c'],
             ['-DXI8_TEST=1'], 'INTEGER_QUANT_EXHAUSTIVE_S16_AND_S24_REFERENCE_PASS'),
            ('ops', ['linux/picture_new/hwc_fast/tests/test_integer_ops.c'],
             [], 'INTEGER_OPS_POOL_NARROW_PACK_ADD_ALIAS_REFERENCE_PASS'),
        ]:
            binary = out/name
            run(name+'-build', ['cc',*flags,*extra,*[str(source/p) for p in files],
                '-Wl,--gc-sections','-lm','-o',str(binary)])
            assert marker in run(name, [str(binary)])
            rows.append(dict(name=name,pass_=True,full_graph_inference=False))
        verify(root)
        result = dict(status='EXPORTED_MODEL_INT8_NUMERIC_SMOKE_PASS_NOT_BOARD',checks=rows,
            full_graph_inference=False, private_inputs_used=False, hardware_used=False)
    except BaseException:
        (out/'result.json').write_text(json.dumps(dict(status='FAILED_PRESERVED',checks=rows),indent=2)+'\n')
        raise
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])


if __name__ == '__main__':
    main()
