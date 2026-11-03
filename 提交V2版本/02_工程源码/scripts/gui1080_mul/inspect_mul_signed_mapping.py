"""Actual four-DSP signed partial inputs, capture controls, selected32-bit reconstruction and resources."""
from pathlib import Path
import argparse,datetime,hashlib,json,re,sys,traceback
w=Path(__file__).resolve().parent
sys.path[:0]=[str(w),'G:/fpga/performance_soc_cpu85_probeslot_20261021/scripts']
from audit_cpu_ads import signal
from native_data_boundary_graph_v2 import NativeDataGraph
from native_sat_bits import NativeSat,z3
from profile_native_resources import profile

def apms(body, canonical=None):
    body=re.sub(r'/\*.*?\*/|//[^\n]*','',body,flags=re.S)
    cells=[]
    for m in re.finditer(r'\bGTP_APM_E2\s*#\s*\((.*?)\)\s+(\w+)\s*\((.*?)\);',body,re.S):
        params={k:v.strip()for k,v in re.findall(r'\.(\w+)\s*\(([^()]*)\)',m[1])}
        ports={k:signal(v)for k,v in re.findall(r'\.(\w+)\s*\(([^()]*)\)',m[3])}
        assert params['MULT_REG']=='1' and params['USE_MULT']=='1'
        assert all(v=='0'for k,v in params.items()if k.endswith('_REG') and k!='MULT_REG')
        assert all(params[k]=='0'for k in ['ASYNC_RST','X_SEL','XB_SEL','CIN_SEL','ROUNDMODE_SEL','USE_SIMD','USE_ACCLOW','USE_PREADD','USE_POSTADD'])
        assert params['GRS_EN']=='"TRUE"'
        assert ports['CEM']=='io_valid' and ports['CLK']=='clock' and ports['RSTM']=="1'b0"
        assert ports['MODEIN']=="{1'b0,1'b0,1'b0,1'b1,1'b0}"
        assert ports['MODEY']=="{1'b0,1'b0,1'b1}" and ports['MODEZ']=="{1'b0,1'b0,1'b0,1'b0}"
        assert all(not ports[k]for k in ['CPI','CXI','CXBI','XB','Z'])
        found=re.findall(r'prod(00|01|10|11)Reg\[\d+\]',ports['P'])
        assert len(set(found))==1,('Unrecognized partial-product output',m[2],ports['P'])
        part=found[0];width=33 if part in ['01','10'] else 32
        pbits=list(reversed(ports['P'][1:-1].split(',')))
        assert len(pbits)==48
        expected=['prod'+part+'Reg['+str(i)+']'for i in range(width)]
        # In physical-boundary mode use actual P pin positions as the numeric
        # product. The caller proves all X/Y bits and the complete selected WB
        # arithmetic from these physical pins. Removed source-name aliases are
        # never replaced with invented data or treated as graph inputs.
        if canonical is None:assert pbits[:width]==expected
        data_bits=pbits[:width]
        assert len(set(pbits))==48 and all(n not in ["1'bx","1'b0","1'b1"]for n in pbits)
        cells.append(dict(part=part,name=m[2],parameters=params,ports=ports,width=width,data_bits=data_bits))
    assert len(cells)==4 and {c['part']for c in cells}=={'00','01','10','11'}
    assert len({c['name']for c in cells})==4
    assert 'correctionReg'not in body
    return cells

def audit(source):
    g=NativeDataGraph(source);ctx=g.h.find('Mul');mdu=ctx[:-1]
    body=g.h.modules[g.h.contexts[ctx][0]];cells=apms(body,lambda n:g.h.canonical(ctx,n))
    for name in ['io_a','io_b']:
        for i in range(32):g.anchor(ctx,name+'['+str(i)+']')
    s=NativeSat(g);rs=g.h.find('RsMdu');head=s.net(rs,'head')
    op=[z3.If(head,s.net(rs,'aluOp_1['+str(i)+']'),s.net(rs,'aluOp_0['+str(i)+']'))for i in range(3)]
    sa=z3.Or(op[0],op[1]);sb=z3.Or(op[0],z3.And(op[1],z3.Not(op[2])))
    a=[s.net(ctx,'io_a['+str(i)+']')for i in range(32)]
    b=[s.net(ctx,'io_b['+str(i)+']')for i in range(32)]
    rows=[]
    # Vendor USE_MULT/USE_SIMD=0 consumes signed X[24:0]*Y[17:0].
    # X[29:25] is outside that explicitly verified primitive mode.
    for c in cells:
        x=g.h.vector_bits(ctx,c['ports']['X']);y=g.h.vector_bits(ctx,c['ports']['Y'])
        assert len(x)==30 and len(y)==18
        hi_a=c['part'][0]=='1';hi_b=c['part'][1]=='1'
        expected_x=(a[16:]+[z3.And(sa,a[31])]*9)if hi_a else a[:16]+[z3.BoolVal(False)]*9
        expected_y=(b[16:]+[z3.And(sb,b[31])]*2)if hi_b else b[:16]+[z3.BoolVal(False)]*2
        proofs=[s.prove(c['part']+'/X'+str(i),s.net(ctx,n),expected_x[i])for i,n in enumerate(x[:25])]
        proofs += [s.prove(c['part']+'/Y'+str(i),s.net(ctx,n),expected_y[i])for i,n in enumerate(y)]
        rows.append(dict(**c,operand_bit_proofs=proofs,unused_X_bits=list(x[25:])))
    words={c['part']:s.word(ctx,c['data_bits'])for c in cells}
    total=z3.ZeroExt(32,words['00'])+(z3.SignExt(31,words['01'])<<16)+(z3.SignExt(31,words['10'])<<16)+(z3.ZeroExt(32,words['11'])<<32)
    low=s.net(mdu,'mulLowR');done=s.net(ctx,'io_done')
    expected=z3.If(low,z3.Extract(31,0,total),z3.Extract(63,32,total))
    recon=[s.prove('wbData['+str(i)+']',s.net(mdu,'io_wbData['+str(i)+']'),z3.Extract(i,i,expected)==1,done)for i in range(32)]
    ff=g.h.cone('Mul').primitive('io_done')
    assert ff['type']=='GTP_DFF_R' and ff['ports']==dict(Q='io_done',CLK='clock',D='io_valid',R='reset')
    return dict(apms=rows,operand_bits_proven=172,reconstruction_bits_proven=32,
                selected_writeback_proofs=recon,completion_register=ff,native_boolean_nodes=len(s.symbols),
                scope='Exact binary input/sign extension and done-conditioned32-bit writeback reconstruction at four explicit clocked APM product boundaries. Four DSP modes/capture controls/one completion FF checked. Vendor multiplier sequential arithmetic, other MDU arbitration/whole CPU/STA/board are separate.')

