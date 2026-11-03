"""Inject faults into actual mapped IB metadata; never modify the native input."""
import argparse,hashlib,json,re
from pathlib import Path
from audit_ib_rf_metadata_ads import audit
from audit_icache_pad_ads import module,cells,ports,clean

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--netlist',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    assert not a.output.exists();raw=a.netlist.read_bytes();source=clean(raw.decode());positive=audit(source)
    body=module(source,'InstBuffer');match=re.search(r'(?m)^\s*(\w+)\s+bank_0_ext\s*\(',body);assert match
    kind=match[1];bank=next(m for m in cells(body,kind) if m['name']=='bank_0_ext');ram=module(source,kind)
    meta=next(m for m in cells(ram,'GTP_RAM32X2DP') if 'W0_data[80]' in ports(m['ports'])['DI'])
    def replace_once(text,old,new):
        assert text.count(old)==1,(old,text.count(old));return text.replace(old,new,1)
    def within(outer,old_body,new_body):return replace_once(outer,old_body,new_body)
    faults=[]
    for label,port,new in [('ram_clock','WCLK',"1'b0"),('ram_enable','WE',"1'b1"),('ram_write_address','WADDR',"5'b0"),('ram_read_address','RADDR',"5'b0"),('ram_metadata_di','DI','{W0_data[81], W0_data[81]}'),('ram_metadata_do','DO','{R0_data[80], R0_data[81]}')]:
        changed,n=re.subn(r'\.'+port+r'\s*\([^()]*\)',lambda _:'.'+port+' ('+new+')',meta.group());assert n==1
        faults.append((label,within(source,ram,within(ram,meta.group(),changed))))
    for label,transform in [('bank_clock',lambda s:re.sub(r'\.R0_clk\s*\([^()]*\)',".R0_clk (1'b0)",s)),
                            ('capture_metadata_zero',lambda s:re.sub(r'(\.W0_data\s*\(\s*\{)[^,]+',lambda m:m[1]+"1'b0",s))]:
        changed=transform(bank.group());assert changed!=bank.group();faults.append((label,within(source,body,within(body,bank.group(),changed))))
    for label,mutant in faults:
        assert mutant!=source
    results=[]
    for label,mutant in faults:
        try:audit(mutant)
        except (AssertionError,ValueError) as e:results.append(dict(case=label,status='REJECTED',diagnostic=str(e),mutated_netlist_sha256=hashlib.sha256(mutant.encode()).hexdigest()))
        else:raise AssertionError('Fault escaped: '+label)
    assert a.netlist.read_bytes()==raw
    r=dict(status='IB_RF_METADATA_NATIVE_MUTATIONS_PASS',scope='Read-only native fault fixtures; no new hardware acceptance',netlist_sha256=hashlib.sha256(raw).hexdigest(),positive=positive,faults=results,source_sha256={n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in ['test_ib_rf_metadata_ads.py','audit_ib_rf_metadata_ads.py','audit_cpu_ads.py','audit_icache_pad_ads.py','ads_bdd.py','ads_frontend_ib_cone.py']})
    a.output.write_text(json.dumps(r,indent=2)+'\n');print(r['status'],'faults='+str(len(results)))

if __name__=='__main__':main()
