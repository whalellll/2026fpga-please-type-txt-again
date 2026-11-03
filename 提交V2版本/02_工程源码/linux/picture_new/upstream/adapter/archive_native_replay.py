"""Compare the completed native-device offline replay with the frozen C oracle.

FEN/piece placement conformance is distinct from bit-exact MAC verification.
Postprocessing floating differences are reported, not hidden as integer proof.
"""
import hashlib,json,re,math
from datetime import datetime,timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
OUT=REPO/'docs/validation/picture-p21-runtime-20261020'
BUILD=REPO/'build/picture-p21-native'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def packet(p):
    lines=p.read_text().splitlines();head=lines[0].split()
    assert len(head)==7 and head[0]=='XQ_MODEL_RESULT_V1'
    n=int(head[6]);assert int(head[5])==0 and 2<=n<=32 and len(lines)==2+n+4
    pieces={}
    for line in lines[2:2+n]:
        v=line.split();assert len(v)==8
        key=tuple(map(int,v[:3]));assert key not in pieces
        box=tuple(map(float,v[4:]));score=int(v[3])
        assert 0<=key[0]<14 and 0<=key[1]<9 and 0<=key[2]<10 and 50<=score<=1000
        assert all(map(math.isfinite,box)) and 0<=box[0]<box[2]<=1280 and 0<=box[1]<box[3]<=720
        pieces[key]=(score,box)
    corners=[list(map(float,s.split())) for s in lines[2+n:]]
    assert all(len(q)==2 and all(map(math.isfinite,q)) for q in corners)
    return dict(header=head,fen=lines[1],pieces=pieces,corners=corners)
actual_path=OUT/'native-device-replay.packet.txt';log_path=OUT/'native-device-replay.log.txt'
reference_path=BUILD/'host-r04/sample2.packet'
actual,reference=packet(actual_path),packet(reference_path)
assert actual['header'][1:4]==reference['header'][1:4]
assert actual['header'][4]=='rv32-driver-quantized-mac'
assert actual['fen']==reference['fen'] and set(actual['pieces'])==set(reference['pieces'])
matches=re.findall(r'XQ_NATIVE_RECOGNITION (.+)',log_path.read_text());assert len(matches)==1
stats={key:int(value) for key,value in (word.split('=') for word in matches[0].split())}
assert stats['status']==0 and stats['models_loaded']==3 and stats['executed_mask']==7 and stats['cpu_reference']==0
assert stats['jobs']>0 and stats['cycles']>0
record=dict(schema_version=1,status='PASS',recorded_utc=datetime.now(timezone.utc).isoformat(),
    scope='Real FPGA/RV32 RGB565 offline functional replay; transformed training IMG00908, NOT live camera/M0/game acceptance',
    reference='PC C CPU_REFERENCE host-r04; original Torch backend distinction remains explicit',
    frame_source='IMG00908 RGB565, nearest sampling x2 and replication; input remains 1280x720 tight little endian',
    raw_input_sha256='57f756dd81126689d235686d92c070b63f50808003ebc3d393b9ec56435de6fd',
    pieces=len(actual['pieces']),fen=actual['fen'],fen_equal=True,piece_square_class_sets_equal=True,
    confidence_max_abs_permille=max(abs(v[0]-reference['pieces'][k][0]) for k,v in actual['pieces'].items()),
    boxes_max_abs_px=max(abs(x-y) for k,v in actual['pieces'].items() for x,y in zip(v[1],reference['pieces'][k][1])),
    corners_max_abs_px=max(abs(x-y) for a,b in zip(actual['corners'],reference['corners']) for x,y in zip(a,b)),
    exact_postprocessing_packet_values_equal=(actual['pieces']==reference['pieces'] and actual['corners']==reference['corners']),
    stats=stats,latency_5s_gate_pass=stats['total_ms']<=5000,
    timing_scope='RGB565 conversion through FEN; excludes model cold loading, capture, GUI display and voice',
    m0_accepted=False,independent_test=False,live_camera_positive_acceptance=False,
    files={str(p.relative_to(REPO)):sha(p) for p in (actual_path,log_path,reference_path,BUILD/'rv32-r05/xq-native-worker')})
dest=OUT/'native-device-replay.json';assert not dest.exists()
dest.write_text(json.dumps(record,indent=2)+'\n')
print('NATIVE_DEVICE_REPLAY_PASS models=3 backend=driver pieces='+str(record['pieces'])+' total_ms='+str(stats['total_ms']))
