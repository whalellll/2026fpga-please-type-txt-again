"""Exact RGB input quantization cache vs the frozen quantizer; no hardware."""
from pathlib import Path
import argparse,hashlib,json,shlex,subprocess
from picture_workspace import ROOT,workspace_path,wsl_path

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    assert a.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(a.output);out.mkdir(parents=True,exist_ok=False)
    sources=['linux/picture_new/hwc_fast/input_quant.c','linux/picture_new/hwc_fast/tests/test_input_quant.c','linux/picture_new/vision32_layer.c']
    inc=['linux/picture_new/hwc_fast','linux/picture_new','linux/mac_accel','linux/vision','artifacts/vision-model-20261020-adapter/runtime']
    files=set(sources+['scripts/check_picture_hwc_input.py','linux/picture_new/hwc_fast/input_quant.h',
        'linux/picture_new/vision32_locality.c','linux/picture_new/vision32_exact.c',
        'linux/picture_new/whole_layer_fast/vision32_layer.c','linux/picture_new/upstream/adapter/runtime/xq_int8_layer.c',
        'linux/picture_new/upstream/adapter/runtime/xq_int8_layer.h'])
    for d in inc:files.update(p.relative_to(ROOT).as_posix() for p in (ROOT/d).glob('*.h'))
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();before={n:sha(ROOT/n) for n in sorted(files)}
    result=dict(status='FAILED_PRESERVED',source_sha256=before,hardware_used=False,runs=[])
    def run(label,args):
        with (out/(label+'.log')).open('xb') as f:r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
            'ulimit -c 0\nexec timeout --kill-after=5 120 '+shlex.join(args)],stdout=f,stderr=subprocess.STDOUT,timeout=140)
        result['runs'].append(dict(name=label,exit=r.returncode));assert r.returncode==0,(label,(out/(label+'.log')).read_text(errors='replace')[-2000:])
    try:
        for target in ['host','rv32','host-asan']:
            cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'gcc'
            flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off','-ffunction-sections','-fdata-sections']
            if target=='rv32':flags+=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align']
            if target=='host-asan':flags+=['-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
            binary=out/target
            run(target+'-build',[cc,*flags,*['-I'+wsl_path(ROOT/d) for d in inc],*[wsl_path(ROOT/s) for s in sources],'-Wl,--gc-sections','-lm','-o',wsl_path(binary)])
            run(target+'-run',[*(['qemu-riscv32'] if target=='rv32' else []),wsl_path(binary)])
            assert 'HWC_RGB_QUANT_ALL241_EXPONENTS_COLORS_NEIGHBORS_RANDOM_EXCEPTION_PREFIX_PASS_NOT_BOARD' in (out/(target+'-run.log')).read_text()
        assert all(sha(ROOT/n)==h for n,h in before.items())
        result.update(status='HWC_RGB_INPUT_EXACT_HOST_RV32_ASAN_UBSAN_PASS_NOT_BOARD',source_stable=True,
            all_supported_exponents=True,all256_normalized_colors_and_neighbors=True,arbitrary_float_fallback_and_invalid_prefix_equal=True,
            per_inference_table=True,timing_is_not_hardware=True)
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])
if __name__=='__main__':main()
