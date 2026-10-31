#!/usr/bin/env python3
"""Fixtures for exact frontend metadata ADS checking; no PDS or board operation."""
import argparse,hashlib,json,random
from pathlib import Path
from audit_cpu_ads import Cone
from audit_frontend_metadata_ads import patterns,evaluate,expected,audit_metadata
from ads_bdd import BDD,cone_evaluator

def fixture():
    lines=['module CoreFrontend ();']
    def lut(name,inputs,init):
        lines.append("GTP_LUT%d #(.INIT(%d'h%x)) %s (.Z(%s),%s);"%(
            len(inputs),1<<len(inputs),init,name+'_cell',name,
            ','.join('.I%d(%s)'%(n,v) for n,v in enumerate(inputs))))
    for lane in range(4):
        def d(bit):return 'D%d_%d'%(lane,bit)
        def n(name):return name+str(lane)
        for bit in range(32):
            name='pdInsts_%d[%d]'%(lane,bit)
            lines.append('GTP_DFF_E \\%s (.Q(\\%s ),.D(%s),.CLK(clock),.CE(fcToPd));'%(name,name,d(bit)))
        lut(n('jalLow'),[d(i) for i in range(6)],1<<0x2f)
        lut(n('jalrLow'),[d(i) for i in range(6)],1<<0x27)
        lut(n('jal'),[n('jalLow'),d(6)],8)
        lut(n('jalrOp'),[n('jalrLow'),d(6)],8)
        lut(n('functZero'),[d(i) for i in range(12,15)],1)
        lut(n('jalr'),[n('jalrOp'),n('functZero')],8)
        lut(n('rdZero'),[d(i) for i in range(7,12)],1)
        lut(n('rdLink'),[d(i) for i in [7,8,10,11]],2)
        lut(n('rsLink'),[d(i) for i in [15,16,18,19]],2)
        lut(n('retD'),[n('jalr'),n('rdZero'),n('rsLink')],0x80)
        lut(n('callD'),[n('jal'),n('jalr'),n('rdLink')],0xe0)
        for flag,data in [('Returns',n('retD')),('Calls',n('callD'))]:
            name='pd%s_%d'%(flag,lane)
            lines.append('GTP_DFF_E %s (.Q(%s),.D(%s),.CLK(clock),.CE(fcToPd));'%(name,name,data))
    return '\n'.join(lines)+'\nendmodule\n'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();rng=random.Random(0x8f1a);mask,bit=patterns(8);cases=0
    for width in range(1,7):
        for _ in range(8):
            init=rng.getrandbits(1<<width)
            pins=','.join('.I%d(x%d)'%(i,i) for i in range(width))
            source="module m (); GTP_LUT%d #(.INIT(%d'h%x)) cell0 (.Z(y),%s);\nendmodule"%(width,1<<width,init,pins)
            c=Cone(source,'m');value=evaluate(c,'y',{'x'+str(i):bit[i] for i in range(8)},mask)
            variables=['x'+str(i) for i in range(8)];rng.shuffle(variables)
            bdd=BDD(variables);root=cone_evaluator(c,bdd)('y')
            for k in range(256):
                values={'x'+str(i):(k>>i)&1 for i in range(8)}
                scalar=c.evaluate('y',values)
                assert (value>>k)&1==scalar
                node=root
                while node>1:
                    var,low,high=bdd.nodes[node];node=high if values[variables[var]] else low
                assert node==scalar
            cases+=256
    c=Cone("module m (); GTP_LUT2 #(.INIT(4'hc)) g (.Z(y),.I0(y),.I1(x0));\nendmodule",'m')
    assert evaluate(c,'y',{'x0':bit[0]},mask)==bit[0]
    for kind in ['GTP_MUX2LUT7','GTP_MUX2LUT8']:
        text='module m (); '+kind+' g (.Z(y),.I0(x0),.I1(x1),.S(x2));\nendmodule'
        cone=Cone(text,'m');bdd=BDD(['x0','x1','x2']);root=cone_evaluator(cone,bdd)('y')
        for k in range(8):
            node=root
            while node>1:
                var,low,high=bdd.nodes[node];node=high if (k>>var)&1 else low
            assert node==cone.evaluate('y',{'x'+str(i):(k>>i)&1 for i in range(3)})
    mask20,bits20=patterns(20);out=expected(mask20,bits20)
    for instruction in list(range(4096))+[rng.getrandbits(20) for _ in range(4096)]:
        opcode=instruction&127;rd=(instruction>>7)&31;fn=(instruction>>12)&7;rs1=(instruction>>15)&31
        ret=opcode==0x67 and fn==0 and rd==0 and rs1 in (1,5)
        call=(opcode==0x6f or (opcode==0x67 and fn==0)) and rd in (1,5)
        assert (out['Returns']>>instruction)&1==ret
        assert (out['Calls']>>instruction)&1==call
    source=fixture();valid=audit_metadata(Cone(source,'CoreFrontend'))
    assert len(valid['results'])==8
    renamed=source
    for flag in ['Returns','Calls']:
        for lane in range(4):
            name='pd%s_%d'%(flag,lane)
            renamed=renamed.replace('GTP_DFF_E '+name+' ', 'GTP_DFF_E '+name+'_vname ')
    assert len(audit_metadata(Cone(renamed,'CoreFrontend'))['results'])==8
    changes={
        'wrong_enable':('.CE(fcToPd)','.CE(wrongEnable)'),
        'wrong_clock':('.CLK(clock)','.CLK(wrongClock)'),
        'wrong_rd_decode':("GTP_LUT5 #(.INIT(32'h1)) rdZero0_cell","GTP_LUT5 #(.INIT(32'h3)) rdZero0_cell"),
        'cross_lane_metadata':('.D(retD0)','.D(retD1)'),
        'metadata_cell_lost':('GTP_DFF_E pdReturns_0','GTP_LOST pdReturns_0'),
        'unknown_dependency':('.I0(D0_7)','.I0(unknownLeaf)')}
    rejected={}
    for name,(a,b) in changes.items():
        assert a in source,name
        try:audit_metadata(Cone(source.replace(a,b,1),'CoreFrontend'))
        except (ValueError,AssertionError,KeyError) as e:rejected[name]=str(e)
        else:raise AssertionError('Malformed fixture accepted '+name)
    for name,text in [('sequential_leaf',"module m (); GTP_DFF g (.Q(y),.D(x),.CLK(clock));\nendmodule"),
                      ('unknown_leaf',"module m (); GTP_LUT1 #(.INIT(2'h2)) g (.Z(y),.I0(missing));\nendmodule")]:
        try:evaluate(Cone(text,'m'),'y',{},mask)
        except ValueError as e:rejected[name]=str(e)
        else:raise AssertionError(name+' accepted')
    record={'status':'PASS','scalar_vector_cases':cases,'scalar_bdd_cases':cases+16,'integer_reference_cases':8192,
            'native_metadata_cases_per_lane':1<<20,'native_metadata_flags':8,'negative_cases':rejected,
            'checker_sha256':hashlib.sha256(Path(__file__).with_name('audit_frontend_metadata_ads.py').read_bytes()).hexdigest(),
            'bdd_engine_sha256':hashlib.sha256(Path(__file__).with_name('ads_bdd.py').read_bytes()).hexdigest()}
    if args.output:args.output.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record))
if __name__=='__main__':main()
