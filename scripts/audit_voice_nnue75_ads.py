"""Prove a found-gated call selector before using the unchanged CPU oracle.

The mapper shared RAS push with updateValid and moved found into the selected
call LUT. Independent pin assignments found=0/call=1 are unreachable. Prove
that correlation through the actual producer, rather than assuming pin values.
"""
from pathlib import Path
import hashlib,itertools,json,re,sys
import audit_cpu_ads as original
from ads_bdd import cone_leaves
BASE_EVALUATE=original.Cone.evaluate
BASE_BIND=original.bind_registered_frontend_controls
BASE_PRIMITIVE=original.Cone.primitive
VIRTUAL='__proven_found_cofactor_call__'
PROOFS=[]

def bind(frontend,source):
    try:return BASE_BIND(frontend,source)
    except ValueError as error:
        if str(error)!='Folded RAS push truth function differs':raise
    body=re.search(r'(?ms)^module CoreFrontend\s.*?^endmodule',source).group()
    ras=re.findall(r'(?s)\bRas\s+ras\s*\((.*?)\);',body)
    assert len(ras)==1
    targets=re.findall(r'\.io_specPush\s*\(([^()]*)\)',ras[0]);assert len(targets)==1
    target=original.signal(targets[0]);node,port=frontend.drivers[target]
    assert node['kind']=='GTP_LUT6D' and port=='Z5'
    pins={v for k,v in node['ports'].items() if k.startswith('I') and v not in ["1'b0","1'b1"]}
    returns={'pdReturns_'+str(i) for i in range(4)};calls={'pdCalls_'+str(i) for i in range(4)}
    rets=[n for n in pins if returns<=cone_leaves(frontend,[n])]
    selected=[n for n in pins if calls<=cone_leaves(frontend,[n])]
    assert len(rets)==len(selected)==1
    ret,call=rets[0],selected[0]
    assert pins=={ret,call,'found','pdAccept','trainValid'}
    producer,producer_port=frontend.drivers[call]
    assert producer['kind']=='GTP_LUT6' and producer_port=='Z'
    producer_inputs=sorted({v for k,v in producer['ports'].items() if k.startswith('I')})
    assert len(producer_inputs)==6 and 'found' in producer_inputs
    count=0
    for values in itertools.product(range(2),repeat=6):
        state=dict(zip(producer_inputs,values));cofactor=dict(state,found=1)
        assert BASE_EVALUATE(frontend,call,state)==state['found']*BASE_EVALUATE(frontend,call,cofactor),'Call producer is not exactly found-gated'
        count+=1
    for r,c,found,accept,train in itertools.product(range(2),repeat=5):
        state={ret:r,call:found*c,'found':found,'pdAccept':accept,'trainValid':train}
        assert BASE_EVALUATE(frontend,target,state)==(1-r)*c*found*accept,'Reachable RAS push cofactor differs'
        count+=1
    frontend._proven_voice_call=call
    proof=dict(mode='folded_ras_push',return_selector=ret,call_target=VIRTUAL,push_target=target,
        native_call_target=call,truth_cases=count,consumer='CoreFrontend.ras.io_specPush',mapped_output=port,
        producer=frontend.primitive(call),push=frontend.primitive(target),
        correlation='native_call = found AND native_call[found=1]; all64 producer cofactors and32 reachable push cofactors checked')
    PROOFS.append(proof);return proof

def evaluate(self,target,values,cache=None,active=None):
    if original.signal(target)==VIRTUAL:
        assert hasattr(self,'_proven_voice_call')
        return BASE_EVALUATE(self,self._proven_voice_call,dict(values,found=1))
    return BASE_EVALUATE(self,target,values,cache,active)

def primitive(self,target):
    if original.signal(target)==VIRTUAL:
        assert hasattr(self,'_proven_voice_call')
        result=BASE_PRIMITIVE(self,self._proven_voice_call)
        result.update(cofactor_fixed={'found':1},native_target=self._proven_voice_call,
                      logical_target=VIRTUAL,scope='Actual producer cell; the evaluated selector is its explicitly proven found=1 cofactor')
        return result
    return BASE_PRIMITIVE(self,target)

def main():
    original.bind_registered_frontend_controls=bind;original.Cone.evaluate=evaluate;original.Cone.primitive=primitive
    try:original.main()
    finally:
        original.bind_registered_frontend_controls=BASE_BIND;original.Cone.evaluate=BASE_EVALUATE
        original.Cone.primitive=BASE_PRIMITIVE
    out=Path(sys.argv[sys.argv.index('--output')+1]);record=json.loads(out.read_text())
    assert record['status']=='PASS'
    record['voice_nnue_ras_adapter']={'status':'ACTUAL_RAS_PRODUCER_CORRELATION_AND_UNCHANGED_CPU_ORACLE_PASS',
        'proofs':PROOFS,'adapter_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    out.write_text(json.dumps(record,indent=2)+'\n')
    print('VOICE_NNUE75_NATIVE_RAS_CORRELATION_CPU_ORACLE_PASS proofs='+str(len(PROOFS)))
if __name__=='__main__':main()
