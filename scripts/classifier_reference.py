"""Build the independent C int64 classifier oracle and bind its four tensors."""
import copy
from pathlib import Path
import re
import check_picture_integer_graph as check


def verify(cc, flags, sources, prefix, models, inputs, output, target, old_expected, seconds):
    selected=[str(p) for p in sources if Path(p).name!='graph_runtime.c']
    for name in ['graph_tensor.c','graph_ops.c','graph_profile.c','test_classifier_s16_reference.c']:
        path=str(check.ROOT/'linux/picture_new'/name)
        if path not in selected:selected.append(path)
    binary=output/(target+'-classifier-reference')
    check.run([cc,*flags,'-DXQ_GRAPH_PROFILE','-DXQ_NATIVE_COACH',*selected,
               '-Wl,--wrap=ioctl','-Wl,--gc-sections','-lm','-o',binary],
              output/(target+'-classifier-reference-compile.log'),90)
    checks=output/(target+'-classifier-reference.txt');log=output/(target+'-classifier-reference.log')
    check.run([*prefix,binary,models/'classifier.xqm',inputs/'classifier.input',checks],log,seconds)
    text=log.read_text();assert 'CLASSIFIER_DIRECT_INT64_EIGHT_LAYER_FOUR_TENSOR_AND_BOUNDARY_PASS_NOT_BOARD' in text
    assert 'ERROR: AddressSanitizer' not in text and 'runtime error:' not in text
    lines=checks.read_text().splitlines();assert lines[0]=='XQ_NATIVE_CHECKS_V1'
    rows=[]
    for line in lines[1:]:
        fields=line.split();assert len(fields)==11
        rows.append([*map(int,fields[:3]),*[int(v,16) for v in fields[3:7]],*fields[7:]])
    assert len(rows)==8 and [row[0] for row in rows]==list(range(72,80))
    # Anchors the independent implementation to immutable old goldens for the
    # entire prefix; the head is expected to change after integer GAP.
    assert rows[:7]==old_expected['rows'][72:79]
    expected=copy.deepcopy(old_expected);expected['rows'][72:80]=rows
    expected['variant']='79 unchanged original layers plus int64 reference for classifier head79'
    samples=[dict(re.findall(r'(\w+)=(\w+)',line)) for line in text.splitlines()
             if line.startswith('CLASSIFIER_INTEGER_REFERENCE ')]
    assert [int(row['batch']) for row in samples]==[1,3,8]
    return expected,dict(status='PASS',layers=8,tensors_per_layer=4,reference='Direct int64 dot/division; no production dot or GAP kernel',
                         checks_sha256=check.sha(checks),binary_sha256=check.sha(binary),samples=samples,
                         current_integer_head_differs_from_legacy=rows[7]!=old_expected['rows'][79])
