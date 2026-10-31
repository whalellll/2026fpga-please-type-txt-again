"""Training-image RGB565 replay through complete C pipeline and r08 exact INT64 oracle.

This is engineering conformance, never new independent model acceptance.
"""
import argparse,json,subprocess,sys,zlib,time
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1];G=HERE.parent/'vision-model-20261020/golden'
sys.path[:0]=[str(G/'software'),str(G/'quantization')]
import cv2,numpy as np,torch,integer_ops
p=argparse.ArgumentParser();p.add_argument('--models',type=Path,required=True);p.add_argument('--worker',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--range',nargs=2,type=int,metavar=('FIRST','LAST'));p.add_argument('--continue-on-mismatch',action='store_true')
p.add_argument('--checks',action='store_true')
a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
from pc_exact import install
install()
model=integer_ops.load_integer_runtime(G/'software',G/'quantization/candidate_v1')
identity=json.loads((REPO/'docs/validation/picture-p20-combined-20261020/fp32/inputs.json').read_text())
dataset=Path(identity['files']['IMG00908/image']['path']).parent
replays=json.loads((REPO/'docs/validation/picture-p20-combined-20261020/quantized-mac/end_to_end_per_frame.json').read_text())
usable=next(row['frame'] for row in replays if row['can_use_as_candidate'])
names=[usable,'IMG00908','IMG00862'] if not a.range else [f'IMG{i:05d}' for i in range(a.range[0],a.range[1]+1)]
reports=[]
for i,name in enumerate(names):
    image=cv2.imread(str(dataset/(name+'.PNG')));assert image is not None
    words=((image[:,:,2].astype(np.uint16)>>3)<<11)|((image[:,:,1].astype(np.uint16)>>2)<<5)|(image[:,:,0].astype(np.uint16)>>3)
    raw=words.astype('<u2').tobytes();rawpath=a.out/(name+'.rgb565');rawpath.write_bytes(raw)
    request=a.out/(name+'.request');packet=a.out/(name+'.packet');request.write_text(f'XQ_MODEL_REQUEST_V1 {i+1} {i+1} {zlib.crc32(raw):08x} pc-quantized-mac\n')
    start=time.monotonic();reference=model.predict(rawpath,pixel_format='rgb565',width=1280,height=720,byte_order='little',stride_bytes=2560)
    command=[str(a.worker),'--models',str(a.models),'--cpu-reference','--request',str(request),'--input',str(rawpath),'--output',str(packet)]
    if a.checks:command+=['--checks',str(a.out/(name+'.checks'))]
    run=subprocess.run(command,text=True,capture_output=True,timeout=120)
    (a.out/(name+'.native.log')).write_text(run.stdout+run.stderr)
    (a.out/(name+'.reference.json')).write_text(json.dumps(reference,indent=2)+'\n')
    assert packet.is_file(),(name,run.returncode,run.stdout,run.stderr)
    lines=packet.read_text().splitlines();status=int(lines[0].split()[5]);fen=lines[1].split(' ')[0] if status==0 else None
    expected=reference['board_placement_fen']
    row=dict(frame=name,reference_status=reference['status'],reference_usable=reference['can_use_as_candidate'],native_status=status,
             reference_fen=expected,native_fen=fen,fen_equal=fen==expected,elapsed_s=time.monotonic()-start,native_log=run.stdout)
    reports.append(row);print('NATIVE_PIPELINE_FRAME',json.dumps(row),flush=True)
    (a.out/'progress.json').write_text(json.dumps(reports,indent=2)+'\n')
    row['conformant']=row['fen_equal'] and ((status==0)==reference['can_use_as_candidate'])
    if not a.continue_on_mismatch:assert row['conformant'],row
(a.out/'result.json').write_text(json.dumps(dict(status='PASS' if all(r['conformant'] for r in reports) else 'FAIL',scope='RGB565 replay, PC C CPU_REFERENCE vs adapter r08 exact-int64 Python; not independent or board acceptance',
   frames=reports,integer_oracle='r08-exact-int64; torch._int_mm is never golden'),indent=2)+'\n')
