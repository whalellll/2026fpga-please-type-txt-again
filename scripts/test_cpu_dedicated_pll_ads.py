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
# CPU80 switches the actual reference input, not only the declared period.
fixture80=fixture75
for old,new in [('.CLKIN_FREQ(27)','.CLKIN_FREQ(125.0)'),('.STATIC_RATIOI(1)','.STATIC_RATIOI(5)'),
                ('.STATIC_RATIOF(25.0)','.STATIC_RATIOF(32.0)'),('.STATIC_RATIO3(9)','.STATIC_RATIO3(10)'),
                ('.STATIC_DUTY3(9)','.STATIC_DUTY3(10)'),('.clkin1 (nt_free_clk)','.clkin1 (ref_clk)')]:
    assert fixture80.count(old)==1,old
    fixture80=fixture80.replace(old,new)
fixture80+='\nGTP_INBUFDS #(.IOSTANDARD("DEFAULT"), .TERM_DIFF("ON")) u_refclk (.O(ref_clk), .I(ref_clk_p), .IB(ref_clk_n));\nmodule MacAccelCore; endmodule\nmodule pff1_stagea_gather; endmodule\n'
resource80=re.sub(r'(Total DRM =\s+)120\.5',r'\g<1>119.5',resource)
resource80=re.sub(r'(Total APMs =\s+)177',r'\g<1>171',resource80)
assert resource80!=resource
clock80=dict(clock75,cpu_clock_source='dedicated800',cpu_hz=80000000,cpu_pll_vco_hz=800000000,cpu_divisor=10,cpu_reference_hz=125000000)
cases.append(('valid_cpu80_excerpt',fixture80,resource80,clock80,True))
for name,old,new in [('cpu80_wrong_input','.clkin1 (ref_clk)','.clkin1 (nt_free_clk)'),
                     ('cpu80_wrong_idiv','.STATIC_RATIOI(5)','.STATIC_RATIOI(1)'),
                     ('cpu80_wrong_reference','.CLKIN_FREQ(125.0)','.CLKIN_FREQ(27.0)'),
                     ('cpu80_wrong_buffer','.IB(ref_clk_n)','.IB(free_clk)'),
                     ('cpu80_missing_gather','module pff1_stagea_gather; endmodule',''),
                     ('cpu80_legacy_present','module MacAccelCore; endmodule','module MacAccelCore; endmodule\nmodule xiangqi_sparse_eval; endmodule')]:
    assert fixture80.count(old)==1,(name,old)
    cases.append((name,fixture80.replace(old,new),resource80,clock80,False))
cases.append(('cpu80_wrong_resources',fixture80,resource,clock80,False))
cases.append(('cpu80_loose_fdc',fixture80,resource80,clock80,False))
cases.append(('cpu80_wrong_ref_fdc',fixture80,resource80,clock80,False))
fixture_frac=fixture75.replace('(object CLKOUT3)','(object CLKOUT0)').replace('.clkout3 (cpu_clk)','.clkout0 (cpu_clk)')
for name,value in [('STATIC_RATIOF','40.0'),('STATIC_RATIO0','13.5'),('STATIC_DUTY0','13'),('STATIC_CPHASE0','1'),('STATIC_RATIO3','27'),('STATIC_DUTY3','27')]:
    fixture_frac,count=re.subn(r'\.'+name+r'\([\d.]+\)','.'+name+'('+value+')',fixture_frac)
    assert count==1,name
fixture_frac,count=re.subn(r'\.CLKOUT0\s*\([^)]*\)','.CLKOUT0(clkout0)',fixture_frac)
if count==0:fixture_frac=fixture_frac.replace('.CLKOUT3(','.CLKOUT0(clkout0), .CLKOUT3(')
else:assert count==1
fixture_frac+='\nmodule MacAccelCore; endmodule\nmodule pff1_stagea_gather; endmodule\n'
clock_frac=dict(clock75,cpu_clock_source='dedicated1080frac',cpu_hz=80000000,cpu_pll_vco_hz=1080000000,cpu_divisor=27,cpu_reference_hz=27000000,cpu_output_divisor_eighths=108)
cases.append(('valid_cpu80_fractional_excerpt',fixture_frac,resource80,clock_frac,True))
for name,old,new in [('frac_wrong_divider','.STATIC_RATIO0(13.5)','.STATIC_RATIO0(13.0)'),('frac_wrong_phase','.STATIC_CPHASE0(1)','.STATIC_CPHASE0(0)'),('frac_wrong_output','.clkout0 (cpu_clk)','.clkout3 (cpu_clk)')]:
    assert fixture_frac.count(old)==1,(name,old)
    cases.append((name,fixture_frac.replace(old,new),resource80,clock_frac,False))
cases.append(('frac_wrong_fdc_output',fixture_frac,resource80,clock_frac,False))
results=[]
with tempfile.TemporaryDirectory(prefix='cpu-pll-check-') as d:
    work=Path(d)
    for name,vm,snr,config,accepted in cases:
        (work/'mapped.vm').write_text(vm)
        (work/'resources.txt').write_text(snr)
        (work/'clocks.json').write_text(json.dumps(config))
        out=work/(name+'.json')
        fdc_text=a.fdc.read_text()
        mode=config.get('cpu_clock_source')
        if mode in ('dedicated675','dedicated800','dedicated1080frac'):
            fdc_text=fdc_text.replace('14.109347','13.320000')
            fdc_text=fdc_text.replace('20.202020','20.202000')
            if name=='cpu75_untightened_fdc':fdc_text=fdc_text.replace('13.320000','13.333333')
            if name=='cpu75_mixed_precision_sys':fdc_text=fdc_text.replace('20.202000','20.202020')
        extra=[]
        if mode in ('dedicated800','dedicated1080frac'):
            fdc_text=fdc_text.replace('13.320000','12.495000')
            if name=='cpu80_loose_fdc':fdc_text=fdc_text.replace('12.495000','12.500000')
            if name=='cpu80_wrong_ref_fdc':fdc_text=fdc_text.replace('-period {8.0}','-period {37.037037}')
            (work/'soc_top.v').write_text('module soc_top #(parameter integer ENABLE_H128_SPARSE = 0)(); endmodule\n')
            extra=['--soc-top',str(work/'soc_top.v')]
        if mode=='dedicated1080frac':
            if name!='frac_wrong_fdc_output':fdc_text=fdc_text.replace('g_dedicated_cpu.u_cpu_pll/clkout3','g_dedicated_cpu.u_cpu_pll/clkout0')
        (work/'soc.fdc').write_text(fdc_text)
        result=subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('audit_cpu_dedicated_pll_ads.py')),
            '--netlist',str(work/'mapped.vm'),'--resources',str(work/'resources.txt'),
            '--clocks',str(work/'clocks.json'),'--fdc',str(work/'soc.fdc'),'--output',str(out),*extra],capture_output=True,timeout=30)
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
