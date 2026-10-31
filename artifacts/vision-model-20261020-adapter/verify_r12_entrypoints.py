"""Game-3-only verification of the E default and explicit rollback identities."""
import argparse
import hashlib
import json
import subprocess
import sys
import zlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--receipt',type=Path,required=True)
    parser.add_argument('--default-only',action='store_true')
    args=parser.parse_args();out=args.out.resolve()
    assert out.is_relative_to(REPO/'build') and not out.exists() and not args.receipt.exists()
    out.mkdir(parents=True)
    inputs=json.loads((REPO/'build/picture-r11-20261022/adapter-inputs/game3-inputs.json').read_text())
    frame=inputs['frames'][0];assert inputs['game']==3 and 152<=frame['index']<=234
    source=REPO/frame['path'];assert hashlib.sha256(source.read_bytes()).hexdigest()==frame['sha256']
    cases=[('default_E',[],dict(classifier='v3c',detector='frozen640',backend='fp32'))]
    if not args.default_only:
        cases.extend([
            ('rollback_v2band',['--profile','rollback-v2-band'],dict(classifier='v2-band',detector='frozen640',backend='fp32')),
            ('rollback_v2band_exact',['--profile','rollback-v2-band','--backend','quantized-mac'],dict(classifier='v2-band',detector='frozen640',backend='quantized-mac')),
            ('legacy_r09',['--profile','working-r09'],dict(classifier='v2-band',detector='det416-r09',backend='quantized-mac')),
            ('quantized_E_rejected',['--backend','quantized-mac'],None)])
    report={}
    for name,options,expected in cases:
        target=out/(name+'.json')
        command=[sys.executable,'-B',str(HERE/'recognize_working.py'),'--input',str(source),'--output',str(target),*options]
        result=subprocess.run(command,cwd=REPO,capture_output=True,timeout=300)
        (out/(name+'.log')).write_bytes(result.stdout+result.stderr)
        if expected is None:
            assert result.returncode and not target.exists() and b'No exact-int64 INT8 payload' in result.stderr
            report[name]=dict(passed=True,no_output=True)
        else:
            assert result.returncode==0,result.stderr.decode(errors='replace')
            data=json.loads(target.read_text())
            assert data['selected_classifier']==expected['classifier'],('wrong default classifier',data['selected_classifier'])
            assert data['selected_detector']==expected['detector'] and data['delivery_backend']==expected['backend']
            assert not data['production_ready'] and not data['full_integer_pipeline']
            if expected['backend']=='fp32':assert 'integer_oracle' not in data
            else:assert data['integer_oracle']=='r08-exact-int64'
            if name=='default_E':
                assert data['working_profile']=='working-r12'
                assert data['models']['classifier']['sha256']=='b186ae36c099c3adcd6587b644dc53b5c4f39afc6115f67bd133ee6b3ca101ca'
                assert data['models']['detector']['sha256']=='02245fba7d0f04823d2de75ec3577ad83b9a12c0702342ff2bae3d112d7d9c2d'
            report[name]=dict(passed=True,profile=data['working_profile'],backend=data['delivery_backend'],models={k:v['sha256'] for k,v in data['models'].items()})
        print('R12_ENTRYPOINT_PASS',name,flush=True)
    if not args.default_only:
        import cv2
        import numpy as np
        image=cv2.imread(str(source));assert image.shape==(720,1280,3)
        raw=(((image[:,:,2].astype(np.uint16)>>3)<<11)|((image[:,:,1].astype(np.uint16)>>2)<<5)|(image[:,:,0].astype(np.uint16)>>3)).astype('<u2').tobytes()
        raw_path=out/'training.rgb565';raw_path.write_bytes(raw)
        for label,backend,success in [('E_peer_fp32','pc-fp32',True),('E_peer_wrong_backend','pc-quantized-mac',False)]:
            request=out/(label+'.request');target=out/(label+'.packet');detail=out/(label+'.json')
            request.write_text(f'XQ_MODEL_REQUEST_V1 17 42 {zlib.crc32(raw):08x} {backend}\n')
            result=subprocess.run([sys.executable,'-B',str(HERE/'recognize_peer.py'),'--request',str(request),
                '--input',str(raw_path),'--output',str(target),'--result-json',str(detail)],cwd=REPO,capture_output=True,timeout=300)
            (out/(label+'.log')).write_bytes(result.stdout+result.stderr)
            if success:
                assert result.returncode==0,result.stderr.decode(errors='replace')
                data=json.loads(detail.read_text())
                assert data['working_profile']=='working-r12' and data['delivery_backend']=='PC_ASSISTED_fp32'
                assert 'integer_oracle' not in data
                assert target.read_text().splitlines()[0].split()[4]=='pc-fp32'
            else:
                assert result.returncode and not target.exists() and not detail.exists() and b'invalid_capture_request' in result.stderr
            report[label]=dict(passed=True,backend=backend)
            print('R12_ENTRYPOINT_PASS',label,flush=True)
    args.receipt.write_text(json.dumps(dict(status='PASS',checks=report,input_scope='one allowed game-3 training frame; no accuracy acceptance',
        game2_images_read=0,game2_inference_runs=0,hardware_used=False,production_ready=False),indent=2)+'\n')


if __name__=='__main__':main()
