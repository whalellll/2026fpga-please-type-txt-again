"""Reject missing weights, reinstated generic engines and resource mismatches."""
import argparse
from pathlib import Path
from pikafish_dedicated_resource_contract import pikafish_dedicated_resource_contract as check

ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--native-root',type=Path,required=True);a=ap.parse_args()
n=(a.native_root/'pds/synthesize/soc_top_syn.vm').read_text()
r=(a.native_root/'pds/synthesize/soc_top.snr').read_text()
t=(a.native_root/'rtl/soc/soc_top.v').read_text()
cnn='.CNN_ENABLE(1)' in t
result=check(n,r,t)
assert result['drm']==(19. if cnn else 18.5)+(4. if '.ENABLE_NNUE_BATCH(1)' in t else 0.)+(1. if result['voice_quant'] else 0.)
faults=[(n+'\nmodule MacAccelCore();endmodule',r,t),
        (n.replace('module pikafish_mlp_dedicated','module missing_dedicated'),r,t),
        (n,r,t.replace('.PIKAFISH_ONLY(1)','.PIKAFISH_ONLY(0)')),
        (n.replace('GTP_DRM36K_E1','MISSING_DRM36K',1+n[:n.index('module pikafish_mlp_dedicated')].count('GTP_DRM36K_E1')),r,t),
        (n,r+'\n'+next(x for x in r.splitlines() if '|     + g_dedicated.u_chain ' in x),t)]
if cnn:
    faults += [(n.replace('module voice_cnn_tile_core','module missing_voice_cnn'),r,t),
               (n+'\nmodule voice_classifier_core();endmodule',r,t),
               (n,r,t.replace('.CNN_ENABLE(1)','.CNN_ENABLE(0)'))]
for i,args in enumerate(faults):
    try:check(*args)
    except AssertionError:continue
    raise AssertionError(('Unexpected dedicated gate acceptance',i))
print(f'PIKAFISH_DEDICATED_NATIVE_RESOURCE_CONTRACT_PASS positive=1 rejected={len(faults)} NOT_STA_OR_BOARD')
