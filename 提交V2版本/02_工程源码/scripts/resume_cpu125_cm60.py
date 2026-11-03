"""Read-only check by default; --run explicitly resumes the preserved offline native job."""
from pathlib import Path
import argparse,subprocess,sys
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--work',type=Path,default=Path(__file__).resolve().parents[2])
p.add_argument('--run',action='store_true')
p.add_argument('--attempt',type=int,default=2)
a=p.parse_args();work=a.work.resolve()
assert work.is_relative_to(Path('G:/fpga').resolve()),'New runs and outputs must remain in G:/fpga'
assert work.name=='cpu125-coremark60-20261102-01' and (work/'resume_native.py').is_file()
assert 2<=a.attempt<=999
args=[sys.executable,'-X','utf8','-B',str(work/'resume_native.py'),'--attempt',str(a.attempt)]
if a.run:args.append('--run')
raise SystemExit(subprocess.run(args,cwd=work).returncode)
