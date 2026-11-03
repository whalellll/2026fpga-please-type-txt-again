"""Exhaustive soundness check of conservative free-value LUT cofactors."""
import itertools
from audit_rob_promoted_reads_ads import CofactorHierarchy
class Harness(CofactorHierarchy):
    def __init__(self,table):self.table=table
    def driver(self,path,wire):
        if wire=='out':return 'lut',(self.table,tuple(((),n) for n in ('a','b','c')))
        return 'free',None
def main():
    count=0
    for table in range(256):
        h=Harness(table)
        for values in itertools.product((None,0,1),repeat=3):
            stops={((),name):value for name,value in zip(('a','b','c'),values) if value is not None}
            concrete={(table>>index)&1 for index in range(8) if all(v is None or (index>>i)&1==v for i,v in enumerate(values))}
            expected=next(iter(concrete)) if len(concrete)==1 else None
            assert h.evaluate((),'out',stops)==expected,(table,values)
            count+=1
    print('ROB_PROMOTED_TERNARY_COFACTOR_SOUNDNESS_PASS cases='+str(count))
if __name__=='__main__':main()
