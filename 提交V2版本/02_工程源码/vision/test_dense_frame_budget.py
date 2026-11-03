"""Full-frame accounting must agree with the actual legacy job packer."""
import copy
import json
import unittest
from pathlib import Path

from dense_tiled_conv import ConvSpec, make_jobs
from dense_frame_budget import frame_budget, measured_budget


def layer(spec, name='conv'):
    return {'name': name, 'operator': 'Conv2d',
            'input_shape': [1, spec.cin, spec.height, spec.width],
            'output_shape': [1, spec.cout, spec.oh, spec.ow],
            'weight_shape': [spec.cout, spec.cin, spec.kernel, spec.kernel],
            'kernel': [spec.kernel]*2, 'stride': [spec.stride]*2,
            'padding': [spec.pad]*2, 'groups': 1}


class DenseFrameBudgetTests(unittest.TestCase):
    def graph(self, layers):
        return {'model_sha256': 'a'*64, 'layers': layers}

    def test_exact_packer_traffic_with_all_three_tails(self):
        spec = ConvSpec(17, 1, 257, 257, 1, 1, 0)
        jobs = list(make_jobs(spec, bytes(spec.width*spec.cin), bytes(spec.cout*spec.k)))
        result = frame_budget(self.graph([layer(spec)]))
        self.assertEqual(result['jobs'], len(jobs))
        self.assertEqual(result['read_bytes'], sum(len(j.inputs)+len(j.weights) for j in jobs))
        self.assertEqual(result['write_bytes'], sum(j.pixels*j.cout*4 for j in jobs))
        self.assertEqual(result['macs'], 17*257*257)
        self.assertEqual(result['compute_lower_bound_ms'], result['macs']/128/49500)
        self.assertEqual(result['board_fps'], None)
        self.assertFalse(result['device_model_ready'])

    def test_reject_invalid_graph_geometry_identity_and_groups(self):
        original = self.graph([layer(ConvSpec(5,5,16,32,3,1,1))])
        for mutation in ('groups', 'shape', 'identity', 'batch', 'duplicate'):
            graph = copy.deepcopy(original)
            if mutation=='groups': graph['layers'][0]['groups']=16
            if mutation=='shape': graph['layers'][0]['output_shape'][2]=4
            if mutation=='identity': graph['model_sha256']='bad'
            if mutation=='batch': graph['layers'][0]['input_shape'][0]=2
            if mutation=='duplicate': graph['layers']*=2
            with self.assertRaises(ValueError): frame_budget(graph)

    def test_cycle_evidence_must_cover_all_shapes_and_match_traffic(self):
        result = frame_budget(self.graph([layer(ConvSpec(17,1,4,33,1,1,0))]))
        log = '\n'.join('DENSE_TILED_RTL_JOB_PASS index=%d pixels=%d k=%d cout=%d cycles=100 read_bytes=%d write_bytes=%d' %
                        (i,s['pixels'],s['k'],s['cout'],s['read_bytes'],s['write_bytes'])
                        for i,s in enumerate(result['job_shapes']))
        measured = measured_budget(result, log)
        self.assertEqual(measured['conv_dma_cycles'], result['jobs']*100)
        self.assertEqual(measured['model_execution'], False)
        with self.assertRaises(ValueError): measured_budget(result, '')
        with self.assertRaises(ValueError): measured_budget(result, log+ '\n'+log)
        with self.assertRaises(ValueError): measured_budget(result, log.replace('read_bytes=384','read_bytes=1'))

    def test_real_320_graph_work_and_traffic(self):
        path=Path(__file__).resolve().parents[1]/'build/vision/train_20261005/evaluation_final/trained_graph.json'
        if not path.exists(): self.skipTest('trained graph is an external candidate artifact')
        result=frame_budget(json.loads(path.read_text(encoding='utf-8')))
        self.assertEqual(result['conv_layers'],60)
        self.assertEqual(result['macs'],523033600)
        self.assertEqual(result['jobs'],6956)
        self.assertEqual(len(result['job_shapes']),26)
        self.assertEqual(result['read_bytes'],60735488)
        self.assertEqual(result['write_bytes'],16094800)
        self.assertEqual(result['silu_elements'],2956800)
        self.assertGreater(result['compute_lower_bound_ms'],33.333333)


if __name__=='__main__': unittest.main()
