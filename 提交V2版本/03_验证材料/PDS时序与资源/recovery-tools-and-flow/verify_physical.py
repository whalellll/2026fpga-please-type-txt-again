"""Verify PDS25 primitive exports, including LUT6Q FY/FF paired-slot notation."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,xml.etree.ElementTree as ET
B=Path(__file__).resolve().parent;P=B/'source/pds';O=B/'physical-verification-01';O.mkdir(exist_ok=False)
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
pre=read(B/'pnr-preflight-05/result.json');review=read(B/'final-review-02/result.json')
pnr=P/'prj_tasks/pnr_1/place_route/soc_top_pnr.adf';assert sha(pnr)==review['artifact_sha256'][str(pnr)]
exports=B/'physical-readback-01'
assert not re.search(r'(?m)^E:',(exports/'stdout.log').read_text(errors='replace'))
netlist=P/'prj_tasks/pnr_1/place_route/soc_top_route_optimize.netlist';raw=netlist.read_text()
assert sha(netlist)==review['artifact_sha256'][str(netlist)]
canon=lambda n:re.sub(r'_perm$','',n)
kinds={}
for m in re.finditer(r'(?m)^Inst\n([^;\r\n]+);([^;\r\n]+)',raw):
 key=canon(m[1]);assert key not in kinds,key;kinds[key]=m[2]
aliases=[]
requested_names={canon(re.search(r'\{([^}]+)\}',line)[1]) for line in pre['placements_retained']}
def sites(text,from_export=False):
 result={}
 for m in re.finditer(r'(?m)^def_inst_site \{([^}]+)\} (\S+) (\S+?)(?: -no_check)?\s*$',text):
  name=canon(m[1]);slot=m[3]
  if from_export and name in requested_names and name.endswith('/opit_0_L6Q') and re.fullmatch('FF[0-3]',slot):
   assert kinds[name]=='gopLUT6Q',name
   paired='FY'+'ABCD'[int(slot[-1])]
   aliases.append(dict(cell=name,actual_export_slot=slot,paired_lut_slot=paired,primitive=kinds[name]))
   slot=paired
  assert name not in result,name;result[name]=(m[2],slot)
 return result
actual=sites((exports/'csr-final.pcf').read_text()+'\n'+(exports/'tage-final.pcf').read_text(),True)
released_name='u_cpu/u_cpu_wrapper/u_cpu/core/frontend/tage/tagMem_2_ext/Memory_1/gopdrm_18k'
assert released_name in actual
released_actual_site=actual[released_name]
requested=sites('\n'.join(pre['placements_retained']))
assert len(requested)==30 and len(aliases)==30
assert all(actual.get(n)==v for n,v in requested.items()),{n:(v,actual.get(n)) for n,v in requested.items() if actual.get(n)!=v}
def ports(text):
 out={}
 for m in re.finditer(r'(?m)^def_port \{([^}]+)\} (.*)$',text):
  assert m[1] not in out;out[m[1]]=dict(re.findall(r'(\w+)=([^\s]+)',m[2]))
 return out
base=ports((P/'prj_tasks/pnr_1/device_map/soc_top.pcf').read_text());got=ports((exports/'io-final.pcf').read_text())
assert len(base)==165
assert all(got.get(n,{}).get('LOC')==v['LOC'] for n,v in base.items())
route=P/'prj_tasks/pnr_1/place_route/run_route.log';rt=route.read_text()
netnames={re.sub(r'\s+','',line.split(';')[0]) for line in raw.splitlines() if ';' in line}
for n in pre['priority_constraints_kept']:
 commands={'def_route -prior_net {'+n+'}'}
 if not re.search(r'\s',n):
  commands.add('def_route -prior_net '+n)
 assert sum(len(re.findall(r'(?m)^Executing : '+re.escape(command)+r' successfully\.\s*$',rt)) for command in commands)==1,n
 assert re.sub(r'\s+','',n) in netnames,n
skew=[]
for corner in ['slow','fast']:
 path=P/('prj_tasks/pnr_1/report_timing/report_db/report_timing_'+corner+'_path_max_skew.db')
 data=path.read_bytes();assert b'<!DOCTYPE' not in data and b'<!ENTITY' not in data
 root=ET.fromstring(data);tables=root.findall('./table');assert len(tables)==1
 table=tables[0];assert table.get('title')=='Max Skew Path'
 headers=[x.text or '' for x in table.findall('./column_headers/data')]
 rows=table.findall('./row');assert len(rows)==10
 for row in rows:
  fields=dict(zip(headers,[x.text or '' for x in row.findall('./data')]))
  assert float(fields['Slack'])>=0 and float(fields['Required Skew'])==7.192,fields
  assert 0<=float(fields['Actual Skew'])<=7.192,fields
  skew.append(dict(corner=corner,fields=fields,xml_sha256=sha(path)))
record=dict(status=f"PDS25_FINAL30_PAIRED_SITES_165_PINS_{len(pre['priority_constraints_kept'])}_PRIORITIES_20_MAX_SKEW_READBACK_PASS_NOT_BOARD",
 native_run=review['native_run'],source_commit=review['source_commit'],pnr_adf_sha256=sha(pnr),
 released_tage_actual_site=released_actual_site,slots_verified=30,pins_verified=165,priority_nets_verified=len(pre['priority_constraints_kept']),max_skew_rows_verified=20,paired_slot_aliases=aliases,
 alias_policy='PDS25 exports the registered gopLUT6Q at FF0..FF3; input FY A..D names identify the corresponding paired LUT site. Require the exact final gopLUT6Q primitive and same CLM; do not apply this normalization to other cells or FFAPP slots.',
 export_sha256={str(p):sha(p) for p in exports.glob('*.pcf')},max_skew=skew,
 final_sta_pass=review['final_sta_pass'],board_tested=False,recorded_utc=datetime.now(timezone.utc).isoformat())
(O/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(record['status'])
