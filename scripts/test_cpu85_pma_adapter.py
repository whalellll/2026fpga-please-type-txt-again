"""Exercise actual mapped PMA page boundary and reject three targeted faults."""
from pathlib import Path
import argparse,hashlib,json
import audit_cpu85_half_ads as a
p=argparse.ArgumentParser();p.add_argument('--netlist',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
assert not args.output.exists();raw=args.netlist.read_bytes();source=raw.decode();proof=a.prove_boundary(source);assert proof['cases']==1024
base=a.original.Cone;ports=a.original.instance_ports;cases=[]
for name in ['producer_positive_bit_removed','consumer_positive_bit_removed','parent_link_disconnected']:
    class MutatedCone(base):
        def __init__(self,source,module):
            super().__init__(source,module)
            if name=='producer_positive_bit_removed' and module=='PmaMmu':
                self.drivers['N92'][0]['init']^=1<<43
            if name=='consumer_positive_bit_removed' and module=='CoreFrontend':
                ff=self.primitive('fcFaults[7]');target=ff['ports']['D'];node=self.primitive(target)
                bit=sum(1<<i for i in range(6) if node['ports']['I'+str(i)] in [a.PAGE,'io_ifu_pma_req',"1'b1"])
                if node['output']=='Z5':bit &= 31
                self.drivers[target][0]['init']^=1<<bit
    def bad_ports(source,parent,child,instance):
        d=ports(source,parent,child,instance)
        if name=='parent_link_disconnected' and parent=='Core' and child=='CoreFrontend':
            d=dict(d);d[a.PAGE]='disconnected_page_wire'
        return d
    a.original.Cone=MutatedCone;a.original.instance_ports=bad_ports
    try:
        try:a.prove_boundary(source)
        except AssertionError:cases.append(name)
        else:raise RuntimeError('Mapped PMA fault accepted: '+name)
    finally:a.original.Cone=base;a.original.instance_ports=ports
assert args.netlist.read_bytes()==raw
args.output.write_text(json.dumps(dict(status='NATIVE_PMA_PAGE_1024_CASES_AND_THREE_FAULTS_PASS_NOT_STA',netlist_sha256=hashlib.sha256(raw).hexdigest(),adapter_sha256=hashlib.sha256(Path(a.__file__).read_bytes()).hexdigest(),cases=proof['cases'],faults=cases),indent=2)+'\n')
print('NATIVE_PMA_PAGE_1024_CASES_AND_THREE_FAULTS_PASS_NOT_STA')
