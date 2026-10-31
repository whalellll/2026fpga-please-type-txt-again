"""Mutation tests for the mapped PLL checker; not new FPGA evidence."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--netlist',type=Path,required=True)
p.add_argument('--clocks',type=Path,required=True)
p.add_argument('--resources',type=Path,required=True)
p.add_argument('--fdc',type=Path,required=True)
p.add_argument('--report',type=Path,required=True)
a=p.parse_args()
text=a.netlist.read_text()
module=re.search(r'(?ms)^module pll_cpu\b.*?^endmodule',text).group(0)
instance=re.search(r'(?s)\bpll_cpu\s+\\g_dedicated_cpu\.u_cpu_pll\s*\(.*?\);',text).group(0)
fixture=module+'\n'+instance
bad_annotation_fixture=fixture
if "(inferred)" not in bad_annotation_fixture:
    bad_annotation_fixture=bad_annotation_fixture.replace("(clock cpu_clk)","(clock free_clk|unreviewed) (inferred)")
fixture=re.sub(r'\(clock free_clk\|[^)]+\) \(inferred\)', '(clock cpu_clk) (738 : FIXTURE_ONLY/soc.fdc)',fixture)
resource=a.resources.read_text()
clock=json.loads(a.clocks.read_text())
cases=[('valid_excerpt',fixture,resource,clock,True)]
cases.append(('inferred_cpu_clock',bad_annotation_fixture,resource,clock,False))
for name,pattern,replacement in [
    ('wrong_feedback',r'\.STATIC_RATIOF\(15\.75\)', '.STATIC_RATIOF(16.5)'),
    ('wrong_divisor',r'\.STATIC_RATIO3\(12\)', '.STATIC_RATIO3(13)'),
    ('wrong_output',r'\.clkout3 \(cpu_clk\)', '.clkout3 (wrong_clk)'),
    ('dynamic_phase',r'\.CLK_DPS3_EN\("FALSE"\)', '.CLK_DPS3_EN("TRUE")'),
]:
    changed,count=re.subn(pattern,replacement,fixture)
    assert count==1,(name,count)
    cases.append((name,changed,resource,clock,False))
cases.append(('wrong_gpll_count',fixture,resource.replace('GTP_GPLL                      4 uses','GTP_GPLL                      3 uses'),clock,False))
bad=dict(clock,cpu_hz=74250000)
cases.append(('wrong_declared_frequency',fixture,resource,bad,False))
# New-profile fixtures are synthetic checker coverage, never routed evidence.
fixture75=fixture
for old,new in [('.STATIC_RATIOM(2)','.STATIC_RATIOM(1)'),
                ('.STATIC_RATIOF(15.75)','.STATIC_RATIOF(25.0)'),
                ('.STATIC_RATIO3(12)','.STATIC_RATIO3(9)'),
                ('.STATIC_DUTY3(12)','.STATIC_DUTY3(9)')]:
    assert fixture75.count(old)==1,old
    fixture75=fixture75.replace(old,new)
clock75=dict(clock,cpu_clock_source='dedicated675',cpu_hz=75000000,cpu_pll_vco_hz=675000000,cpu_divisor=9)
cases.append(('valid_cpu75_excerpt',fixture75,resource,clock75,True))
cases.append(('cpu75_wrong_divisor',fixture75.replace('.STATIC_RATIO3(9)','.STATIC_RATIO3(12)'),resource,clock75,False))
cases.append(('cpu75_untightened_fdc',fixture75,resource,clock75,False))
cases.append(('cpu75_mixed_precision_sys',fixture75,resource,clock75,False))
results=[]
with tempfile.TemporaryDirectory(prefix='cpu-pll-check-') as d:
    work=Path(d)
    for name,vm,snr,config,accepted in cases:
        (work/'mapped.vm').write_text(vm)
        (work/'resources.txt').write_text(snr)
        (work/'clocks.json').write_text(json.dumps(config))
        out=work/(name+'.json')
        fdc_text=a.fdc.read_text()
        if config.get('cpu_clock_source')=='dedicated675':
            fdc_text=fdc_text.replace('14.109347','13.320000')
            fdc_text=fdc_text.replace('20.202020','20.202000')
            if name=='cpu75_untightened_fdc':fdc_text=fdc_text.replace('13.320000','13.333333')
            if name=='cpu75_mixed_precision_sys':fdc_text=fdc_text.replace('20.202000','20.202020')
        (work/'soc.fdc').write_text(fdc_text)
        result=subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('audit_cpu_dedicated_pll_ads.py')),
            '--netlist',str(work/'mapped.vm'),'--resources',str(work/'resources.txt'),
            '--clocks',str(work/'clocks.json'),'--fdc',str(work/'soc.fdc'),'--output',str(out)],capture_output=True,timeout=30)
        assert (result.returncode==0)==accepted,(name,result.stderr.decode(errors='replace')[-1500:])
        assert out.exists()==accepted,name
        if accepted:
            receipt=json.loads(out.read_text())
            assert receipt['cpu_hz']==config['cpu_hz'] and receipt['pll_vco_hz']==config['cpu_pll_vco_hz'],name
        results.append(dict(name=name,expected_accepted=accepted,exit=result.returncode))
record=dict(status='PLL_CHECKER_FIXTURES_PASS_NOT_HARDWARE',cases=results,
    scope='Synthetic mapped excerpts and mutations including the preserved native inferred-clock failure; not new hardware evidence.')
a.report.write_text(json.dumps(record,indent=2)+'\n')
print(f'DEDICATED_PLL_CHECKER_FIXTURES_PASS cases={len(cases)} NOT_HARDWARE')
