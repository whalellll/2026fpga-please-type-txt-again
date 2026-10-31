"""Compare the optional board-corner tables with the frozen function, off-board."""
import argparse
import hashlib
import json
import shlex
import subprocess
from pathlib import Path
from picture_workspace import ROOT, workspace_path, wsl_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build-bench-only',action='store_true',help='Compile host/RV32 no-probe --bench programs without running them')
    args = parser.parse_args()
    assert args.output.absolute().is_relative_to(ROOT / 'build')
    out = workspace_path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    frozen_path = 'artifacts/vision-model-20261020-adapter/runtime/xq_native_graph.c'
    candidate_path = 'linux/picture_new/graph_runtime.c'
    frozen = (ROOT / frozen_path).read_text()
    frozen = frozen[frozen.index('int xqn_board_corners('):]
    candidate = (ROOT / candidate_path).read_text()
    candidate = candidate[candidate.index('int xqn_board_corners('):]
    begin = '/* XQ_BOARD_CORNER_TABLE_BEGIN */\n'
    old = '/* XQ_BOARD_CORNER_TABLE_FROZEN */\n'
    end = '/* XQ_BOARD_CORNER_TABLE_END */\n'
    restored = candidate[:candidate.index(begin)] + candidate.split(old, 1)[1].split('#endif\n'+end, 1)[0] + candidate.split(end, 1)[1]
    assert restored == frozen, 'The unselected function must remain exact frozen source'
    reference = out / 'frozen-reference.h'
    reference.write_text(frozen.replace('int xqn_board_corners(', 'static int xqg_corner_frozen_reference(', 1))
    includes = ['linux/picture_new', 'artifacts/vision-model-20261020-adapter/runtime',
                'linux/vision', 'linux/mac_accel', 'sw/xiangqi', 'sw/bootloader']
    names = {frozen_path, candidate_path, 'linux/picture_new/test_board_corner_table.c',
             'scripts/check_picture_board_corner_table.py'}
    for folder in includes:
        names.update(p.relative_to(ROOT).as_posix() for p in (ROOT / folder).glob('*.h'))
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    before = {name: sha(ROOT / name) for name in sorted(names)}
    checks = []
    def run(name, argv, seconds=120, expect_success=True):
        with (out / (name+'.log')).open('xb') as log:
            result = subprocess.run(['wsl.exe', '-d', 'Ubuntu-22.04', '--', 'sh', '-c',
                'ulimit -c 0\nexec timeout --kill-after=5 '+str(seconds)+' '+shlex.join(argv)],
                stdout=log, stderr=subprocess.STDOUT, timeout=seconds+15)
        text = (out / (name+'.log')).read_text(errors='replace')
        if expect_success:
            assert result.returncode == 0, (name,text[-2000:])
        else:
            assert result.returncode != 0 and 'Assertion' in text and 'memcmp' in text, (name,text[-2000:])
        return text
    def build(name, target, selected, source):
        cc = '/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'gcc'
        flags = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-ffp-contract=off',
                 '-ffunction-sections', '-fdata-sections', '-DXQ_BOARD_CORNER_TABLE='+str(selected)]
        if target=='rv32':flags += ['-static', '-march=rv32ima', '-mabi=ilp32', '-mstrict-align']
        if target=='sanitizer':flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
        binary = out / name
        run(name+'-build',[cc,*flags,*['-I'+wsl_path(ROOT / folder) for folder in includes],
            '-DGRAPH_RUNTIME_SOURCE="'+wsl_path(source)+'"',
            '-DFROZEN_CORNER_REFERENCE="'+wsl_path(reference)+'"',
            wsl_path(ROOT / 'linux/picture_new/test_board_corner_table.c'),
            '-Wl,--wrap=malloc', '-Wl,--gc-sections', '-lm', '-o',wsl_path(binary)])
        return binary
    if args.build_bench_only:
        binaries={}
        for target in ['host','rv32']:
            binary=build('bench-'+target,target,1,ROOT / candidate_path)
            binaries[target]=dict(path=str(binary),sha256=sha(binary),arguments=['--bench'])
        assert before=={name:sha(ROOT / name) for name in sorted(names)}
        result=dict(status='BOARD_CORNER_NO_PROBE_BENCH_HOST_RV32_COMPILE_ONLY_NOT_RUN',
                    hardware_used=False,source_sha256=before,binaries=binaries,
                    benchmark_executed=False,performance_measured=False,
                    repeats_per_path=3,prewarm_and_complete_output_check_before_timing=True,
                    assertions_and_logging_outside_timing=True,malloc_monitoring_disabled_during_timing=True)
        (out / 'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(result['status'])
        return
    for target in ['host','rv32','sanitizer']:
        for selected in [0,1]:
            name=target+'-table'+str(selected)
            binary=build(name,target,selected,ROOT / candidate_path)
            text=run(name,[*(['qemu-riscv32'] if target=='rv32' else []),wsl_path(binary)])
            assert 'BOARD_CORNER_COORD_TABLE_FROZEN_BITS_GUARDS_NO_ALLOC_PASS' in text
            checks.append(dict(target=target,selected=selected,result=text.strip()))
    # A tempting reciprocal/predivided-coordinate rewrite must go red.
    mutation=out / 'wrong-operation-order.c'
    text=(ROOT / candidate_path).read_text()
    assert text.count('sx+=v*numerators[i%48]/48.f')==1
    mutation.write_text(text.replace('sx+=v*numerators[i%48]/48.f','sx+=v*coordinates[i%48]'))
    binary=build('negative-order','host',1,mutation)
    run('negative-order',[wsl_path(binary)],30,expect_success=False)
    assert before=={name:sha(ROOT / name) for name in sorted(names)}
    result=dict(status='BOARD_CORNER_TABLE_FROZEN_BITS_HOST_RV32_SANITIZERS_GUARDS_NO_ALLOC_NEGATIVE_ORDER_PASS_NOT_BOARD',
                hardware_used=False,source_sha256=before,checks=checks,table_array_bytes=768,
                total_compiled_stack_frame_not_measured=True,no_new_heap_allocation=True,
                default_frozen_function_source_identical=True,wrong_division_order_negative_control_rejected=True,
                performance_measured=False)
    (out / 'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])


if __name__=='__main__':
    main()
