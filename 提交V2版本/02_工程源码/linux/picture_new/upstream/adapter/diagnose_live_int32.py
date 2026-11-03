"""Explicit INT32 diagnostic on the same live image, not the original backend."""
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
REPO=Path(__file__).resolve().parents[2]
G=REPO/'artifacts/vision-model-20261020/golden'
LIVE=REPO/'build/picture-p21-native/live-sd-r01'
sys.path[:0]=[str(G/'software'),str(G/'quantization')]
import torch
import integer_ops

assert not (LIVE/'explicit-int32-reference.json').exists()
integer_ops.exact_mm=lambda a,b:a.to(torch.int32)@b.to(torch.int32)
model=integer_ops.load_integer_runtime(G/'software',G/'quantization/candidate_v1')
result=model.predict(LIVE/'frame.rgb565',pixel_format='rgb565',width=1280,height=720,byte_order='little',stride_bytes=2560)
result['diagnostic_backend']='EXPLICIT_INT32_ORACLE_NOT_ORIGINAL_TORCH_INT_MM'
(LIVE/'explicit-int32-reference.json').write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
header=(LIVE/'cpu-int32-reference.packet').read_text().splitlines()[0].split()
assert header[4]=='cpu-int32-reference'
summary=dict(diagnostic_backend=result['diagnostic_backend'],status=result['status'],
             strict_usable=result['can_use_as_candidate'],piece_count=len(result.get('pieces',[])),
             c_status=int(header[5]),strict_state_equal=result['can_use_as_candidate']==(header[5]=='0'),
             issues=result.get('issues',[]))
(LIVE/'explicit-int32-comparison.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(summary,ensure_ascii=False))
