"""Reject the original truncated-initrd failure despite internally valid FDT."""
from pathlib import Path
import argparse,struct,json
from verify_cpu120_board_release import verify_initrd_bounds,fdt
def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 dtb=a.root/'linux/boot/soc.dtb';size=(a.root/'linux/boot/rootfs.cpio').stat().st_size;props=verify_initrd_bounds(dtb,size);raw=dtb.read_bytes()
 old=props['/chosen','linux,initrd-end'];assert raw.count(old)==1
 rejected=[]
 for label,delta in [('original-truncation',-346624),('one-byte-short',-1),('one-byte-long',1)]:
  new=struct.pack('>I',struct.unpack('>I',old)[0]+delta);path=a.output/(label+'.dtb');path.write_bytes(raw.replace(old,new));assert fdt(path)['/chosen','linux,initrd-end']==new
  try:verify_initrd_bounds(path,size)
  except AssertionError:rejected.append(label)
  else:raise AssertionError('Invalid initrd bounds accepted: '+label)
 # Truncated CPIO and wrong runtime frequencies cannot pass the same gate.
 try:verify_initrd_bounds(dtb,size-1)
 except AssertionError:rejected.append('actual-rootfs-length-mismatch')
 else:raise AssertionError('Wrong actual rootfs size accepted')
 r=dict(status='CPU120_VALID_FDT_ORIGINAL_TRUNCATION_AND_BOUNDARY_NEGATIVES_REJECTED_PASS',valid_initrd_bytes=size,rejected=rejected)
 (a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(r['status'])
if __name__=='__main__':main()
