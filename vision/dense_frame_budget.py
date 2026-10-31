"""Account for all trained convolutions using the existing dense ABI.

Shape measurements are isolated integer DMA jobs, not model inference. The
reported full-frame sum excludes CPU packing, ioctls, nonlinear operators,
camera and contention; it must never be presented as a board frame rate.
"""
import argparse
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

from dense_tiled_conv import ConvSpec, write_cases


def chunks(size, limit):
    return [(min(limit,size-start),1) for start in range(0,size,limit)]


def traffic(pixels, k, cout):
    ci_tiles=(k+3)//4
    return pixels*ci_tiles*8+((cout+31)//32)*ci_tiles*128, pixels*cout*4


def frame_budget(graph, clock_mhz=49.5):
    identity=graph.get('model_sha256','')
    if not re.fullmatch(r'[0-9a-f]{64}',identity) or clock_mhz<=0:
        raise ValueError('invalid model identity or clock')
    shapes=Counter()
    layers=[]
    names=set()
    silu_elements=0
    for item in graph['layers']:
        if item['operator']=='SiLU': silu_elements+=math.prod(item['output_shape'])
        if item['operator']!='Conv2d': continue
        name=item['name']
        if name in names: raise ValueError('duplicate convolution name')
        names.add(name)
        if item['groups']!=1 or item['input_shape'][0]!=1 or item['output_shape'][0]!=1:
            raise ValueError('only dense batch-one convolutions are supported')
        if any(len(item[key])!=2 or item[key][0]!=item[key][1] for key in ('kernel','stride','padding')):
            raise ValueError('asymmetric convolution geometry')
        _,cin,h,w=item['input_shape']
        _,cout,oh,ow=item['output_shape']
        spec=ConvSpec(w,h,cin,cout,item['kernel'][0],item['stride'][0],item['padding'][0])
        if (spec.oh,spec.ow)!=(oh,ow) or item['weight_shape']!=[cout,cin,spec.kernel,spec.kernel]:
            raise ValueError('inconsistent convolution shapes')
        local=Counter((p,k,co) for p,_ in chunks(oh*ow,16)
                      for k,_ in chunks(spec.k,256) for co,_ in chunks(cout,256))
        shapes.update(local)
        read=sum(n*traffic(*shape)[0] for shape,n in local.items())
        write=sum(n*traffic(*shape)[1] for shape,n in local.items())
        weights_once=sum(((co+31)//32)*((k+3)//4)*128 for co,_ in chunks(cout,256) for k,_ in chunks(spec.k,256))
        layers.append({'name':name, 'pixels':oh*ow,'cin':cin,'cout':cout,'k':spec.k,
                       'macs':oh*ow*cout*spec.k,'jobs':sum(local.values()),
                       'read_bytes':read,'write_bytes':write,
                       'packed_weights_once_bytes':weights_once})
    if not layers: raise ValueError('graph has no convolution')
    macs=sum(x['macs'] for x in layers)
    read=sum(x['read_bytes'] for x in layers)
    write=sum(x['write_bytes'] for x in layers)
    compute_ms=macs/128/(clock_mhz*1000)
    bus_ms=(read+write)/4/(clock_mhz*1000)
    return {'model_sha256':identity,'clock_mhz':clock_mhz,'conv_layers':len(layers),
            'macs':macs,'jobs':sum(shapes.values()),'read_bytes':read,'write_bytes':write,
            'silu_elements':silu_elements,'compute_lower_bound_ms':compute_ms,
            'dma_bus_lower_bound_ms':bus_ms,
            'serial_conv_lower_bound_ms':compute_ms+bus_ms,
            'required_effective_macs_per_cycle_30fps':macs*30/(clock_mhz*1e6),
            'packed_weights_once_bytes':sum(x['packed_weights_once_bytes'] for x in layers),
            'job_shapes':[{'pixels':p,'k':k,'cout':co,'count':n,
                           'read_bytes':traffic(p,k,co)[0],'write_bytes':traffic(p,k,co)[1]}
                          for (p,k,co),n in sorted(shapes.items())],
            'layers':layers,'device_model_ready':False,'board_fps':None}


def measured_budget(budget, log):
    pattern=r'DENSE_TILED_RTL_JOB_PASS index=\d+ pixels=(\d+) k=(\d+) cout=(\d+) cycles=(\d+) read_bytes=(\d+) write_bytes=(\d+)'
    measured={}
    for fields in re.findall(pattern,log):
        p,k,co,cycles,read,write=map(int,fields)
        shape=(p,k,co)
        if shape in measured or (read,write)!=traffic(*shape) or cycles<=0:
            raise ValueError('duplicate shape, wrong traffic or invalid cycle evidence')
        measured[shape]=cycles
    expected={(x['pixels'],x['k'],x['cout']) for x in budget['job_shapes']}
    if set(measured)!=expected: raise ValueError('cycle evidence must cover every job shape exactly once')
    per_layer=[]
    # Use the layer shapes independently of the global histogram.
    for layer in budget['layers']:
        cycles=sum(measured[(p,k,co)] for p,_ in chunks(layer['pixels'],16)
                   for k,_ in chunks(layer['k'],256) for co,_ in chunks(layer['cout'],256))
        per_layer.append({'name':layer['name'],'conv_dma_cycles':cycles,
                          'shape_sum_ms':cycles/(budget['clock_mhz']*1000)})
    cycles=sum(x['conv_dma_cycles'] for x in per_layer)
    return {'conv_dma_cycles':cycles,'conv_dma_shape_sum_ms':cycles/(budget['clock_mhz']*1000),
            'model_execution':False,'board_fps':None,'layers':per_layer,
            'excluded':['CPU im2col/packing/copy','ioctl/lock wait','INT32 partial merging/requantization',
                        'SiLU/residual/Concat/MaxPool/Upsample','Detect/NMS/FEN',
                        'camera/HDMI/CPU/Pikafish contention']}


def write_shape_probes(budget, output):
    import numpy as np
    rng=np.random.default_rng(20261005)
    shapes=budget['job_shapes']
    directories=[]
    # DCT1 and the strict device probe intentionally allow at most 16 cases.
    for group in range(0,len(shapes),16):
        cases=[]
        for shape in shapes[group:group+16]:
            p,k,co=shape['pixels'],shape['k'],shape['cout']
            x=rng.integers(-128,128,size=(p,k),dtype=np.int16).astype(np.int8)
            w=rng.integers(-128,128,size=(co,k),dtype=np.int16).astype(np.int8)
            golden=x.astype(np.int64) @ w.astype(np.int64).T
            cases.append({'name':'p%d_k%d_co%d'%(p,k,co), 'spec':ConvSpec(p,1,k,co,1,1,0),
                          'shift':10,'bias':[0]*co,'input':x.tobytes(),
                          'weights':w.tobytes(),'expected':golden.reshape(-1).tolist()})
        directory=output/('shape_probes_%d'%(group//16))
        binary=directory/'cases.bin'
        write_cases(cases,binary)
        manifest={'model_sha256':budget['model_sha256'],
                  'cases_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
                  'synthetic_shape_probe':True,'complete_model_inference':False,
                  'shapes':shapes[group:group+16]}
        (directory/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
        directories.append(str(directory))
    return directories


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graph',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--rtl-log',type=Path,action='append',default=[])
    parser.add_argument('--write-probes',action='store_true')
    args=parser.parse_args()
    budget=frame_budget(json.loads(args.graph.read_text(encoding='utf-8')))
    budget['graph_sha256']=hashlib.sha256(args.graph.read_bytes()).hexdigest()
    if args.write_probes: budget['probe_directories']=write_shape_probes(budget,args.output.parent)
    if args.rtl_log:
        budget['shape_measurements']=measured_budget(budget,'\n'.join(p.read_text(encoding='utf-8') for p in args.rtl_log))
        budget['cycle_evidence_sha256']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in args.rtl_log}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(budget,indent=2)+'\n',encoding='utf-8')
    summary={key:budget[key] for key in ('conv_layers','macs','jobs','read_bytes','write_bytes','serial_conv_lower_bound_ms','board_fps')}
    if 'shape_measurements' in budget: summary['conv_dma_shape_sum_ms']=budget['shape_measurements']['conv_dma_shape_sum_ms']
    print(json.dumps(summary))


if __name__=='__main__': main()
