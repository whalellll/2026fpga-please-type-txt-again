"""Compare every public weight-store signal against the pre-optimization RTL."""
from pathlib import Path
import argparse, hashlib, json, subprocess, os

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--iverilog',default='G:/fpga/workspace/tools/msys64/ucrt64/bin/iverilog.exe')
    p.add_argument('--vvp',default='G:/fpga/workspace/tools/msys64/ucrt64/bin/vvp.exe')
    a=p.parse_args();os.environ['PATH']=str(Path(a.iverilog).parent)+os.pathsep+os.environ.get('PATH','');root=Path(__file__).resolve().parents[1];out=a.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
    reference=root/'sim/reference/mac_weight_double_buffer_metadata.v'
    candidate=root/'rtl/mac_accel/mac_weight_double_buffer.v'
    tb=root/'sim/tb_weight_metadata_equivalence.sv'
    result=dict(status='RUNNING',files_sha256={str(f.relative_to(root)):sha(f) for f in [reference,candidate,tb]},cases=[])
    def run(label,source,width,depth,negative=False):
        image=out/(label+'.vvp');log=out/(label+'.log');aw=2 if depth==4 else 5
        cmd=[a.iverilog,'-g2012','-s','tb_weight_metadata_equivalence',
             '-Ptb_weight_metadata_equivalence.W='+str(width),
             '-Ptb_weight_metadata_equivalence.DEPTH='+str(depth),
             '-Ptb_weight_metadata_equivalence.AW='+str(aw),'-o',str(image),str(reference),str(source),str(tb)]
        c=subprocess.run(cmd,capture_output=True,timeout=60);log.write_bytes(c.stdout+c.stderr)
        assert c.returncode==0,log
        c=subprocess.run([a.vvp,str(image)],capture_output=True,timeout=120)
        with log.open('ab') as f:f.write(c.stdout+c.stderr)
        if negative:assert c.returncode!=0 and b'public cycle mismatch' in c.stdout,log
        else:assert c.returncode==0 and b'WEIGHT_METADATA_CYCLE_EQUIVALENCE_PASS' in c.stdout,log
        result['cases'].append(dict(name=label,width=width,depth=depth,negative=negative,log_sha256=sha(log)))
    try:
        for width in [544,1024]:
            for depth in [4,27,32]:run(f'w{width}-d{depth}',candidate,width,depth)
        # A metadata fault must be observed, rather than passing a data-only test.
        mutant=out/'wrong_generation.v';text=candidate.read_text()
        text,n=__import__('re').subn(r'active_generation <= [^;]+;',"active_generation <= 32'b0;",text)
        assert n>=2;mutant.write_text(text)
        run('reject-wrong-generation',mutant,544,4,True)
        result.update(status='WEIGHT_METADATA_120000_PUBLIC_CYCLES_AND_FAULT_REJECTION_PASS_NOT_STA',cycles=120000)
    except Exception as error:
        result.update(status='FAILED_PRESERVED',error=repr(error));raise
    finally:
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(result['status'],flush=True)

if __name__=='__main__':main()
