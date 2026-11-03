"""Read native routed summaries without hiding failed corners or clock pairs."""
import argparse,hashlib,json,xml.etree.ElementTree as ET
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--native-root',type=Path,required=True)
 ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 root=a.native_root.resolve();pds=root/'pds';xml=pds/'report_timing/rtr.db'
 tables={t.attrib['id']:t for t in ET.parse(xml).getroot().findall('table')}
 rows=[];violations=[]
 for corner in ('slow','fast'):
  for kind in ('setup','hold','recovery','removal','mpw'):
   table=tables[f'report_timing_{corner}_{kind}']
   for row in table.findall('row'):
    cells=[''.join(c.itertext()).strip() for c in row.findall('data')]
    off=1 if kind=='mpw' else 2
    assert len(cells)==off+4,(corner,kind,cells)
    r=dict(corner=corner,kind=kind,clocks=cells[:off],wns_ns=float(cells[off]),tns_ns=float(cells[off+1]),violating_endpoints=int(cells[off+2]),endpoints=int(cells[off+3]),abnormal=row.attrib.get('abnormal',''))
    rows.append(r)
    if r['wns_ns']<0 or r['tns_ns']!=0 or r['violating_endpoints']!=0:violations.append(r)
 snapshot=json.loads((pds/'build_snapshot.json').read_text(encoding='utf-8-sig'))
 receipt_path=pds/'input-snapshots'/snapshot['run_id']/'physical-result.json'
 if not receipt_path.exists():
  receipt_path=root/'physical-launch.json'
  receipt=json.loads(receipt_path.read_text(encoding='utf-8-sig'))
  assert receipt['status'] in ['ROUTED_FULL_STA_PASS_NOT_BOARD','ROUTED_STA_FAILED_NOT_BOARD'] and receipt['pnr_complete']
  assert receipt['snapshot_sha256']==sha(pds/'build_snapshot.json')
  for rel in ['report_timing/soc_top.rtr','report_timing/rtr.db']:
   assert receipt['reports'][rel]==sha(pds/rel),rel
 else:receipt=json.loads(receipt_path.read_text(encoding='utf-8-sig'))
 assert receipt['run_id']==snapshot['run_id']
 reports={f.as_posix():sha(f) for f in (xml,pds/'report_timing/soc_top.rtr',receipt_path)}
 focus={}
 for clock in ('cpu_clk','sys_clk'):
  for kind in ('setup','hold'):
   group=[r for r in rows if r['kind']==kind and r['clocks']==[clock,clock]]
   assert len(group)==2,(clock,kind,group)
   focus[clock+'_'+kind]=min(group,key=lambda r:r['wns_ns'])
 report=dict(status=receipt['status'],run_id=receipt['run_id'],native_root=root.as_posix(),reports_sha256=reports,
             summary_row_count=len(rows),summary=rows,violations=violations,focus=focus,
             physical_receipt=receipt,parser_sha256=sha(Path(__file__)),scope='Routed STA evidence only; not board or driver acceptance')
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(dict(status=receipt['status'],summary_rows=len(rows),violations=violations,focus=focus)))
if __name__=='__main__':main()
