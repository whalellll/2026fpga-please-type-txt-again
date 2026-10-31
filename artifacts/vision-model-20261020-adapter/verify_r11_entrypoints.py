"""Exercise default/explicit candidate CLI identity using game 3 only."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--receipt',type=Path,required=True)
    args=parser.parse_args();out=args.out.resolve()
    assert out.is_relative_to(REPO/'build') and not out.exists() and not args.receipt.exists()
    out.mkdir(parents=True)
    inputs=json.loads((REPO/'build/picture-r11-20261022/adapter-inputs/game3-inputs.json').read_text())
    assert inputs['game']==3
    frame=inputs['frames'][0];assert 152<=frame['index']<=234
    source=REPO/frame['path'];assert hashlib.sha256(source.read_bytes()).hexdigest()==frame['sha256']
    rows={}
    for label,options in (
        ('quantized_v3c_rejected',['--classifier','v3c']),
        ('explicit_v3c_mix',['--backend','fp32','--classifier','v3c','--detector','det416mix-r11']),
        ('default_v2_band',[])):
        target=out/(label+'.json')
        command=[sys.executable,'-B',str(HERE/'recognize_working.py'),'--input',str(source),'--output',str(target),*options]
        result=subprocess.run(command,cwd=REPO,capture_output=True,timeout=300)
        (out/(label+'.log')).write_bytes(result.stdout+result.stderr)
        if label=='quantized_v3c_rejected':
            assert result.returncode and not target.exists() and b'no r11 INT8 payload' in result.stderr
            rows[label]=True
        else:
            assert result.returncode==0,result.stderr.decode(errors='replace')
            data=json.loads(target.read_text())
            assert not data['production_ready'] and not data['full_integer_pipeline']
            models={name:item['sha256'] for name,item in data['models'].items()}
            assert data['selected_classifier']==('v3c' if label=='explicit_v3c_mix' else 'v2-band')
            assert models['classifier']==('b186ae36c099c3adcd6587b644dc53b5c4f39afc6115f67bd133ee6b3ca101ca' if label=='explicit_v3c_mix' else 'd184f7970f16311515110c008ca768b33e62ac43ffcf09f125085acc9905d3be')
            assert data['selected_detector']==('det416mix-r11' if label=='explicit_v3c_mix' else 'det416-r09')
            if label=='default_v2_band':assert data['integer_oracle']=='r08-exact-int64'
            rows[label]=dict(passed=True,models=models,profile=data['working_profile'])
        print('R11_ENTRYPOINT_PASS',label,flush=True)
    args.receipt.write_text(json.dumps(dict(status='PASS',checks=rows,hardware_used=False,
        input_scope='one game-3 training frame, not accuracy acceptance',game2_frames_read=0,
        game2_annotations_read=0,game2_inference_runs=0,production_ready=False),indent=2)+'\n')


if __name__=='__main__':main()
