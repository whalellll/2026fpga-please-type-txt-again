import argparse,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--models',type=Path,required=True);a=p.parse_args()
dest=a.models/'native_parameters.h'
if dest.exists():raise FileExistsError(dest)
manifest=json.loads((a.models/'native_manifest.json').read_text())
detector=manifest['models']['detector'];margins=json.loads((HERE.parent/'vision-model-20261020/golden/software/config/roi_adapter.json').read_text())['margins']
def array(v,suffix=''):
    if isinstance(v,list):return '{'+','.join(array(x,suffix) for x in v)+'}'
    return float(v).hex()+suffix
dest.write_text('/* Adapter-generated exact frozen anchors/margins; no new calibration. */\n'+
    'static const float native_anchors[3][3][2]='+array(detector['anchors'],'f')+';\n'+
    'static const float native_strides[3]='+array(detector['strides'],'f')+';\n'+
    'static const double native_roi_margins[4]='+array(margins)+';\n')
print('NATIVE_PARAMETERS_EXPORTED')
