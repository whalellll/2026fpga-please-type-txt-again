"""Exact native footprint for the fixed, single-bucket Pikafish profile."""
import re

def enabled(top):
    matches=re.findall(r'\.PIKAFISH_ONLY\s*\(\s*([01])\s*\)',top)
    assert len(matches)<=1,'Ambiguous dedicated profile'
    return matches==['1']

def pikafish_dedicated_resource_contract(netlist,report,top):
    assert enabled(top),'Dedicated profile not explicitly selected'
    assert '.ENABLE_NNUE_PIPELINE(1)' in top,'Dedicated pipeline disabled'
    modules=re.findall(r'(?m)^module\s+(\w+)\b',netlist)
    cnn=bool(re.search(r'\.CNN_ENABLE\s*\(\s*1\s*\)',top))
    for name in ('pikafish_mlp_dedicated','nnue_pipeline_frontend','nnue_stream_transform',
                 'pff1_stagea_gather','voice_accel_mmio','voice_feature_core'):
        assert modules.count(name)==1,('Required dedicated module missing/duplicated',name)
    assert modules.count('voice_classifier_core')==int(not cnn),'Legacy voice classifier profile mismatch'
    assert modules.count('voice_cnn_tile_core')==int(cnn),'Small CNN profile mismatch'
    voice_core=re.findall(r'(?ms)^module voice_cnn_tile_core\b.*?^endmodule',netlist)
    quant=bool(cnn and re.search(r'\bquant_mode\b',voice_core[0]))
    for name in ('MacAccelCore','mac_accel_dma_kernel','nnue_mlp_chain','xiangqi_sparse_eval'):
        assert modules.count(name)==0,('Removed generic/legacy module reappeared',name)
    result={'apm':0.,'drm':0.,'subtrees':{}}
    profiles=[('g_nnue.u_nnue',37.,14.),('u_voice_accel',16. if quant else 12. if cnn else 9.,6. if quant else 5. if cnn else 4.5),
              ('g_dedicated.u_chain',35.,13.)]
    batch=bool(re.search(r'\.ENABLE_NNUE_BATCH\s*\(\s*1\s*\)',top))
    if batch:
        assert modules.count('pikafish_eval_batch')==1,'Batch controller missing'
        profiles.append(('g_batch.u_batch',0.,4.))
    for name,apm,drm in profiles:
        found=[]
        for line in report.splitlines():
            fields=line.split('|')
            if len(fields)<8 or not re.fullmatch(r'\s*\d+\s*',fields[2]):continue
            if fields[1].strip().removeprefix('+').strip()==name:
                found.append(dict(lut=float(fields[2]),ff=float(fields[3]),apm=float(fields[5]),drm=float(fields[6])))
        assert len(found)==1,('Native subtree missing/duplicated',name)
        row=found[0]
        assert row['lut']>0 and row['ff']>0 and row['apm']==apm and row['drm']==drm,('Dedicated footprint changed',name,row)
        result['subtrees'][name]=row
        if name!='g_dedicated.u_chain':result['apm']+=apm;result['drm']+=drm
    core=re.findall(r'(?ms)^module pikafish_mlp_dedicated\b.*?^endmodule',netlist)
    assert len(core)==1
    assert len(re.findall(r'\bGTP_APM_E2\s',core[0]))==35,'Dedicated DSP mapping changed'
    assert len(re.findall(r'\bGTP_DRM36K_E1\s',core[0]))==8,'FC0 resident banks missing'
    assert len(re.findall(r'\bGTP_DRM18K_E1\s',core[0]))==10,'FC1/feature/metadata banks missing'
    if cnn:
        voice=re.findall(r'(?ms)^module voice_cnn_tile_core\b.*?^endmodule',netlist)
        assert len(voice)==1
        assert len(re.findall(r'\bGTP_APM_E2\s',voice[0]))==(11 if quant else 7),'Four products/control/optional scalar requant DSP mapping changed'
        assert len(re.findall(r'\bGTP_DRM36K_E1\s',voice[0]))==3,'CNN resident/input SRAM missing'
        assert len(re.findall(r'\bGTP_DRM18K_E1\s',voice[0]))==(3 if quant else 1),'CNN output/optional per-channel parameters SRAM missing'
        row=next(line.split('|') for line in report.splitlines() if re.search(r'\|\s*\+ g_cnn\.u_cnn\s*\|',line))
        # An accidentally inferred register file passed the DRM count alone.
        assert float(row[2])<=1600 and float(row[3])<=800,'CNN tile memories expanded into LUTs/FFs'
    result['voice_quant']=quant
    return result
