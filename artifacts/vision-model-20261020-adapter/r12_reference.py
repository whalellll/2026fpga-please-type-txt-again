"""Current working selection with explicit precision and rollback identities."""
import hashlib
import json
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]


def resolve_selection(profile=None,backend=None,classifier=None,detector=None):
    config=json.loads((HERE/'working_combination.json').read_text(encoding='utf-8'))
    profile=profile or config['default_profile'];base=config['profiles'][profile]
    wanted_classifier=classifier or base['classifier'];wanted_detector=detector or base['detector']
    if (wanted_classifier,wanted_detector)!=(base['classifier'],base['detector']):
        matches=[(name,item) for name,item in config['profiles'].items() if item['classifier']==wanted_classifier and item['detector']==wanted_detector]
        if len(matches)!=1:raise ValueError('no unique registered classifier/detector combination')
        profile,base=matches[0]
    selected=dict(base,profile=profile,backend=backend or base['default_backend'])
    if selected['backend'] not in base['backends']:
        raise ValueError('No exact-int64 INT8 payload delivered for this combination; use FP32 or an explicit registered rollback. Never substitute old quantized weights.')
    return selected


def load_model(selection):
    root=REPO/selection['root']
    for name,item in selection['models'].items():
        if hashlib.sha256((root/item['path']).read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError('model identity mismatch: '+name)
    if selection['backend']=='quantized-mac':
        candidate=REPO/selection['quantized_candidate']
        graph_path=candidate/'integer_graph.json'
        graph=json.loads(graph_path.read_text(encoding='utf-8'))
        if graph['model_SHA256']!={k:v['sha256'] for k,v in selection['models'].items()}:
            raise ValueError('quantized graph model identity mismatch')
        if selection.get('quantized_graph_sha256') and hashlib.sha256(graph_path.read_bytes()).hexdigest()!=selection['quantized_graph_sha256']:
            raise ValueError('quantized graph identity mismatch')
        sys.path[:0]=[str(root),str(HERE.parent/'vision-model-20261020/golden/quantization')]
        from pc_exact import load_integer_runtime
        model=load_integer_runtime(root,candidate)
    else:
        sys.path.insert(0,str(root))
        from recognizer import Recognizer
        model=Recognizer(root,device='cpu',precision='fp32')
    model.pipeline.detector.input_size=selection['detector_input']
    if selection['refinement']=='full':
        import pipeline
        from line_refinement import refine_board
        pipeline.refine_board=refine_board
    from r09_reference import configure
    return configure(model,selection['candidate_filter'],selection['refinement'])


def annotate(result,selection):
    result.update(delivery_backend=selection['backend'],working_profile=selection['profile'],
        selected_classifier=selection['classifier'],selected_detector=selection['detector'],
        new_camera_domain_suitable=selection['domain_suitable'],full_integer_pipeline=False,production_ready=False)
    if selection['backend']=='quantized-mac':
        result['integer_oracle']='r08-exact-int64'
        if 'quantized_gate' in selection:
            result['quantized_gate']=selection['quantized_gate']
            result['integer_acceptance']=selection['integer_acceptance']
        result['numeric_backend']=dict(CNN_MAC='S8xS8_INT32',preactivation='S16',activation='S8_LUT',host_non_MAC='FP32')
        for identity in result['models'].values():identity['precision']='W8A8_MAC_with_host_FP32_graph'
    return result
