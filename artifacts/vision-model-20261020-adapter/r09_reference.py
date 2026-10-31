"""Adapter-owned Scheme A and B selection; frozen runtime sources stay read-only."""
import ast
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def selected_paths():
    import json
    registration = json.loads((HERE / 'candidates/det416-r09/registration.json').read_text(encoding='utf-8'))
    return REPO / registration['local_release'], REPO / registration['local_quantized_candidate']


def load_working_model(backend='quantized-mac'):
    import sys
    release, candidate = selected_paths()
    sys.path[:0] = [str(release), str(HERE.parent / 'vision-model-20261020/golden/quantization')]
    if backend == 'quantized-mac':
        from pc_exact import load_integer_runtime
        model = load_integer_runtime(release, candidate)
    elif backend == 'fp32':
        from recognizer import Recognizer
        model = Recognizer(release, device='cpu', precision='fp32')
    else:
        raise ValueError('unsupported backend')
    return configure(model, True, 'B')


def refinement_b():
    import numpy as np
    import line_refinement as LR
    source = next((REPO / 'build/picture-r09-20261021/delivery').glob('Task3*/task3_refine_downgrade.py'))
    tree = ast.parse(source.read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'refined_impl')
    scope = dict(np=np, LR=LR)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), scope)
    implementation = scope['refined_impl']
    def run(image_rgb, coarse_corners, *, rank_axis, occluder_boxes=None):
        parameters = dict(LR.PARAMETERS)
        parameters['ransac_trials'] = 80
        return implementation(image_rgb, coarse_corners, rank_axis, occluder_boxes, parameters, True, 5)
    return run


def configure(model, candidate_filter=False, refinement='full'):
    if refinement == 'B':
        import pipeline
        pipeline.refine_board = refinement_b()
    if not candidate_filter:
        return model
    import numpy as np
    import torch
    from types import MethodType
    from live_two_stage import (letterbox, non_max_suppression, input_to_variant,
                                variant_to_original, crop_piece)

    @torch.inference_mode()
    def predict(self, image, roi):
        x1, y1, x2, y2 = map(int, roi)
        height, width = image.shape[:2]
        assert 0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height
        crop = image[y1:y2, x1:x2]
        inp, ratio, pad = letterbox(crop, (self.input_size, self.input_size), auto=False, scaleup=False, stride=32)
        tensor = torch.from_numpy(np.ascontiguousarray(inp[:, :, ::-1].transpose(2, 0, 1))).to(self.device)
        tensor = (tensor.half() if self.fp16 else tensor.float())[None] / 255
        raw = self.detector(tensor, augment=False)
        p = non_max_suppression(raw, .001, .6, multi_label=True, agnostic=False, max_det=300)[0].float().cpu().numpy()
        p[:, :4] = variant_to_original(input_to_variant(p[:, :4], ratio, pad, x2-x1, y2-y1), (x1, y1))
        q = p[(p[:, 2] > p[:, 0]) & (p[:, 3] > p[:, 1])].astype(np.float64)
        before = len(q)
        q = q[q[:, 4] >= .05]
        self._r09_counts = dict(before=before, classifier_batch=len(q))
        if not len(q):
            return np.empty((0, 6), dtype=np.float32)
        patches = [crop_piece(image, b[:4], size=self.classifier_input_size) for b in q]
        prob = []
        for j in range(0, len(patches), 256):
            x = torch.tensor(np.stack(patches[j:j+256]).transpose(0, 3, 1, 2), device=self.device, dtype=torch.float32)/255
            prob.append(self.classifier(x).softmax(1).cpu().numpy())
        prob = np.concatenate(prob)
        cid = prob.argmax(1); keep = cid < 14; q = q[keep]; cid = cid[keep]
        if not len(q):
            return np.empty((0, 6), dtype=np.float32)
        score = q[:, 4] * prob.max(1)[keep]
        fused = torch.zeros(1, len(q), 19, device=self.device, dtype=torch.float32)
        fused[0, :, :2] = torch.tensor((q[:, :2]+q[:, 2:4])/2, device=self.device)
        fused[0, :, 2:4] = torch.tensor(q[:, 2:4]-q[:, :2], device=self.device)
        fused[0, :, 4] = torch.tensor(score, device=self.device)
        fused[0, torch.arange(len(q), device=self.device), 5+torch.tensor(cid, device=self.device)] = 1
        return non_max_suppression(fused, .001, .6, multi_label=True, agnostic=False, max_det=300)[0].float().cpu().numpy()
    model.pipeline.detector.predict = MethodType(predict, model.pipeline.detector)
    return model
