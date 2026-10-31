"""Adjacent single-consumer Concat view: frozen outputs and lifetime checks."""
import argparse,hashlib,json,shlex,subprocess
from pathlib import Path
from picture_workspace import ROOT,workspace_path,wsl_path
HWC='linux/picture_new/hwc_fast'
RUNTIME='artifacts/vision-model-20261020-adapter/runtime'

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--kit',type=Path,default=ROOT/'build/hwc-acceptance-kit')
    a=ap.parse_args();assert a.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(a.output);assert not out.exists();out.mkdir(parents=True)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    kit=workspace_path(a.kit);expected=json.loads((kit/'expected.json').read_text())
    assert sha(kit/'models/detector.xqm')=='d65b4b8686520ae1546d0a207c1bcb9f30efe0d40e7f5c8245c4dd11ff9ca09d'
    assert sha(kit/'models/detector.xqi')=='d72d039041b41310f037344772eb75ce895ec6fe678bbb31ed547a7ad7453942'
    provider=(ROOT/HWC/'integer_hwc.c').read_text();candidate=(ROOT/HWC/'concat_view.h').read_text()
    original='static int convolution('+provider.split('static int convolution(',1)[1].split('static int nonconv(',1)[0]
    # The provider declares the next helper between convolution and nonconv.
    original=original[:original.index('\n}\n')+3]
    clone=candidate.split('/* XQIH_CONCAT_CONV_BEGIN */\n',1)[1].split('/* XQIH_CONCAT_CONV_END */',1)[0]
    clone='\n'.join(q for q in clone.splitlines() if not q.startswith('#pragma'))+'\n'
    restored=clone.replace('static int xqih_convolution_view(','static int convolution(').replace(',const xqih_concat_view *view){','){')
    restored=restored.replace('if(!xqih_pack_concat(io->shadow,view,j.width,j.height,source_x,source_y,n[18],stats,io))return 0;',
        'pack_input(io->shadow,src,j.width,j.height,source_x,source_y,n[18],stats);')
    assert restored.strip()==original.strip(),'convolution dispatch/layout/output drift'
    common=[HWC+'/tests/picture_new_graph_mock.c','linux/picture_new/graph_profile.c',
        'linux/picture_new/vision32_layer.c','linux/picture_new/vision32_backend.c',RUNTIME+'/xq_sha256.c','sw/bootloader/crc32_fast.c']
    includes=[HWC,RUNTIME,'linux/picture_new','linux/vision','linux/mac_accel','sw/bootloader']
    files=set(common+[HWC+'/'+q for q in ['adapter.c','concat_view.h','tail_columns.h','integer_hwc.c','input_quant.c',
        'tests/test_concat_view.c','tests/product_concat_view.c','rgb8_direct.h']]+['scripts/check_picture_hwc_concat_view.py',
        'linux/picture_new/vision32_locality.c','linux/picture_new/vision32_exact.c',
        'linux/picture_new/whole_layer_fast/vision32_layer.c','linux/picture_new/upstream/adapter/runtime/xq_int8_layer.c',
        HWC+'/tests/vision_exact_capture.h'])
    for d in includes:files.update(q.relative_to(ROOT).as_posix() for q in (ROOT/d).glob('*.h'))
    before={q:sha(ROOT/q) for q in sorted(files)}
    result=dict(status='FAILED_PRESERVED',hardware_used=False,device_mocked=True,source_sha256=before,
        convolution_clone_reverses_exactly=True,unit_checks=[],full_heads_checks=[])
    def run(name,args,seconds=180,allowed=(0,)):
        with (out/(name+'.log')).open('xb') as f:
            r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                'ulimit -c 0\nexec timeout --kill-after=5 '+str(seconds)+' '+shlex.join(args)],stdout=f,stderr=subprocess.STDOUT,timeout=seconds+20)
        text=(out/(name+'.log')).read_text(errors='replace')
        assert r.returncode in allowed,(name,r.returncode,text[-2000:])
        return text
    def build(name,target,src,extra):
        cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'cc'
        flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off','-ffunction-sections','-fdata-sections']
        if target=='rv32':flags+=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align']
        if target=='sanitizers':flags+=['-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-no-pie']
        exe=out/name
        run(name+'-build',[cc,*flags,*['-I'+wsl_path(ROOT/q) for q in includes],*extra,
            *[wsl_path(ROOT/q) if not Path(q).is_absolute() else wsl_path(Path(q)) for q in src],'-Wl,--gc-sections','-lm','-o',wsl_path(exe)])
        return exe
    try:
        for target in ['host','rv32','sanitizers']:
            prefix=['qemu-riscv32'] if target=='rv32' else []
            exe=build(target+'-unit',target,[HWC+'/tests/test_concat_view.c'],[])
            text=run(target+'-unit',[*prefix,wsl_path(exe)])
            assert 'PASS cases=252' in text
            result['unit_checks'].append(dict(target=target,cases=252,two_stage_storage_exact=True,halo_pitch_cancel_reject=True))
        mutant=candidate.replace('int32_t stored=src->bits==8?(int8_t)scaled:(int16_t)scaled;','int32_t stored=scaled;')
        assert mutant!=candidate;(out/'concat-mutant.h').write_text(mutant)
        unit=(ROOT/HWC/'tests/test_concat_view.c').read_text().replace('"../integer_hwc.c"','"'+wsl_path(ROOT/HWC/'integer_hwc.c')+'"').replace('"../concat_view.h"','"'+wsl_path(out/'concat-mutant.h')+'"')
        (out/'mutant.c').write_text(unit)
        exe=build('missing-storage-mutant','host',[str(out/'mutant.c')],[])
        text=run('missing-storage-mutant',[wsl_path(exe)],allowed=(6,134))
        assert 'memcmp' in text;result['missing_storage_cast_mutation_rejected']=True
        for target,cases in [('host',['fixed','zero','signed']),('rv32',['fixed']),('sanitizers',['fixed'])]:
            prefix=['qemu-riscv32'] if target=='rv32' else []
            extra=['-DXQ_HWC_TAIL_COLUMNS=1','-DXQ_HWC_CONCAT_VIEW=1','-DXQ_HWC_WORD_INPUT=1','-DXQ_HWC_RGB8_DIRECT=1',
                '-Wl,--wrap=open,--wrap=close,--wrap=mmap,--wrap=munmap,--wrap=ioctl,--wrap=malloc,--wrap=calloc']
            exe=build(target+'-product',target,[HWC+'/tests/product_concat_view.c',*common],extra)
            for case in cases:
                dest=out/(target+'-'+case+'.heads.f32');faults=target in ['host','sanitizers'] and case=='fixed'
                text=run(target+'-'+case,[*prefix,wsl_path(exe),wsl_path(kit/'models/detector.xqm'),
                    wsl_path(kit/('synthetic/'+case+'.f32')),wsl_path(dest),*(['--faults'] if faults else [])],900)
                assert 'CONCAT_VIEW_FULL_FROZEN_HEADS_9_NODES_4300800_BYTES_ELIDED_NOT_BOARD' in text
                if faults:assert 'CONCAT_VIEW_FUSED_PARENT_LIFETIME_OOM_IO_CANCEL_HEAD_FAILURE_RECOVERY_PASS' in text
                assert sha(dest)==expected['cases'][case]['output_sha256'],(target,case,'heads differ')
                assert 'allocated=16727200 peak=2457600 jobs=152' in text
                result['full_heads_checks'].append(dict(target=target,case=case,jobs=152,three_heads_equal_frozen_cpu=True,lifetime_faults=faults))
        assert before=={q:sha(ROOT/q) for q in before}
        result.update(status='CONCAT_VIEW_HOST_RV32_SANITIZERS_FULL_HEADS_LIFETIME_PASS_NOT_BOARD',
            source_stable=True,default_selected=False,board_latency_accepted=False,elided_nodes=9,elided_bytes=4300800,
            allocated_tensor_bytes=16727200,peak_tensor_bytes=2457600)
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])
if __name__=='__main__':main()
