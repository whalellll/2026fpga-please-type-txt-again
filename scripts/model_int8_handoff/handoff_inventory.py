"""Standard-library-only, read-only inventory of the frozen deployment graphs."""
from collections import Counter
from pathlib import Path
import hashlib
import math
import struct
import zlib


MODELS = {
    'board.xqm': ('baseline-models/board.xqm', 'fbd8a4e8bcd78918a44674eb69225f7d82ac4547ac24a777ea4b4b11cf495efe'),
    'classifier.xqm': ('baseline-models/classifier.xqm', 'fc03674b9f73f8c0d0fffd1cbdd10b4edebccd2056740d8aeec7e472b522697f'),
    'detector.xqm': ('baseline-oracle/models/detector.xqm', 'd65b4b8686520ae1546d0a207c1bcb9f30efe0d40e7f5c8245c4dd11ff9ca09d'),
    'detector.xqi': ('baseline-oracle/models/detector.xqi', 'd72d039041b41310f037344772eb75ce895ec6fe678bbb31ed547a7ad7453942'),
}
OPS = {1:'conv', 3:'sigmoid', 4:'maxpool', 5:'nearest', 6:'bilinear',
       7:'concat', 8:'add', 9:'gap', 10:'identity', 11:'relu'}


def graph(data, expected):
    assert hashlib.sha256(data).hexdigest() == expected, 'Frozen model SHA mismatch'
    assert len(data) >= 48 and data[:8] in (b'XQGRPH1\0', b'XQINT81\0')
    header = struct.unpack_from('<10I', data, 8)
    body = data[48:]
    assert 0 < header[2] <= 200 and 0 < header[3] <= 3
    assert len(body) == header[8] and zlib.crc32(body) == header[9]
    hwc = data[:8] == b'XQINT81\0'
    descriptor = 16 if not hwc and header[0] == 2 else 0
    assert len(body) == descriptor+header[2]*128+header[7]
    nodes = [struct.unpack_from('<32i', body, descriptor+i*128) for i in range(header[2])]
    outputs = list(header[4:4+header[3]])
    assert len(set(outputs)) == len(outputs) and all(0 <= n < len(nodes) for n in outputs)
    consumers = [[] for _ in nodes]
    for i, node in enumerate(nodes):
        assert node[0] in OPS and all(n > 0 for n in node[1:4]) and 1 <= node[4] <= 4
        for parent in node[5:5+node[4]]:
            assert -1 <= parent < i
            if parent >= 0:
                consumers[parent].append(i)
    rows = []
    for i, n in enumerate(nodes):
        parents = list(n[5:5+n[4]])
        row = dict(index=i, operation=OPS[n[0]], opcode=n[0], shape_chw=list(n[1:4]),
            parents=parents, consumers=consumers[i], is_output=i in outputs,
            output_exponent=n[19] if hwc or n[0] == 1 else None,
            storage_bits=n[27] if hwc else None,
            storage_semantics='XQI executable dtype' if hwc else 'XQM reserved dtype is not execution storage')
        if hwc:
            assert n[27] in (8, 16, 32)
            row.update(proven_absolute_integer_bound=n[28],
                logical_output_bytes=math.prod(n[1:4])*n[27]//8)
        if n[0] == 1:
            ci = nodes[parents[0]][1] if parents[0] >= 0 else 3
            k = ci*n[10]*n[11]
            row.update(layer_id=n[9], input_channels=ci, kernel_hw=list(n[10:12]),
                stride_hw=list(n[12:14]), padding_hw=list(n[14:16]), dilation_hw=list(n[16:18]),
                input_exponent=n[18], linear=bool(n[25]), k=k,
                dense_macs=math.prod(n[1:4])*k, weight_dtype='S8', bias_dtype='I32',
                accumulation_dtype='I32', preactivation_dtype='S16', lut_bytes=n[24],
                complete_k_exact_k_limit_met=k <= 1152)
            if hwc:
                blob = body[header[2]*128:]
                groups = (n[1]+7)//8
                assert n[21] >= 0 and n[21]+groups*8*12 <= len(blob)
                parameters = [struct.unpack_from('<iII', blob, n[21]+j*12) for j in range(groups*8)]
                row.update(parameter_multipliers=sorted(set(p[1] for p in parameters)),
                    per_output_channel_right_shifts=[p[2] for p in parameters[:n[1]]],
                    weights_bytes=n[29], parameters_bytes=n[30],
                    device_output_storage_bits=16)
        rows.append(row)
    return dict(magic=data[:7].decode('ascii'), format_version=header[0], model_kind=header[1],
        bytes=len(data), sha256=expected, crc32_body='%08x' % header[9],
        node_count=len(nodes), output_nodes=outputs, output_shapes_nchw=[[1,*nodes[i][1:4]] for i in outputs],
        operations=dict(sorted(Counter(OPS[n[0]] for n in nodes).items())),
        activation_storage_node_counts=dict(sorted(Counter(str(n[27]) for n in nodes).items())) if hwc else None,
        dense_conv_linear_macs=sum(row.get('dense_macs', 0) for row in rows), nodes=rows)


def inventory(root):
    root = Path(root)
    graphs = {name:graph((root/rel).read_bytes(), sha) for name,(rel,sha) in MODELS.items()}
    detector = graphs['detector.xqi']
    assert detector['activation_storage_node_counts'] == {'8':69, '16':16}
    assert detector['output_shapes_nchw'] == [[1,57,80,80],[1,57,40,40],[1,57,20,20]]
    return dict(schema='picture-model-int8-frozen-inventory-v1', status='READ_ONLY_METADATA_NO_INFERENCE',
        model_paths={name:rel for name,(rel,sha) in MODELS.items()}, graphs=graphs,
        input_contract=dict(side=640, channels=3, layout='HWC4', input_dtype='S8',
                            zero_point=0, exponent=detector['nodes'][0]['input_exponent']),
        actual_xqi_s32_activation_nodes=0, convolution_accumulator_bits=32,
        xqm_n27_is_not_execution_dtype=True, board_nonconv_preserves_fp32_semantics=True,
        classifier_s16_gap_already_available=True, geometric_refinement_binary64=True,
        model_training_checkpoint_included=False, quality_or_latency_measured=False)
