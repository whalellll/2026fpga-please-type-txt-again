"""Generate a local STA-passing candidate, without accessing any board."""
from pathlib import Path
from datetime import datetime,timezone
import os,sys,json,hashlib,importlib.util,re
B=Path(__file__).resolve().parent;S=B/'source';P=S/'pds';O=B/'bitstream-01';O.mkdir(exist_ok=False)
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
review=read(B/'final-review-02/result.json');f=read(B/'frozen-inputs.json');assert review['final_sta_pass']
for n,h in f['native_inputs_sha256'].items():assert sha(S/n)==h,n
pnr=P/'prj_tasks/pnr_1/place_route/soc_top_pnr.adf';assert sha(pnr)==review['artifact_sha256'][str(pnr)]
T=Path('G:/fpga/pds_mcp_portable_20260905/pds_mcp_portable');I=Path('G:/fpga/PDS_2025.2-ads-win64/pango/PDS_2025.2-ads')
os.environ.update(PDS_MCP_SERVER_ROOT=str(T/'pds-ai-extension/server/python'),PDS_MCP_PYTHON=sys.executable,
 PDS_PATH=str(I/'bin/pds_shell.exe'),PDS_ROOT=str(I),PANGOPATH=str(I),PDS_WORKSPACE_ROOT=str(B),PDS_MCP_LOG_DIR=str(O/'mcp-logs'),
 PDS_MCP_PORT='0',TEMP=str(B/'tmp'),TMP=str(B/'tmp'),TMPDIR=str(B/'tmp'),PYTHONDONTWRITEBYTECODE='1')
command='gen_bit_stream -force_to_run -create_bit_file TRUE -create_bin_file'
record=dict(status='RUNNING_LOCAL_CANDIDATE_BITSTREAM_GENERATION_NOT_BOARD',source_commit=f['source_commit'],native_run=review['native_run'],
 command=command,owner_pid=os.getpid(),started_utc=datetime.now(timezone.utc).isoformat(),pnr_adf_sha256=sha(pnr),
 final_review_sha256=sha(B/'final-review-02/result.json'),controller_sha256=sha(Path(__file__)),board_tested=False,remote_pushed=False,formal_delivery=False)
(O/'input-binding.json').write_text(json.dumps(record,indent=2)+'\n')
spec=importlib.util.spec_from_file_location('client',T/'clients/mcp_probe_flow.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);c=m.McpClient(str(O/'rpc.log'))
try:
 c.initialize();r=c.tool('pds_start',dict(workdir=P.as_posix(),project=(P/'soc25_synth.pds').as_posix(),mock=False),120)
 record['pds_session_pid']=r['pid']
 r=c.tool('pds_execute',dict(command=command,timeout_ms=600000),630);assert r['ok']
 (O/'response.json').write_text(json.dumps(r,indent=2)+'\n')
 c.tool('pds_stop',{},120)
 assert sha(pnr)==record['pnr_adf_sha256']
 for n,h in f['native_inputs_sha256'].items():assert sha(S/n)==h,n
 files=[p for p in (P/'prj_tasks/pnr_1').rglob('soc_top.*') if p.suffix in ('.sbit','.bit','.bin')]
 assert any(p.suffix=='.sbit' for p in files) and any(p.suffix=='.bin' for p in files)
 record.update(status='LOCAL_STA_PASSING_CANDIDATE_BITSTREAM_GENERATED_NOT_BOARD_OR_DELIVERY',
  artifact_sha256={str(p):sha(p) for p in files},completed_utc=datetime.now(timezone.utc).isoformat())
except Exception as e:record.update(status='CANDIDATE_BITSTREAM_GENERATION_FAILED_PRESERVED',error=repr(e));raise
finally:
 c.close();(O/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print(record['status'])
