"""Bounded 135-frame selected-combination regression; no hardware."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from r09_reference import selected_paths

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--backend',choices=['fp32','quantized-mac'],required=True)
    p.add_argument('--refinement',choices=['full','B'],default='B')
    p.add_argument('--no-candidate-filter',action='store_true',help='Offline control only')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    release,candidate=selected_paths()
    identity=json.loads((REPO/'docs/validation/picture-p20-combined-20261020/fp32/inputs.json').read_text())['files']
    dataset=Path(identity['IMG00908/image']['path']).parents[1]
    board=Path(identity['IMG00908/board']['path']).parent
    with (a.out/'probe.log').open('w') as log:
        subprocess.run([sys.executable,'-B',str(HERE/'probe_mm_char.py'),'--out',str(a.out/'probe.json')],
                       stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    with (a.out/'evaluation.log').open('w') as log:
        subprocess.run([sys.executable,'-B',str(HERE/'evaluate_combined.py'),'--backend',a.backend,
                        '--release',str(release),'--candidate',str(candidate),
                        *([] if a.no_candidate_filter else ['--candidate-filter']),
                        '--refinement',a.refinement,'--dataset',str(dataset),'--board-dir',str(board),
                        '--label-policy','user-original-game3-20261020','--out',str(a.out/'results')],
                       stdout=log,stderr=subprocess.STDOUT,check=True,timeout=7200)
    print('R09_COMBINATION_EVALUATION_COMPLETE',a.backend,a.refinement,flush=True)
