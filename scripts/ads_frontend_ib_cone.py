"""Resolve native shared LUT terms across the actual CoreFrontend.buffer link."""
import re
from audit_cpu_ads import Cone,signal
from audit_icache_pad_ads import module,cells,ports

def widths(body):
    return {signal(name):int(high)+1 for high,name in re.findall(r'\b(?:input|output|wire)\s+\[(\d+):0\]\s+(\\\S+|\w+)',body)}

def expand(value,sizes):
    value=signal(value)
    if value.startswith('{') and value.endswith('}'):
        return [b for part in value[1:-1].split(',') for b in expand(part,sizes)]
    m=re.fullmatch(r"(\d+)'([bh])([0-9a-fA-FxX_]+)",value)
    if m:
        if 'x' in m[3].lower():return ["1'bx"]*int(m[1])
        n=int(m[3].replace('_',''),2 if m[2]=='b' else 16)
        return ["1'b"+str((n>>i)&1) for i in reversed(range(int(m[1])))]
    m=re.fullmatch(r'(.+)\[(\d+):(\d+)\]',value)
    if m:return [f'{m[1]}[{i}]' for i in range(int(m[2]),int(m[3])-1,-1)]
    if '[' in value:return [value]
    return [f'{value}[{i}]' for i in reversed(range(sizes[value]))] if sizes.get(value,1)>1 else [value]

def bind(source):
    parent=module(source,'CoreFrontend');child=module(source,'InstBuffer')
    links=cells(parent,'InstBuffer');assert len(links)==1 and links[0]['name']=='buffer','Actual frontend/IB link required'
    pairs=re.findall(r'\.(\\[^\s()]+|\w+)\s*\(([^()]*)\)',links[0]['ports'])
    pins={signal(n):signal(v) for n,v in pairs};assert len(pins)==len(pairs),'Duplicate IB port'
    sizes=widths(parent)
    declarations=re.findall(r'\b(input|output)\s+(?:\[(\d+):0\]\s+)?(\\\S+|\w+)\s*(?=[,\n])',child[:child.index(');')])
    mapping={};directions={}
    for direction,high,rawname in declarations:
        name=signal(rawname);assert name in pins,'Missing actual IB port '+name
        actual=expand(pins[name],sizes);count=int(high)+1 if high else 1
        assert len(actual)==count,'IB link width mismatch '+name
        local=[f'{name}[{i}]' for i in reversed(range(count))] if count>1 else [name]
        for a,b in zip(local,actual):mapping[a]=b;directions[a]=direction
    assert len(mapping)>100,'Incomplete IB port declaration parse'
    def translate(n):return n if n.startswith("1'b") else mapping.get(n,'__ib/'+n)
    combined=Cone(source,'CoreFrontend');local=Cone(source,'InstBuffer')
    for n,(node,port) in local.drivers.items():
        target=translate(n);mapped=dict(node,name='__ib/'+node['name'],ports={p:translate(v) for p,v in node['ports'].items()})
        assert target not in combined.drivers,'Multiple hierarchy output drivers '+target
        combined.drivers[target]=(mapped,port)
    for n,value in local.aliases.items():
        target=translate(n)
        assert target not in combined.aliases,'Multiple hierarchy aliases '+target
        combined.aliases[target]=translate(value)
    # Incoming cross-hierarchy ports must agree with the actual parent net.
    # Each driver was renamed via the complete declaration/connection mapping.
    return combined,translate,dict(instance='CoreFrontend.buffer',mapped_port_bits=len(mapping),child_module_sha256=__import__('hashlib').sha256(child.encode()).hexdigest())
