"""Check the explicit NCHW RGB8 entry against original F32 normalization/graph.

Only generated colors are used. No photos, dataset access, hardware or timing.
"""
import argparse,hashlib,json,shlex,struct,subprocess
from pathlib import Path
from picture_workspace import ROOT,workspace_path,wsl_path

ADAPTER='artifacts/vision-model-20261020-adapter/runtime'
HWC='linux/picture_new/hwc_fast'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--models',type=Path,default=ROOT/'build/picture-e42-20261025/hwc-product-host-r01/models')
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--prepare-benchmark-only',action='store_true',help='Build and verify no-probe input-prepare programs without timing or graph runs')
    mode.add_argument('--unit-only',action='store_true',help='Check palette/packing/failures in six unit configurations; do not rerun complete graphs')
    args=parser.parse_args();assert args.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(args.output);out.mkdir(parents=True,exist_ok=False)
    models=workspace_path(args.models)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    assert sha(models/'detector.xqm')=='d65b4b8686520ae1546d0a207c1bcb9f30efe0d40e7f5c8245c4dd11ff9ca09d'
    assert sha(models/'detector.xqi')=='d72d039041b41310f037344772eb75ce895ec6fe678bbb31ed547a7ad7453942'
    unit=[HWC+'/tests/test_rgb8_direct.c','linux/picture_new/vision32_layer.c']
    product=[HWC+'/tests/product_rgb8_direct.c',HWC+'/adapter.c',HWC+'/tests/picture_new_graph_mock.c',
             'linux/picture_new/graph_tensor.c','linux/picture_new/graph_ops.c','linux/picture_new/vision32_layer.c',
             'linux/picture_new/vision32_backend.c','linux/picture_new/graph_profile.c',ADAPTER+'/xq_sha256.c',
             'sw/bootloader/crc32_fast.c']
    include=[HWC,ADAPTER,'linux/picture_new','linux/vision','linux/mac_accel','sw/bootloader']
    names=set(unit+product+['linux/picture_new/graph_runtime.c','linux/picture_new/graph_rgb8.h',
        HWC+'/rgb8_direct.h',HWC+'/integer_hwc.c',HWC+'/input_quant.c',HWC+'/export_tile.h',
        'linux/picture_new/vision32_locality.c','linux/picture_new/vision32_exact.c',
        'linux/picture_new/whole_layer_fast/vision32_layer.c',
        'linux/picture_new/upstream/adapter/runtime/xq_int8_layer.c',
        'scripts/check_picture_hwc_rgb8_direct.py'])
    for directory in include:names.update(p.relative_to(ROOT).as_posix() for p in (ROOT/directory).glob('*.h'))
    before={name:sha(ROOT/name) for name in sorted(names)}
    model_before={name:sha(models/name) for name in ['detector.xqm','detector.xqi']}
    result=dict(status='FAILED_PRESERVED',hardware_used=False,image_access=False,performance_measured=False,
                source_sha256=before,model_sha256=model_before,unit_checks=[],product_checks=[])
    def run(name,argv,seconds=120):
        with (out/(name+'.log')).open('xb') as log:
            proc=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                'ulimit -c 0\nexec timeout --kill-after=5 '+str(seconds)+' '+shlex.join(argv)],
                stdout=log,stderr=subprocess.STDOUT,timeout=seconds+20)
        text=(out/(name+'.log')).read_text(errors='replace')
        assert proc.returncode==0,(name,proc.returncode,text[-2200:])
        return text
    def flags(target):
        values=['-std=c11','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off','-ffunction-sections','-fdata-sections']
        if target=='rv32':values+=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align']
        if target=='sanitizer':values+=['-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
        return values
    def build(name,sources,target,extra):
        cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'gcc'
        binary=out/name
        run(name+'-build',[cc,*flags(target),*extra,*['-I'+wsl_path(ROOT/p) for p in include],
            *[wsl_path(ROOT/p) for p in sources],'-Wl,--gc-sections','-lm','-o',wsl_path(binary)])
        return binary
    try:
        if args.prepare_benchmark_only:
            binaries=[]
            for target in ['host','rv32']:
                binary=build('prepare-'+target,unit,target,
                    ['-DXQIH_RGB8_PREP_NO_PROBE','-DXQ_HWC_RGB_QUANT=0'])
                prefix=['qemu-riscv32'] if target=='rv32' else []
                text=run('prepare-'+target+'-verify',[*prefix,wsl_path(binary)])
                assert 'RGB8_PREP_NO_PROBE_F32_PIXEL_BLOCK32_COMPLETE_HWC_BYTES_PASS_NOT_GRAPH_OR_BOARD' in text
                binaries.append(dict(target=target,binary=str(binary),result=text.strip()))
            assert before=={name:sha(ROOT/name) for name in before}
            result.update(status='RGB8_INPUT_PREP_NO_PROBE_BINARIES_CORRECTNESS_PASS_NOT_BOARD',
                source_stable=True,benchmark_executed=False,no_malloc_or_counter_probes=True,
                no_probe_binaries=binaries,scope='input normalize+packing only, no graph or board',
                benchmark_variants={'0':'F32_normalize_then_word','1':'original_direct_pixel','2':'direct_block32'})
            print(result['status'])
            return
        for target in ['host','rv32','sanitizer']:
            prefix=['qemu-riscv32'] if target=='rv32' else []
            for cache in [0,1]:
                name='unit-'+target+'-lookup'+str(cache)
                binary=build(name,unit,target,['-DXQ_HWC_RGB_QUANT='+str(cache),'-Wl,--wrap=malloc'])
                text=run(name,[*prefix,wsl_path(binary)])
                assert 'RGB8_DIRECT_BLOCK32_PIXEL_F32_PALETTE_FULL_HWC_BYTES_LENGTH_CANCEL_OOM_PASS' in text
                result['unit_checks'].append(dict(target=target,rgb_cache=cache,result=text.strip()))
        if args.unit_only:
            assert before=={name:sha(ROOT/name) for name in before}
            result.update(status='RGB8_BLOCK32_PIXEL_F32_PALETTE_BYTES_HOST_RV32_SANITIZERS_UNIT_PASS_NOT_BOARD',
                source_stable=True,all_241_palette_exponents=True,original_pixel_reference_compared=True,
                complete_graphs_rerun=False,block_array_bytes=96)
            print(result['status'])
            return
        wrap=['-DXQ_HWC_DETECTOR=1','-DXQ_HWC_RGB8_DIRECT=1','-DXQ_HWC_WORD_INPUT=1','-DXQ_HWC_TILE_EXPORT=1',
              '-DXQ_CLASSIFIER_S16=1','-DXQ_FAST_REQUANT=1',
              '-Wl,--wrap=open,--wrap=close,--wrap=mmap,--wrap=munmap,--wrap=ioctl,--wrap=malloc,--wrap=calloc']
        for target in ['host','sanitizer','rv32']:
            binary=build('product-'+target,product,target,wrap)
            prefix=['qemu-riscv32'] if target=='rv32' else []
            if target=='rv32':
                data=binary.read_bytes();assert data[:6]==b'\x7fELF\x01\x01' and struct.unpack_from('<H',data,18)[0]==243 and struct.unpack_from('<I',data,36)[0]==0
                text=run('product-rv32-guards',[*prefix,wsl_path(binary),wsl_path(models/'detector.xqm'),'--guards-only'],240)
                assert 'RGB8_GRAPH_API_PREFLIGHT_RETENTION_HWC_INVALIDATION_EARLY_FAILURE_PASS_NOT_FULL_HEADS' in text
                result['product_checks'].append(dict(target=target,scope='guards_and_early_failures',result=text.strip()))
                text=run('product-rv32-pair',[*prefix,wsl_path(binary),wsl_path(models/'detector.xqm'),'--pair-only'],360)
                assert 'RGB8_GRAPH_API_COMPLETE_THREE_HEADS_PAIR_PASS_NOT_BOARD' in text
                result['product_checks'].append(dict(target=target,scope='old_float_vs_rgb8_complete_three_heads',result=text.strip()))
            else:
                text=run('product-'+target,[wsl_path(binary),wsl_path(models/'detector.xqm')],240)
                assert 'RGB8_GRAPH_API_OLD_FLOAT_COMPLETE_THREE_HEADS_FAILURE_RECOVERY_PASS_NOT_BOARD' in text
                result['product_checks'].append(dict(target=target,scope='complete_three_heads_guards_failures_and_recovery',result=text.strip()))
        assert before=={name:sha(ROOT/name) for name in before}
        assert model_before=={name:sha(models/name) for name in model_before}
        result.update(status='RGB8_DIRECT_PALETTE_HWC_BYTES_OLD_FLOAT_THREE_HEADS_FAILURE_RECOVERY_HOST_RV32_SANITIZERS_PASS_NOT_BOARD',
            source_stable=True,all_241_palette_exponents=True,original_float_api_preserved=True,
            general_preflight_preserves_old_outputs=True,accepted_hwc_request_invalidates_outputs=True,
            invalid_length_no_graph=True,cpu_observer_and_missing_exact_rejected=True,
            no_cpu_fallback=True,full_graph_transport_mocked=True)
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])
if __name__=='__main__':main()
