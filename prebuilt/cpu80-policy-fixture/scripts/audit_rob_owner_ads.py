#!/usr/bin/env python3
"""Inspect ROB result storage and prove selected mapped write-enable truth tables.

Uses actual LUT INITs and hierarchy bindings, stopping at FF outputs. Unknown
primitives, multi-drivers and unresolved inputs fail closed. The output states
exactly which properties were checked; it is not full sequential equivalence.
"""
import argparse
import hashlib
import itertools
import json
import re
from functools import lru_cache
from pathlib import Path

from audit_cpu_ads import Cone, bits, check, module_text, signal


def split_top(text):
    parts, start, depth = [], 0, 0
    for i, char in enumerate(text):
        depth += char == '{'
        depth -= char == '}'
        if char == ',' and depth == 0:
            parts.append(text[start:i]); start = i + 1
    parts.append(text[start:])
    return parts


def expand(expr, width):
    """Return least-significant bit first; accept only plain mapped wiring."""
    expr = signal(expr)
    if expr.startswith('{') and expr.endswith('}'):
        result = []
        for part in reversed(split_top(expr[1:-1])):
            if part.startswith('{') or re.search(r"\d+'|\[\d+:\d+\]$", part):
                result.extend(expand(part, None))
            else:
                result.append(part)
        check(width is None or len(result) == width, 'Port concatenation width mismatch: ' + expr)
        return result
    constant = re.fullmatch(r"(\d+)'([bdh])([0-9a-fA-FxXzZ_]+)", expr)
    if constant:
        n, base, value = constant.groups(); n = int(n)
        check(width is None or width == n, 'Constant port width mismatch')
        if re.search('[xXzZ]', value):
            return ["1'bx"] * n
        value = int(value.replace('_',''), {'b':2,'d':10,'h':16}[base])
        return ["1'b%d" % ((value >> bit) & 1) for bit in range(n)]
    span = re.fullmatch(r'(.+)\[(\d+):(\d+)\]', expr)
    if span:
        name, high, low = span.groups(); high, low = int(high), int(low)
        check(high >= low, 'Unsupported ascending vector: ' + expr)
        result = [name + '[%d]' % bit for bit in range(low, high + 1)]
        check(width is None or len(result) == width, 'Port slice width mismatch')
        return result
    check(re.fullmatch(r'[A-Za-z_$][\w$./]*(?:\[\d+\](?:_[A-Za-z0-9_]+)?)?', expr) is not None,
          'Unsupported mapped expression: ' + expr)
    if width is None or width == 1 or expr.endswith(']'):
        return [expr]
    return [expr + '[%d]' % bit for bit in range(width)]


