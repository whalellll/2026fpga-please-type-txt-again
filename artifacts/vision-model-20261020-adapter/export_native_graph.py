"""Losslessly pack delivered INT8/LUT tensors and explicit host graph operations.

No calibration, training, weight rounding, altered anchors or new model export.
The three files are adapter-owned and bind every copied tensor to its source SHA.
"""
import argparse,hashlib,json,operator,struct,sys,zlib
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;G=HERE.parent/'vision-model-20261020/golden'
sys.path[:0]=[str(G/'software'),str(G/'quantization')]
import numpy as np,torch
from torch import nn
from torch.fx import Tracer
from pc_exact import ensure_integer_ops,load_integer_runtime
ensure_integer_ops()
from integer_ops import IntegerOp
OP=dict(qop=1,sigmoid=3,pool=4,nearest=5,bilinear=6,cat=7,add=8,mean=9,flatten=10,relu=11)
class Trace(Tracer):
    def is_leaf_module(self,m,path):return isinstance(m,IntegerOp) or type(m).__name__=='Detect' or super().is_leaf_module(m,path)
def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--release',type=Path,default=G/'software');p.add_argument('--candidate',type=Path,default=G/'quantization/candidate_v1')
    p.add_argument('--detector-size',type=int,choices=[416,640],default=640);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    model=load_integer_runtime(a.release,a.candidate)
    assert model.pipeline.detector.input_size==a.detector_size
    graph=json.loads((a.candidate/'integer_graph.json').read_text())
    ids={m['layer_id']:i for i,m in enumerate(graph['layers'])}
    roots=dict(board=model.pipeline.locator.model,detector=model.pipeline.detector.detector.model,classifier=model.pipeline.detector.classifier)
    reports={}
    for model_number,(name,root) in enumerate(roots.items()):
        fx=Trace().trace(root,concrete_args={'augment':False,'profile':False,'visualize':False} if name=='detector' else None)
        nodes=[];mapping={};shapes={-1:(3,192,192) if name=='board' else (3,a.detector_size,a.detector_size) if name=='detector' else (3,32,32)}
        blob=bytearray();sources={};outputs=[];labels=[]
        def data(array):
            while len(blob)%8:blob.append(0)
            offset=len(blob);blob.extend(array.tobytes());return offset
        def emit(kind,parents,shape,parameters=None,label=''):
            row=[0]*32;row[0]=OP[kind];row[1:4]=shape;row[4]=len(parents);row[5:5+len(parents)]=parents
            for k,v in (parameters or {}).items():row[k]=v
            i=len(nodes);nodes.append(row);shapes[i]=shape;labels.append(label);return i
        def qop(op,parent):
            meta=op.metadata;w=op.qw.numpy();linear=meta['kind']=='linear';c,h,ww=shapes[parent]
            kh,kw=(1,1) if linear else w.shape[2:]
            sh,sw=(1,1) if linear else meta['stride'];ph,pw=(0,0) if linear else meta['padding'];dh,dw=(1,1) if linear else meta['dilation']
            shape=(w.shape[0],1 if linear else (h+2*ph-dh*(kh-1)-1)//sh+1,1 if linear else (ww+2*pw-dw*(kw-1)-1)//sw+1)
            assert c==w.shape[1] and (not linear or h==ww==1)
            params={9:ids[op.layer_id],10:kh,11:kw,12:sh,13:sw,14:ph,15:pw,16:dh,17:dw,
                18:op.input_exp,19:op.output_exp if op.lut.numel() else op.pre_exp,
                20:data(w),21:data(op.qb.numpy().astype('<i4')),22:data(op.shifts.numpy().astype('<i8')),
                23:data(op.lut.numpy()),24:op.lut.numel(),25:int(linear)}
            path=a.candidate/'int8'/(op.layer_id+'.npz')
            sources[op.layer_id]=hashlib.sha256(path.read_bytes()).hexdigest()
            return emit('qop',[parent],shape,params,op.layer_id)
        prior=None
        for n in fx.nodes:
            if n.op=='placeholder':
                if n.target=='x':mapping[n]=-1
                continue
            if n.op=='call_module':
                m=root.get_submodule(n.target)
                if type(m).__name__=='Detect':
                    outputs=[qop(layer,mapping[parent]) for layer,parent in zip(m.m,n.args[0])]
                    anchors=(m.anchors*m.stride[:,None,None]).numpy().tolist()
                    break
                parent=mapping[n.args[0]];shape=shapes[parent]
                if isinstance(m,IntegerOp):mapping[n]=qop(m,parent)
                elif isinstance(m,nn.Identity):mapping[n]=parent
                elif isinstance(m,nn.Flatten):mapping[n]=emit('flatten',[parent],(int(np.prod(shape)),1,1),label=n.name)
                elif isinstance(m,nn.Sigmoid):mapping[n]=emit('sigmoid',[parent],shape,label=n.name);prior=mapping[n]
                elif isinstance(m,nn.ReLU):mapping[n]=emit('relu',[parent],shape,label=n.name)
                elif isinstance(m,nn.MaxPool2d):
                    assert m.kernel_size==5 and m.stride==1 and m.padding==2
                    mapping[n]=emit('pool',[parent],shape,{10:5,14:2},n.name)
                elif isinstance(m,nn.Upsample):
                    assert m.mode=='nearest' and m.scale_factor==2
                    mapping[n]=emit('nearest',[parent],(shape[0],shape[1]*2,shape[2]*2),label=n.name)
                else:raise ValueError((name,n,m))
                if name=='board' and n.target=='corner_maps':outputs=[prior,mapping[n]];break
            elif n.op=='call_function':
                if n.target in (operator.eq,torch._assert):continue
                if n.target==torch.cat:
                    assert n.args[1]==1
                    parents=[mapping[x] for x in n.args[0]];ss=[shapes[x] for x in parents]
                    assert len(set(s[1:] for s in ss))==1
                    mapping[n]=emit('cat',parents,(sum(s[0] for s in ss),*ss[0][1:]),label=n.name)
                elif n.target==operator.add:
                    parents=[mapping[x] for x in n.args];assert shapes[parents[0]]==shapes[parents[1]]
                    mapping[n]=emit('add',parents,shapes[parents[0]],label=n.name)
                elif n.target==torch.nn.functional.interpolate:
                    assert n.kwargs['mode']=='bilinear' and n.kwargs['align_corners'] is False
                    parent=mapping[n.args[0]];mapping[n]=emit('bilinear',[parent],(shapes[parent][0],*n.kwargs['size']),label=n.name)
                else:raise ValueError((name,n))
            elif n.op=='call_method':
                if n.target=='reshape':mapping[n]=mapping[n.args[0]]
                elif n.target=='mean':
                    assert n.args[1]==(2,3);parent=mapping[n.args[0]]
                    mapping[n]=emit('mean',[parent],(shapes[parent][0],1,1),label=n.name)
                else:raise ValueError((name,n))
            elif n.op=='output':outputs=[mapping[n.args[0]]]
            else:raise ValueError((name,n))
        assert outputs
        for row in nodes:
            for parent in row[5:5+row[4]]:
                if parent>=0:nodes[parent][26]+=1
        for parent in outputs:nodes[parent][26]+=1
        version=2 if a.detector_size==416 else 1
        body=(struct.pack('<4I',*shapes[-1],0) if version==2 else b'')+b''.join(struct.pack('<32i',*row) for row in nodes)+blob
        header=struct.pack('<8s10I',b'XQGRPH1\0',version,model_number,len(nodes),len(outputs),*(outputs+[0xffffffff]*(3-len(outputs))),len(blob),len(body),zlib.crc32(body))
        path=a.out/(name+'.xqm');path.write_bytes(header+body)
        reports[name]=dict(file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size,
            nodes=len(nodes),outputs=outputs,input_shape=shapes[-1],output_shapes=[shapes[i] for i in outputs],labels=labels,source_tensors=sources)
        if name=='detector':reports[name].update(anchors=anchors,strides=m.stride.numpy().tolist())
    (a.out/'native_manifest.json').write_text(json.dumps(dict(schema_version=1,scope='EXPERIMENTAL lossless tensor packing; NOT M0 or full-integer acceptance',
       detector_input=a.detector_size,source_graph_sha256=hashlib.sha256((a.candidate/'integer_graph.json').read_bytes()).hexdigest(),models=reports),indent=2)+'\n')
    print('NATIVE_GRAPH_EXPORT',json.dumps({k:(v['nodes'],v['bytes']) for k,v in reports.items()}),flush=True)
if __name__=='__main__':main()
