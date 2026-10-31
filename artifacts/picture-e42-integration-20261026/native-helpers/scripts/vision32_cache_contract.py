"""Prove native LUTRAM cache capacity, scalar ports and weight-bank decoders."""
import re
import itertools
import sys
from functools import lru_cache
from pathlib import Path
from audit_cpu_ads import Cone, signal
from audit_icache_pad_ads import module, cells, ports
from ads_bdd import BDD, cone_leaves, cone_evaluator


def read_boundary(netlist, boundary, folded_guards=(), decoder_targets=None, exports=()):
    """Bind a synthesized export by its actual accepted-read logic and wiring."""
    assert re.fullmatch(r'N[0-9]+', boundary), 'Unknown native read export'
    sys.path.insert(0,str(Path(__file__).with_name('gui1080_mul')))
    from native_hier_cone_vector_v2 import VectorHierCone
    h=VectorHierCone(re.sub(r'\(\*.*?\*\)','',netlist,flags=re.S),root='soc_top')
    vision=h.find('vision32_layer');mac=h.find('mac_accel_ddr_kernel_top')
    state_bits=sorted(int(re.fullmatch(r'state\[(\d+)\]',n)[1])
                      for n in h.cone('vision32_layer').drivers if re.fullmatch(r'state\[(\d+)\]',n))
    assert state_bits in [list(range(5)),list(range(6))],('Unknown vision state encoding',state_bits)
    # Mapping can fold drain/error and owner terms across several real module
    # ports. Follow every vector bit to its actual driver instead of requiring
    # floating/unused export bits to have particular generated names.
    stops={n:(vision,n) for n in ['mem_rsp_error','stop_pending']+['state['+str(i)+']' for i in state_bits]}
    response_boundary='kernel-response'
    try:h.canonical(mac,'mem_rsp_valid')
    except AssertionError as missing:
        assert missing.args[0]==('Unknown/multiple scalar vector driver',(mac,'mem_rsp_valid'),[])
        # This mapping folds the adapter's valid mux into owner qualification.
        # Cut only at the actual AXI response wires and actual adapter flops;
        # keep the valid/owner logic inside the proof.
        response_boundary='shared-ddr-response-and-adapter-state'
        adapter=h.find('mac_accel_axi_master32')
        for kind in ['r','b']:stops['shared_'+kind+'valid']=(mac,'a_'+kind+'valid')
        for name in ['rd_active','rd_owner','wr_active','wr_owner']:
            port='u_ddr_arbiter/'+name
            assert h.directions('mac_accel_ddr_kernel_top').get(port)=='input'
            stops['ddr_'+name]=(mac,port)
        adapter_states=sorted(n for n in h.cone('mac_accel_axi_master32').drivers
                              if re.fullmatch(r'state_reg\[\d+\]',n))
        assert 1<=len(adapter_states)<=8,'Unknown adapter state registers'
        for i,n in enumerate(adapter_states):stops['adapter_state'+str(i)]=(adapter,n)
    else:stops['response_valid']=(mac,'mem_rsp_valid')
    owners=sorted(n for n in h.cone('mac_accel_ddr_kernel_top').drivers if re.fullmatch(r'memory_owner_reg\[\d+\]',n))
    assert 1<=len(owners)<=8,'Unknown mapped owner registers'
    for i,n in enumerate(owners):stops['owner'+str(i)]=(mac,n)
    if decoder_targets is not None:
        # Split memories can produce more than one exported partial decoder.
        # Follow every export through real hierarchy; prove the complete WE
        # cones instead of treating either numeric export as an assumption.
        inputs=['load_index[0]']+[f'load_index[{i}]' for i in range(7,12)]+[f'read_kind[{i}]' for i in range(3)]
        for n in inputs:stops[n]=(vision,n)
        valid,leaves=h.expression(vision,'mem_rsp_valid',stops)
        expressions={}
        for key,target in decoder_targets.items():
            expressions[key],used=h.expression(vision,target,stops);leaves|=used
        required=set(inputs)|{'stop_pending','mem_rsp_error'}|{f'state[{i}]' for i in state_bits}
        names=sorted(leaves|required);assert len(names)<=32
        bdd=BDD(names)
        @lru_cache(None)
        def convert(expr):
            if expr[0]=='const':return expr[1]
            if expr[0]=='var':return bdd.var(expr[1])
            table,pins=expr[1],[convert(x) for x in expr[2]]
            def apply(value,width):
                if value==0:return 0
                if value==(1<<(1<<width))-1:return 1
                half=1<<(width-1);mask=(1<<half)-1
                return bdd.ite(pins[width-1],apply(value>>half,width-1),apply(value&mask,width-1))
            return apply(table,len(pins))
        base=convert(valid)
        for i in state_bits:
            v=bdd.var(f'state[{i}]');base=bdd.land(base,v if (9>>i)&1 else bdd.inv(v))
        for n in ['stop_pending','mem_rsp_error']:base=bdd.land(base,bdd.inv(bdd.var(n)))
        for i in range(3):
            v=bdd.var(f'read_kind[{i}]');base=bdd.land(base,v if (2>>i)&1 else bdd.inv(v))
        for (half,bank),expr in expressions.items():
            parity=bdd.var('load_index[0]');expected=bdd.land(base,parity if half=='hi' else bdd.inv(parity))
            for i in range(5):
                v=bdd.var(f'load_index[{i+7}]');expected=bdd.land(expected,v if (bank>>i)&1 else bdd.inv(v))
            assert convert(expr)==expected,('Full hierarchical native bank decoder mismatch',half,bank)
        producers={n:h.contexts[h.canonical(vision,n)[0]][0] for n in exports}
        return dict(export=boundary,exports=list(exports),producer=producers[boundary],export_producers=producers,
                    response_boundary=response_boundary,truth='all bank WEs equal actual response/state/guards/kind/parity/row range',
                    proof_method='complete hierarchical ROBDD equality',bdd_nodes=len(bdd.nodes),
                    cofactors=1<<len(names),cut_variables=names,hierarchy_bound=True,hierarchy_hops=len(h.hops))
    actual,actual_leaves=h.expression(vision,boundary,stops)
    valid,valid_leaves=h.expression(vision,'mem_rsp_valid',stops)
    names=sorted(actual_leaves|valid_leaves|{'state['+str(i)+']' for i in state_bits}|set(folded_guards))
    # Owner/adapter terms may be folded across the hierarchy. Prove the same
    # complete truth table symbolically, including every physical FSM bit.
    assert len(names)<=32,'Unexpected read boundary complexity'
    bdd=BDD(names)
    @lru_cache(None)
    def convert(expr):
        if expr[0]=='const':return expr[1]
        if expr[0]=='var':return bdd.var(expr[1])
        table,pins=expr[1],[convert(x) for x in expr[2]]
        def apply(value,width):
            if value==0:return 0
            if value==(1<<(1<<width))-1:return 1
            half=1<<(width-1);mask=(1<<half)-1
            return bdd.ite(pins[width-1],apply(value>>half,width-1),apply(value&mask,width-1))
        return apply(table,len(pins))
    expected=convert(valid)
    for i in state_bits:
        bit=bdd.var('state['+str(i)+']')
        expected=bdd.land(expected,bit if (9>>i)&1 else bdd.inv(bit))
    for name in folded_guards:expected=bdd.land(expected,bdd.inv(bdd.var(name)))
    assert convert(actual)==expected,'Read export differs from actual valid/state/guard expression'
    producer_context,_=h.canonical(vision,boundary)
    return dict(export=boundary,producer=h.contexts[producer_context][0],response_boundary=response_boundary,
                truth='mem_rsp_valid && state==R_WAIT(9)'+''.join(' && !'+n for n in sorted(folded_guards)),
                folded_guards=sorted(folded_guards),cofactors=1<<len(names),hierarchy_bound=True,
                proof_method='complete hierarchical ROBDD equality',bdd_nodes=len(bdd.nodes),
                hierarchy_hops=len(h.hops),cut_variables=names)


