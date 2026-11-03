"""Store extraction-tree RTL retests beside existing native/board evidence."""
from pathlib import Path
import gzip,hashlib,json
R=Path(__file__).resolve().parents[1];O=R/'artifacts/validated_accelerators_20261025';p=O/'manifest.json';m=json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
checks={}
for key,run,expected in [('serial','publication-serial-01','SERIAL_LEGACY_SIGNED33_UNSIGNED31_PRODUCT_ABORT_RESET_PASS_NOT_BOARD'),
 ('legacy','publication-legacy-01','VISION32_NUMPY_DIFFERENTIAL_DMA_PASS_NOT_BOARD'),('exact','publication-exact-01','VISION32_EXACT_S16_LUT65536_RTL_PASS_NOT_BOARD')]:
 B=R/'build'/run;d=json.loads((B/'result.json').read_text());assert d['status']==expected
 entries=d.get('inputs_sha256',d.get('source_sha256',{}))
 assert next(h for n,h in entries.items() if n.replace('\\','/')=='rtl/mac_accel/vision32_layer.v')==m['hardware_source_sha256']['rtl/mac_accel/vision32_layer.v']
 names=['result.json','simulation.log']+[n for n in ['vectors.json','tb.sv','tb_exact.sv','bases.hex','scales.hex','gold.hex'] if (B/n).exists()]
 for name in names:
  dest='publication-checks/'+key+'/'+name;target=O/dest;target.parent.mkdir(parents=True,exist_ok=True);assert not target.exists()
  target.write_bytes((B/name).read_bytes());m['files'][dest]=dict(sha256=sha(target),bytes=target.stat().st_size,source_path=str(B/name),source_sha256=sha(B/name),compressed=False)
 checks[key]=dict(status=expected,cases=d['cases'],result_path='publication-checks/'+key+'/result.json')
m['publication_checks']=checks;p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(checks,indent=2))
