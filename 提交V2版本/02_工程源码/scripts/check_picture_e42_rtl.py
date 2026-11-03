"""Run the published vision RTL with its original independent integer oracle.

Windows orchestrates Ubuntu/WSL; --native is its bounded Linux simulation
stage. No RTL edits, PDS, device, photos or SD media operations are performed.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--suite', choices=['exact','legacy'], required=True)
    ap.add_argument('--soc', action='store_true')
    ap.add_argument('--native', action='store_true', help=argparse.SUPPRESS)
    ap.add_argument('--numpy-dir', type=Path)
    a = ap.parse_args()
    if not a.native:
        from picture_workspace import workspace_path, wsl_path
        assert a.output.absolute().is_relative_to(ROOT/'build')
        out = workspace_path(a.output)
        assert not out.exists()
        args = ['wsl.exe','-d','Ubuntu-22.04','--']
        if a.numpy_dir:args += ['env','PYTHONPATH='+wsl_path(a.numpy_dir)]
        args += ['python3',wsl_path(Path(__file__)),'--native','--suite',a.suite,
                 '--output', '/mnt/'+str(a.output.absolute())[0].lower()+a.output.absolute().as_posix()[2:]]
        if a.soc:args.append('--soc')
        result = subprocess.run(args, timeout=1260)
        assert result.returncode==0, 'Native result/log retained'
        return
    assert os.name=='posix' and a.output.absolute().is_relative_to(ROOT/'build')
    out=a.output;out.mkdir(parents=True,exist_ok=False)
    from test_vision32 import fixture,cases
    import numpy as np
    if a.suite=='legacy':jobs=cases()
    else:
        jobs=[]
        for flags in [4,5]:
            for shift in range(63):
                jobs.append(dict(w=1,h=1,ci=1,co=14,k=1,s=1,p=0,exact_edges=True,
                                 exact_shift=shift,flags=flags,name='exact_shift_'+str(shift)))
            for base in [dict(w=1,h=1,ci=1,co=256,k=1,s=1,p=0,exact_edges=True),
                         dict(w=5,h=3,ci=7,co=9,k=1,s=1,p=0),
                         dict(w=5,h=3,ci=4,co=17,k=3,s=2,p=1),
                         dict(w=3,h=3,ci=128,co=9,k=3,s=1,p=0),
                         dict(w=3,h=1,ci=1,co=9,k=1,s=1,p=0,half_ties=True),
                         dict(w=5,h=3,ci=7,co=9,k=1,s=1,p=0,cross=True),
                         dict(w=1,h=1,ci=1,co=2,k=1,s=1,p=0,overflow=True)]:
                jobs.append(dict(base,flags=flags,name='exact_'+str(flags)+'_'+str(len(jobs))))
            for fault in [1,2,3,4,5]:jobs.append(dict(w=5,h=3,ci=4,co=9,k=3,s=1,p=1,flags=flags,fault=fault,name='exact_fault_'+str(fault)))
            for bad in ['overlap','out_of_range','bad_shift']:
                jobs.append(dict(w=3,h=1,ci=4,co=9,k=1,s=1,p=0,flags=flags,bad=bad,name='exact_bad_'+bad))
    vectors=[fixture(job,i,out) for i,job in enumerate(jobs)]
    (out/'vectors.json').write_text(json.dumps(vectors,indent=2)+'\n')
    tb=ROOT/'sim/tb_vision32_layer.sv'
    sources=[ROOT/'rtl/mac_accel/vision32_pe.v',ROOT/'rtl/mac_accel/vision32_layer.v',tb]
    if a.soc:sources=sorted((ROOT/'rtl/mac_accel').glob('*.v'))+[tb,ROOT/'sim/gtp_apm_e2_perf_sim.v']
    source_files=sources+[Path(__file__),ROOT/'scripts/test_vision32.py',ROOT/'sim/vectors/vision32_shapes.json']
    before={p.relative_to(ROOT).as_posix():sha(p) for p in source_files}
    if a.suite=='exact':
        body=tb.read_text();needle='  if(rd!==32\'h56333231)$fatal(1,"ID %h",rd);'
        assert body.count(needle)==1
        generated=out/'tb_exact.sv'
        generated.write_text(body.replace(needle,needle+'\n  ra=8\'h6c;#1;if(rd!==32\'h00010001)$fatal(1,"EXACT_CAP_VERSION %h",rd);'))
        sources=[generated if p==tb else p for p in sources]
    commands=[['iverilog','-g2012','-s','tb_vision32_layer',
               '-Ptb_vision32_layer.CASES='+str(len(jobs)),'-Ptb_vision32_layer.SOC='+str(int(a.soc)),
               '-o',str(out/'vision.vvp'),*map(str,sources)], ['vvp',str(out/'vision.vvp')]]
    result={'status':'FAILED_PRESERVED_NOT_BOARD','suite':a.suite,'soc':a.soc,'cases':len(jobs),
            'source_sha256':before,'commands':commands,'numpy_version':np.__version__,
            'hardware_used':False,'new_rtl_or_synthesis':False}
    try:
        with (out/'simulation.log').open('xb') as log:
            for command in commands:
                run=subprocess.run(command,cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=1200)
                assert run.returncode==0, 'Simulation failed; see retained log'
        assert b'VISION32_ALL_PASS' in (out/'simulation.log').read_bytes()
        assert all(sha(ROOT/p)==digest for p,digest in before.items()),'RTL/source changed during simulation'
        result.update(status='E42_'+a.suite.upper()+'_ORIGINAL_INTEGER_ORACLE_RTL_PASS_NOT_BOARD',
                      source_stable=True,vector_sha256=sha(out/'vectors.json'),log_sha256=sha(out/'simulation.log'))
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'],len(jobs),flush=True)


if __name__=='__main__':main()
