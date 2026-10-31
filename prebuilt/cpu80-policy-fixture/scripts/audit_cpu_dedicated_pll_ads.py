"""Check the actual mapped dedicated CPU GPLL, independently of FDC periods.

Read-only ADS evidence. Does not establish routed timing or board operation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
from decimal import Decimal, ROUND_HALF_UP

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--netlist',type=Path,required=True)
p.add_argument('--clocks',type=Path,required=True)
p.add_argument('--resources',type=Path,required=True)
p.add_argument('--fdc',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
clock=json.loads(a.clocks.read_text())
profiles={
    'dedicated850p5': (70875000,850500000,12,2,'15.75'),
    'dedicated675': (75000000,675000000,9,1,'25.0'),
}
assert clock['cpu_clock_source'] in profiles,'Unreviewed dedicated clock profile'
cpu_hz,vco_hz,divisor,multiplier,feedback=profiles[clock['cpu_clock_source']]
assert clock['cpu_hz']==cpu_hz and clock['cpu_pll_vco_hz']==vco_hz
assert clock['sys_hz']==clock['timebase_hz']==49500000 and clock['cpu_divisor']==divisor
physical_period=Decimal(1000000000)/Decimal(cpu_hz)
constraint_period=Decimal('13.320000') if clock['cpu_clock_source']=='dedicated675' else physical_period
assert constraint_period<=physical_period,'Timing target may not relax physical period'
period=str(constraint_period.quantize(Decimal('0.000001'),rounding=ROUND_HALF_UP))
text=a.netlist.read_text()
modules=re.findall(r'(?ms)^module pll_cpu\b(.*?)^endmodule',text)
assert len(modules)==1,'Dedicated CPU PLL module missing or duplicated'
module=modules[0]
clock_annotations=re.findall(r'SDC constraint\s*:\s*\(object CLKOUT3\).*?\(clock ([^)]+)\)',module)
assert clock_annotations==['cpu_clk'],('CPU PLL does not carry the declared cpu_clk in native ADS',clock_annotations)
assert '(inferred)' not in module,'Unexpected automatically inferred CPU clock'
fdc=a.fdc.read_text()
assert len(re.findall(r'(?m)^create_clock -name \{cpu_clk\} -period \{'+re.escape(period)+r'\} \[get_nets \{g_dedicated_cpu\.u_cpu_pll/clkout3\}\]\s*$',fdc))==1,'FDC CPU clock target mismatch'
sys_period='20.202000' if clock['cpu_clock_source']=='dedicated675' else '20.202020'
assert len(re.findall(r'(?m)^create_clock -name \{sys_clk\} -period \{'+re.escape(sys_period)+r'\} \[get_nets \{u_video_pll/clkout1\}\]\s*$',fdc))==1,'FDC SYS timing grid mismatch'
assert len(re.findall(r'\bGTP_GPLL\b',module))==1
for name,value in [('CLKIN_FREQ','27.0'),('STATIC_RATIOI','1'),('STATIC_RATIOM',str(multiplier)),
                   ('STATIC_RATIOF',feedback),('STATIC_RATIO3',str(divisor)),('STATIC_DUTY3',str(divisor))]:
    found=re.findall(r'\.'+name+r'\s*\(\s*([\d.]+)\s*\)',module)
    assert len(found)==1 and float(found[0])==float(value),(name,found)
for name,value in [('INTERNAL_FB','CLKOUTF'),('EXTERNAL_FB','DISABLE'),('SSC_MODE','DISABLE'),
                   ('CLK_DPS3_EN','FALSE'),('CLKOUT3_SYN_EN','FALSE')]:
    assert re.findall(r'\.'+name+r'\s*\(\s*"([^"]+)"\s*\)',module)==[value],name
for name,net in [('CLKIN1','clkin1'),('CLKOUT3','clkout3'),('LOCK','lock')]:
    assert len(re.findall(r'\.'+name+r'\s*\(\s*'+net+r'\s*\)',module))==1,name
instances=re.findall(r'(?s)\bpll_cpu\s+\\g_dedicated_cpu\.u_cpu_pll\s*\((.*?)\);',text)
assert len(instances)==1
for name,net in [('clkout3','cpu_clk'),('lock','cpu_pll_lock'),('clkin1','nt_free_clk')]:
    assert re.findall(r'\.'+name+r'\s*\(\s*([\w]+)\s*\)',instances[0])==[net],name
resource=a.resources.read_text()
assert re.search(r'GTP_GPLL\s+4 uses\b',resource),'Expected four mapped GPLLs'
counts={}
for key,pattern in [('lut',r'Total LUTs:\s+(\d+)'),('ff',r'Total Registers:\s+(\d+)'),
                    ('latch',r'Total Latches:\s+(\d+)'),('drm',r'Total DRM =\s+([\d.]+)'),
                    ('apm',r'Total APMs =\s+([\d.]+)')]:
    counts[key]=float(re.search(pattern,resource).group(1))
assert counts['latch']==0 and counts['drm']==120.5 and counts['apm']==177
record=dict(status='DEDICATED_CPU_PLL_ADS_PASS_NOT_STA_OR_BOARD',cpu_hz=cpu_hz,sys_hz=49500000,
    sta_cpu_period_ns=period,sta_sys_period_ns=sys_period,
    pll_vco_hz=vco_hz,mapped_gpll=4,resources=counts,
    native_cpu_clock_name='cpu_clk',audit_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    inputs={str(path):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [a.netlist,a.clocks,a.resources,a.fdc,Path(__file__)]})
a.output.write_text(json.dumps(record,indent=2)+'\n')
print(f'DEDICATED_CPU_PLL_ADS_PASS cpu={cpu_hz} sys=49500000 gpll=4 drm=120.5 apm=177 NOT_STA_OR_BOARD')
