"""Collect final PDS25 route/STA facts; never promote pending tool/board checks."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,sys
B=Path(__file__).resolve().parent;S=B/'source';P=S/'pds';O=B/'final-review-02';O.mkdir(exist_ok=False)
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
q=read(B/'status.json');frozen=read(B/'frozen-inputs.json');binding=read(B/'pnr-02/input-binding.json')
assert q['status']=='PDS25_CPU125_PLACE_ROUTE_AND_TIMING_REPORT_COMPLETED_REVIEW_ALL_CORNERS'
started=datetime.fromisoformat(q['pnr_started_utc'])
for n,h in frozen['native_inputs_sha256'].items():assert sha(S/n)==h,n
for n,h in binding['actual_route_constraint_sha256'].items():assert sha(Path(n))==h,n
mapped=P/'prj_tasks/pnr_1/device_map/soc_top_map.adf';assert sha(mapped)==binding['native_map_adf_sha256']
report=P/'prj_tasks/pnr_1/report_timing/soc_top.rtr'
assert report.exists() and datetime.fromtimestamp(report.stat().st_mtime,timezone.utc)>=started
t=report.read_text(encoding='utf-8')
def clocks(text):
 body=text.split('Clock Summary:',1)[1].split('Clock Groups:',1)[0]
 return {m[1]:float(m[2]) for m in re.finditer(r'(?m)^\s*(\S+)\s+(\d+\.\d+)\s+\{',body)}
actual_clocks=clocks(t)
baseline_clocks=clocks((B.parent/'pds25-cpu80-20261031-06/source/pds/prj_tasks/pnr_1/report_timing/soc_top.rtr').read_text())
baseline_clocks['cpu_clk']=7.992
assert actual_clocks==baseline_clocks,dict(actual=actual_clocks,baseline=baseline_clocks)
assert actual_clocks['cpu_clk']==7.992 and actual_clocks['sys_clk']==20.202
summary=t.split('Design Summary :',1)[1]
headline=summary.splitlines()[0].strip()
cut=re.search(r'(?m)^Slow Corner\s*$',summary);assert cut
summary=summary[:cut.start()]
rows=[]
for m in re.finditer(r'(?m)^\s*([^\r\n]+?) Summary\((Slow|Fast) Corner\):([\s\S]*?)\n=+',summary):
 for line in m[3].splitlines():
  parts=line.split()
  if len(parts)==6:a,b,wns,tns,ends,total=parts
  elif len(parts)==5 and m[1].strip()=='Minimum Pulse Width':a,wns,tns,ends,total=parts;b=a
  else:continue
  if not (re.fullmatch(r'[-\d.]+',wns) and re.fullmatch(r'[-\d.]+',tns) and ends.isdecimal() and total.isdecimal()):continue
  rows.append(dict(check=m[1].strip(),corner=m[2],launch=a,capture=b,wns_ns=float(wns),tns_ns=float(tns),violating_endpoints=int(ends),total_endpoints=int(total)))
old_rows=read(B.parent/'pds25-cpu80-20261031-04/final-review-02/summary-rows.json')
key=lambda x:(x['check'],x['corner'],x['launch'],x['capture'])
oldkeys={key(x) for x in old_rows};newkeys={key(x) for x in rows}
assert len(newkeys)==len(rows) and len(rows)>=116
removed=oldkeys-newkeys;added=newkeys-oldkeys
allowed_removed={(kind,corner,a,b) for kind in ('Setup','Hold') for corner in ('Slow','Fast') for a,b in [('cpu_clk','sys_clk'),('sys_clk','cpu_clk')]}
assert removed<=allowed_removed and not added,dict(removed=sorted(removed),added=sorted(added))
coverage=dict(previous_rows=len(old_rows),current_rows=len(rows),removed_normal_cross_domain_rows=sorted(removed),added_rows=sorted(added),
 rationale='All original clock periods and48 CDC directives unchanged. Targeted register mapping restores source tag propagation; normal synchronous cross-clock rows may disappear once the original max-delay/hold exceptions cover their physical starts. Retain exception reports separately; do not silently drop other summary coverage.')
exception_report=P/'prj_tasks/pnr_1/report_timing/soc_top_exception.rtr'
try:
 et=exception_report.read_text(encoding='utf-8');exception_encoding='utf-8'
except UnicodeDecodeError:
 et=exception_report.read_text(encoding='gb18030');exception_encoding='gb18030'
sections=list(re.finditer(r'(?m)^\| Exception type\s*:\s*(\S+)',et));exception_checks=[];exception_bad=[]
for index,m in enumerate(sections):
 block=et[m.start():sections[index+1].start() if index+1<len(sections) else len(et)]
 if m[1].startswith('set_false_path'):continue
 values=[float(x) for x in re.findall(r'(?m)^\s*Slack \([^)]*\)\s+([-\d.]+)',block)]
 group=dict(type=m[1],corner='Slow' if '| Slow Corner' in block else 'Fast',paths=len(values),worst_slack_ns=min(values) if values else None,
            fdc_lines=sorted(set(map(int,re.findall(r'Exception constraint line number:\s*(\d+)',block)))))
 exception_checks.append(group)
 if any(x<0 for x in values):exception_bad.append(group)
payload_lines=[i+1 for i,l in enumerate((P/'soc.fdc').read_text().splitlines()) if l.startswith('set_max_delay ') and '/storage' in l]
for corner in ('Slow','Fast'):
 analyzed=set().union(*(set(x['fdc_lines']) for x in exception_checks if x['corner']==corner and x['type']=='set_max_delay(setup)'))
 assert set(payload_lines)<=analyzed,(corner,payload_lines,analyzed)

cpu=[x for x in rows if x['launch']==x['capture']=='cpu_clk' and x['check'] in ('Setup','Hold')];assert len(cpu)==4
bad=[x for x in rows if x['wns_ns']<0 or x['tns_ns']<0 or x['violating_endpoints']]
passed=headline=='All Constraints Met.' and not bad and not exception_bad and all(x['wns_ns']>0 for x in cpu)
native=P/'prj_tasks/pnr_1/place_route';errors=[];critical=[];hashes={str(report):sha(report),str(exception_report):sha(exception_report)}
for name in ['run_place.log','run_route.log','run_route_optimize.log']:
 path=native/name;assert path.exists()
 text=path.read_text(errors='replace')
 errors.extend(dict(file=name,line=line) for line in text.splitlines() if line.startswith('E:'))
 critical.extend(dict(file=name,line=line) for line in text.splitlines() if 'unspecified I/O constraint' in line)
 hashes[str(path)]=sha(path)
assert not errors and not critical,dict(errors=errors,io_missing=critical)
for name in ['soc_top_plc.adf','soc_top_route.adf','soc_top_pnr.adf']:
 path=native/name;assert path.exists() and path.stat().st_size>1000000;hashes[str(path)]=sha(path)
for name in ['soc_top_route.netlist','soc_top_route_optimize.netlist']:
 path=native/name;assert path.exists();hashes[str(path)]=sha(path)
r=dict(status='PDS25_CPU125_ROUTED_ALL_CORNER_STA_PASS_PHYSICAL_READBACK_AND_TOOL_QUALIFICATION_PENDING' if passed else 'PDS25_CPU125_ROUTED_FINAL_STA_FAILED_NOT_BOARD',
 source_commit=frozen['source_commit'],native_run=q['native_run'],pnr_attempt='pnr-02',snapshot_sha256=sha(P/'build_snapshot.json'),inputs_verified=len(frozen['native_inputs_sha256']),
 tool_version='2025.2 build211867',cpu_hz=125000000,sys_hz=49500000,clocks=actual_clocks,clock_count=len(actual_clocks),
 headline=headline,summary_rows=len(rows),coverage_delta=coverage,exception_report_encoding=exception_encoding,exception_checks=exception_checks,exception_violations=exception_bad,cpu_timing=cpu,violating_summary_rows=bad,final_sta_pass=passed,
 constraints=read(B/'pnr-preflight-05/result.json'),artifact_sha256=hashes,
 full_native_control_and_cdc_qualification_pass=False,board_tested=False,remote_pushed=False,formal_delivery=False,
 recorded_utc=datetime.now(timezone.utc).isoformat())
(O/'result.json').write_text(json.dumps(r,indent=2)+'\n');(O/'summary-rows.json').write_text(json.dumps(rows,indent=2)+'\n')
q.update(status=r['status'],final_sta_pass=passed,final_review='final-review-02/result.json',final_report_sha256=sha(report),cpu_final_timing=cpu,violating_summary_rows=len(bad))
(B/'status.json').write_text(json.dumps(q,indent=2)+'\n')
print(json.dumps(dict(status=r['status'],headline=headline,cpu=cpu,violating_summary_rows=bad)))
