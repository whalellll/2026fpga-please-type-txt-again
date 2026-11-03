"""Fail-closed physical contract for the 1024+128 row synchronous cache.

Checks mapped pins/parameters and complete combinational ROBDD relations.
RAM sequential semantics are the specified vendor SIMPLE_DUAL_PORT primitive;
this does not prove the whole inference FSM, routed timing or board operation.
"""
import re
import sys
from pathlib import Path
from functools import lru_cache
from audit_icache_pad_ads import module, cells, ports
from ads_bdd import BDD

sys.path.insert(0, str(Path(__file__).with_name('gui1080_mul')))
from native_hier_cone_vector_v2 import VectorHierCone


class BramCone(VectorHierCone):
    @lru_cache(None)
    def cone(self, kind):
        c = super().cone(kind)
        # These buffers have no inversion or state. Opaque RAM/PLL outputs are
        # terminals, never evaluated as LUTs or invented as combinational RAM.
        body = module(self.source, kind)
        ctx = next(k for k, v in self.contexts.items() if v[0] == kind)
        for cell_kind in ('GTP_INBUF', 'GTP_OUTBUF', 'GTP_CLKBUFG', 'GTP_CLKBUF'):
            for m in cells(body, cell_kind):
                p = ports(m['ports'])
                assert set(p) == {'I', 'O'}, ('Unknown buffer', cell_kind, p)
                assert p['O'] not in c.drivers and p['O'] not in c.aliases
                c.aliases[p['O']] = p['I']
        for cell_kind, outputs in [('GTP_DRM36K_E1', ('DOA', 'DOB')),
                                   ('GTP_DRM18K_E1', ('DOA', 'DOB')),
                                   ('GTP_GPLL', tuple('CLKOUT'+x for x in ('0','1','2','3','4','5','F')))]:
            for m in cells(body, cell_kind):
                p = ports(m['ports'])
                node = dict(kind=cell_kind, name=m['name'], ports=p)
                for port in outputs:
                    if not p.get(port):
                        continue
                    for bit in self.vector_bits(ctx, p[port]):
                        if bit in ("1'b0", "1'b1"):
                            continue
                        assert bit not in c.drivers, ('Multiple primitive output', bit)
                        c.drivers[bit] = (node, port)
        return c


def bdd_converter(expressions, required=()):
    def leaves(e):
        if e[0] == 'var': return {e[1]}
        if e[0] == 'const': return set()
        return set().union(*(leaves(x) for x in e[2]))
    names = sorted(set(required) | set().union(*(leaves(e) for e in expressions)))
    b = BDD(names)
    @lru_cache(None)
    def conv(e):
        if e[0] == 'const': return e[1]
        if e[0] == 'var': return b.var(e[1])
        table, pins = e[1], [conv(x) for x in e[2]]
        def apply(t, n):
            if t == 0: return 0
            if t == (1 << (1 << n))-1: return 1
            half = 1 << (n-1)
            return b.ite(pins[n-1], apply(t >> half, n-1), apply(t & ((1 << half)-1), n-1))
        return apply(table, len(pins))
    return b, conv, names


