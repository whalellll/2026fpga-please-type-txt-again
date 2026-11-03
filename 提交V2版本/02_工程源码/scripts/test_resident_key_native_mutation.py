"""In-memory mutation of actual mapped key FF D, with unchanged VM on disk."""
from pathlib import Path
import hashlib,json,re,sys
from analyze_resident_key_boundary import analyze
from audit_icache_pad_ads import module,clean,cells,ports
p=Path(sys.argv[1]);out=Path(sys.argv[2]);assert not out.exists()
raw=p.read_bytes();text=raw.decode();body=module(text,'RsMem');clean_body=clean(body)
candidate=json.loads(Path(sys.argv[3]).read_text())
assert candidate['netlist_sha256']==hashlib.sha256(raw).hexdigest()
assert candidate['status']=='RESIDENT_KEY_NO_SAME_EDGE_RAW_DATA_BOUNDARY_OBSERVED' and candidate['forbidden_count']==0
name=candidate['results'][0]['instance']
matches=[m for kind in ('GTP_DFF','GTP_DFF_R','GTP_DFF_RE','GTP_DFF_E','GTP_DFF_S','GTP_DFF_SE','GTP_DFF_C','GTP_DFF_CE') for m in cells(clean_body,kind) if m['name'].lstrip('\\')==name.lstrip('\\')]
assert len(matches)==1,(name,len(matches));m=matches[0];pins=ports(m['ports'])
assert 'input [31:0] io_wb_0_bits_data' in body
replacement,n=re.subn(r'\.D\s*\([^()]*\)',r'.D (io_wb_0_bits_data[0])',m[0]);assert n==1
mutated_body=clean_body[:m.start()]+replacement+clean_body[m.end():]
assert text.count(body)==1;mutated=text.replace(body,mutated_body)
result=analyze(mutated)
assert result['status']=='SAME_EDGE_RAW_DATA_REACHES_KEY_FF' and result['forbidden_count']>0
assert p.read_bytes()==raw
q=dict(status='ACTUAL_KEY_FF_RAW_WB_D_MUTATION_DETECTED_VM_UNCHANGED',netlist_sha256=hashlib.sha256(raw).hexdigest(),checker_sha256=hashlib.sha256((Path(__file__).parent/'analyze_resident_key_boundary.py').read_bytes()).hexdigest(),mutation='Actual retained key FF D is driven directly from actual io_wb_0_bits_data[0]',instance=name,old_D=pins['D'],forbidden_count=result['forbidden_count'])
out.write_text(json.dumps(q,indent=2)+'\n');print(q['status'])
