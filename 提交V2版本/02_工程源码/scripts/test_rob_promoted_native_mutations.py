"""Actual-netlist positive and in-memory native RF mutation checks; no PnR."""
from pathlib import Path
import argparse,hashlib,json,re
from audit_rob_owner_ads import audit,RF_PATH
from audit_rob_promoted_reads_ads import prove,CofactorHierarchy
from audit_icache_pad_ads import module,clean,cells,ports

def main():
    p=argparse.ArgumentParser();p.add_argument('--netlist',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    assert not a.output.exists();raw=a.netlist.read_bytes();text=raw.decode();h=CofactorHierarchy(text)
    positive=audit(text,promoted_reads=True);assert positive['status']=='PASS' and len(positive['promoted_read_contract']['reads'])==2
    checks=[]
    def reject(name,mutated,entry,expected):
        assert mutated!=text
        try:entry(mutated)
        except (ValueError,KeyError,AssertionError) as e:
            assert expected in str(e),(name,str(e));checks.append(dict(name=name,status='REJECTED',reason=str(e)));return
        raise AssertionError('Native mutation was accepted: '+name)
    backend=RF_PATH[:-2];rob=RF_PATH[:-1];dispatch=backend+('u_dispatch',)
    def invert_at(path,net):
        context,wire=h.canonical(path,net);kind=h.context(context)[0];node,pin=h.module(kind)['cone'].drivers[wire]
        assert node['kind'].startswith('GTP_LUT')
        old=module(text,kind);body=clean(old)
        matches=[m for m in cells(body,node['kind']) if m['name'].lstrip('\\')==node['name'].lstrip('\\')];assert len(matches)==1;m=matches[0]
        params=ports(m['params']);init=params['INIT'];number=re.fullmatch(r"(\d+)'([bBhH])([0-9a-fA-F_]+)",init);assert number,init
        width=int(number[1]);value=int(number[3].replace('_',''),2 if number[2].lower()=='b' else 16)^((1<<width)-1)
        replacement,n=re.subn(r"\.INIT\s*\([^()]*\)",'.INIT ('+str(width)+"'h"+format(value,'x')+')',m[0]);assert n==1
        changed=body[:m.start()]+replacement+body[m.end():];assert text.count(old)==1
        return text.replace(old,changed)
    reject('effective_read_actual_producer_INIT_inverted',invert_at(dispatch,'io_robRdata_0[0]'),prove,'Effective RF read mismatch')
    old=module(text,'CoreBackend');body=clean(old);matches=[m for m in cells(body,'Dispatch') if m['name']=='u_dispatch'];assert len(matches)==1;m=matches[0]
    replacement,n=re.subn(r'\.io_robRdata_0\s*\([^()]*\)',".io_robRdata_0 (32'b0)",m[0]);assert n==1
    changed=body[:m.start()]+replacement+body[m.end():]
    reject('actual_dispatch_consumer_binding_zero',text.replace(old,changed),prove,'Actual dispatch/Rob read binding differs')
    rf=h.module('RobTagRegisterFile');we=rf['instances']['resultBanks_0_ext'][1]['W0_en']
    reject('actual_bank0_WE_producer_INIT_inverted',invert_at(RF_PATH,we),lambda source:audit(source,promoted_reads=True),'RAM WE truth table differs')
    wire,node=next((wire,node) for wire,(node,pin) in rf['cone'].drivers.items() if pin=='Q' and wire=='resultOwner_0_reg[1]')
    old=module(text,'RobTagRegisterFile');body=clean(old);matches=[m for m in cells(body,node['kind']) if m['name'].lstrip('\\')==node['name'].lstrip('\\')];assert len(matches)==1;m=matches[0]
    reject('actual_owner_FF_removed',text.replace(old,body[:m.start()]+body[m.end():]),lambda source:audit(source,promoted_reads=True),'Unexpected owner one-hot state topology')
    assert a.netlist.read_bytes()==raw
    result=dict(status='NATIVE_PROMOTED_RF_POSITIVE_AND_FOUR_ACTUAL_MUTATIONS_PASS_NOT_STA',netlist_sha256=hashlib.sha256(raw).hexdigest(),positive=positive,checks=checks,checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
if __name__=='__main__':main()
