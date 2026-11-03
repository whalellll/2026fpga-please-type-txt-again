"""Run the complete CRAM programmer with a run-bound full project audit.

Keep the original programmer and frozen audit untouched. Generated host copies
only anchor their helper paths and adapt the two exact inherited functions.
All device, bitstream, STA, Tcl, volatile CRAM and DONE checks remain intact.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,re,subprocess,traceback,shutil

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def quote(s):return "'"+str(s).replace("'","''")+"'"
FUNCTIONS={
 'rtl/mac_accel/mac_conv_weight_dma.v':'ddfb2c60daabc4d0df80759a9f3bb95adc7a3de02619523c921e9504186a6f19',
 'sim/tb_conv_weight_fold.sv':'8ea92f4da293bd4b8da7ece33b8536dbc1b1c832042d8201e29b0bb15a6b7c47'}
GUI1080_FUNCTIONS={**FUNCTIONS,
 'rtl/mac_accel/mac_conv_weight_dma.v':'5b80d58075a0c01b4f1d5cf294a5f3109298cb48278a32674f62c39091de96eb'}
VOICE75_FUNCTIONS={**FUNCTIONS,
 'rtl/mac_accel/mac_conv_weight_dma.v':'d331ce15b43ee824d2392cd6f3eb3c6be432c39d55b963198b1c8e323db55f76'}

def adapt_voice75_functions(root,audit):
 """Allow only the byte-identical inherited P3 source for this clock contract."""
 clocks=read(root/'config/clocks.json');display=read(root/'config/display.json')
 if clocks['cpu_hz'] not in (75000000,70000000):return audit,GUI1080_FUNCTIONS
 assert clocks['sys_hz']==49500000
 assert display['width']==1920 and display['height']==1080
 assert display['pixel_hz']==74250000 and display['refresh_hz']==30
 assert re.search(r'\.ENABLE_NNUE_PIPELINE\s*\(\s*1\s*\)',(root/'rtl/soc/soc_top.v').read_text())
 name='rtl/mac_accel/mac_conv_weight_dma.v'
 # This entire file, including its existing function, is identical to parent2f3d0ab.
 # The exact-source allowlist remains closed to any new/modified function.
 assert sha(root/name)==VOICE75_FUNCTIONS[name]
 old=GUI1080_FUNCTIONS[name];assert audit.count(old)==1
 return audit.replace(old,VOICE75_FUNCTIONS[name]),VOICE75_FUNCTIONS

def prepare(root,run,out):
 root=Path(root).resolve();out=Path(out).resolve()
 assert re.fullmatch('[0-9a-f]{32}',run)
 snap=read(root/'artifacts/build_snapshot.json');ev=read(root/'artifacts/build_evidence.json')
 assert snap['run_id']==ev['run_id']==run
 assert ev['timing']=='All Constraints Met' and ev['max_skew_verified'] and ev['timing_scope_verified']
 assert sha(root/'artifacts/soc_top.sbit')==ev['outputs']['artifacts/soc_top.sbit']
 for n,h in snap['inputs'].items():assert sha(root/n)==h,n
 # Select only the production display contracts actually covered by these audits.
 width=read(root/'config/display.json')['width'] if (root/'config/display.json').exists() else 1280
 if width==1920:
  audit_path=Path(__file__).with_name('audit_gui1080_candidate.ps1')
  audit=audit_path.read_text(encoding='utf-8-sig')
  assert '[Parameter(Mandatory=$true)][string]$ExpectedRunId' in audit
  audit_kind='GUI1080_FULL_FROZEN_PROJECT_AUDIT'
 elif width==1280:
  assert run=='44aa982f752c4b7d91accea60292735f'
  audit_path=root/'scripts/audit_project.ps1';audit=audit_path.read_text(encoding='utf-8-sig')
  old='        throw "Prohibited Verilog function in $relative"'
  assert audit.count(old)==1
  hashes='\n'.join('            '+quote(n)+' = '+quote(h) for n,h in FUNCTIONS.items())
  replacement='''        $known=@{
HASHES
        }
        $actual=(Get-FileHash -LiteralPath (Join-Path $Root $relative) -Algorithm SHA256).Hash.ToLowerInvariant()
        if(!$known.ContainsKey($relative) -or $known[$relative] -cne $actual){throw "Prohibited new or modified Verilog function in $relative"}'''.replace('HASHES',hashes)
  audit=audit.replace(old,replacement)
  param='[Parameter(Mandatory=$true)][string]$ExpectedRunId, '
  assert audit.count('param(')>=1
  audit=audit.replace('param(', 'param('+param,1)
  marker="$ErrorActionPreference = 'Stop'"
  assert audit.count(marker)==1
  bind="\n$actualRun=([IO.File]::ReadAllText((Join-Path $Root 'artifacts/build_snapshot.json'))|ConvertFrom-Json).run_id\nif($ExpectedRunId -cne '44aa982f752c4b7d91accea60292735f' -or $actualRun -cne $ExpectedRunId){throw 'Wrong approved R3 native run'}\n"
  audit=audit.replace(marker,marker+bind)
  audit_kind='APPROVED_R3_FULL_PROJECT_AUDIT_EXACT_INHERITED_FUNCTIONS'
 else:raise AssertionError(('Unsupported production display',width))
 if width==1920:
  audit,selected_functions=adapt_voice75_functions(root,audit)
 else:selected_functions=FUNCTIONS
 for n,h in selected_functions.items():assert sha(root/n)==h,n
 scripts=quote((root/'scripts').as_posix())
 audit=audit.replace('$PSScriptRoot',scripts)
 effective_audit=out/'project_audit_effective.ps1';effective_audit.write_text(audit,encoding='utf-8')
 original=root/'scripts/program_cram.ps1'
 assert sha(original)=='e77967f5b72c43b1a213b660439672f5a3daf8caf502bd231e5e0e7f7a1cd6da','Unreviewed CRAM programmer source'
 text=original.read_text(encoding='utf-8-sig')
 line="    & (Join-Path $PSScriptRoot 'audit_project.ps1') -Root $Root | ForEach-Object { Write-Host $_ }"
 assert text.count(line)==1
 text=text.replace(line,'    & '+quote(effective_audit.as_posix())+' -Root $Root -ExpectedRunId '+quote(run)+' | ForEach-Object { Write-Host $_ }')
 count=text.count('$PSScriptRoot');assert count==4,count
 text=text.replace('$PSScriptRoot',scripts)
 # CDT writes *_run.tcl and configuration_tcl.log beside its input scripts.
 # Preserve the independently unpacked project by using exact template copies
 # and an external working/report directory. All arguments remain absolute.
 templates={}
 for name in ['pds_program_cram.tcl','pds_scan_chain.tcl']:
  shutil.copy2(root/'scripts'/name,out/name)
  assert sha(out/name)==sha(root/'scripts'/name)
  templates[name]=sha(out/name)
  old='Join-Path '+scripts+' '+quote(name)
  assert text.count(old)==1
  text=text.replace(old,'Join-Path '+quote(out.as_posix())+' '+quote(name))
 assert text.count('-WorkingDirectory $root')==3
 text=text.replace('-WorkingDirectory $root','-WorkingDirectory '+quote(out.as_posix()))
 assert text.count("'-port', \"$JtagServerPort\", '-work_dir', $root")==1
 text=text.replace("'-port', \"$JtagServerPort\", '-work_dir', $root","'-port', \"$JtagServerPort\", '-work_dir', "+quote(out.as_posix()))
 effective=out/'program_cram_effective.ps1';effective.write_text(text,encoding='utf-8')
 return dict(root=str(root),run_id=run,bitstream_sha256=sha(root/'artifacts/soc_top.sbit'),
  source_programmer_sha256=sha(original),effective_programmer_sha256=sha(effective),
  source_audit_sha256=sha(audit_path),effective_audit_sha256=sha(effective_audit),
  audit_kind=audit_kind,inherited_function_sources=selected_functions,anchored_programmer_helper_paths=count,
  configuration_templates_sha256=templates,
  adaptation='Replace full audit dispatch, anchor helper paths and relocate unchanged configuration Tcl copies/work directories to external evidence. No device, timing, bitstream, configuration Tcl content, CRAM or DONE check removed',
  effective_programmer=str(effective),effective_audit=str(effective_audit))

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 for n in ['root','output']:ap.add_argument('--'+n,type=Path,required=True)
 ap.add_argument('--expected-run',required=True)
 ap.add_argument('--jtag-server-port',type=int,default=65420)
 mode=ap.add_mutually_exclusive_group();mode.add_argument('--program',action='store_true');mode.add_argument('--scan-only',action='store_true')
 a=ap.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
 assert 1<=a.jtag_server_port<=65535
 result=dict(status='FULL_PROJECT_PROGRAM_ADAPTER_PREFLIGHT',started_utc=datetime.now(timezone.utc).isoformat(),flash_written=False)
 def save():(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 save()
 try:
  result['adapter']=prepare(a.root,a.expected_run,out);save()
  def run(mode):
   command=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',result['adapter']['effective_programmer'],'-'+mode,'-JtagServerPort',str(a.jtag_server_port),'-PdsRoot','G:/fpga/PDS_2022.2-SP6.4','-LogPath',str(out/(mode+'.log')),'-EvidencePath',str(out/(mode+'.json'))]
   result['command']=command;save()
   with (out/(mode+'-owner.log')).open('xb') as log:p=subprocess.run(command,cwd=a.root,stdout=log,stderr=subprocess.STDOUT,timeout=400)
   assert p.returncode==0,(mode,out/(mode+'-owner.log'))
   if mode=='DryRun':assert b'DRY_RUN_PASS:' in (out/(mode+'-owner.log')).read_bytes()
  run('DryRun');result['status']='FULL_PROJECT_AUDIT_ADAPTER_DRY_RUN_PASS_NO_BOARD';save()
  if a.program:
   run('Program');p=read(out/'Program.json')
   assert p['status']=='PASS' and p['device_id']=='0x00602899' and p['bitstream_sha256']==result['adapter']['bitstream_sha256']
   result.update(status='FULL_PROJECT_AUDIT_VOLATILE_CRAM_PROGRAM_PASS',program_receipt_sha256=sha(out/'Program.json'))
  elif a.scan_only:
   run('ScanOnly');assert b'SCAN_ONLY_PASS:' in (out/'ScanOnly-owner.log').read_bytes()
   result['status']='FULL_PROJECT_AUDIT_READ_ONLY_JTAG_SCAN_PASS_NO_PROGRAM'
 except Exception:
  result.update(status='FAILED_PROGRAM_AUDIT_ADAPTER_PRESERVED',error=traceback.format_exc());save();raise
 finally:
  result['completed_utc']=datetime.now(timezone.utc).isoformat();save();print(result['status'],flush=True)
if __name__=='__main__':main()
