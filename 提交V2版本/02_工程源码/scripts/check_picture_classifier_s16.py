"""Offline, frozen-r14 classifier graph experiment. No recalibration or v2 loader."""
import argparse
import json
from pathlib import Path
import re
import struct
import check_picture_integer_graph as common


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();assert not a.output.exists()
    model=common.ROOT/'build/picture-merge-20261023/native-models/classifier.xqm'
    pinned=dict(line.split()[::-1] for line in (common.ROOT/'linux/picture_new/r14-models.sha256').read_text().splitlines())
    assert common.sha(model)==pinned['classifier.xqm']
    sources=[n for n in common.BASE if not n.endswith('graph_runtime.c')]+[
        'linux/picture_new/test_classifier_s16_trial.c','linux/picture_new/graph_tensor.c','linux/picture_new/graph_ops.c']
    files=set(sources+['linux/picture_new/graph_runtime.c','linux/picture_new/graph_tensor.h',
                      'linux/picture_new/graph_ops.h','linux/picture_new/graph_profile.h',
                      'linux/picture_new/vision32_locality.c','linux/picture_new/test_v321_mock.h',
                      'linux/picture_new/upstream/adapter/runtime/xq_int8_layer.c',
                      'linux/picture_new/upstream/adapter/runtime/xq_int8_layer.h',
                      'scripts/check_picture_classifier_s16.py','scripts/check_picture_integer_graph.py'])
    for directory in common.INCLUDES:
        files.update(p.relative_to(common.ROOT).as_posix() for p in (common.ROOT/directory).glob('*.h'))
    hashes={n:common.sha(common.ROOT/n) for n in files};a.output.mkdir(parents=True)
    result={'status':'RUNNING','hardware_used':False,'frozen_model_sha256':common.sha(model),
            'source_sha256':hashes,'targets':{},'parameters_changed':False,'production_selected':False,
            'scope':'Synthetic batch1/3/8, seven convs + integer GAP + linear, existing r14 pack; final FP32 handoff only. '
                    'Comparison is quantized-v1 vs frozen integer-GAP experiment, not real FP32 model accuracy or v2 acceptance.'}
    for target,cc,extra,prefix in [('host','gcc',[],[]),('qemu','/opt/toolchain/bin/riscv32-linux-musl-gcc',
        ['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align'],['qemu-riscv32'])]:
        binary=a.output/('classifier-'+target)
        common.run([cc,*common.FLAGS,*extra,'-DXQ_INTEGER_CARRIER=1','-DXQ_FAST_REQUANT=1',
                    *['-I'+str(common.ROOT/d) for d in common.INCLUDES],*[common.ROOT/n for n in sources],
                    '-Wl,--wrap=ioctl','-Wl,--gc-sections','-lm','-o',binary],a.output/(target+'-compile.log'),90)
        log=a.output/(target+'.log');common.run([*prefix,binary,model],log,120)
        assert 'CLASSIFIER_S16_GAP_TRIAL_FROZEN_EXPONENTS_AND_FATAL_IO_PASS_NOT_SELECTION' in log.read_text()
        rows=[dict(re.findall(r'(\w+)=(\w+)',line)) for line in log.read_text().splitlines() if line.startswith('CLASSIFIER_S16_TRIAL ')]
        assert [int(row['batch']) for row in rows]==[1,3,8]
        if target=='qemu':
            elf=binary.read_bytes();assert struct.unpack_from('<H',elf,18)[0]==243 and struct.unpack_from('<I',elf,36)[0]==0
        result['targets'][target]={'samples':rows,'binary_sha256':common.sha(binary)}
    assert result['targets']['host']['samples']==result['targets']['qemu']['samples']
    assert all(common.sha(common.ROOT/n)==h for n,h in hashes.items()) and common.sha(model)==pinned['classifier.xqm']
    result['status']='CLASSIFIER_INTEGER_GAP_TRIAL_PASS_NOT_V2_OR_ACCURACY_ACCEPTANCE'
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status']);print(json.dumps(result['targets']['host']['samples']))


if __name__=='__main__':
    main()
