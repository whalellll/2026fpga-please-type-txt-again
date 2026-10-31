"""Exact binary native graph conversion with bounded SAT; unknown leaves reject."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent/'tools/python'))
import z3

class NativeSat:
    def __init__(self,g):
        self.g=g; self.solver=z3.Solver(); self.solver.set(timeout=15000)
        self.symbols={}; self.leaves=set(); self.constraints=0
    def bit(self,key):
        assert key is not None and key[0]!=('UNKNOWN',),('Unknown SAT bit',key)
        if key[1] in ["1'b0","1'b1"]:return z3.BoolVal(key[1][-1]=='1')
        if key in self.symbols:return self.symbols[key]
        node=self.g.nodes.get(key)
        assert node is not None,('Unbuilt native bit',key)
        value=z3.Bool('native_'+str(len(self.symbols))); self.symbols[key]=value
        if node[0]=='const':self.solver.add(value==bool(node[1])); self.constraints+=1
        elif node[0]=='truth':
            pins=[self.bit(child) for child in node[2]]
            def truth(table,width):
                if width==0:return z3.BoolVal(bool(table&1))
                half=1<<(width-1);mask=(1<<half)-1
                return z3.If(pins[width-1],truth(table>>half,width-1),truth(table&mask,width-1))
            self.solver.add(value==truth(node[1],len(pins))); self.constraints+=1
        else:
            assert node[0] in ['input','ff','ram','opaque_native_data','external'],('Unreviewed native leaf',key,node)
            self.leaves.add(key)
        return value
    def net(self,ctx,net):return self.bit(self.g.build(ctx,net))
    def word(self,ctx,nets):
        bits=[self.net(ctx,n) for n in nets]
        return z3.Concat(*[z3.If(v,z3.BitVecVal(1,1),z3.BitVecVal(0,1))for v in reversed(bits)])
    def prove(self,label,actual,expected,condition=None):
        condition=z3.BoolVal(True) if condition is None else condition
        self.solver.push();self.solver.add(condition);reachable=self.solver.check();self.solver.pop()
        assert reachable==z3.sat,('Proof condition unproven/unreachable',label,str(reachable))
        self.solver.push();self.solver.add(condition,actual!=expected);answer=self.solver.check()
        reason=self.solver.reason_unknown() if answer==z3.unknown else None
        witness=str(self.solver.model())[:1200] if answer==z3.sat else None
        self.solver.pop()
        assert answer==z3.unsat,('Native mismatch or incomplete proof',label,str(answer),reason,witness)
        return dict(label=label,condition_satisfiable=True,result='UNSAT',solver_version=z3.get_version_string(),
                    native_nodes=len(self.symbols),constraints=self.constraints)