class Hierarchy:
    def __init__(self, source):
        self.source = re.sub(r'\(\*.*?\*\)', '', source, flags=re.S)
        self.source = re.sub(r'(?m)^[ \t]+(?=module )', '', self.source)
        self.names = set(re.findall(r'(?m)^module\s+(\w+)', self.source))
        self.modules = {}
        self.contexts = {}

    def module(self, name):
        if name in self.modules:
            return self.modules[name]
        body = module_text(self.source, name)
        clean = re.sub(r'/\*.*?\*/|//[^\n]*', '', body, flags=re.S)
        ports = {}
        for direction, high, low, port in re.findall(
                r'(?m)^\s*(input|output)\s*(?:\[(\d+):(\d+)\]\s*)?(\\[^\s,]+|\w+)\s*[,;)]', clean):
            ports[signal(port)] = (direction, int(high)-int(low)+1 if high else 1)
        instances = {}
        for kind, instance, connections in re.findall(
                r'(?m)^\s*(\w+)\s+(\\[^\s]+|\w+)\s*\((.*?)\);', clean, re.S):
            if kind not in self.names:
                continue
            bindings = {signal(k):signal(v) for k,v in re.findall(r'\.(\\[^\s(]+|\w+)\s*\(([^()]*)\)', connections)}
            instances[signal(instance)] = (kind, bindings)
        driven=set()
        for primitive in re.finditer(r'\bGTP_\w+\s*(?:#\s*\(.*?\))?\s+(?:\\[^\s]+|\w+)\s*\((.*?)\);',clean,re.S):
            for wire in re.findall(r'\.(?:Z|Z5|COUT|Q)\s*\(([^()]*)\)',primitive[1]):
                wire=signal(wire)
                if not wire: continue
                check(wire not in driven,'Multiple mapped drivers for '+name+'/'+wire)
                driven.add(wire)
        value = {'cone':Cone(body,name), 'ports':ports, 'instances':instances, 'body':body}
        self.modules[name] = value
        return value

    def context(self, path):
        if path in self.contexts:
            return self.contexts[path]
        if not path:
            value = ('soc_top', {}, None)
        else:
            parent = path[:-1]
            parent_kind, _, _ = self.context(parent)
            kind, bindings = self.module(parent_kind)['instances'][path[-1]]
            value = (kind, bindings, parent)
        self.contexts[path] = value
        return value

    def parent_input(self, path, wire):
        kind, bindings, parent = self.context(path)
        if parent is None:
            return None
        for name, (direction, width) in self.module(kind)['ports'].items():
            if direction != 'input' or name not in bindings:
                continue
            local = expand(name,width)
            if wire in local:
                return parent, expand(bindings[name],width)[local.index(wire)]
        return None

    @lru_cache(maxsize=131072)
    def child_output(self, path, wire):
        kind, _, _ = self.context(path)
        for instance,(child_kind,bindings) in self.module(kind)['instances'].items():
            for name,(direction,width) in self.module(child_kind)['ports'].items():
                if direction != 'output' or name not in bindings:
                    continue
                # Most child ports do not share this base name; avoid expanding.
                binding = bindings[name]
                if wire.split('[')[0] not in binding:
                    continue
                actual = expand(binding,width)
                if wire in actual:
                    return path+(instance,),expand(name,width)[actual.index(wire)]
        return None

    def evaluate(self, path, wire, values, cache=None, active=None):
        key = (path,signal(wire)); path,wire = key
        cache = {} if cache is None else cache
        active = set() if active is None else active
        if key in values: return values[key]
        if wire in ("1'b0","1'b1"): return int(wire[-1])
        if key in cache: return cache[key]
        check(key not in active,'Combinational cycle: '+str(key))
        active.add(key)
        kind,_,_ = self.context(path); cone = self.module(kind)['cone']
        ev = lambda target:self.evaluate(path,target,values,cache,active)
        if wire in cone.aliases:
            answer = ev(cone.aliases[wire])
        elif wire in cone.drivers:
            node,port = cone.drivers[wire]; cell,pins = node['kind'],node['ports']
            match = re.fullmatch(r'GTP_LUT([1-6])(D)?',cell)
            if match:
                width = 5 if port == 'Z5' else int(match[1])
                init = node['init']; check(init is not None,'Missing LUT INIT')
                # Ignore exactly the pins whose remaining INIT cofactor is
                # independent. This avoids false dependencies from shared LUT6D.
                fixed = {}
                for bit in range(width):
                    pin = pins['I'+str(bit)]
                    if pin in ("1'b0","1'b1"): fixed[bit]=int(pin[-1])
                    elif (path,pin) in values: fixed[bit]=values[(path,pin)]
                allowed = [i for i in range(1<<width) if all(((i>>b)&1)==v for b,v in fixed.items())]
                index = sum(v<<b for b,v in fixed.items())
                for bit in range(width):
                    if bit not in fixed and any(((init>>i) ^ (init>>(i^(1<<bit))))&1 for i in allowed):
                        index |= ev(pins['I'+str(bit)]) << bit
                answer = (init >> index) & 1
            elif cell.startswith('GTP_MUX2'):
                answer = ev(pins['I'+str(ev(pins['S']))])
            else:
                raise ValueError('Unknown or unbound sequential driver: '+cell+' '+str(key))
        else:
            mapped = self.parent_input(path,wire) or self.child_output(path,wire)
            check(mapped is not None,'Unresolved mapped wire: '+str(key))
            answer = self.evaluate(*mapped,values,cache,active)
        active.remove(key); cache[key]=answer
        return answer

    def dependencies(self, path, wire, local_only=False, boundary_cuts=frozenset()):
        """Mapped combinational support across hierarchy, stopping at FF Q.

        Ignore LUT pins only when the INIT proves independence for both values;
        a shared LUT6D pin must not create a false clear/allocate dependency.
        """
        seen, leaves = set(), set()
        def visit(path, wire):
            wire=signal(wire); key=(path,wire)
            if key in seen or wire in ("1'b0","1'b1"): return
            seen.add(key)
            if key in boundary_cuts: leaves.add(key); return
            kind,_,_=self.context(path); cone=self.module(kind)['cone']
            if wire in cone.aliases:
                visit(path,cone.aliases[wire]); return
            if wire in cone.drivers:
                node,port=cone.drivers[wire]; pins=node['ports']
                if port=='Q': leaves.add(key); return
                match=re.fullmatch(r'GTP_LUT([1-6])(D)?',node['kind'])
                if match:
                    width=5 if port=='Z5' else int(match[1]); init=node['init']
                    check(init is not None,'Missing LUT INIT in structural cone')
                    fixed={i:int(pins['I'+str(i)][-1]) for i in range(width)
                           if pins['I'+str(i)] in ("1'b0","1'b1")}
                    allowed=[i for i in range(1<<width) if all(((i>>b)&1)==v for b,v in fixed.items())]
                    for bit in range(width):
                        if bit not in fixed and any(((init>>i)^(init>>(i^(1<<bit))))&1 for i in allowed):
                            visit(path,pins['I'+str(bit)])
                elif node['kind'].startswith('GTP_MUX2'):
                    for pin in ('I0','I1','S'): visit(path,pins[pin])
                else: raise ValueError('Unsupported structural primitive '+node['kind']+' '+str(key))
                return
            if local_only:
                declaration=self.module(kind)['ports'].get(wire.split('[')[0])
                if declaration and declaration[0]=='input': leaves.add(key); return
            mapped=self.parent_input(path,wire) or self.child_output(path,wire)
            if mapped is None:
                # Only an actual top input is a legitimate terminal.
                check(not path and wire.split('[')[0] in self.module(kind)['ports'],
                      'Unresolved structural wire '+str(key))
                leaves.add(key)
            else: visit(*mapped)
        visit(path,wire)
        return seen,leaves

    def assert_nonconstant(self, path, wire):
        """Require a retained LUT/mux output with a nonconstant INIT cofactor."""
        kind,_,_=self.context(path); cone=self.module(kind)['cone']; wire=signal(wire)
        if wire in cone.aliases: return self.assert_nonconstant(path,cone.aliases[wire])
        if wire not in cone.drivers:
            mapped=self.parent_input(path,wire) or self.child_output(path,wire)
            check(mapped is not None,'Missing nonconstant mapped control '+str((path,wire)))
            return self.assert_nonconstant(*mapped)
        node,port=cone.drivers[wire]
        match=re.fullmatch(r'GTP_LUT([1-6])(D)?',node['kind'])
        if match:
            width=5 if port=='Z5' else int(match[1]); init=node['init']
            fixed={i:int(node['ports']['I'+str(i)][-1]) for i in range(width)
                   if node['ports']['I'+str(i)] in ("1'b0","1'b1")}
            values={(init>>i)&1 for i in range(1<<width) if all(((i>>b)&1)==v for b,v in fixed.items())}
            check(values=={0,1},'Constant mapped control '+str((path,wire)))
        else:
            check(node['kind'].startswith('GTP_MUX2'),'Unexpected retained control '+node['kind'])
            check(node['ports']['I0']!=node['ports']['I1'],'Collapsed mapped selector '+str((path,wire)))
        return {'wire':wire,'primitive':node['kind'],'instance':node['name'],'output':port}


