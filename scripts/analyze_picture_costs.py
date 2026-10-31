"""Read frozen graph metadata; no inference, calibration or model modification."""
from pathlib import Path
import argparse
from collections import Counter
import hashlib
import json
import math
import struct
import zlib
from picture_workspace import ROOT,workspace_path

OPS={1:'conv',3:'sigmoid',4:'maxpool',5:'nearest',6:'bilinear',7:'concat',8:'add',9:'gap',10:'identity',11:'relu'}
XQI_SHA='d72d039041b41310f037344772eb75ce895ec6fe678bbb31ed547a7ad7453942'


def read_graph(path,expected):
    data=path.read_bytes();assert hashlib.sha256(data).hexdigest()==expected
    assert data[:8] in [b'XQGRPH1\0',b'XQINT81\0']
    header=struct.unpack_from('<10I',data,8);body=data[48:]
    assert len(body)==header[8] and zlib.crc32(body)==header[9]
    descriptor=16 if data[:8]==b'XQGRPH1\0' and header[0]==2 else 0
    nodes=[list(struct.unpack_from('<32i',body,descriptor+i*128)) for i in range(header[2])]
    return header,nodes


def tile_plan(n,parent,side=640,scale=1,output_s8=False,adaptive_tail=False):
    ci,ih,iw=(parent[1],int(parent[2]*scale),int(parent[3]*scale)) if parent else (3,side,side)
    co,oh,ow=n[1],int(n[2]*scale),int(n[3]*scale)
    kernel,stride,pad=n[10],n[12],n[14];k=ci*kernel*kernel;groups=(co+7)//8
    def layout(w,h,p):
        outw=(w+2*p-kernel)//stride+1;outh=(h+2*p-kernel)//stride+1
        input_bytes=w*h*((ci+3)&~3)
        weights=groups*k*8;params=groups*8*12
        lut=65536 if n[24] else 0
        output=outw*outh*co*(1 if output_s8 and n[27]==8 else 2)
        scratch=input_bytes+weights+params+lut+output
        work=outw*outh*co*(k+512)
        valid=0<w<=640 and 0<h<=640 and scratch<=0x100000 and work<=67108864
        return valid,scratch,work,input_bytes
    assert (ih+2*pad-kernel)//stride+1==oh and (iw+2*pad-kernel)//stride+1==ow
    full=layout(iw,ih,pad);rectangles=not full[0]
    th,tw=oh,ow
    if rectangles:
        maxside=(640-kernel)//stride+1;tw=min(ow,maxside)
        lo,hi=0,min(oh,maxside)
        while lo<hi:
            mid=(lo+hi+1)//2
            if layout((tw-1)*stride+kernel,(mid-1)*stride+kernel,0)[0]:lo=mid
            else:hi=mid-1
        assert lo>0
        th=lo
    copied_input=converted=staged_input=jobs=0
    bits=parent[27] if parent else 8
    exponent=parent[19] if parent else n[18]
    pitch=ci if parent else 4;cp=(ci+3)&~3
    rectangles_to_run=[]
    if adaptive_tail and rectangles:
        # Preserve the original parameter/output offsets: both new input and
        # output lengths must fit their original maximum tile footprints.
        input_capacity=((tw-1)*stride+kernel)*((th-1)*stride+kernel)*cp
        output_capacity=tw*th*co*(1 if output_s8 and n[27]==8 else 2)
        for tx in range(0,ow,tw):
            nx=min(tw,ow-tx);w=(nx-1)*stride+kernel
            lo,hi=0,min(oh,(640-kernel)//stride+1)
            while lo<hi:
                mid=(lo+hi+1)//2;h=(mid-1)*stride+kernel
                output_bytes=nx*mid*co*(1 if output_s8 and n[27]==8 else 2)
                valid=layout(w,h,0)[0] and w*h*cp<=input_capacity and output_bytes<=output_capacity
                if valid:lo=mid
                else:hi=mid-1
            assert lo>0
            for ty in range(0,oh,lo):rectangles_to_run.append((tx,ty,nx,min(lo,oh-ty)))
    else:
        for ty in range(0,oh,th):
            for tx in range(0,ow,tw):rectangles_to_run.append((tx,ty,min(tw,ow-tx),min(th,oh-ty)))
    assert sum(nx*ny for _,_,nx,ny in rectangles_to_run)==oh*ow
    for tx,ty,nx,ny in rectangles_to_run:
        w,h=((nx-1)*stride+kernel,(ny-1)*stride+kernel) if rectangles else (iw,ih)
        sx,sy=(tx*stride-pad,ty*stride-pad) if rectangles else (0,0)
        valid_width=max(0,min(w,iw-sx)-max(0,-sx))
        valid_height=max(0,min(h,ih-sy)-max(0,-sy))
        valid_pixels=valid_width*valid_height
        if bits==8 and exponent==n[18] and pitch==cp:copied_input+=valid_pixels*cp
        else:converted+=valid_pixels*ci
        staged_input+=w*h*cp;jobs+=1
    return dict(jobs=jobs,tile_output=[th,tw],full_scratch_bytes=full[1],
        full_work_estimate=full[2],full_fails_scratch=full[1]>0x100000,
        full_fails_work_guard=full[2]>67108864,staged_input_bytes=staged_input,
        copied_input_bytes=copied_input,converted_input_values=converted,
        macs=oh*ow*co*k,exact_s16_output_bytes=oh*ow*co*2)


def summarize(header,nodes):
    rows=[];hist=Counter();macs=0
    for i,n in enumerate(nodes):
        hist[OPS[n[0]]]+=1
        if n[0]!=1:continue
        p=nodes[n[5]] if n[5]>=0 else None;ci=p[1] if p else 3
        cost=n[1]*n[2]*n[3]*ci*n[10]*n[11];macs+=cost
        rows.append(dict(node=i,layer=n[9],output_shape=n[1:4],input_channels=ci,
            kernel=n[10],stride=n[12],linear=bool(n[25]),macs=cost))
    ineligible=[]
    for row in rows:
        if row['input_channels']*row['kernel']**2>1152:
            ineligible.append(dict(node=row['node'],layer=row['layer'],reason='K_exceeds1152',
                input_channels=row['input_channels'],kernel=row['kernel'],k=row['input_channels']*row['kernel']**2))
        if row['linear']:ineligible.append(dict(node=row['node'],layer=row['layer'],reason='linear_uses_other_backend'))
    return dict(nodes=len(nodes),operations=dict(hist),dense_conv_macs_per_input=macs,
        complete_k_exact_ineligible_nodes=ineligible,
        top_conv_nodes=sorted(rows,key=lambda x:x['macs'],reverse=True)[:8])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models',type=Path,default=ROOT/'build/picture-e42-20261025/hwc-product-host-r01/models')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();models=workspace_path(args.models)
    assert args.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(args.output);assert not out.exists();out.mkdir(parents=True)
    manifest={name:digest for digest,name in (line.split() for line in (ROOT/'linux/picture_new/r14-models.sha256').read_text().splitlines())}
    sources=['scripts/analyze_picture_costs.py','linux/picture_new/hwc_fast/integer_hwc.c',
        'linux/mac_accel/pango_mac_uapi.h','linux/picture_new/r14-models.sha256']
    source_sha={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in sources}
    result=dict(status='STATIC_FROZEN_GRAPH_METADATA_COST_ANALYSIS_NOT_TIMING_OR_QUALITY',
        hardware_used=False,inference_run=False,training_run=False,models_modified=False,
        images_accessed=False,source_sha256=source_sha,graphs={})
    for name,expected in manifest.items():
        header,nodes=read_graph(models/name,expected)
        result['graphs'][name]=summarize(header,nodes)
    header,nodes=read_graph(models/'detector.xqi',XQI_SHA)
    hwc=summarize(header,nodes);plans=[];concat=[];nearest=[];consumers=[[] for _ in nodes]
    outputs=set(header[4:4+header[3]])
    for i,n in enumerate(nodes):
        for p in n[5:5+n[4]]:
            if p>=0:consumers[p].append(i)
    for i,n in enumerate(nodes):
        if n[0]==1:
            p=nodes[n[5]] if n[5]>=0 else None
            plan=tile_plan(n,p);plan.update(node=i,output_bits=n[27]);plans.append(plan)
        if n[0] in [5,7]:
            row=dict(node=i,shape=n[1:4],bits=n[27],output_bytes=math.prod(n[1:4])*n[27]//8,
                consumers=consumers[i],single_conv_consumer=len(consumers[i])==1 and nodes[consumers[i][0]][0]==1 and i not in outputs)
            (concat if n[0]==7 else nearest).append(row)
    hwc.update(storage_node_counts=dict(Counter(str(n[27]) for n in nodes)),convolution_plans=plans,
        predicted_jobs=sum(p['jobs'] for p in plans),staged_input_bytes=sum(p['staged_input_bytes'] for p in plans),
        copied_input_bytes=sum(p['copied_input_bytes'] for p in plans),
        converted_input_values=sum(p['converted_input_values'] for p in plans),
        exact_s16_output_bytes=sum(p['exact_s16_output_bytes'] for p in plans),
        potential_native_s8_logical_output_bytes_saved=sum(p['exact_s16_output_bytes']//2 for p in plans if p['output_bits']==8),
        concat_nodes=concat,nearest_nodes=nearest,concat_materialized_bytes=sum(x['output_bytes'] for x in concat),
        concat_single_conv_consumer_bytes=sum(x['output_bytes'] for x in concat if x['single_conv_consumer']))
    assert hwc['predicted_jobs']==166,'Static planner must match the frozen existing166-job boundary'
    hwc['predicted_input_zero_bytes']=hwc['staged_input_bytes']-hwc['copied_input_bytes']-hwc['converted_input_values']
    assert hwc['staged_input_bytes']==19086576 and hwc['predicted_input_zero_bytes']==203056
    refs=[n[26] for n in nodes];allocations=[None]*len(nodes)
    live=peak=allocated=reused=0
    for i,n in enumerate(nodes):
        size=math.prod(n[1:4])*n[27]//8;alias=None
        if n[0]==8:
            alias=next((p for p in n[5:5+n[4]] if refs[p]==1 and nodes[p][27]==n[27]),None)
        if alias is None:allocated+=size;live+=size
        else:allocations[alias]=None;reused+=size
        allocations[i]=size;peak=max(peak,live)
        for p in n[5:5+n[4]]:
            if p<0:continue
            refs[p]-=1
            if not refs[p] and allocations[p] is not None:live-=allocations[p];allocations[p]=None
    assert (allocated,reused,peak)==(21028000,819200,2867200)
    hwc.update(logical_tensor_allocated_bytes=allocated,logical_add_reused_bytes=reused,logical_peak_tensor_bytes=peak)
    hypothetical=[]
    for side in [512,416,320]:
        scale=side/640
        if not all((n[2]*side)%640==0 and (n[3]*side)%640==0 for n in nodes):continue
        ps=[tile_plan(n,nodes[n[5]] if n[5]>=0 else None,side,scale) for n in nodes if n[0]==1]
        hypothetical.append(dict(input_side=side,dense_conv_macs=sum(p['macs'] for p in ps),predicted_jobs=sum(p['jobs'] for p in ps),
            hypothetical_shape_only=True,current_hwc_loader_supports=False,quality_evaluated=False))
    s8plans=[tile_plan(n,nodes[n[5]] if n[5]>=0 else None,output_s8=True) for n in nodes if n[0]==1]
    tailplans=[tile_plan(n,nodes[n[5]] if n[5]>=0 else None,adaptive_tail=True) for n in nodes if n[0]==1]
    hwc.update(shape_only_scenarios=hypothetical,native_s8_hypothetical_jobs=sum(p['jobs'] for p in s8plans),
        native_s8_is_unimplemented_new_abi_and_hardware=True,
        adaptive_tail_hypothetical_jobs=sum(p['jobs'] for p in tailplans),
        adaptive_tail_not_implemented_or_timed=True,
        adaptive_tail_changed_nodes=[dict(node=p['node'],before_jobs=p['jobs'],after_jobs=q['jobs'])
            for p,q in zip(plans,tailplans) if p['jobs']!=q['jobs']])
    result['graphs']['detector.xqi']=hwc
    result['model_sha256']={name:hashlib.sha256((models/name).read_bytes()).hexdigest() for name in [*manifest,'detector.xqi']}
    assert all(result['model_sha256'][name]==value for name,value in {**manifest,'detector.xqi':XQI_SHA}.items())
    result['limitations']='MACs/bytes/job plans are static logical estimates, not measured DDR traffic, cycles, latency or accuracy. Smaller input and native-S8 scenarios create no model or RTL files and are unsupported by the frozen runtime.'
    assert all(hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h for f,h in source_sha.items())
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])
    for name,g in result['graphs'].items():print(name,'MACs',g['dense_conv_macs_per_input'],'nodes',g['nodes'])
    print('HWC jobs',hwc['predicted_jobs'],'concat bytes',hwc['concat_materialized_bytes'],'S8 logical output saving',hwc['potential_native_s8_logical_output_bytes_saved'])
    print('shape-only scenarios',hypothetical)


if __name__=='__main__':main()
