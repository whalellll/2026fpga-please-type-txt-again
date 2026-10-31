import sys,json
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
G=HERE.parent/'vision-model-20261020/golden'
sys.path[:0]=[str(G/'software'),str(G/'quantization')]
from integer_ops import load_integer_runtime,IntegerOp
import torch
from torch.fx import Tracer,GraphModule
m=load_integer_runtime(G/'software',G/'quantization/candidate_v1')
roots=dict(board=m.pipeline.locator.model,detector=m.pipeline.detector.detector.model,classifier=m.pipeline.detector.classifier)
class T(Tracer):
    def is_leaf_module(self,module,name):
        return isinstance(module,IntegerOp) or type(module).__name__=='Detect' or super().is_leaf_module(module,name)
for name,root in roots.items():
    print('MODEL',name,type(root),flush=True)
    try:
        graph=T().trace(root,concrete_args={'augment':False,'profile':False,'visualize':False} if name=='detector' else None)
        print(GraphModule(root,graph).code,flush=True)
        print('MODULES',[(n,type(x).__name__) for n,x in root.named_modules() if type(x).__name__ in ('Detect','MaxPool2d','Upsample','AdaptiveAvgPool2d','Flatten','Sigmoid')])
    except Exception as e:print('GRAPH_FAILED',repr(e),flush=True)
