"""Integer convolution mapped to the existing dense ABI, without RTL changes.

This experiment verifies layer arithmetic and packing. It does not implement
whole-model calibration, SiLU or the complete YOLO graph runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import time
import zlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ConvSpec:
    width: int
    height: int
    cin: int
    cout: int
    kernel: int
    stride: int
    pad: int

    def __post_init__(self):
        values = (self.width, self.height, self.cin, self.cout, self.kernel, self.stride, self.pad)
        if (any(type(v) is not int for v in values) or
                not 1 <= self.width <= 320 or not 1 <= self.height <= 320 or
                not 1 <= self.cin <= 512 or not 1 <= self.cout <= 512 or
                self.kernel not in (1, 3, 6) or self.stride not in (1, 2) or
                not 0 <= self.pad < self.kernel or self.ow < 1 or self.oh < 1):
            raise ValueError('unsupported or invalid convolution geometry')

    @property
    def ow(self): return (self.width + 2*self.pad-self.kernel)//self.stride+1
    @property
    def oh(self): return (self.height + 2*self.pad-self.kernel)//self.stride+1
    @property
    def k(self): return self.cin*self.kernel*self.kernel


@dataclass(frozen=True)
class DenseJob:
    p0: int
    co0: int
    k0: int
    pixels: int
    cout: int
    k: int
    inputs: bytes
    weights: bytes


def signed(value): return value if value < 128 else value-256


def requant(value, shift):
    magnitude = (abs(value) + ((1 << (shift-1)) if shift else 0)) >> shift
    return max(-128, min(127, -magnitude if value < 0 else magnitude))


def validate_buffers(spec, inputs, weights):
    if len(inputs) != spec.width*spec.height*spec.cin or len(weights) != spec.cout*spec.k:
        raise ValueError('NHWC input or OIHW weight length mismatch')


def input_scalar(spec, inputs, position, k):
    ci, kernel_offset = divmod(k, spec.kernel*spec.kernel)
    ky, kx = divmod(kernel_offset, spec.kernel)
    oy, ox = divmod(position, spec.ow)
    iy, ix = oy*spec.stride-spec.pad+ky, ox*spec.stride-spec.pad+kx
    if iy < 0 or ix < 0 or iy >= spec.height or ix >= spec.width:
        return 0
    return signed(inputs[(iy*spec.width+ix)*spec.cin+ci])


def make_jobs(spec, inputs, weights):
    validate_buffers(spec, inputs, weights)
    for p0 in range(0, spec.oh*spec.ow, 16):
        for co0 in range(0, spec.cout, 256):
            for k0 in range(0, spec.k, 256):
                pixels, cout, k = min(16, spec.oh*spec.ow-p0), min(256, spec.cout-co0), min(256, spec.k-k0)
                ci_tiles = (k+3)//4
                a = bytearray(pixels*ci_tiles*8)
                b = bytearray(((cout+31)//32)*ci_tiles*128)
                for p in range(pixels):
                    for ki in range(k):
                        struct.pack_into('<h', a, (p*ci_tiles*4+ki)*2, input_scalar(spec, inputs, p0+p, k0+ki))
                for co in range(cout):
                    for ki in range(k):
                        address = ((co//32*ci_tiles+ki//4)*128 + (co%32//2*4+ki%4)*2+co%2)
                        b[address] = weights[(co0+co)*spec.k+k0+ki]
                yield DenseJob(p0, co0, k0, pixels, cout, k, bytes(a), bytes(b))


def dense_reference(spec, inputs, weights, bias):
    validate_buffers(spec, inputs, weights)
    return [bias[co]+sum(input_scalar(spec, inputs, p, k)*signed(weights[co*spec.k+k])
                        for k in range(spec.k))
            for p in range(spec.oh*spec.ow) for co in range(spec.cout)]


def run_tiled(spec, inputs, weights, bias, shift, submit):
    if (len(bias) != spec.cout or any(not -(1 << 31) <= v < (1 << 31) for v in bias)
            or not 0 <= shift <= 30):
        raise ValueError('invalid INT32 bias or shift')
    accum = [0]*(spec.oh*spec.ow*spec.cout)
    count, packed_crc = 0, 0
    for job in make_jobs(spec, inputs, weights):
        partials = submit(job)  # Errors propagate; there is no fallback.
        if len(partials) != job.pixels*job.cout:
            raise ValueError('backend returned wrong result length')
        for p in range(job.pixels):
            for co in range(job.cout):
                value = partials[p*job.cout+co]
                if not -(1 << 31) <= value < (1 << 31):
                    raise ValueError('backend INT32 overflow')
                accum[(job.p0+p)*spec.cout+job.co0+co] += value
        packed_crc = zlib.crc32(job.inputs, packed_crc)
        packed_crc = zlib.crc32(job.weights, packed_crc)
        count += 1
    accum = [v+bias[i % spec.cout] for i, v in enumerate(accum)]
    if any(not -(1 << 31) <= v < (1 << 31) for v in accum):
        raise ValueError('final INT32 overflow')
    return {'int32': accum, 's8': bytes(requant(v, shift) & 255 for v in accum),
            'jobs': count, 'packed_crc32': '%08x' % packed_crc}


def write_cases(cases, path):
    payload = bytearray()
    for case in cases:
        spec = case['spec']
        validate_buffers(spec, case['input'], case['weights'])
        if len(case['bias']) != spec.cout or len(case['expected']) != spec.oh*spec.ow*spec.cout:
            raise ValueError('bias or golden length mismatch')
        name = case['name'].encode('ascii')
        if len(name) >= 32 or not 0 <= case['shift'] <= 30:
            raise ValueError('case name or shift invalid')
        payload += name.ljust(32, b'\0')
        payload += struct.pack('<8I', spec.width, spec.height, spec.cin, spec.cout,
                               spec.kernel, spec.stride, spec.pad, case['shift'])
        payload += struct.pack('<%di' % spec.cout, *case['bias'])
        payload += case['input']+case['weights']
        payload += struct.pack('<%di' % len(case['expected']), *case['expected'])
        payload += bytes(requant(v, case['shift']) & 255 for v in case['expected'])
    if not 1 <= len(cases) <= 16 or len(payload) > 16*1024*1024:
        raise ValueError('probe file size or case count exceeds limit')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack('<5I', 0x31544344, 1, len(cases), len(payload), zlib.crc32(payload))+payload)


def read_cases(path):
    data = path.read_bytes()
    if not 20 <= len(data) <= 16*1024*1024+20:
        raise ValueError('invalid probe length')
    magic, version, count, length, crc = struct.unpack_from('<5I', data)
    if magic != 0x31544344 or version != 1 or not 1 <= count <= 16 or length != len(data)-20 or zlib.crc32(data[20:]) != crc:
        raise ValueError('invalid probe header or CRC')
    cursor, cases = 20, []
    for _ in range(count):
        if len(data)-cursor < 64: raise ValueError('truncated case')
        name = data[cursor:cursor+32].split(b'\0', 1)[0].decode('ascii')
        fields = struct.unpack_from('<8I', data, cursor+32)
        spec, shift = ConvSpec(*fields[:7]), fields[7]
        if shift > 30: raise ValueError('invalid shift')
        cursor += 64
        n, wn, on = spec.width*spec.height*spec.cin, spec.cout*spec.k, spec.oh*spec.ow*spec.cout
        needed = spec.cout*4+n+wn+on*5
        if needed > len(data)-cursor: raise ValueError('truncated tensors')
        bias = list(struct.unpack_from('<%di' % spec.cout, data, cursor)); cursor += spec.cout*4
        inputs = data[cursor:cursor+n]; cursor += n
        weights = data[cursor:cursor+wn]; cursor += wn
        golden = list(struct.unpack_from('<%di' % on, data, cursor)); cursor += on*4
        golden8 = data[cursor:cursor+on]; cursor += on
        if golden8 != bytes(requant(v, shift) & 255 for v in golden): raise ValueError('inconsistent requant golden')
        cases.append({'name': name, 'spec': spec, 'shift': shift, 'bias': bias,
                      'input': inputs, 'weights': weights, 'expected': golden})
    if cursor != len(data): raise ValueError('unexpected trailing payload')
    return cases


def export_checkpoint(model_path, image_path, output):
    import cv2
    import numpy as np
    import torch
    from yolov5.utils.augmentations import letterbox

    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if digest != '463b20a814b07ac5aa7da3f20a07a0202368cc3c1716ca52efa0555927958c9a':
        raise ValueError('experiment requires the previously verified local trained checkpoint')
    checkpoint = torch.load(model_path, map_location='cpu', weights_only=False)
    model = (checkpoint.get('ema') or checkpoint['model']).float().eval()
    selections = [('model.0.conv', 16), ('model.1.conv', 9), ('model.7.conv', 8),
                  ('model.9.cv2.conv', 5), ('model.24.m.0', 5), ('model.24.m.2', 5)]
    modules = dict(model.named_modules())
    captured = {}
    hooks = [modules[name].register_forward_pre_hook(
        lambda module, args, name=name: captured.__setitem__(name, args[0].detach().clone()))
        for name, _ in selections]
    bgr = cv2.imread(str(image_path))
    if bgr is None: raise ValueError('cannot read image')
    rgb = letterbox(bgr, (320, 320), auto=False)[0][:, :, ::-1].copy()
    with torch.inference_mode(): model(torch.from_numpy(rgb.transpose(2, 0, 1)).unsqueeze(0).float()/255.)
    for hook in hooks: hook.remove()
    cases, records = [], []
    def round_away(values): return np.sign(values)*np.floor(np.abs(values)+.5)
    for name, size in selections:
        conv = modules[name]
        h, w = captured[name].shape[2:]
        size = min(size, h, w)
        y, x = (h-size)//2, (w-size)//2
        sample = captured[name][0, :, y:y+size, x:x+size].numpy()
        parent = modules[name.rsplit('.', 1)[0]]
        weight = conv.weight.detach().numpy().copy()
        bias = np.zeros(conv.out_channels, dtype=np.float32) if conv.bias is None else conv.bias.detach().numpy().copy()
        if hasattr(parent, 'bn'):
            bn = parent.bn
            multiplier = bn.weight.detach().numpy()/np.sqrt(bn.running_var.detach().numpy()+bn.eps)
            weight *= multiplier[:, None, None, None]
            bias = (bias-bn.running_mean.detach().numpy())*multiplier+bn.bias.detach().numpy()
        input_scale = max(float(np.max(np.abs(sample))), 1.e-12)/127.
        weight_scale = np.maximum(np.max(np.abs(weight), axis=(1, 2, 3)), 1.e-12)/127.
        qi = np.clip(round_away(sample/input_scale), -127, 127).astype(np.int8)
        qw = np.clip(round_away(weight/weight_scale[:, None, None, None]), -127, 127).astype(np.int8)
        qb = round_away(bias/(input_scale*weight_scale)).astype(np.int64)
        if np.any(qb < -2**31) or np.any(qb >= 2**31): raise ValueError('bias overflow')
        spec = ConvSpec(size, size, conv.in_channels, conv.out_channels, conv.kernel_size[0], conv.stride[0], conv.padding[0])
        case = {'name': name, 'spec': spec, 'input': qi.transpose(1, 2, 0).tobytes(),
                'weights': qw.tobytes(), 'bias': qb.tolist(), 'shift': 10}
        # Independent direct conv oracle uses no packed matrices or segmented sum.
        started = time.perf_counter()
        case['expected'] = dense_reference(spec, case['input'], case['weights'], case['bias'])
        elapsed = (time.perf_counter()-started)*1000
        cases.append(case)
        jobs = list(make_jobs(spec, case['input'], case['weights']))
        crc = 0
        for job in jobs:
            crc = zlib.crc32(job.inputs, crc); crc = zlib.crc32(job.weights, crc)
        records.append({'name': name, 'spec': vars(spec), 'crop_xy': [x, y], 'jobs': len(jobs),
                        'input_scale': input_scale, 'weight_scales': weight_scale.tolist(),
                        'shift': 10, 'packed_crc32': '%08x' % crc, 'reference_ms': elapsed,
                        'int32_elements': len(case['expected'])})
    output.mkdir(parents=True, exist_ok=True)
    write_cases(cases, output/'cases.bin')
    identity = {'model_sha256': digest, 'image_sha256': hashlib.sha256(image_path.read_bytes()).hexdigest(),
                'cases_sha256': hashlib.sha256((output/'cases.bin').read_bytes()).hexdigest(),
                'purpose': 'layer arithmetic probe, not full-model calibrated quantization',
                'input': 'NHWC S8, symmetric zero point 0', 'weights': 'OIHW S8, fused BN where present',
                'rounding': 'half away from zero', 'partial_output': 'INT32, zero bias, zero shift, no activation',
                'final': 'INT32 bias once, shift=10 once, S8 saturation; SiLU excluded',
                'full_model_acceptance': False, 'board_acceptance': False, 'cases': records}
    (output/'manifest.json').write_text(json.dumps(identity, indent=2)+'\n', encoding='utf-8')
    return cases, identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    _, identity = export_checkpoint(args.model.resolve(), args.image.resolve(), args.output.resolve())
    print('DENSE_TILED_VECTOR_EXPORT_PASS cases=%d jobs=%d model=%s' %
          (len(identity['cases']), sum(c['jobs'] for c in identity['cases']), identity['model_sha256']))


if __name__ == '__main__': main()
