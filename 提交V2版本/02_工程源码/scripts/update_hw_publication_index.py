"""Register verified hardware publication and its software handoff; no cleanup."""
from pathlib import Path
import json,re,subprocess,sys
R=Path(__file__).resolve().parents[1];C=Path('G:/fpga/performance_soc_voice_hw');W=Path('G:/fpga')
group=dict(patterns=['performance_soc_hw_publish_20261025'],role='已验证硬件独立分支推送与软件优化交接',policy='用户2026-10-25明确授权推送已验证硬件；仅vision32_layer.v及原生e42位流/STA/板测证据、测试和文档；软件优化代码留本地，CoreMark A/B待，main与正式交付不变。')
shared=json.loads((C/'scripts/project_directory_catalog.json').read_text(encoding='utf-8'))['workspace_groups']
for root in [R,C]:
 p=root/'scripts/project_directory_catalog.json';d=json.loads(p.read_text(encoding='utf-8'))
 groups=[group]+shared+d['workspace_groups'];seen=set();unique=[]
 for g in groups:
  key=tuple(g['patterns'])
  if key not in seen:unique.append(g);seen.add(key)
 d['workspace_groups']=unique;p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 for tail in [[],['--check']]:subprocess.run([sys.executable,'-X','utf8',str(root/'scripts/update_project_index.py'),*tail],cwd=root,check=True)
p=W/'PROJECT_INDEX.md';text=p.read_bytes().decode('utf-8');begin='<!-- HW_PUBLICATION_INDEX_20261025_BEGIN -->';end='<!-- HW_PUBLICATION_INDEX_20261025_END -->'
block=begin+'\n- [已验证硬件推送](performance_soc_hw_publish_20261025/docs/Validated_Hardware_Publication_20261025.md)；[软件优化方向交接](performance_soc_hw_publish_20261025/docs/Software_Optimization_Handoff_20261025.md)：独立hardware/validated-accelerators-20261025分支，原main保留，原生e42/STA及板测证据绑定。\n'+end+'\n'
if begin in text:text=re.sub(re.escape(begin)+r'[\s\S]*?'+re.escape(end),lambda _:block.strip(),text,count=1)
else:
 first,tail=text.split('\n',1);text=first+'\n\n'+block+'\n'+tail
p.write_bytes(text.encode('utf-8'));print('HARDWARE_PUBLICATION_INDEX_UPDATED_NO_CLEANUP')
