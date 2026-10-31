"""Strict vector/concatenation binding extension for native scalar LUT proofs."""
from functools import lru_cache
import re
from native_hier_cone import HierCone
from audit_cpu_ads import signal

class VectorHierCone(HierCone):
    @lru_cache(None)
    def declarations(self, kind):
        text=re.sub(r'/\*.*?\*/|//[^\n]*','',self.modules[kind],flags=re.S)
        result={}
        pattern=r'\b(?:input|output|inout|wire|reg)\s+(?:signed\s+)?(?:\[(\d+):(\d+)\]\s*)?(\\[^\s,;]+|\w+)'
        for high,low,name in re.findall(pattern,text):
            name=signal(name);value=(int(high),int(low)) if high else None
            assert name not in result or result[name]==value,('Conflicting declaration',kind,name)
            result[name]=value
        return result

    @lru_cache(None)
    def vector_bits(self, context, expression):
        text=signal(expression);kind=self.contexts[context][0]
        const=re.fullmatch(r"(\d+)'([bBoOdDhH])([0-9a-fA-F_xXzZ]+)",text)
        if const:
            width=int(const[1]);radix={'b':2,'o':8,'d':10,'h':16}[const[2].lower()];digits=const[3].replace('_','')
            assert width>0
            if any(ch.lower() in 'xz' for ch in digits):
                assert radix in [2,8,16],('Unknown decimal',text)
                group={2:1,8:3,16:4}[radix];out=[]
                for ch in reversed(digits):
                    if ch.lower() in 'xz':out.extend(["1'b"+ch.lower()]*group)
                    else:
                        value=int(ch,radix);out.extend("1'b"+str((value>>i)&1) for i in range(group))
                assert len(out)>=width,('Underspecified unknown literal',text)
                return tuple(out[:width])
            value=int(digits,radix);assert value<(1<<width),('Constant width',text)
            return tuple("1'b"+str((value>>i)&1) for i in range(width))
        if text.startswith('{'):
            assert text.endswith('}'),('Unbalanced concat',text)
            body=text[1:-1];rep=re.fullmatch(r'(\d+)\{(.*)\}',body)
            if rep:
                count=int(rep[1]);assert count>0
                return self.vector_bits(context,rep[2])*count
            parts=[];start=0;level=0
            for i,ch in enumerate(body):
                if ch=='{':level+=1
                elif ch=='}':level-=1;assert level>=0,('Concat nesting',text)
                elif ch==',' and level==0:parts.append(body[start:i]);start=i+1
            assert level==0,('Concat nesting',text)
            parts.append(body[start:]);assert all(parts)
            return tuple(bit for part in reversed(parts) for bit in self.vector_bits(context,part))
        declarations=self.declarations(kind)
        if text in declarations:
            width=declarations[text]
            if width is None:return (text,)
            high,low=width;step=1 if high>=low else -1
            return tuple(text+'['+str(i)+']' for i in range(low,high+step,step))
        select=re.fullmatch(r'(.+)\[(\d+)(?::(\d+))?\]',text)
        if select:
            base=select[1];high=int(select[2]);low=int(select[3]) if select[3] else high
            if base in declarations:
                width=declarations[base];assert width is not None,('Select scalar',text)
                assert min(width)<=min(high,low)<=max(high,low)<=max(width),('Out-of-range select',text,width)
            step=1 if high>=low else -1
            return tuple(base+'['+str(i)+']' for i in range(low,high+step,step))
        assert re.fullmatch(r'[A-Za-z_$][\w$./]*',text),('Unsupported expression',text)
        return (text,)

    @lru_cache(None)
    def scalar_aliases(self, context):
        kind=self.contexts[context][0];result={}
        for left,right in self.cone(kind).aliases.items():
            lefts=self.vector_bits(context,left);rights=self.vector_bits(context,right)
            assert len(lefts)==len(rights),('Alias width mismatch',kind,left,right)
            for a,b in zip(lefts,rights):
                assert a not in result or result[a]==b,('Multiple alias drivers',kind,a)
                result[a]=b
        return result

    @lru_cache(None)
    def input_binding(self, context, net):
        kind,parent,ports=self.contexts[context]
        if parent is None:return None
        found=[];directions=self.directions(kind)
        for name,value in ports.items():
            if directions.get(name) not in ('input','inout'):continue
            locals_=self.vector_bits(context,name)
            if net not in locals_:continue
            parents=self.vector_bits(parent,value)
            assert len(locals_)==len(parents),('Input port width mismatch',context,name,value,len(locals_),len(parents))
            found.append((parent,parents[locals_.index(net)]))
        assert len(found)<=1,('Duplicate input binding',context,net)
        return found[0] if found else None

    @lru_cache(None)
    def child_output_bindings(self, context):
        result={}
        for child in self.children(context):
            kind,_,ports=self.contexts[child];directions=self.directions(kind)
            for name,value in ports.items():
                if directions.get(name) not in ('output','inout') or not value:continue
                children=self.vector_bits(child,name);parents=self.vector_bits(context,value)
                assert len(children)==len(parents),('Output port width mismatch',child,name,value,len(children),len(parents))
                for parent,local in zip(parents,children):
                    result.setdefault(parent,[]).append((child,local))
        return result

    def canonical(self, context, net, active=None):
        active=set() if active is None else active;net=signal(net);key=(context,net)
        assert key not in active,('Port/alias cycle',key)
        active.add(key)
        try:
            kind,parent,ports=self.contexts[context];c=self.cone(kind)
            assert net not in ("1'bx","1'bz"),('Unknown value in requested proof',key)
            if net in ("1'b0","1'b1") or net in c.drivers:return key
            aliases=self.scalar_aliases(context)
            if net in aliases:return self.canonical(context,aliases[net],active)
            binding=self.input_binding(context,net)
            if binding is not None:target=binding
            else:
                base=re.sub(r'\[\d+\]$','',net)
                if parent is None and self.directions(kind).get(base) in ('input','inout'):return key
                matches=self.child_output_bindings(context).get(net,[])
                assert len(matches)==1,('Unknown/multiple scalar vector driver',key,matches)
                target=matches[0]
            self.hops.append((key,target))
            return self.canonical(*target,active=active)
        finally:active.remove(key)