def cache_contract(netlist):
    body = module(netlist, 'vision32_layer')
    memories = {m['name']: ports(m['ports']) for m in cells(body, 'GTP_RAM64X1DP')}
    weight_names = set()
    enables = {}
    outputs = set()
    compact = any(n.startswith('weight_tail_') for n in memories)
    raddr = '{'+','.join(f'weight_ra[{i}]' for i in reversed(range(6)))+'}'
    waddr = '{'+','.join(f'load_index[{i}]' for i in range(6, 0, -1))+'}'
    for half in ('lo', 'hi'):
        for bank in range(18 if compact else 32):
            wes = set()
            for bit in range(32):
                name = (f'weight_tail_{half}_{bank-16}_{bit}' if compact and bank>=16
                        else f'weight_{half}_{bank}_{bit}')
                weight_names.add(name)
                assert name in memories, ('Native weight bit missing', name)
                p = memories[name]
                assert p.get('RADDR') == raddr and p.get('WADDR') == waddr, ('Cache address port changed', name)
                assert p.get('DI') == f'mem_rsp_rdata[{bit}]' and p.get('WCLK') == 'clk', ('Cache data/clock changed', name)
                assert p.get('DO') not in (None, "1'b0", "1'b1") and p['DO'] not in outputs, ('Collapsed cache output', name)
                outputs.add(p['DO'])
                assert p.get('WE') not in (None, "1'b0", "1'b1"), ('Cache WE missing/constant', name)
                wes.add(p['WE'])
            assert len(wes) == 1, ('Per-bit bank enable mismatch', half, bank)
            enables[half, bank] = wes.pop()
    assert {n for n in memories if n.startswith(('weight_lo_', 'weight_hi_', 'weight_tail_'))} == weight_names
    for pixel in range(4):
        for bit in range(32):
            name = f'input{pixel}_{bit}'
            assert name in memories, ('Input buffer bit missing', name)
            p = memories[name]
            assert p.get('DI') == f'input_wd[{bit}]' and p.get('WCLK') == 'clk'
            assert p.get('RADDR') == '{buffer_bank,feed_index[6],feed_index[5],feed_index[4],feed_index[3],feed_index[2]}'
            assert p.get('WADDR') == '{buffer_bank,fill_offset[6],fill_offset[5],fill_offset[4],fill_offset[3],fill_offset[2]}'
    for bit in range(32):
        p = memories.get(f'lut_mem_{bit}', {})
        assert p.get('DI') == f'mem_rsp_rdata[{bit}]' and p.get('WCLK') == 'clk', 'Activation table capacity/ports'
        assert p.get('RADDR') == '{quant_byte[7],quant_byte[6],quant_byte[5],quant_byte[4],quant_byte[3],quant_byte[2]}'
        assert p.get('WADDR') == '{load_index[5],load_index[4],load_index[3],load_index[2],load_index[1],load_index[0]}'
    # Native export numbers change after valid logic edits. Prove the producer
    # and all hierarchy bindings before using that accepted-read boundary.
    c = Cone(netlist, 'vision32_layer')
    leaves = cone_leaves(c, list(enables.values()))
    expected_leaves = {'load_index[0]'} | {
        f'load_index[{i}]' for i in range(7, 12)} | {f'read_kind[{i}]' for i in range(3)}
    guards={'stop_pending','mem_rsp_error'}
    local_guards=leaves&guards;folded_guards=guards-local_guards
    unknown=leaves-expected_leaves-local_guards
    assert 1<=len(unknown)<=4 and expected_leaves<=leaves, ('Unknown decoder boundary', sorted(leaves))
    assert all(re.fullmatch(r'N\d+',n) for n in unknown)
    boundary=sorted(unknown)[0]
    whole_hierarchy=len(unknown)>1
    producer_proof=read_boundary(netlist,boundary,folded_guards,enables if whole_hierarchy else None,sorted(unknown))
    bdd = BDD(sorted(leaves))
    evaluate = cone_evaluator(c, bdd)
    for (half, bank), target in enables.items():
        if whole_hierarchy:continue  # Complete WE equality was proved above.
        expected = bdd.var(boundary)
        for name in sorted(local_guards):
            expected = bdd.land(expected, bdd.inv(bdd.var(name)))
        for i in range(3):
            value = bdd.var(f'read_kind[{i}]')
            expected = bdd.land(expected, value if (2>>i)&1 else bdd.inv(value))
        parity = bdd.var('load_index[0]')
        expected = bdd.land(expected, parity if half == 'hi' else bdd.inv(parity))
        for i in range(5):
            value = bdd.var(f'load_index[{i+7}]')
            expected = bdd.land(expected, value if (bank>>i)&1 else bdd.inv(value))
        assert evaluate(target) == expected, ('Native bank decoder truth mismatch', half, bank)
    return dict(weight_logical_bytes=9216, weight_physical_capacity_bytes=9216 if compact else 16384,
                weight_mapping='split_1024_128' if compact else 'padded_2048',
                weight_ram64x1_cells=len(weight_names), input_ping_pong_bytes=1024,
                activation_table_bytes=256, weight_decoder_roots_proven=len(enables),
                decoder_free_variables=len(leaves), native_read_boundary=producer_proof,
                sequential_equivalence=False, sta=False)
