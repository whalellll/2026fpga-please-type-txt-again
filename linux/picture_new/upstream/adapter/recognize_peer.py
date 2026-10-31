"""PC assisted experimental worker; all THREE original golden models run.

This is an intermediate backend. It is deliberately distinct from RV32 driver
inference and emits no usable packet for any golden strict-interface rejection.
Camera inputs/results belong under build/, never the tracked evidence tree.
"""
import argparse,hashlib,json,math,sys,zlib
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
G=HERE.parent/'vision-model-20261020/golden'
sys.path[:0]=[str(G/'software'),str(G/'quantization')]
def packet(request,raw,result,backend):
    fields=request.split()
    if len(fields)!=5 or fields[0]!='XQ_MODEL_REQUEST_V1' or fields[4]!=backend:
        raise ValueError('request_backend_or_format')
    token,fid,crc=int(fields[1]),int(fields[2]),int(fields[3],16)
    if len(raw)!=1280*720*2 or zlib.crc32(raw)!=crc:raise ValueError('capture_size_or_CRC')
    prefix=f'XQ_MODEL_RESULT_V1 {token} {fid} {crc:08x} {backend}'
    if (result.get('status')!='candidate_board' or result.get('can_use_as_candidate') is not True or
        not result.get('board_placement_fen') or result.get('issues') or
        result.get('production_ready') is not False or result.get('automatic_action_allowed') is not False):
        return prefix+' 1 0\n',False
    pieces=result['pieces']
    if not 2<=len(pieces)<=32: return prefix+' 1 0\n',False
    lines=[prefix+f' 0 {len(pieces)}',result['board_placement_fen']+' w - - 0 1']
    for p in pieces:
        grid=p['grid']
        if not grid['inside'] or p['assignment_uncertain']:raise ValueError('unsafe_grid')
        box=p['bbox_original'];score=math.floor(float(p['score'])*1000)
        if score<50 or not all(math.isfinite(v) for v in box):raise ValueError('unsafe_piece')
        lines.append(f"{p['class_id']} {grid['file']} {9-grid['rank']} {score} "+' '.join(f'{v:.9g}' for v in box))
    H=result['geometry']['H_grid_to_original']
    for f,r in ((0,9),(8,9),(8,0),(0,0)):
        d=H[2][0]*f+H[2][1]*r+H[2][2]
        lines.append(' '.join(f'{(H[i][0]*f+H[i][1]*r+H[i][2])/d:.17g}' for i in (0,1)))
    return '\n'.join(lines)+'\n',True
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--request',type=Path,required=True);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--result-json',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or a.result_json.exists():p.error('choose fresh outputs')
    raw=a.input.read_bytes();request=a.request.read_text()
    fields=request.split()
    if len(fields)!=5 or fields[4]!='pc-quantized-mac' or zlib.crc32(raw)!=int(fields[3],16):
        raise ValueError('invalid_capture_request')
    from integer_ops import load_integer_runtime
    model=load_integer_runtime(G/'software',G/'quantization/candidate_v1')
    result=model.predict(a.input,pixel_format='rgb565',width=1280,height=720,byte_order='little',stride_bytes=2560)
    result['delivery_backend']='PC_ASSISTED_quantized-mac';result['full_integer_pipeline']=False
    text,usable=packet(request,raw,result,'pc-quantized-mac')
    a.output.write_text(text);a.result_json.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(status=result['status'],strict_packet_usable=usable,production_ready=False,
                         backend='PC_ASSISTED_quantized-mac',models=list(result['models']),
                         input_sha256=hashlib.sha256(raw).hexdigest(),packet_sha256=hashlib.sha256(text.encode()).hexdigest())))
if __name__=='__main__':main()
