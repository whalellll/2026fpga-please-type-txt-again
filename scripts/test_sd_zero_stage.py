"""Exercise the production zero-address boot load wrapper with guarded buffers."""
import argparse,hashlib,json,os,subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--gcc',required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args();root=Path(__file__).resolve().parents[1]
a.output.mkdir(parents=True,exist_ok=False)
record=dict(status='RUNNING',commands=[])
env=os.environ.copy();env['PATH']=str(Path(a.gcc).parent)+os.pathsep+env['PATH']
try:
    exe=a.output/'sd-zero-stage.exe'
    for name,cmd in [('compile',[a.gcc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-I',str(root/'sw/bootloader'),str(root/'sim/sd_zero_stage_host_test.c'),'-o',str(exe)]),('run',[str(exe)])]:
        result=subprocess.run(cmd,capture_output=True,timeout=60,env=env)
        (a.output/(name+'.log')).write_bytes(result.stdout+result.stderr)
        record['commands'].append(dict(command=cmd,returncode=result.returncode))
        assert result.returncode==0,(name,(result.stdout+result.stderr).decode(errors='replace'))
    assert b'SD_ZERO_STAGE_HOST_PASS' in (a.output/'run.log').read_bytes()
    record.update(status='SD_ZERO_STAGE_HOST_PASS_NOT_BOARD',source_sha256={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ['sim/sd_zero_stage_host_test.c','sw/bootloader/sd_boot_load.h']})
except Exception as e:
    record.update(status='FAILED_PRESERVED',error=repr(e));raise
finally:
    (a.output/'result.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(record['status'])
