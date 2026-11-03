"""Known uncertainty and padded little-endian RGB565 receiver checks."""
import argparse,copy,json,os,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1];GOLDEN=HERE.parent/'vision-model-20261020/golden'
def main():
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,required=True);a=p.parse_args()
    sys.path[:0]=[str(GOLDEN/'software'),str(GOLDEN/'quantization')]
    import cv2,numpy as np
    from io_images import decode_rgb565
    from recognizer import Recognizer
    from integer_ops import load_integer_runtime
    out=HERE/'validation/interface-inputs';out.mkdir(parents=True,exist_ok=False)
    image=cv2.imread(str(a.dataset/'in/IMG00861.PNG'));assert image.shape==(720,1280,3)
    words=((image[:,:,2].astype(np.uint16)>>3)<<11)|((image[:,:,1].astype(np.uint16)>>2)<<5)|(image[:,:,0].astype(np.uint16)>>3)
    rows=np.full((720,2576),0xa5,np.uint8);rows[:,:2560]=np.frombuffer(words.astype('<u2').tobytes(),np.uint8).reshape(720,2560)
    raw=out/'frame565-stride.raw';raw.write_bytes(rows.tobytes())
    decoded=decode_rgb565(raw.read_bytes(),1280,720,stride_bytes=2576)
    png=out/'frame565-decoded.png';png.write_bytes(cv2.imencode('.png',decoded)[1].tobytes())
    records=[]
    for backend in ('fp32','quantized-mac'):
        model=Recognizer(GOLDEN/'software',device='cpu',precision='fp32') if backend=='fp32' else load_integer_runtime(GOLDEN/'software',GOLDEN/'quantization/candidate_v1')
        states=[]
        for idx in (862,863,864):
            result=model.predict(a.dataset/'in'/f'IMG{idx:05d}.PNG')
            states.append({'frame':idx,'status':result['status'],'usable_fen':result['board_placement_fen'],'candidate_fen':result['candidate_placement_fen']})
            assert result['board_placement_fen'] is None and result['automatic_action_allowed'] is False,(backend,idx,result['status'])
        r=model.predict(raw,pixel_format='rgb565',width=1280,height=720,byte_order='little',stride_bytes=2576)
        q=model.predict(png)
        for result in (r,q):result.pop('timings_ms');result.pop('frame')
        assert r==q,backend+' raw/padded PNG result mismatch'
        records.append({'backend':backend,'uncertainty':states,'rgb565_padded_stride':2576,'rgb565_vs_decoded_png_all_nonframe_nontiming_fields_exact':True})
    try:decode_rgb565(raw.read_bytes()[:-1],1280,720,stride_bytes=2576)
    except ValueError:pass
    else:raise AssertionError('truncated RGB565 accepted')
    evidence=REPO/'docs/validation/picture-p20-combined-20261020/interface-checks.json'
    evidence.write_text(json.dumps({'checks':records,'truncated_raw_rejected':True,'production_ready':False},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('P20_INTERFACE_CHECKS_PASS both backends known uncertainties and padded RGB565',flush=True)
if __name__=='__main__':main()
