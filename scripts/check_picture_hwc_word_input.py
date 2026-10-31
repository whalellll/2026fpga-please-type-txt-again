"""Check contiguous normal-RAM HWC4 input packing; no hardware or timing claim."""
from pathlib import Path
import argparse,hashlib,json,shlex,subprocess
from picture_workspace import ROOT,workspace_path,wsl_path

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();assert args.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(args.output);out.mkdir(parents=True,exist_ok=False)
    sources=['linux/picture_new/hwc_fast/tests/test_word_input.c','linux/picture_new/vision32_layer.c']
    include=['linux/picture_new/hwc_fast','linux/picture_new','linux/mac_accel','linux/vision','artifacts/vision-model-20261020-adapter/runtime','sw/bootloader']
    files=set(sources+['scripts/check_picture_hwc_word_input.py','linux/picture_new/hwc_fast/adapter.c',
        'linux/picture_new/hwc_fast/integer_hwc.c','linux/picture_new/hwc_fast/input_quant.c',
        'linux/picture_new/vision32_locality.c','linux/picture_new/vision32_exact.c',
        'linux/picture_new/whole_layer_fast/vision32_layer.c','linux/picture_new/upstream/adapter/runtime/xq_int8_layer.c'])
    for folder in include:files.update(p.relative_to(ROOT).as_posix() for p in (ROOT/folder).glob('*.h'))
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    before={name:sha(ROOT/name) for name in sorted(files)};checks=[]
    def run(name,argv):
        with (out/(name+'.log')).open('xb') as log:
            result=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                'ulimit -c 0\nexec timeout --kill-after=5 120 '+shlex.join(argv)],stdout=log,stderr=subprocess.STDOUT,timeout=140)
        text=(out/(name+'.log')).read_text(errors='replace')
        assert result.returncode==0,(name,text[-2000:]);return text
    for target in ['host','rv32','sanitizer']:
        cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'gcc'
        flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off','-ffunction-sections','-fdata-sections']
        if target=='rv32':flags+=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align']
        if target=='sanitizer':flags+=['-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
        for cache in [0,1]:
            name=target+'-lookup'+str(cache);binary=out/name
            run(name+'-build',[cc,*flags,'-DXQ_HWC_RGB_QUANT='+str(cache),
                *['-I'+wsl_path(ROOT/p) for p in include],*[wsl_path(ROOT/p) for p in sources],
                '-Wl,--wrap=malloc','-Wl,--gc-sections','-lm','-o',wsl_path(binary)])
            text=run(name,[*(['qemu-riscv32'] if target=='rv32' else []),wsl_path(binary)])
            assert 'HWC_WORD_INPUT_FULL_BYTES_RGB0_FLOAT_EXCEPTION_CANCEL_OOM_PASS_NOT_BOARD' in text
            checks.append(dict(target=target,rgb_lookup=cache,result=text.strip()))
    assert before=={name:sha(ROOT/name) for name in sorted(files)}
    receipt=dict(status='HWC_CONTIGUOUS_NORMAL_RAM_INPUT_HOST_RV32_SANITIZERS_PASS_NOT_BOARD',
        hardware_used=False,source_sha256=before,checks=checks,performance_measured=False,
        original_quantizer_unchanged=True,normal_malloc_ram_only=True,all_four_lanes_written=True)
    (out/'result.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(receipt['status'])
if __name__=='__main__':main()