def bram_cache_contract(netlist):
    h = BramCone(re.sub(r'\(\*.*?\*\)', '', netlist, flags=re.S), root='soc_top')
    v = h.find('vision32_layer')
    mac = h.find('mac_accel_ddr_kernel_top')
    adapter = h.find('mac_accel_axi_master32')
    pe = h.find('vision32_pe')
    body = module(h.source, 'vision32_layer')
    # Warm cones only after the complete hierarchy has been registered.
    vc = h.cone('vision32_layer')
    clk = h.canonical((), 'sys_clk')
    assert h.canonical(v, 'clk') == clk, 'Vision cache must use SYS clock'
    def bits(x): return h.vector_bits(v, x)
    def same(a, b): return h.canonical(v, a) == h.canonical(v, b)
    def equal_vector(actual, expected, label):
        aa, bb = bits(actual), bits(expected)
        assert len(aa) == len(bb) and all(same(a, b) for a, b in zip(aa, bb)), ('Mapped pin mismatch', label, actual, expected)
    def literal(actual, expected, label):
        assert bits(actual) == bits(expected), ('Primitive control mismatch', label, actual, expected)

    ram_cells = [(kind, m) for kind in ('GTP_DRM36K_E1', 'GTP_DRM18K_E1') for m in cells(body, kind)]
    assert len(ram_cells) == 4, ('Expected four weight RAM primitives', len(ram_cells))
    expected_names = {'weight_lo', 'weight_hi', 'weight_tail_lo', 'weight_tail_hi'}
    assert {m['name'] for _, m in ram_cells} == expected_names
    enables, read_enables, data_bits, bank_outputs = {}, {}, {}, {}
    primitive_records = []
    all_outputs = set()
    for kind, m in ram_cells:
        name = m['name']; tail = name.startswith('weight_tail_')
        assert kind == ('GTP_DRM18K_E1' if tail else 'GTP_DRM36K_E1')
        par, p = ports(m['params']), ports(m['ports'])
        for k, value in dict(GRS_EN='"TRUE"', DATA_WIDTH_A='32', DATA_WIDTH_B='32',
                             DOA_REG='0', DOB_REG='0', DOA_REG_CLKINV='0', DOB_REG_CLKINV='0',
                             WRITE_MODE_A='"NORMAL_WRITE"', WRITE_MODE_B='"NORMAL_WRITE"',
                             RST_TYPE='"SYNC"', RAM_MODE='"SIMPLE_DUAL_PORT"',
                             RAM_DATA_WIDTH='9',RAM_ADDR_WIDTH='11' if tail else '12').items():
            assert par.get(k) == value, ('Unknown RAM parameter', name, k, par.get(k))
        if not tail:
            for k,value in dict(RAM_CASCADE='"NONE"',ECC_READ_EN='"FALSE"',ECC_WRITE_EN='"FALSE"').items():
                assert par.get(k)==value, ('Unknown main RAM mode',name,k)
        for k in ('CLKA', 'CLKB'):
            assert h.canonical(v, p[k]) == clk, ('RAM clock not SYS', name, k)
        for k in ('RSTA','RSTB','WEB','ADDRA_HOLD','ADDRB_HOLD'):
            literal(p[k], "1'b0", (name,k))
        literal(p['CEA'], "1'b1", name)
        if not tail:
            for k in ('CSA', 'CSB'): literal(p[k], "3'b111", (name,k))
            for k in ('CSA_MASK', 'CSB_MASK'): assert par[k] == "3'b111"
        literal(p['BWEA'], "4'b1111" if tail else "8'b00001111", name)
        literal(p['BWEB'], "2'b00" if tail else "4'b0000", name)
        # Low five native address bits are fixed at 1 in the vendor x32 mode.
        # Main selects all 1024 rows; tail uses exactly 128 of 512 physical rows.
        w = "{2'b00," if tail else "{1'b1,"
        w += ','.join(f'load_index[{i}]' for i in range(7 if tail else 10, 0, -1)) + ",5'b11111}"
        r = "{2'b00," if tail else "{1'b1,"
        r += ','.join(f'weight_ra[{i}]' for i in range(6 if tail else 9, -1, -1)) + ",5'b11111}"
        equal_vector(p['ADDRA'], w, (name,'ADDRA'))
        equal_vector(p['ADDRB'], r, (name,'ADDRB'))
        di = bits(p['DIA']) + (bits(p['DIB']) if tail else ())
        do = (bits(p['DOA']) + bits(p['DOB'])) if tail else bits(p['DOB'])
        assert len(di) == len(do) == 36
        used_di = [di[i+i//8] for i in range(32)]
        used_do = [do[i+i//8] for i in range(32)]
        for i in (8,17,26,35): literal(di[i], "1'b0", (name,'parity'))
        for i, bit in enumerate(used_do):
            key = h.canonical(v, bit)
            assert key not in all_outputs and key[1] not in ("1'b0","1'b1"), ('Aliased RAM data outputs', name, i)
            all_outputs.add(key)
            node, port = h.cone(h.contexts[key[0]][0]).drivers[key[1]]
            assert node['name'] == name and port in ('DOA','DOB')
        enables[name] = p['WEA'];read_enables[name] = p['CEB']
        data_bits[name] = used_di; bank_outputs[name] = used_do
        primitive_records.append(dict(name=name,kind=kind,logical_rows=128 if tail else 1024,
                                      logical_bits=32,physical_rows=512 if tail else 1024))

    state = sorted(n for n in vc.drivers if re.fullmatch(r'state\[\d+\]', n))
    assert set(state) == {f'state[{i}]' for i in range(6)}
    assert all(vc.drivers[n][1] == 'Q' for n in state)
    stops = {n:(v,n) for n in state + ['stop_pending','mem_rsp_error'] +
             [f'load_index[{i}]' for i in (0,8,9,10,11)] + [f'read_kind[{i}]' for i in range(3)]}
    mc = h.cone('mac_accel_ddr_kernel_top')
    owners = sorted(n for n in mc.drivers if re.fullmatch(r'memory_owner_reg\[\d+\]', n))
    assert 1 <= len(owners) <= 8
    for n in owners:
        assert mc.drivers[n][1] == 'Q'; stops['owner_'+n]=(mac,n)
    for kind in ('r','b'): stops['shared_'+kind+'valid']=(mac,'a_'+kind+'valid')
    for n in ('rd_active','rd_owner','wr_active','wr_owner'):
        assert h.directions('mac_accel_ddr_kernel_top').get('u_ddr_arbiter/'+n) == 'input'
        stops['ddr_'+n]=(mac,'u_ddr_arbiter/'+n)
    ac = h.cone('mac_accel_axi_master32')
    states = sorted(n for n in ac.drivers if re.fullmatch(r'state_reg\[\d+\]', n))
    assert 1 <= len(states) <= 8
    for n in states:
        assert ac.drivers[n][1] == 'Q';stops['adapter_'+n]=(adapter,n)
    # Reviewed PDS one-hot adapter mapping: state_reg[2] is S_R_DATA.
    # Preserve the zero data for a write-response state too; do not assume
    # arbitrary independent state cuts form a legal read transaction.
    assert 'state_reg[2]' in states, 'Unknown adapter read-state mapping'
    assert h.directions('mac_accel_ddr_kernel_top').get('d_rdata')=='input'
    assert len(h.vector_bits(mac,'d_rdata'))==32
    for i in range(32): stops['ddr_data'+str(i)]=(mac,f'd_rdata[{i}]')
    valid,_ = h.expression(v, 'mem_rsp_valid', stops)
    wes = {n:h.expression(v,e,stops)[0] for n,e in enables.items()}
    inputs = {n:[h.expression(v,x,stops)[0] for x in d] for n,d in data_bits.items()}
    b,conv,names = bdd_converter([valid,*wes.values(),*(x for row in inputs.values() for x in row)], stops)
    base = conv(valid)
    assert base != 0, 'Vacuous response boundary'
    def const_bits(base, prefix, width, value):
        for i in range(width):
            x=b.var(f'{prefix}[{i}]');base=b.land(base,x if value>>i&1 else b.inv(x))
        return base
    base = const_bits(base,'state',6,9)
    base = const_bits(base,'read_kind',3,2)
    for n in ('stop_pending','mem_rsp_error'): base=b.land(base,b.inv(b.var(n)))
    for name, e in wes.items():
        expected = base
        parity=b.var('load_index[0]')
        expected=b.land(expected,parity if name.endswith('_hi') else b.inv(parity))
        if name.startswith('weight_tail_'):
            for i in range(8,12):
                x=b.var(f'load_index[{i}]');expected=b.land(expected,x if i==11 else b.inv(x))
        else: expected=b.land(expected,b.inv(b.var('load_index[11]')))
        assert expected != 0 and conv(e) == expected, ('BRAM write decoder mismatch',name)
        for i,e in enumerate(inputs[name]):
            data=b.land(b.var('ddr_data'+str(i)),b.var('adapter_state_reg[2]'))
            assert conv(e)==data, ('Shared DDR data/read-state mask permutation',name,i)

    read_stops={n:(v,n) for n in state}
    res=[h.expression(v,e,read_stops)[0] for e in read_enables.values()]
    rb,rc,rnames=bdd_converter(res,state)
    feed=1
    for i in range(6):
        x=rb.var(f'state[{i}]');feed=rb.land(feed,x if 16>>i&1 else rb.inv(x))
    assert all(rc(e)==feed for e in res), 'RAM read CE must equal complete FEED state'
    selected='weight_tail_selected_q'
    node,port=vc.drivers[selected]
    assert port=='Q' and node['kind']=='GTP_DFF' and h.canonical(v,node['ports']['CLK'])==clk
    assert node['string_params'].get('GRS_EN')=='TRUE' and node['init']==0
    row_inputs=[f'k_base[{i}]' for i in range(11)]+[f'feed_index[{i}]' for i in range(8)]
    for n in row_inputs:
        assert vc.drivers[n][1]=='Q' and h.canonical(v,vc.drivers[n][0]['ports']['CLK'])==clk, ('Row address cut must be actual SYS FF',n)
    sel_stops=dict(read_stops,selected=(v,selected))
    sel_stops.update({n:(v,n) for n in row_inputs})
    expression,_=h.expression(v,node['ports']['D'],sel_stops)
    row_expressions=[h.expression(v,f'weight_ra[{i}]',sel_stops)[0] for i in range(10)]
    sb,sc,snames=bdd_converter([expression,*row_expressions],sel_stops)
    carry=0;sums=[]
    for i in range(11):
        a=sb.var(f'k_base[{i}]');bb=sb.var(f'feed_index[{i}]') if i<8 else 0
        xor=sb.ite(a,sb.inv(bb),bb)
        sums.append(sb.ite(xor,sb.inv(carry),carry))
        carry=sb.lor(sb.land(a,bb),sb.land(xor,carry))
    assert all(sc(e)==sums[i] for i,e in enumerate(row_expressions)), 'Physical read row is not k_base+feed_index'
    sf=1
    for i in range(6):
        x=sb.var(f'state[{i}]');sf=sb.land(sf,x if 16>>i&1 else sb.inv(x))
    assert sc(expression)==sb.ite(sf,sums[10],sb.var('selected')), 'Read bank selector latency/hold mismatch'
    mux_stops={'selected':(v,selected)}
    for name, row in bank_outputs.items():
        for i,bit in enumerate(row): mux_stops[name+str(i)]=(v,bit)
    # Check real child input ports rather than an unused exported weight wire.
    assert h.directions('vision32_pe').get('weights')=='input'
    consumer=[h.expression(pe,f'weights[{i}]',mux_stops)[0] for i in range(64)]
    mb,mc,mnames=bdd_converter(consumer,mux_stops)
    for i,e in enumerate(consumer):
        half='lo' if i<32 else 'hi';j=i%32
        assert mc(e)==mb.ite(mb.var('selected'),mb.var('weight_tail_'+half+str(j)),mb.var('weight_'+half+str(j))), ('PE weight mux permutation',i)
    apms=cells(module(h.source,'vision32_pe'),'GTP_APM_E2')
    assert len(apms)==32
    lanes=[0]*8
    for apm in apms:
        y=h.vector_bits(pe,ports(apm['ports'])['Y'])
        matches=[]
        for channel in range(8):
            expected=[f'weights[{channel*8+min(i,7)}]' for i in range(18)]
            if len(y)==18 and all(h.canonical(pe,a)==h.canonical(pe,b) for a,b in zip(y,expected)):
                matches.append(channel)
        assert len(matches)==1, ('Actual APM weight byte/sign connection',apm['name'])
        lanes[matches[0]]+=1
    assert lanes==[4]*8, ('Each weight byte must feed four physical APMs',lanes)

    memories={m['name']:ports(m['ports']) for m in cells(body,'GTP_RAM64X1DP')}
    assert not any(n.startswith('weight') for n in memories), 'Unexpected LUTRAM weight fallback'
    for pixel in range(4):
        for bit in range(32):
            p=memories[f'input{pixel}_{bit}']
            equal_vector(p['DI'],f'input_wd[{bit}]','input data')
            assert h.canonical(v,p['WCLK'])==clk
            equal_vector(p['RADDR'],'{buffer_bank,feed_index[6],feed_index[5],feed_index[4],feed_index[3],feed_index[2]}','input read')
            equal_vector(p['WADDR'],'{buffer_bank,fill_offset[6],fill_offset[5],fill_offset[4],fill_offset[3],fill_offset[2]}','input write')
    for bit in range(32):
        p=memories[f'lut_mem_{bit}']
        equal_vector(p['DI'],f'mem_rsp_rdata[{bit}]','activation data')
        assert h.canonical(v,p['WCLK'])==clk
        equal_vector(p['RADDR'],'{quant_byte[7],quant_byte[6],quant_byte[5],quant_byte[4],quant_byte[3],quant_byte[2]}','activation read')
        equal_vector(p['WADDR'],'{load_index[5],load_index[4],load_index[3],load_index[2],load_index[1],load_index[0]}','activation write')
    return dict(profile='bram_1024_128_sync_v1',weight_logical_bytes=9216,
                weight_physical_capacity_bytes=12288,weight_drm36k_equivalent=3,
                primitives=primitive_records,weight_decoder_roots_proven=4,
                accepted_write_data_bits_proven=128,read_enable_roots_proven=4,
                pe_weight_mux_bits_proven=64,input_ping_pong_bytes=1024,activation_table_bytes=256,
                physical_apm_weight_consumers=32,read_address_sum_bits_proven=11,
                clock_domain='sys_clk',read_latency_cycles=1,registered_bank_select=True,
                proof_method='complete hierarchical ROBDD equality and primitive pin/parameter binding',
                bdd_nodes=dict(write=len(b.nodes),read=len(rb.nodes),selector=len(sb.nodes),mux=len(mb.nodes)),
                response_boundary='shared-ddr-response-and-adapter-state',
                sequential_equivalence=False,sta=False)
