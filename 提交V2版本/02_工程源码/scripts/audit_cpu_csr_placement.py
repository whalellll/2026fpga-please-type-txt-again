"""Strictly bind an optional CSR placement experiment to native executed sites."""
import argparse,hashlib,json,re
from pathlib import Path
PREFIX='u_cpu/u_cpu_wrapper/u_cpu/core/backend/u_csr_trap/'
EXPECTED={PREFIX+f'sepc[{i}]/opit_0_L6Q' for i in range(2,32)}|{PREFIX+'N1131/gateop',PREFIX+'mcause[8]/opit_0_L5Q'}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def canonical(s):return re.sub(r'_perm$','',s)
def sites(text,strict=False):
    result={}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):continue
        m=re.fullmatch(r'def_inst_site \{([^}]+)\} (CLM[AS]_\d+_\d+) (FY[ABCD])'+('' if strict else r'(?: -no_check)?'),line)
        if not m:
            if strict:raise ValueError('Unexpected placement command: '+line)
            continue
        name,site,slot=m.groups();name=canonical(name)
        if name in result:raise ValueError('Duplicate or ambiguous placement: '+name)
        result[name]=(site,slot)
    return result
def inputs(root):
    pcf=root/'pds/cpu75_csr_reference.pcf';contract=root/'pds/cpu75_csr_reference.json'
    q=json.loads(contract.read_text());requested=sites(pcf.read_text(),True)
    if q['cpu_rtl_sha256']!=sha(root/'rtl/cpu/CoreTop.sv') or q['cpu_hz'] not in (75000000,80000000):raise ValueError('Foreign CPU or clock contract')
    clock=json.loads((root/'config/clocks.json').read_text(encoding='utf-8-sig'))
    if clock['cpu_hz']!=q['cpu_hz']:raise ValueError('Wrong current clock')
    profile={75000000:('dedicated675',675000000,9),80000000:('dedicated800',800000000,10)}[q['cpu_hz']]
    if tuple(clock[k] for k in ('cpu_clock_source','cpu_pll_vco_hz','cpu_divisor'))!=profile or clock['sys_hz']!=49500000:raise ValueError('Wrong placement clock profile')
    rows={r['cell']:r for r in q['selected']}
    expected=EXPECTED if q['cpu_hz']==75000000 else EXPECTED-{PREFIX+'mcause[8]/opit_0_L5Q'}
    if set(rows)!=expected or set(requested)!=expected:raise ValueError('Missing or additional CSR constraints')
    if any(requested[n]!=tuple(rows[n]['reference_site']) for n in expected):raise ValueError('Unreviewed reference site/slot')
    if len(set(requested.values()))!=len(requested):raise ValueError('Slot collision')
    return q,requested
def post(root,stdout,mapped,actual):
    q,want=inputs(root);raw=stdout.read_text(errors='replace');mapping=mapped.read_text();got=sites(actual.read_text())
    snapshot=root/'pds/build_snapshot.json';snap=json.loads(snapshot.read_text(encoding='utf-8-sig'))
    for name in ['pds/cpu75_csr_reference.pcf','pds/cpu75_csr_reference.json','scripts/audit_cpu_csr_placement.py']:
        if snap['inputs'].get(name)!=sha(root/name):raise ValueError('Native snapshot differs: '+name)
    cells={}
    for name,kind in re.findall(r'(?m)^Inst\r?\n([^;\r\n]+);([^;\r\n]+)',(root/'pds/place_route/soc_top_pnr.netlist').read_text()):
        key=canonical(name)
        if key in cells:raise ValueError('Ambiguous native cell: '+key)
        cells[key]=kind
    for r in q['selected']:
        name=r['cell'];site,slot=want[name]
        line=f'def_inst_site {{{name}}} {site} {slot}'
        if len(re.findall(r'(?m)^Executing : '+re.escape(line)+r' successfully\.?\s*$',raw))!=1:raise ValueError('No unique strict execution: '+name)
        if mapping.splitlines().count(line)!=1:raise ValueError('Missing/duplicate mapped request: '+name)
        if got.get(name)!=(site,slot):raise ValueError('Final site differs: '+name)
        if cells.get(name)!=r['cell_type']:raise ValueError('Packed cell type differs: '+name)
    return dict(status=f"CPU{q['cpu_hz']//1000000}_CSR_NATIVE_STRICT_EXECUTION_AND_FINAL_SITES_PASS_NOT_STA_OR_BOARD",cells=len(want),
        run_id=snap['run_id'],snapshot_sha256=sha(snapshot),
        constraint_sha256=sha(root/'pds/cpu75_csr_reference.pcf'),contract_sha256=sha(root/'pds/cpu75_csr_reference.json'),
        actual_export_sha256=sha(actual),pnr_sha256=sha(root/'pds/place_route/soc_top_pnr.adf'))
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True)
    for n in ['stdout','mapped','actual','output']:ap.add_argument('--'+n,type=Path)
    a=ap.parse_args();q,want=inputs(a.root)
    if any([a.stdout,a.mapped,a.actual,a.output]):
        assert all([a.stdout,a.mapped,a.actual,a.output]);q=post(a.root,a.stdout,a.mapped,a.actual);a.output.write_text(json.dumps(q,indent=2)+'\n')
        print(q['status'],q['cells'])
    else:print(f"CPU{q['cpu_hz']//1000000}_CSR_STRICT_INPUT_CONTRACT_PASS",len(want))
if __name__=='__main__':main()
