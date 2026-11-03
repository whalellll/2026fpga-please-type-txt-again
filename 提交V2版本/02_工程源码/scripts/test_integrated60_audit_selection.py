"""Exercise both exact PowerShell combined-audit selectors on all profiles."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,tempfile,itertools
R=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--output',required=True,type=Path);a=ap.parse_args();assert not a.output.exists()
rows=[];hashes={}
for name in ['build_cpu_ads_gate.ps1','build_fpga.ps1']:
 p=R/'scripts'/name;s=p.read_text();m=re.findall(r'(?m)^\s*\$integratedCpuAdapter = (.*)$',s);assert len(m)==1
 assert s.count("'scripts/audit_integrated60_ads.py'")>=1
 assert 'ACTUAL_PMA_AND_RAS_BOUNDARIES_WITH_UNCHANGED_CPU_ORACLE_PASS' in s and '$result.pma_page_export_contract.cases -ne 1024' in s
 hashes[name]=hashlib.sha256(p.read_bytes()).hexdigest()
 with tempfile.TemporaryDirectory(prefix='i60-audit-selector-') as d:
  root=Path(d);(root/'rtl/soc').mkdir(parents=True)
  for voice,cnn,vision,dedicated in itertools.product(range(2),repeat=4):
   top=f'.ENABLE_NNUE_PIPELINE({voice}) .CNN_ENABLE({cnn}) .PIKAFISH_ONLY({dedicated}) parameter integer ENABLE_VISION32_CANDIDATE = {vision}'
   (root/'rtl/soc/soc_top.v').write_text(top)
   script="$root='"+str(root).replace("'","''")+"'\n$voiceNnueAdapter=$"+str(bool(voice)).lower()+"\n[bool]("+m[0]+")"
   r=subprocess.run(['powershell.exe','-NoProfile','-Command',script],capture_output=True,text=True,timeout=30)
   expected=bool(voice and cnn and vision and dedicated)
   assert r.returncode==0 and r.stdout.strip()==str(expected),(name,top,r.stdout,r.stderr)
   rows.append(dict(entry=name,voice=voice,cnn=cnn,vision=vision,dedicated=dedicated,combined_adapter=expected))
a.output.write_text(json.dumps(dict(status='COMBINED_CPU_AUDIT_EXACT_SELECTORS_AND_PROOF_GUARDS_PASS_NOT_PDS',cases=rows,source_sha256=hashes),indent=2)+'\n');print('COMBINED_CPU_AUDIT_EXACT_SELECTORS_AND_PROOF_GUARDS_PASS cases=32')
