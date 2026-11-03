"""Apply only the selected original generator's intended trap substitution."""
from pathlib import Path
import ast,hashlib,json,os,re,runpy
B=Path(__file__).resolve().parent;C=B/'cpu-source/cpu';out=C/'work/cpu-test'
name=os.environ['CPU_TEST_ORIGINAL_GENERATOR'];allowed={'cpu','atomic','privileged','memory_order','bus_error','ialign32','write_error'}
assert name.startswith('scripts/generate_') and name.endswith('_test.py')
kind=name[len('scripts/generate_'):-len('_test.py')];assert kind in allowed
original=C/name;raw=original.read_bytes();tree=ast.parse(raw.decode('utf-8-sig'))
intents=[]
for node in ast.walk(tree):
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='replace' and len(node.args)>=2 and all(isinstance(a,ast.Constant) and isinstance(a.value,str) for a in node.args[:2]):
        before,after=[a.value for a in node.args[:2]]
        if '$fatal' in before and 'Unexpected architectural trap in CoreMark pc=%h' in before:
            assert '$display' in after and 'dut.u_cpu.core.backend.cmt_csr_pc' in after
            intents.append((before,after))
assert len(intents)<=1
runpy.run_path(str(original),run_name='__main__')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
program_sha=sha(out/'test.S');oracle_sha=sha(out/'oracle.json')
tb=out/'tb_cpu_architecture.v';text=tb.read_text();applied=False
if intents:
    pattern=r'\$fatal\(\s*1\s*,\s*"Unexpected architectural trap in CoreMark pc=%h"\s*,\s*dut\.u_cpu\.core\.backend\.cmt_csr_pc\s*\);'
    matches=list(re.finditer(pattern,text));assert len(matches)<=1
    if matches:
        text=re.sub(pattern,lambda _:intents[0][1],text,count=1);tb.write_text(text);applied=True
    assert not re.search(pattern,text) and intents[0][1] in text
assert sha(out/'test.S')==program_sha and sha(out/'oracle.json')==oracle_sha
receipt=dict(generator=name,generator_sha256=hashlib.sha256(raw).hexdigest(),adapter_sha256=sha(Path(__file__)),original_intended_trap_replacement=bool(intents),whitespace_compatibility_fix_applied=applied,assembly_sha256=program_sha,oracle_sha256=oracle_sha,testbench_sha256=sha(tb),scope='Only execute the original generator-intended trap display replacement robustly to whitespace. Original assembly/oracle/pass-fail markers unchanged; no blanket trap suppression.')
(out/'fixture-adaptation.json').write_text(json.dumps(receipt,indent=2)+'\n')
