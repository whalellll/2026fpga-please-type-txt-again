"""Compare native SNR resource reports; retain hashes and full hierarchy rows."""
from pathlib import Path
import argparse, hashlib, json, re

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def read(p):
 text=p.read_text(encoding='utf-8',errors='replace')
 patterns={'lut':r'Total LUTs: (\d+)', 'ff':r'Total Registers: (\d+)',
           'lutram':r'LUTs as dram: (\d+)', 'drm36k':r'Total DRM = ([\d.]+)',
           'apm':r'Total APMs = ([\d.]+)'}
 total={k:float(re.search(v,text).group(1)) for k,v in patterns.items()}
 rows=[]
 for line in text.splitlines():
  if not line.startswith('|'):continue
  cols=[s.strip() for s in line.split('|')]
  if len(cols)<7 or not re.fullmatch(r'\d+',cols[2]):continue
  rows.append(dict(name=cols[1],**{k:float(cols[i]) for k,i in [('lut',2),('ff',3),('lutram',4),('apm',5),('drm36k',6)]}))
 return dict(path=p.as_posix(),sha256=digest(p),total=total,hierarchy=rows)

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--baseline',type=Path,required=True);ap.add_argument('--candidate',type=Path,required=True)
 ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 old,new=read(a.baseline.resolve()),read(a.candidate.resolve())
 delta={k:new['total'][k]-v for k,v in old['total'].items()}
 pct={k:round(delta[k]/v*100,3) for k,v in old['total'].items()}
 r=dict(status='NATIVE_SYNTHESIS_RESOURCES_ONLY_NOT_STA_OR_BOARD',baseline=old,candidate=new,
        delta=delta,delta_percent=pct,device_capacity=dict(lut=66600,ff=133200,drm36k=155,apm=240))
 a.output.parent.mkdir(parents=True,exist_ok=True)
 a.output.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(dict(baseline=old['total'],candidate=new['total'],delta=delta,delta_percent=pct)))
 for tag,data in [('baseline',old),('candidate',new)]:
  for row in data['hierarchy']:
   if any(x in row['name'] for x in ('u_mac_accel','g_nnue.u_nnue','u_dma_kernel','g_dedicated.u_chain','g_pff1.u_gather','g_conv.u_conv','u_voice_accel','u_transform')):
    print(tag,json.dumps(row))
if __name__=='__main__':main()
