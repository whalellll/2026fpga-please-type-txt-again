"""Summarize only completed, exact-bitstream board receipts and comparable samples."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,sys
ROOT=Path(__file__).resolve().parents[1];B=ROOT/'build/board-trial-dedicated-02'
sys.path.insert(0,str(ROOT/'scripts'))
from collect_gui1080_board import display
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def text(p):return p.read_text(errors='replace').replace('\r','')
def batch(name):
 p=B/name/'result.json';r=read(p);assert r['status']=='DEDICATED_BOARD_SPEC_BATCH_PASS',name
 assert r['run_id']==binding['run_id'] and r['bitstream_sha256']==binding['bitstream_sha256'],name
 return r
binding=read(B/'result.json');sd=read(ROOT/'build/dedicated-sd-04/trial-binding.json')
assert binding['manifest_sha256']==sd['manifest_sha256'] and binding['bitstream_sha256']==sd['bitstream_sha256']
for name in ['initial-01','voice-upload-01','voice-bench-01','mixed-01','restore-01','gui-final-01']:batch(name)
review=read(B/'model-reviewed.json')
assert review['status']=='OFFICIAL_NNUE_AND_THREE_SEARCH_COMPUTE_PARITY_PASS_CPU_POSTCHECK_BUG_RETAINED'
model_batch=read(B/'model-01/result.json')
assert [x['status'] for x in model_batch['checks']]==['BOARD_COMMAND_SPEC_PASS']*3+['FAILED_PRESERVED']
for name,h in review['evidence_sha256'].items():assert sha(B/'model-01'/(name+'.uart'))==h,name
latencies={};breakdowns={};cache={};startup={};host={}
for backend,name in [('cpu','nnue-cpu'),('dedicated','nnue-chain')]:
 t=text(B/'model-01'/(name+'.uart'));assert 'NNUE_LATENCY_CORRECTNESS_PASS' in t
 assert 'NNUE_CLOCK_SOURCE source=clint hz=49500000' in t
 assert 'PIKAFISH_MAC_RUNTIME_FUSED' not in t and 'NNUE_LATENCY_FAIL' not in t
 matches=re.findall(r'^NNUE_LATENCY phase=(cold|warm) samples=(\d+) mean_us=(\d+) min_us=(\d+) p50_us=(\d+) p95_us=(\d+) max_us=(\d+)$',t,re.M)
 assert len(matches)==2
 latencies[backend]={}
 for phase,n,mean,minimum,p50,p95,maximum in matches:
  assert int(n)==100
  latencies[backend][phase]=dict(samples=int(n),mean_us=int(mean),min_us=int(minimum),p50_us=int(p50),p95_us=int(p95),max_us=int(maximum))
 startup[backend]=[int(x) for x in re.findall(r'^info string PIKAFISH_PFF1_STAGE stage=ready elapsed_ms=(\d+)$',t,re.M)]
 host[backend]=read(B/'model-01'/(name+'.result.json'))['commands'][0]['host_response_seconds']
 if backend=='dedicated':
  for line in t.splitlines():
   if line.startswith(('NNUE_PIPELINE_BREAKDOWN ','NNUE_LATENCY_BREAKDOWN ','NNUE_DEDICATED_CACHE ')):
    values=dict(re.findall(r'(\w+)=([\w]+)',line));phase=values.pop('phase')
    if line.startswith('NNUE_DEDICATED_CACHE '):
     cache[phase]={k:int(v) for k,v in values.items()};assert cache[phase]['runs']==100 and cache[phase]['errors']==0
    else:breakdowns.setdefault(phase,{})[line.split()[0]]={k:int(v) for k,v in values.items()}
  assert len(cache)==2
speedup={p:latencies['cpu'][p]['mean_us']/latencies['dedicated'][p]['mean_us'] for p in ['cold','warm']}
search={}
for backend,name in [('cpu','search-cpu'),('dedicated','search-chain')]:
 t=text(B/'model-01'/(name+'.uart'))
 if backend=='dedicated':assert 'PIKAFISH_PIPELINE_SEARCH_PASS' in t
 else:assert 'PIKAFISH_PIPELINE_SEARCH_FAIL reason=hardware-fallback-or-mismatch' in t
 rows=re.findall(r'^PIKAFISH_PIPELINE_SEARCH mode=\S+ case=(\d+) bestmove=(\S+) ponder=(\S*) score=(-?\d+) wdl=(\d+),(\d+),(\d+) nodes=(\d+) elapsed_ms=(\d+) nps=(\d+)$',t,re.M)
 assert len(rows)>=3
 search[backend]=[dict(case=int(r[0]),bestmove=r[1],ponder=r[2],score=int(r[3]),wdl=list(map(int,r[4:7])),nodes=int(r[7]),elapsed_ms=int(r[8])) for r in rows]
assert len(search['cpu'])==len(search['dedicated'])
for a,b in zip(search['cpu'],search['dedicated']):
 assert {k:v for k,v in a.items() if k!='elapsed_ms'}=={k:v for k,v in b.items() if k!='elapsed_ms'},'Search parity'
search_speedup=sum(x['elapsed_ms'] for x in search['cpu'])/sum(x['elapsed_ms'] for x in search['dedicated'])
voice={}
for name in ['short','median','long']:
 t=text(B/'voice-bench-01'/('voice-'+name+'.uart'))
 m=re.search(r'^VOICE_BOARD_EXACT_PASS repeats=(\d+) cpu_total_ns=(\d+) hardware_manual_total_ns=(\d+) scope=offline_same_pcm_including_ioctls$',t,re.M);assert m and int(m[1])==10
 voice[name]=dict(repeats=10,cpu_mean_ms=int(m[2])/10/1e6,hardware_mean_ms=int(m[3])/10/1e6,speedup=int(m[2])/int(m[3]))
mixed=text(B/'mixed-01/mixed-60s.uart');assert 'Q32_MIXED_60S_EXACT_ZERO_OVERFLOW_PASS' in mixed
assert re.search(r'PCM_TRANSPORT_PASS samples=960000 .*overflows=0',mixed)
scanout=display(text(B/'restore-01/display.uart'),expected_refresh_hz=30)
gui=text(B/'gui-final-01/gui-search-audio.uart');assert 'Q32_GUI_SEARCH_AUDIO_PASS' in gui
gui_time=re.search(r'^GUI_REQUEST_TIMING start=([0-9.]+) done=([0-9.]+)$',gui,re.M);assert gui_time
gui_request_seconds=float(gui_time[2])-float(gui_time[1]);assert 0<gui_request_seconds<100
coremark=read(B/'coremark/result.json');assert coremark['status']=='PASS'
hdmi=read(B/'hdmi-confirmation.json');assert hdmi['manifest_sha256']==sd['manifest_sha256']
diagnostic=ROOT/'build/board-trial-dedicated-01/diagnostic-01/dedicated-cache-context.result.json';assert read(diagnostic)['status']=='BOARD_COMMAND_SPEC_PASS'
evidence={p.relative_to(ROOT).as_posix():sha(p) for p in B.rglob('*') if p.is_file() and p.suffix in ['.uart','.json','.log'] and p.name!='summary.json' and 'upload-master' not in p.name and 'diagnostic-master' not in p.name}
evidence[diagnostic.relative_to(ROOT).as_posix()]=sha(diagnostic)
result=dict(status='DEDICATED_SD04_BOARD_TESTS_COMPLETED_CPU_DIAGNOSTIC_BUG_STA_FAIL_NOT_DELIVERY',completed_utc=datetime.now(timezone.utc).isoformat(),
 binding=binding,nnue_latency=latencies,nnue_cpu_over_dedicated=speedup,nnue_breakdowns=breakdowns,mlp_cache=cache,
 nnue_process_startup_ready_ms=startup,nnue_command_host_response_seconds=host,
 nnue_boundary='Full Network::evaluate including Stage A, CPU preparation, driver calls, transform/MLP/PSQT/result merge. FEN parsing, model/attack-table loading and application startup excluded. Cold/warm means CPU accumulator cache; not guaranteed MLP weight-cache state.',
 search=search,search_cpu_over_dedicated_aggregate=search_speedup,search_cpu_diagnostic=review,search_boundary='Fixed-node search result.elapsed_ms; app/model initialization excluded. Node counts and move/score/WDL compared exactly. CPU final harness check aborts due its known disabled-mode counter bug; raw failure retained.',
 voice=voice,voice_scope='Same three prerecorded PCM clips; all CPU/hardware features/logits exact. Not recognition accuracy or utterance-end deadline acceptance; original 300ms silence endpoint unchanged.',
 coremark=dict(status='PASS',mean_coremark_per_mhz=coremark['summary']['mean_coremark_per_mhz'],fresh_control=False,nonregression_gate='NOT_ESTABLISHED_NO_SAME_ROUND_CONTROL'),
 display=scanout,hdmi=hdmi,concurrency=dict(duration_seconds=60,audio_samples=960000,overflows=0),
 gui_search_audio='PASS',gui_request_seconds=gui_request_seconds,gui_request_boundary='Injected NEWGAME+MOVE h2e2 to MOVE_PASS log observation, with concurrent live capture; kernel uptime clock, polling interval100ms. Includes application/GUI/search work, excludes application startup.',independent_cache_context='PASS_SYNTHETIC_MODELS_ON_SAME_BITSTREAM',
 sd_boot=read(B/'sdboot.result.json'),preserved_failure='SD03 old FC0 route; build hooks fixed and card rewritten to SD04. Initial failed receipts retained.',
 final_sta_pass=False,cpu_setup_wns_ns=-0.181,formal_delivery=False,remote_push=False,flash_written=False,evidence_sha256=evidence)
(B/'summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:result[k] for k in ['status','nnue_cpu_over_dedicated','search_cpu_over_dedicated_aggregate','voice','coremark','display']},indent=2))
