"""Explicit FP32 candidate switch; the working quantized v2-band path stays default."""
import hashlib
import json
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]

def load_reference(backend='quantized-mac',classifier='v2-band',detector='det416-r09'):
    if classifier=='v2-band' and detector=='det416-r09':
        from r09_reference import load_working_model
        return load_working_model(backend)
    if backend!='fp32':
        raise ValueError('r11 has FP32 checkpoints only; no r11 INT8 payload delivered. Use explicit --backend fp32; quantized main remains v2-band.')
    if classifier!='v3c':raise ValueError('alternate detectors currently require explicit v3c FP32 candidate profile')
    reg=json.loads((HERE/'candidates/classifier-v3c-r11/registration.json').read_text(encoding='utf-8'))
    profile=reg['fp32_profiles'][detector];root=REPO/profile['root']
    for key,item in profile['models'].items():
        actual=hashlib.sha256((root/item['path']).read_bytes()).hexdigest()
        if actual!=item['sha256']:raise ValueError('candidate model identity mismatch: '+key)
    sys.path.insert(0,str(root))
    from recognizer import Recognizer
    model=Recognizer(root,device='cpu',precision='fp32')
    # Explicit sizing also handles Python module caching when comparing
    # several profiles in one process. Do not depend on a copied default.
    model.pipeline.detector.input_size=profile['detector_input']
    from r09_reference import configure
    return configure(model,True,'B')
