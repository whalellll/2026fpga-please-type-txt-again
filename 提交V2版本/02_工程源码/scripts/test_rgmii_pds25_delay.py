"""Check PG2L100H TX delay migration using the unmodified vendor timing model."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
 p.add_argument('--output',type=Path,required=True)
 p.add_argument('--vendor-model',type=Path,required=True)
 p.add_argument('--icarus-bin',type=Path)
 p.add_argument('--wsl-distro')
 a=p.parse_args();s=a.root.resolve();o=a.output.resolve();o.mkdir(parents=True,exist_ok=False)
 tmp=o/'tmp';tmp.mkdir()
 sha=lambda x:hashlib.sha256(x.read_bytes()).hexdigest()
 def wp(x):
  x=x.resolve().as_posix();assert x[1:3]==':/'
  return '/mnt/'+x[0].lower()+'/'+x[3:]
 rows=[]
 for name,top,files in [
  ('register','tb_eth_tx_delay_limit',[s/'sim/tb_eth_tx_delay_limit.v',s/'rtl/eth/eth_mac_mmio.v']),
  ('vendor-delay','tb_rgmii_tx_delay_pds25',[s/'sim/tb_rgmii_tx_delay_pds25.v',s/'rtl/eth/rgmii_interface.v',a.vendor_model]),
  ('frame-crc','tb_eth_mac_mmio',[s/'sim/tb_eth_mac_mmio.v',s/'rtl/eth/eth_mac_mmio.v']),
  ('100m-byte-alignment','tb_rgmii_100m',[s/'sim/tb_rgmii_100m.v',s/'rtl/eth/rgmii_interface.v'])]:
  image=o/(name+'.vvp');log=o/(name+'.log')
  env=dict(os.environ,TMP=str(tmp),TEMP=str(tmp),TMPDIR=str(tmp))
  if a.wsl_distro:
   # Literal paths avoid a host shell expanding Linux temporary variables.
   script='export TMP='+wp(tmp)+' TEMP='+wp(tmp)+' TMPDIR='+wp(tmp)+'; iverilog -g2012 -s '+top+' -o '+wp(image)+' '+' '.join(wp(x) for x in files)+' && vvp '+wp(image)
   commands=[['wsl.exe','-d',a.wsl_distro,'--','bash','-lc',script]]
  else:
   exe=lambda n:str(a.icarus_bin/(n+('.exe' if os.name=='nt' else ''))) if a.icarus_bin else n
   commands=[[exe('iverilog'),'-g2012','-s',top,'-o',str(image),*[str(x) for x in files]],[exe('vvp'),str(image)]]
  with log.open('xb') as output:
   for cmd in commands:
    r=subprocess.run(cmd,cwd=s,env=env,stdout=output,stderr=subprocess.STDOUT,timeout=180)
    if r.returncode:break
  passed=r.returncode==0 and image.exists() and b'PASS ' in log.read_bytes()
  rows.append(dict(name=name,passed=passed,exit_code=r.returncode,source_sha256={str(x.relative_to(s)) if x.is_relative_to(s) else str(x):sha(x) for x in files},log_sha256=sha(log)))
  print(name,'PASS' if passed else 'FAIL',flush=True)
 result=dict(status='RGMII_PDS25_VENDOR_DELAY_AND_ETHERNET_REGRESSION_PASS' if all(x['passed'] for x in rows) else 'FAIL',checks=rows,
             scope='Vendor simulation model:256 settings/512 edge delays; MMIO saturation/readback, byte strobes, defaults, Ethernet payload/FCS and100M alignment. No board timing acceptance.')
 (o/'result.json').write_text(json.dumps(result,indent=2)+'\n');return 0 if result['status']!='FAIL' else 2
if __name__=='__main__':sys.exit(main())
