"""Read back PDS25 final sites/ports, priorities and split Max Skew XML reports."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,re,subprocess,shutil,xml.etree.ElementTree as ET
B=Path(__file__).resolve().parent;P=B/'source/pds';O=B/'physical-readback-01';O.mkdir(exist_ok=False)
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
q=read(B/'status.json');pre=read(B/'pnr-preflight-05/result.json')
assert not q['status'].startswith('RUNNING_')
I=Path('G:/fpga/PDS_2025.2-ads-win64/pango/PDS_2025.2-ads');env=dict(os.environ,TEMP=str(B/'tmp'),TMP=str(B/'tmp'),TMPDIR=str(B/'tmp'))
pnr=P/'prj_tasks/pnr_1/place_route/soc_top_pnr.adf';native_hash=sha(pnr)
dbargs=' -db {'+pnr.as_posix()+'} -compile_db {'+(P/'prj_tasks/syn_1/compile/soc_top_comp.adf').as_posix()+'} -synthesize_db {'+(P/'prj_tasks/syn_1/synthesize/soc_top_syn.adf').as_posix()+'} -devmap_db {'+(P/'prj_tasks/pnr_1/device_map/soc_top_map.adf').as_posix()+'} -pcf {'+Path(pre['native_placement_pcf']).as_posix()+'}'
commands=['create_project {'+(O/'readonly.pds').as_posix()+'} -syn_tool ads -project_type rtl -force','set_arch -family Logos2 -device PG2L100H -speedgrade -6 -package FBG676',
 'generate_constraint -check -module_inst {u_cpu/u_cpu_wrapper/u_cpu/core/backend/u_csr_trap}'+dbargs+' -file {'+(O/'csr-final.pcf').as_posix()+'}',
 'generate_constraint -dev_unit DRM -check -module_inst {u_cpu/u_cpu_wrapper/u_cpu/core/frontend/tage}'+dbargs+' -file {'+(O/'tage-final.pcf').as_posix()+'}',
 'generate_constraint -device IO -check'+dbargs+' -file {'+(O/'io-final.pcf').as_posix()+'}']
(O/'flow_input.tcl').write_text('\n'.join(commands)+'\n')
with (O/'stdout.log').open('wb') as out,(O/'stderr.log').open('wb') as err:
 result=subprocess.run([str(I/'bin/pds_shell.exe'),'-file','flow_input.tcl','-project_name','readonly_final_sites'],cwd=O,env=env,stdout=out,stderr=err,timeout=240)
assert result.returncode==0,'Native final export failed'
assert not re.search(r'(?m)^E:',(O/'stdout.log').read_text(errors='replace'))
assert sha(pnr)==native_hash,'Readback changed final PNR DB'
(O/'result.json').write_text(json.dumps(dict(status='FINAL_NATIVE_PHYSICAL_EXPORT_COMPLETE',pnr_adf_sha256=native_hash,files={p.name:sha(p) for p in O.glob('*.pcf')}),indent=2)+'\n');print('FINAL_NATIVE_PHYSICAL_EXPORT_COMPLETE')
