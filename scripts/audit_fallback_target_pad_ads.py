"""Prove the shared BTB target write pad and both native target RAM views."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from audit_icache_pad_ads import cells, clean, module, ports, sha


def need(ok, message):
    if not ok:
        raise ValueError('Fallback target pad ADS: ' + message)


def expand(value, widths):
    value = re.sub(r'\s+', '', value)
    if value.startswith('{') and value.endswith('}'):
        return [bit for part in value[1:-1].split(',') for bit in expand(part, widths)]
    match = re.fullmatch(r"(\d+)'([bh])([0-9a-fA-F_]+)", value)
    if match:
        number = int(match[3].replace('_', ''), 2 if match[2] == 'b' else 16)
        return ["1'b" + str((number >> bit) & 1) for bit in reversed(range(int(match[1])))]
    match = re.fullmatch(r'([A-Za-z_][\w$]*)\[(\d+):(\d+)\]', value)
    if match:
        high, low = int(match[2]), int(match[3])
        need(high >= low, 'unknown ascending bus')
        return [f'{match[1]}[{bit}]' for bit in range(high, low - 1, -1)]
    if re.fullmatch(r'[A-Za-z_][\w$]*\[\d+\]', value):
        return [value]
    if re.fullmatch(r'[A-Za-z_][\w$]*', value):
        width = widths.get(value, 1)
        return [f'{value}[{bit}]' for bit in reversed(range(width))] if width > 1 else [value]
    raise ValueError('Unknown fallback mapped connection: ' + value)


def audit(source, standalone_fixture=False):
    if not standalone_fixture:
        for parent, kind, instance in (
            ('soc_top','core_top','u_cpu'),('core_top','cpu_core_top','u_cpu_wrapper'),
            ('cpu_core_top','CoreTop','u_cpu'),('CoreTop','Core','core'),
            ('Core','CoreFrontend','frontend'),('CoreFrontend','FallbackBtb','fallback')):
            found = cells(module(source, parent), kind)
            need(len(found) == 1 and found[0]['name'] == instance, 'actual top hierarchy')
    pad = module(source, 'PangoFallbackTargetPad')
    body = module(source, 'FallbackBtb')
    need(not re.search(r'\bassign\b', clean(pad)), 'pad alias or behavioral replacement')
    need(re.search(r'\binput\s+\[31:0\]\s+dataIn\b', pad), 'input width')
    need(re.search(r'\boutput\s+\[31:0\]\s+dataOut\b', pad), 'output width')
    primitives = cells(pad, 'GTP_LUT6D')
    need(len(primitives) == 16, 'sixteen preserved pairs required')
    need(set(re.findall(r'\bGTP_\w+', clean(pad))) == {'GTP_LUT6D'}, 'unknown pad primitive')
    seen = set()
    for cell in primitives:
        match = re.fullmatch(r'\\data_pad\[(\d+)\]\.u_hold_dual_lut', cell['name'])
        need(match is not None, 'unknown pair instance')
        pair = int(match[1]); need(0 <= pair < 16 and pair not in seen, 'pair coverage')
        seen.add(pair)
        need((cell['attr'] or '').strip() == '(* PAP_DONT_TOUCH *)', 'preservation attribute')
        init = ports(cell['params'] or '').get('INIT', '')
        match = re.fullmatch(r"64'([bh])([0-9a-fA-F_]+)", init)
        need(match and int(match[2].replace('_',''), 2 if match[1]=='b' else 16)==0xCCCCCCCCAAAAAAAA,
             'identity INIT')
        pin = ports(cell['ports'])
        need(set(pin)=={'I0','I1','I2','I3','I4','I5','Z','Z5'}, 'primitive port set')
        expected = dict(I0=f'dataIn[{2*pair}]',I1=f'dataIn[{2*pair+1}]',
                        I2="1'b0",I3="1'b0",I4="1'b0",I5="1'b1",
                        Z5=f'dataOut[{2*pair}]',Z=f'dataOut[{2*pair+1}]')
        need(pin==expected, 'pair source, fixed input or output mismatch')
    refs = Counter(map(int,re.findall(r'\bdataOut\[(\d+)\]',clean(pad))))
    need(refs==Counter({bit:1 for bit in range(32)}), 'pad output driver coverage')
    links=cells(body,'PangoFallbackTargetPad')
    need(len(links)==1 and links[0]['name'] in ('targetHoldPad','targetForWrite_targetHoldPad'), 'one actual shared pad')
    widths={name:int(high)+1 for high,name in re.findall(
        r'\b(?:wire|input|output)\s+\[(\d+):0\]\s+([A-Za-z_][\w$]*)',body)}
    pin=ports(links[0]['ports'])
    need(set(pin)=={'dataIn','dataOut'}, 'shared pad ports')
    need(expand(pin['dataIn'],widths)==[f'io_updTarget[{bit}]' for bit in reversed(range(32))],
         'shared pad source bypass, tie or bit permutation')
    padded=expand(pin['dataOut'],widths)
    need(len(padded)==32 and len(set(padded))==32, 'pad output aliases')
    for net in padded:
        need(not re.search(r'\bassign\s+'+re.escape(net)+r'\s*=',clean(body)), 'pad output alias driver')
    for kind in set(re.findall(r'\bGTP_\w+',clean(body))):
        for cell in cells(body,kind):
            pins=ports(cell['ports'])
            for output in ('Q','Z','Z5','COUT','CO','DO'):
                # Unrelated native escaped nets need no interpretation. Any
                # driver mentioning the actual pad bus must be resolved.
                if output in pins and any(net.split('[')[0] in pins[output] for net in padded):
                    need(not set(expand(pins[output],widths)) & set(padded), 'multiple pad-output drivers')
    children=re.findall(r'(?m)^\s*(\w+)\s+(entryMem_[01]_ext)\s*\(',clean(body))
    need(len(children)==2 and {instance for _,instance in children}=={'entryMem_0_ext','entryMem_1_ext'},
         'both target RAM views required')
    views=[]
    for kind,instance in children:
        found=[cell for cell in cells(body,kind) if cell['name']==instance]
        need(len(found)==1,'duplicate RAM instance')
        pins=ports(found[0]['ports'])
        data=expand(pins['W0_data'],widths)
        need(len(data)>=32 and data[-32:]==padded,'RAM target DI bypass or bit permutation')
        need(pins.get('R0_clk')=='clock','RAM clock domain')
        ram=module(source,kind)
        need(re.search(r'\binput\s+\[5:0\]\s+R0_addr\b',ram) and
             re.search(r'\binput\s+\[5:0\]\s+R1_addr\b',ram),'64-row capacity')
        covered=[]
        for primitive in set(re.findall(r'\bGTP_\w+',clean(ram))):
            for cell in cells(ram,primitive):
                q=ports(cell['ports']);match=re.fullmatch(r'W0_data\[(\d+)\]',q.get('DI',''))
                if not match or int(match[1])>=32: continue
                bit=int(match[1]);covered.append(bit)
                need(primitive=='GTP_RAM64X1DP','target storage mapping')
                need(q.get('DO')==f'R1_data[{bit}]' and q.get('RADDR')=='R1_addr' and
                     q.get('WADDR')=='R0_addr' and q.get('WCLK')=='R0_clk' and q.get('WE')=='W0_en',
                     'target read/write address, data or control')
        need(Counter(covered)==Counter({bit:1 for bit in range(32)}),'target DI/read capacity coverage')
        views.append(dict(instance=instance,module=kind,target_bits=32,rows=64,module_sha256=hashlib.sha256(ram.encode()).hexdigest()))
    return dict(status='PASS',required=True,scope='MAPPED_FALLBACK_TARGET_WRITE_PADS_ONLY_NOT_STA_OR_BOARD',
                source_pairs=16,data_bits=32,di_pins_checked=64,views=views,unique_drivers=True,bypass=False)


def bind_result(netlist, snapshot_path):
    snapshot=json.loads(snapshot_path.read_text(encoding='utf-8-sig'))
    root=snapshot_path.resolve().parent.parent
    rtl=root/'rtl/cpu/CoreTop.sv'
    need(sha(rtl)==snapshot['inputs']['rtl/cpu/CoreTop.sv'],'CPU source binding')
    for name in ('audit_fallback_target_pad_ads.py','audit_icache_pad_ads.py'):
        need(snapshot['inputs']['scripts/'+name]==sha(Path(__file__).with_name(name)),'checker/parser binding')
    source=netlist.read_text(encoding='utf-8');raw=rtl.read_text(encoding='utf-8')
    required=bool(re.search(r'(?m)^module\s+PangoFallbackTargetPad\b',raw))
    if required:
        result=audit(source)
    else:
        need('PangoFallbackTargetPad' not in raw and 'PangoFallbackTargetPad' not in source,'unreviewed pad source/profile')
        result=dict(status='PASS',required=False,scope='LEGACY_CPU_WITHOUT_FALLBACK_TARGET_PAD_NO_PAD_CLAIM')
    result.update(run_id=snapshot['run_id'],input_snapshot_sha256=sha(snapshot_path),
        netlist_sha256=sha(netlist),checker_sha256=sha(Path(__file__)),
        parser_sha256=sha(Path(__file__).with_name('audit_icache_pad_ads.py')),
        cpu_rtl_sha256=snapshot['inputs']['rtl/cpu/CoreTop.sv'])
    return result


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--netlist',type=Path,required=True)
    ap.add_argument('--input-snapshot',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();need(not args.output.exists(),'refuse overwrite')
    result=bind_result(args.netlist,args.input_snapshot)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('FALLBACK_TARGET_PAD_ADS_PASS required='+str(result['required']))