RF_PATH = ('u_cpu','u_cpu_wrapper','u_cpu','core','backend','u_rob','registerFile')


def bind_result(result, netlist, snapshot_path):
    """Bind a checked result to the actual frozen implementation, not a label."""
    snapshot_bytes=snapshot_path.read_bytes()
    snapshot=json.loads(snapshot_bytes.decode('utf-8-sig'))
    checker_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    check(snapshot['inputs'].get('scripts/audit_rob_owner_ads.py')==checker_hash,
          'ROB checker differs from frozen input')
    result.update(schema=1, checker_sha256=checker_hash,
                  vm_sha256=hashlib.sha256(netlist.read_bytes()).hexdigest(),
                  input_snapshot_sha256=hashlib.sha256(snapshot_bytes).hexdigest(),
                  run_id=snapshot['run_id'],
                  cpu_rtl_sha256=snapshot['inputs']['rtl/cpu/CoreTop.sv'],
                  cpu_source_json_sha256=snapshot['inputs']['rtl/cpu/source.json'],
                  cpu_emit_config_sha256=snapshot['inputs']['rtl/cpu/emit-config.json'])
    return result


def audit(source):
    hierarchy = Hierarchy(source)
    check(hierarchy.context(RF_PATH)[0]=='RobTagRegisterFile','Unexpected ROB hierarchy')
    module = hierarchy.module('RobTagRegisterFile'); cone=module['cone']
    for index in range(32):
        for stem in ('tagLive_','resultValid_'):
            name=stem+str(index)
            check(name in cone.drivers and cone.drivers[name][1]=='Q' and
                  cone.drivers[name][0]['kind'].startswith('GTP_DFF'), 'Missing mapped ROB FF '+name)
    owners = {name:node for name,(node,port) in cone.drivers.items()
              if port=='Q' and re.fullmatch(r'resultOwner_\d+_reg\[\d+\]',name)}
    owner_tags = {int(re.search(r'resultOwner_(\d+)',name)[1]) for name in owners}
    check(owner_tags==set(range(32)), 'Owner state does not cover all 32 tags')
    check(set(owners)=={'resultOwner_%d_reg[%d]'%(tag,bit) for tag in range(32) for bit in (1,2,3)} and
          all(node['kind'].startswith('GTP_DFF') for node in owners.values()),
          'Unexpected owner one-hot state topology')
    banks = {int(re.fullmatch(r'resultBanks_(\d+)_ext',name)[1]):value
             for name,value in module['instances'].items() if re.fullmatch(r'resultBanks_\d+_ext',name)}
    check(set(banks)=={0,1,2,3},'Expected four active banks; paired-load port 3 is statically disabled in RsMem')
    bank_results=[]
    for bank,port in ((0,0),(1,1),(2,2),(3,4)):
        _,pins = banks[bank]
        check('W0_en' in pins,'Missing RAM write enable')
        expected_inputs = {'io_write_'+str(port),'io_flush','reset'}
        expected_inputs.update('io_writeTag_%d[%d]'%(port,bit) for bit in range(5))
        expected_inputs.update('tagLive_'+str(tag) for tag in range(32))
        support,_=hierarchy.dependencies(RF_PATH,pins['W0_en'],local_only=True)
        forbidden = sorted(x for path,x in support if path==RF_PATH and
                           x.startswith(('io_clear','io_allocate')) or 'robAllocEn' in x or 'pop0_inst' in x or 'pop1_inst' in x)
        check(not forbidden, 'Decode/allocation still reaches bank%d WE: %s'%(bank,forbidden[:8]))
        # All tags, all write/flush/reset/selected-live combinations; also
        # every other tagLive bit independently toggled to detect bad selection.
        count=0
        for tag in range(32):
            for write,flush,reset,live in itertools.product(range(2),repeat=4):
                local={name:0 for name in expected_inputs}
                local.update(bits('io_writeTag_'+str(port),tag,5))
                local.update({'io_write_'+str(port):write,'io_flush':flush,'reset':reset,'tagLive_'+str(tag):live})
                values={(RF_PATH,name):value for name,value in local.items()}
                actual=hierarchy.evaluate(RF_PATH,pins['W0_en'],values)
                check(actual == (write and live and not flush and not reset),'RAM WE truth table differs for bank%d tag%d'%(bank,tag))
                count+=1
            for other in range(32):
                local={name:0 for name in expected_inputs};local.update(bits('io_writeTag_'+str(port),tag,5))
                local.update({'io_write_'+str(port):1,'tagLive_'+str(other):1})
                actual=hierarchy.evaluate(RF_PATH,pins['W0_en'],{(RF_PATH,k):v for k,v in local.items()})
                check(actual==int(other==tag),'Wrong tagLive select for bank%d'%bank);count+=1
        bank_results.append({'bank':bank,'source_port':port,'write_enable':pins['W0_en'],'checked_vectors':count})
    # A local structural scan alone is not sufficient for the promoted owner,
    # clear-priority and tag-read LUTs. Record their support for same-run review.
    owner_cones=[]
    boundary_cuts=set(); forbidden_cuts=set()
    for name,(direction,width) in module['ports'].items():
        if direction!='input': continue
        forbidden=name.startswith(('io_clear','io_allocate'))
        if not (forbidden or name.startswith(('io_write_','io_writeTag_')) or name in ('io_flush','reset')): continue
        for wire in expand(name,width):
            key=(RF_PATH,wire)
            while key:
                boundary_cuts.add(key)
                if forbidden: forbidden_cuts.add(key)
                key=hierarchy.parent_input(*key)
    owner_hierarchy_seen=set(); owner_hierarchy_leaves=set()
    for name,node in sorted(owners.items()):
        support=set()
        for pin in ('D','CE','R','S'):
            if pin in node['ports']:
                reached,_=hierarchy.dependencies(RF_PATH,node['ports'][pin],local_only=True)
                support.update(wire for path,wire in reached if path==RF_PATH)
                reached,leaves=hierarchy.dependencies(RF_PATH,node['ports'][pin],boundary_cuts=boundary_cuts)
                check(not(reached&forbidden_cuts),'Clear/allocation reaches promoted owner control '+name)
                owner_hierarchy_seen.update(reached); owner_hierarchy_leaves.update(leaves)
        forbidden=sorted(x for x in support if x.startswith(('io_clear','io_allocate')) or 'robAllocEn' in x or 'pop0_inst' in x or 'pop1_inst' in x)
        check(not forbidden,'Decode/allocation still reaches owner '+name)
        leaves=sorted(x for x in support if x not in cone.drivers and x not in cone.aliases and x not in ('',"1'b0","1'b1"))
        owner_cones.append({'q':name,'instance':node['name'],'boundary_inputs':leaves})
    # ADS promotes five tag-data muxes into the parent. All seven RAM read
    # interfaces must remain; exhaust selected bit-0 control cofactors for the
    # two muxes retained locally, and check every bit has a nonconstant output.
    read_bindings=[]
    for bank,(_,pins) in sorted(banks.items()):
        for read in range(7):
            port='R%d_data'%read
            check(port in pins and pins[port]=='_resultBanks_%d_ext_R%d_data'%(bank,read),
                  'Missing or changed result-bank read binding '+str((bank,read)))
            read_bindings.append({'bank':bank,'read_port':read,'wire':pins[port]})
    read_checks=[]
    for lane,read in ((2,4),(4,2)):
        targets=['io_tagData_%d[%d]'%(lane,bit) for bit in range(32)]
        primitives=[hierarchy.assert_nonconstant(RF_PATH,target) for target in targets]
        for target in targets:
            support=cone.fanin(target)
            check({'resultValid_%d'%tag for tag in range(32)} <= support,
                  'Valid masking was removed from '+target)
        count=0
        for tag,bank,valid,data in itertools.product(range(32),range(4),range(2),range(2)):
            local={name:0 for name in owners}
            local.update({'resultValid_%d'%index:0 for index in range(32)})
            local.update(bits('io_tagRead_'+str(lane),tag,5))
            local['resultValid_'+str(tag)]=valid
            if bank: local['resultOwner_%d_reg[%d]'%(tag,bank)]=1
            for data_bank in range(4):
                local.update(bits('_resultBanks_%d_ext_R%d_data'%(data_bank,read),
                                  0xffffffff if data_bank==bank and data else 0,32))
            actual=hierarchy.evaluate(RF_PATH,targets[0],{(RF_PATH,k):v for k,v in local.items()})
            check(actual==(valid and data),'ROB local read select/valid masking mismatch '+str((lane,tag,bank,valid,data)))
            count+=1
        read_checks.append({'tag_lane':lane,'bank_read_port':read,'tested_data_bit':0,
                            'checked_vectors':count,'nonconstant_bits':len(primitives)})
    return {'status':'PASS', 'scope':'MAPPED_ROB_C1_LIMITED',
            'tag_live_ff':32,'result_valid_ff':32,'owner_ff':len(owners),'owner_tags':32,
            'banks':bank_results,'owner_cones':owner_cones,
            'read_port_bindings':read_bindings,'local_read_checks':read_checks,
            'owner_clear_dependency_absent':True,
            'owner_hierarchy_nodes':len(owner_hierarchy_seen),
            'owner_hierarchy_boundary_leaves':['/'.join(path)+'/'+wire for path,wire in sorted(owner_hierarchy_leaves)],
            'full_sequential_equivalence_proven':False,'routed_timing_or_board_proven':False,
            'disabled_interface_port':3,
            'disabled_port_basis':'RsMem.scala explicitly drives issuePairValid/issuePairFire/issuePairAccept false',
            'limitations':['6144 bank WE vectors cover selected live bit and one-hot alternatives; not all 2^32 tagLive states',
                           'Seven bank read interfaces retained; full 32-bit truth tables of five promoted read muxes are not proved',
                           'Owner hierarchy traversal stops at mapped FFs and declared WB/reset/flush interfaces',
                           'ResultValid clear-priority and full lifecycle semantics rely on RTL regression and affected board validation']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--netlist',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--input-snapshot',type=Path)
    args=parser.parse_args()
    source=args.netlist.read_text(encoding='utf-8',errors='strict')
    try:
        result=audit(source)
        if args.input_snapshot: result=bind_result(result,args.netlist,args.input_snapshot)
    except (ValueError,KeyError) as error:
        result={'status':'FAIL','error':str(error)}
    result['schema']=1;result['vm_sha256']=hashlib.sha256(args.netlist.read_bytes()).hexdigest()
    result['checker_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('ROB_OWNER_ADS_'+result['status'])
    if 'error' in result: print(result['error'])
    raise SystemExit(1 if result['status']=='FAIL' else 0)


if __name__=='__main__': main()
