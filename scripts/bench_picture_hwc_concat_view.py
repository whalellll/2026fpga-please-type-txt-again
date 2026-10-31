"""Paired actual nine Concat/conv pack paths with no-op device, not board speed."""
import argparse,hashlib,json,re,shlex,subprocess
from pathlib import Path
from picture_workspace import ROOT,workspace_path,wsl_path

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--kit',type=Path,default=ROOT/'build/hwc-acceptance-kit');a=ap.parse_args()
    assert a.output.absolute().is_relative_to(ROOT/'build');out=workspace_path(a.output);assert not out.exists();out.mkdir(parents=True)
    model=workspace_path(a.kit)/'models/detector.xqi';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    assert sha(model)=='d72d039041b41310f037344772eb75ce895ec6fe678bbb31ed547a7ad7453942'
    paths=['linux/picture_new/hwc_fast/'+q for q in ['tests/bench_concat_view.c','concat_view.h','integer_hwc.c','integer_hwc.h']]
    paths+=['scripts/bench_picture_hwc_concat_view.py','sw/bootloader/crc32_fast.c','sw/bootloader/crc32_fast.h']
    for d in ['linux/picture_new','linux/vision','linux/mac_accel','artifacts/vision-model-20261020-adapter/runtime']:
        paths+=[q.relative_to(ROOT).as_posix() for q in (ROOT/d).glob('*.h')]
    before={p:sha(ROOT/p) for p in sorted(set(paths))};result=dict(status='FAILED_PRESERVED',hardware_used=False,source_sha256=before,results=[])
    def run(name,args,seconds=120):
        with (out/(name+'.log')).open('xb') as f:
            r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c','ulimit -c 0\nexec timeout --kill-after=5 '+str(seconds)+' '+shlex.join(args)],stdout=f,stderr=subprocess.STDOUT,timeout=seconds+20)
        text=(out/(name+'.log')).read_text(errors='replace');assert not r.returncode,(name,text[-2000:]);return text
    try:
        for target in ['host','rv32']:
            cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'cc'
            flags=['-O2','-std=c11','-Wall','-Wextra','-Werror','-ffp-contract=off','-ffunction-sections','-fdata-sections']
            if target=='rv32':flags+=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align']
            includes=['linux/picture_new/hwc_fast','linux/picture_new','linux/vision','linux/mac_accel','sw/bootloader','artifacts/vision-model-20261020-adapter/runtime']
            exe=out/target
            run(target+'-build',[cc,*flags,*['-I'+wsl_path(ROOT/p) for p in includes],wsl_path(ROOT/paths[0]),wsl_path(ROOT/'sw/bootloader/crc32_fast.c'),'-Wl,--gc-sections','-lm','-o',wsl_path(exe)])
            text=run(target,[*(['qemu-riscv32'] if target=='rv32' else []),wsl_path(exe),wsl_path(model)])
            match=re.search(r'CONCAT_CPU_CLUE_PASS jobs=(\d+) original_ns=(\d+) view_ns=(\d+) NOT_BOARD',text);assert match
            jobs,original,view=map(int,match.groups());assert jobs>9
            rounds=[dict(round=int(r),view=bool(int(v)),cpu_ns=int(ns)) for r,v,ns in re.findall(r'CONCAT_CPU_PAIR round=(\d+) view=(\d+) ns=(\d+)',text)]
            assert len(rounds)==8
            result['results'].append(dict(target=target,jobs=jobs,original_ns=original,view_ns=view,ratio=view/original,rounds=rounds))
        assert before=={p:sha(ROOT/p) for p in before}
        result.update(status='CONCAT_PAIRED_CPU_CLUE_EXACT_PACK_BYTES_PASS_NOT_BOARD',source_stable=True,
            measured_scope='nine frozen-shape concats plus packing/output copies; no-op device; allocations excluded',
            before_and_after_all_tile_inputs_equal=True,alternating_four_pairs_after_both_warmups=True,board_cache_or_latency_measured=False)
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status=result['status'],ratios=[dict(target=r['target'],ratio=r['ratio']) for r in result['results']])))
if __name__=='__main__':main()
