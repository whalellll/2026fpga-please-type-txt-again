"""Account for the new native subtrees without weakening legacy resource gates."""
import re
def nnue_voice_resource_contract(netlist,report,top):
    enabled=int('.ENABLE_NNUE_PIPELINE(1)' in top)
    voice=int(bool(re.search(r'\bvoice_accel_mmio\s+u_voice_accel\s*\(',top)))
    modules=re.findall(r'(?m)^module\s+(\w+)\b',netlist)
    for name in ('nnue_pipeline_frontend','nnue_stream_transform','nnue_mlp_chain'):
        assert modules.count(name)==enabled,('NNUE module presence',name)
    for name in ('voice_accel_mmio','voice_feature_core','voice_classifier_core'):
        assert modules.count(name)==voice,('Voice module presence',name)
    profiles=[('g_nnue.u_nnue',enabled,5.,3.),('u_voice_accel',voice,9.,4.5)]
    result={'apm':0.,'drm':0.,'subtrees':{}}
    for name,present,apm,drm in profiles:
        found=[]
        for line in report.splitlines():
            fields=line.split('|')
            if len(fields)<8 or not re.fullmatch(r'\s*\d+\s*',fields[2]):continue
            label=fields[1].strip().removeprefix('+').strip()
            if label==name:found.append(dict(lut=float(fields[2]),ff=float(fields[3]),apm=float(fields[5]),drm=float(fields[6])))
        assert len(found)==present,('Native subtree missing/duplicated',name)
        if present:
            row=found[0]
            assert row['lut']>0 and row['ff']>0 and row['apm']==apm and row['drm']==drm,('Native footprint changed',name,row)
            result['subtrees'][name]=row;result['apm']+=apm;result['drm']+=drm
    return result
