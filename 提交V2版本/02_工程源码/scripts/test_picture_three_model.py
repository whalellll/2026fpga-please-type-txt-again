import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from verify_picture_model import verify


class ThreeModelGateTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.m={'scheme':'board-detect-v2','format_profile':'training-handoff-current-three-model-v1',
                'implementation':'board192-roi640-rgb32-refined','production_ready':False,
                'acceptance':{'full_integer_pipeline':False},'models':{},'files':{},'runtime_aliases':{},
                'metrics':{'board_geometry':{'coarse_board_model':{'P50_px':5,'P95_px':14}}}}
        self.put('training_manifest.json',{'independent_test':False})
        for n in ('requirements.txt','golden/recognize.py','geometry/geometry_reference.c','geometry/board_geometry.py'):
            self.put(n,b'synthetic fixture, not executable model')
        combined={'layer_count':80,'layers':[],'model_SHA256':{}}
        for name,size,count in (('detector',640,60),('board',192,12),('classifier',32,8)):
            prefix='int8' if name=='detector' else name+'_model/int8'
            checkpoint=name+'.pt';onnx=name+'.onnx'
            self.put(checkpoint,b'fixture weights');self.put(onnx,b'fixture graph')
            self.m['models'][name]={'checkpoint':{'path':checkpoint,'sha256':self.m['files'][checkpoint]},
                'onnx':{'path':onnx,'sha256':self.m['files'][onnx],'fixed_input':[1,3,size,size]},'int8_dir':prefix}
            combined['model_SHA256'][name]=self.m['files'][checkpoint]
            layers=[]
            for i in range(count):
                ident=name+'__test_'+str(i)
                layer={'layer_id':ident,'input_dtype':'int8','weight_dtype':'int8','accumulator_dtype':'int32',
                       'preactivation_dtype':'int16','output_dtype':'int8','activation':'SiLU','max_INT32_absolute_bound':10000}
                layers.append(layer);combined['layers'].append(layer)
                self.put(prefix+'/'+ident+'.npz',b'fixture');self.put(prefix+'/'+ident+'.lut',b'fixture')
            self.put(prefix+'/integer_graph.json',{'layer_count':count,'layers':layers})
        self.put('golden/quantization/candidate_v1/integer_graph.json',combined)
        dumps=[]
        for i in range(80):
            name='golden/quantization/candidate_v1/golden_layer_dumps/test'+str(i)+'.npz'
            self.put(name,b'synthetic tensor fixture')
            dumps.append({'path':'golden_layer_dumps/test'+str(i)+'.npz','sha256':self.m['files'][name]})
        self.put('golden/quantization/candidate_v1/golden_dump_manifest.json',dumps)
        self.save()

    def tearDown(self):self.temp.cleanup()
    def put(self,name,data):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes(json.dumps(data).encode() if isinstance(data,(dict,list)) else data)
        self.m['files'][name]=hashlib.sha256(p.read_bytes()).hexdigest()
    def save(self):(self.root/'manifest.json').write_text(json.dumps(self.m),encoding='utf-8')
    def test_integrity_does_not_grant_m0(self):
        r=verify(self.root);self.assertEqual(r['integer_layers'],80)
        self.assertFalse(r['m0_accepted']);self.assertFalse(r['m0_eligible'])
    def test_payload_and_unlisted_nested_manifest_rejected(self):
        p=self.root/'board_model/int8/board__test_0.lut';p.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'identity mismatch'):verify(self.root)
        self.put('board_model/int8/board__test_0.lut',b'fixture');self.save()
        p=self.root/'unlisted/manifest.json';p.parent.mkdir();p.write_text('{}')
        with self.assertRaisesRegex(ValueError,'unlisted'):verify(self.root)
    def test_input_and_model_identity_rejected(self):
        self.m['models']['board']['onnx']['fixed_input']=[1,3,640,640];self.save()
        with self.assertRaisesRegex(ValueError,'input mismatch'):verify(self.root)
    def test_integer_dtype_and_bound_rejected(self):
        name='int8/integer_graph.json';g=json.loads((self.root/name).read_text())
        g['layers'][0]['output_dtype']='float32';self.put(name,g);self.save()
        with self.assertRaisesRegex(ValueError,'dtype mismatch'):verify(self.root)
        g['layers'][0]['output_dtype']='int8';g['layers'][0]['max_INT32_absolute_bound']=2147483648
        self.put(name,g);self.save()
        with self.assertRaisesRegex(ValueError,'accumulator bound'):verify(self.root)
    def test_s16_identity_heads_are_explicitly_allowed(self):
        name='classifier_model/int8/integer_graph.json';g=json.loads((self.root/name).read_text())
        g['layers'][-1].update(activation='Identity',output_dtype='int16');self.put(name,g);self.save()
        combined_name='golden/quantization/candidate_v1/integer_graph.json'
        combined=json.loads((self.root/combined_name).read_text());combined['layers'][-1]=g['layers'][-1]
        self.put(combined_name,combined);self.save()
        self.assertEqual(verify(self.root)['integer_layers'],80)
    def test_production_claim_rejected(self):
        self.m['production_ready']=True;self.save()
        with self.assertRaisesRegex(ValueError,'production'):verify(self.root)


if __name__=='__main__':unittest.main()
