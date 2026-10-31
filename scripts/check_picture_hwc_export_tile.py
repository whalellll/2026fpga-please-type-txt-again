"""Compare optional tiled head export against the frozen exporter; offline only."""
import argparse,hashlib,json,shlex,subprocess
from pathlib import Path
from picture_workspace import ROOT,workspace_path,wsl_path

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prepare-benchmark-only',action='store_true',help='Build and verify separate no-probe host/RV32 programs; do not execute --bench')
    args=parser.parse_args();assert args.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(args.output);out.mkdir(parents=True,exist_ok=False)
    source='linux/picture_new/hwc_fast/tests/test_export_tile.c'
    include=['linux/picture_new/hwc_fast','linux/picture_new','linux/mac_accel','linux/vision',
             'artifacts/vision-model-20261020-adapter/runtime','sw/bootloader']
    files={source,'linux/picture_new/hwc_fast/adapter.c','linux/picture_new/hwc_fast/export_tile.h',
           'linux/picture_new/hwc_fast/integer_hwc.c','scripts/check_picture_hwc_export_tile.py'}
    for folder in include:files.update(p.relative_to(ROOT).as_posix() for p in (ROOT/folder).glob('*.h'))
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    before={name:sha(ROOT/name) for name in sorted(files)};checks=[]
    def run(name,argv,expected_success=True):
        with (out/(name+'.log')).open('xb') as log:
            result=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                'ulimit -c 0\nexec timeout --kill-after=5 120 '+shlex.join(argv)],stdout=log,stderr=subprocess.STDOUT,timeout=140)
        text=(out/(name+'.log')).read_text(errors='replace')
        if expected_success:assert result.returncode==0,(name,text[-2000:])
        return result.returncode,text
    for target in (['host','rv32'] if args.prepare_benchmark_only else ['host','rv32','sanitizer']):
        cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'gcc'
        flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off','-ffunction-sections','-fdata-sections']
        if target=='rv32':flags+=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align']
        if target=='sanitizer':flags+=['-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
        row=dict(target=target)
        if args.prepare_benchmark_only:
            timing=out/(target+'-timing')
            run(target+'-timing-build',[cc,*flags,'-DXQIH_EXPORT_NO_PROBE',
                *['-I'+wsl_path(ROOT/p) for p in include],wsl_path(ROOT/source),
                '-Wl,--gc-sections','-lm','-o',wsl_path(timing)])
            _,text=run(target+'-no-probe-correctness',
                [*(['qemu-riscv32'] if target=='rv32' else []),wsl_path(timing)])
            assert 'HWC_TILE_EXPORT_FULL_HEADS_S16_EXPONENTS_FAILURE_PREFIX_NO_ALLOC_PASS_NOT_BOARD' in text
            row['no_probe_correctness_result']=text.strip()
            row['no_probe_binary']=(timing.relative_to(ROOT).as_posix()
                if timing.is_relative_to(ROOT) else str(timing))
        else:
            binary=out/target
            run(target+'-build',[cc,*flags,*['-I'+wsl_path(ROOT/p) for p in include],wsl_path(ROOT/source),
                                '-Wl,--wrap=malloc','-Wl,--gc-sections','-lm','-o',wsl_path(binary)])
            _,text=run(target,[*(['qemu-riscv32'] if target=='rv32' else []),wsl_path(binary)])
            assert 'HWC_TILE_EXPORT_FULL_HEADS_S16_EXPONENTS_FAILURE_PREFIX_NO_ALLOC_PASS_NOT_BOARD' in text
            row['result']=text.strip()
        checks.append(row)
    assert before=={name:sha(ROOT/name) for name in sorted(files)}
    receipt=dict(status=('HWC_TILED_EXPORT_NO_PROBE_BINARIES_CORRECTNESS_PASS_NOT_BOARD' if args.prepare_benchmark_only else
                        'HWC_TILED_EXPORT_ORIGINAL_BYTES_FAILURE_PREFIX_HOST_RV32_SANITIZERS_PASS_NOT_BOARD'),
                 hardware_used=False,source_sha256=before,checks=checks,performance_measured=False,
                 frozen_integer_hwc_unchanged=True,unsupported_inputs_use_original_exporter=True,
                 allocation_added=False,tile_array_bytes=512,
                 no_probe_timing_binaries_prepared=args.prepare_benchmark_only,benchmark_executed=False)
    (out/'result.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(receipt['status'])
if __name__=='__main__':main()
