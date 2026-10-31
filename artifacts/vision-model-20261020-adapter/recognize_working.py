"""PC CLI for the selected E FP32 baseline and explicit historical rollbacks."""
import argparse
import json
import sys
from pathlib import Path


def main():
    sys.dont_write_bytecode = True
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--profile',choices=['working-r14','rollback-v3d','working-r12','rollback-v2-band','working-r09','frozen640-v1'])
    p.add_argument('--backend', choices=['quantized-mac', 'fp32'])
    p.add_argument('--classifier',choices=['v1','v2-band','v3c','v3d','v3d-QAT'])
    p.add_argument('--detector',choices=['det416-r09','det416mix-r11','frozen640'])
    p.add_argument('--width', type=int)
    p.add_argument('--height', type=int)
    p.add_argument('--byte-order', choices=['little', 'big'], default='little')
    p.add_argument('--stride-bytes', type=int)
    a = p.parse_args()
    if a.output.exists():
        p.error('choose a fresh output path')
    if (a.width is None) != (a.height is None):
        p.error('raw input requires both width and height')
    from r12_reference import resolve_selection,load_model,annotate
    selection=resolve_selection(a.profile,a.backend,a.classifier,a.detector)
    options = {} if a.width is None else dict(pixel_format='rgb565', width=a.width, height=a.height,
                 byte_order=a.byte_order, stride_bytes=a.stride_bytes)
    result = annotate(load_model(selection).predict(a.input, **options),selection)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
    print(json.dumps(dict(status=result['status'], production_ready=False, profile=result['working_profile'])))


if __name__ == '__main__':
    main()
