"""Recheck final C sources against r14 dumps/graphs; no images or hardware."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
R = HERE.parents[1]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--dump-manifest', type=Path, required=True)
    p.add_argument('--receipt', type=Path, required=True)
    a = p.parse_args()
    assert a.out.resolve().is_relative_to(R/'build') and not a.out.exists()
    assert not a.receipt.exists()
    a.out.mkdir(parents=True)
    profile = json.loads((HERE/'working_combination.json').read_text())['profiles']['working-r14']
    candidate, release = R/profile['quantized_candidate'], R/profile['root']
    sources = [HERE/'runtime'/n for n in ('xq_native_graph.c','xq_native_graph.h',
        'xq_int8_layer.c','xq_int8_layer.h','xq_resident_matrix.c','xq_resident_matrix.h',
        'xq_conv_dispatch.h','mock_resident_transport.c','test_resident_matrix.c','test_conv_dispatch.c')]
    sources += [R/'linux/vision/xq_mac.c',R/'linux/vision/xq_mac.h',R/'linux/mac_accel/pango_mac_uapi.h',R/'sw/bootloader/crc32_fast.c']
    bindings = {str(p.relative_to(R)):sha(p) for p in sources}
    env = dict(os.environ, OMP_NUM_THREADS='2', MKL_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2')
    commands = {}

    def run(cmd, name):
        commands[name] = list(map(str,cmd))
        with (a.out/(name+'.log')).open('wb') as log:
            subprocess.run(commands[name], check=True, cwd=R, env=env, timeout=600,
                           stdout=log, stderr=subprocess.STDOUT)
        print('FINAL_NUMERICS_GATE_PASS', name, flush=True)

    for name, extra in [('cpu-layers',[]),('resident-layers',['--mock-resident'])]:
        run([sys.executable,'-B',HERE/'check_native_layers.py','--out',a.out/name,
             '--candidate',candidate,'--dump-manifest',a.dump_manifest,*extra],name)
    inc = ['-I'+str(R/n) for n in ('linux/vision','linux/mac_accel','sw/bootloader')]
    library = a.out/'native-graph.so'
    run(['cc','-shared','-fPIC','-O3','-std=c11','-ffp-contract=off','-DXQ_NATIVE_DIRECT_PACK',*inc,
         *[HERE/'runtime'/n for n in ('xq_native_graph.c','xq_int8_layer.c','xq_resident_matrix.c')],
         R/'sw/bootloader/crc32_fast.c','-lm','-o',library],'graph-build')
    run([sys.executable,'-B',HERE/'check_native_graph.py','--models',R/'build/picture-merge-20261023/native-models',
         '--library',library,'--out',a.out/'graphs','--release',release,'--candidate',candidate],'graphs')
    for name, src in [('resident',['test_resident_matrix.c','xq_resident_matrix.c']),('conv',['test_conv_dispatch.c'])]:
        exe = a.out/name
        run(['cc','-O2','-std=c11','-Wall','-Wextra','-Werror',*inc,
             *[HERE/'runtime'/n for n in src],'-Wl,--wrap=ioctl','-lm','-o',exe],name+'-build')
        run([exe],name+'-unit')
    assert all(sha(R/n) == h for n,h in bindings.items())
    results = {name:json.loads((a.out/name/'result.json').read_text()) for name in ('cpu-layers','resident-layers','graphs')}
    assert all(v['status']=='PASS' for v in results.values())
    for name in ('cpu-layers','resident-layers'):
        assert results[name]['layers'] == 80
    result = dict(status='PASS', scope='final source-bound PC numerical tests; not device acceptance',
                  hardware_used=False, production_ready=False, sources=bindings, source_stable=True,
                  commands=commands, results=results,
                  unit_tests=['resident immutable snapshots, tails, deepK, bias-once, direct NCHW',
                              'conv exact subset, layout, capability/rejection and fatal ioctl'],
                  graph_library_sha256=sha(library),
                  logs={p.name:sha(p) for p in a.out.glob('*.log')})
    a.receipt.parent.mkdir(parents=True,exist_ok=True)
    a.receipt.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('FINAL_80_LAYER_THREE_GRAPH_AND_DISPATCH_PASS', flush=True)


if __name__ == '__main__':
    main()
