"""Require real mapped-cache proofs to reject semantic decoder corruption."""
from pathlib import Path
import argparse,hashlib,json,re
from audit_cpu_ads import Cone,signal
from audit_icache_pad_ads import module,cells,ports
from vision32_cache_contract import cache_contract

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--netlist',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);source=a.netlist.read_text()
    clean=re.sub(r'/\*.*?\*/|//[^\n]*','',source,flags=re.S)
    positive=cache_contract(clean);body=module(clean,'vision32_layer')
    memories={c['name']:ports(c['ports']) for c in cells(body,'GTP_RAM64X1DP')}
    target=memories['weight_lo_0_0']['WE'];cone=Cone(clean,'vision32_layer')
    while target in cone.aliases:target=cone.aliases[target]
    node,out=cone.drivers[target];assert node['kind'].startswith('GTP_LUT') and node['init'] is not None
    primitive=re.compile(r'\b(GTP_\w+)\s*(?:#\s*\((.*?)\))?\s+(\\[^\s]+|\w+)\s*\((.*?)\);',re.S)
    matches=[m for m in primitive.finditer(body) if signal(m[3])==node['name']];assert len(matches)==1
    m=matches[0];params=m[2]
    init=re.search(r"\.INIT\s*\(\s*(\d+)'([bh])([0-9a-fA-F_]+)",params);assert init
    inverted=((1<<int(init[1]))-1)^int(init[3].replace('_',''),2 if init[2]=='b' else 16)
    changed=params[:init.start(3)]+(format(inverted,'b') if init[2]=='b' else format(inverted,'x'))+params[init.end(3):]
    cell=m[0].replace(params,changed,1);badbody=body[:m.start()]+cell+body[m.end():]
    mutated=clean.replace(body,badbody,1);assert mutated!=clean
    (a.output/'inverted-native-decoder.v').write_text(mutated)
    try:cache_contract(mutated)
    except AssertionError as e:
        error=str(e);assert 'decoder' in error.lower() and 'mismatch' in error.lower(),error
    else:raise AssertionError('Corrupt bank decoder accepted')
    sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
    q=dict(status='NATIVE_CACHE_POSITIVE_AND_SEMANTIC_DECODER_MUTATION_REJECTION_PASS_NOT_HARDWARE',input_netlist_sha256=sha(a.netlist),checker_sha256=sha(Path(__file__).with_name('vision32_cache_contract.py')),positive=positive,mutation=dict(primitive=node['name'],output=out,inverted_init=True,rejection=error,fixture_sha256=sha(a.output/'inverted-native-decoder.v')),scope='One real weight-bank LUT INIT inversion with unchanged support and hierarchy. Synthetic corruption proves rejection, not a new mapped implementation.')
    (a.output/'result.json').write_text(json.dumps(q,indent=2)+'\n');print(q['status'])
if __name__=='__main__':main()
