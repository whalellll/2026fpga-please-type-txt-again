"""Exercise the exact PowerShell selector used by both native audit entries."""
from pathlib import Path
import argparse, hashlib, json, re, subprocess, tempfile
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
root=Path(__file__).resolve().parents[1]; cases=[]; sources={}
for name in ['build_cpu_ads_gate.ps1','build_fpga.ps1']:
    path=root/'scripts'/name;text=path.read_text(encoding='utf-8-sig')
    match=re.findall(r'(?m)^\s*\$halfOutputPmaAdapter = (.* -and\n\s*.*dedicated1147p5frac\x27\))',text)
    assert len(match)==1,name
    sources[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='half-pma-selector-') as directory:
        target=Path(directory);(target/'rtl/soc').mkdir(parents=True);(target/'config').mkdir()
        for half,clock,expected in [(0,'dedicated1080frac',False),(1,'dedicated1080frac',False),(0,'dedicated1147p5frac',False),(1,'dedicated1147p5frac',True)]:
            (target/'rtl/soc/soc_top.v').write_text('.HALF_OUTPUT('+str(half)+')')
            (target/'config/clocks.json').write_text(json.dumps(dict(cpu_clock_source=clock)))
            # Source the exact extracted selector; no native evaluator mock.
            script="$root='"+str(target).replace("'","''")+"'\n[bool]("+match[0]+")"
            result=subprocess.run(['powershell.exe','-NoProfile','-Command',script],capture_output=True,text=True,timeout=30)
            assert result.returncode==0 and result.stdout.strip()==str(expected),(name,half,clock,result.stdout,result.stderr)
            cases.append(dict(entry=name,half=half,clock=clock,adapter=expected))
assert not a.output.exists()
a.output.write_text(json.dumps(dict(status='HALF80_STANDARD_HALF85_PROVEN_ADAPTER_SELECTION_PASS',cases=cases,source_sha256=sources),indent=2)+'\n')
print('HALF80_STANDARD_HALF85_PROVEN_ADAPTER_SELECTION_PASS cases=8')
