from nnue_voice_resource_contract import nnue_voice_resource_contract as check
names=['nnue_pipeline_frontend','nnue_stream_transform','nnue_mlp_chain',
       'voice_accel_mmio','voice_feature_core','voice_classifier_core']
net='\n'.join('module '+n+'();endmodule' for n in names)
report='| g_nnue.u_nnue | 1065 | 716 | 96 | 5 | 3 | 0 |\n| u_voice_accel | 2700 | 2800 | 118 | 9 | 4.5 | 0 |'
top='.ENABLE_NNUE_PIPELINE(1) voice_accel_mmio u_voice_accel('
assert check(net,report,top)['apm']==14
assert check('','','')['drm']==0
faults=[(net.replace('module nnue_mlp_chain','module missing'),report,top),
        (net+'\nmodule voice_feature_core();endmodule',report,top),
        (net,report.splitlines()[0],top),(net,report+'\n'+report.splitlines()[1],top),
        (net,report.replace('| 9 | 4.5 |','| 10 | 4.5 |'),top),
        (net,report.replace('| 9 | 4.5 |','| 9 | 3 |'),top),
        (net,report.replace('| 5 | 3 |','| 4 | 3 |'),top),
        (net,report.replace('| 1065 |','| 0 |'),top),
        (net,report,top.replace('.ENABLE_NNUE_PIPELINE(1)','.ENABLE_NNUE_PIPELINE(0)'))]
for i,args in enumerate(faults):
    try:check(*args)
    except AssertionError:continue
    raise AssertionError(('unexpected acceptance',i))
print('NNUE_VOICE_NATIVE_RESOURCE_CONTRACT_PASS positive=2 rejected=9 NOT_BOARD')
