"""Negative tests for additive SD tools before any compiler/device access."""
import argparse,hashlib,importlib.util,json,struct,tempfile
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--tools',type=Path,required=True);ap.add_argument('--report',type=Path,required=True);a=ap.parse_args()
spec=importlib.util.spec_from_file_location('sd_builder',Path(__file__).with_name('build_cpu80_conv_sd.py'));mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
manifest=json.loads((a.tools/'manifest.json').read_text());name=next(iter(manifest['files_sha256']));payload=(a.tools/name).read_bytes()
cases=[('unsafe_parent','usr/bin/../bad',payload,None),('existing_tool','usr/bin/xiangqi-pikafish',payload,None),('wrong_hash','usr/bin/probe',payload,'0'*64),('truncated_elf','usr/bin/probe',b'ELF',None),('wrong_machine','usr/bin/probe',payload[:18]+b'\0\0'+payload[20:],None)]
rvc=bytearray(payload);struct.pack_into('<I',rvc,36,struct.unpack_from('<I',rvc,36)[0]|1);cases.append(('compressed_isa','usr/bin/probe',bytes(rvc),None))
results=[]
with tempfile.TemporaryDirectory(prefix='cpu80-conv-sd-mutations-') as temp:
 for label,path,data,digest in cases:
  work=Path(temp)/label;extra=work/'extras';extra.mkdir(parents=True)
  if '..' not in Path(path).parts:
   p=extra/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
  (extra/'manifest.json').write_text(json.dumps(dict(files_sha256={path:digest or hashlib.sha256(data).hexdigest()})))
  try:mod.build(a.source.resolve(),work/'output','unused-must-not-call-wsl',extra)
  except (ValueError,struct.error) as e:
   assert not (work/'output').exists(),'Unsafe tools reached build/output creation'
   results.append(dict(case=label,rejected=True,reason=str(e)));continue
  raise AssertionError('Unsafe additive SD tool accepted: '+label)
a.report.write_text(json.dumps(dict(status='ADDITIVE_CONV_SD_MUTATIONS_PASS_NOT_BOARD',cases=results),indent=2)+'\n');print('ADDITIVE_CONV_SD_MUTATIONS_PASS cases='+str(len(results)))
