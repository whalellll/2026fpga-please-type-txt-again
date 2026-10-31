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
p.add_argument('--soc-top',type=Path)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
clock=json.loads(a.clocks.read_text())
profiles={
    'dedicated850p5': (70875000,850500000,12,2,'15.75',27,1),
    'dedicated675': (75000000,675000000,9,1,'25.0',27,1),
    'dedicated800': (80000000,800000000,10,1,'32.0',125,5),
    'dedicated1080frac': (80000000,1080000000,27,1,'40.0',27,1),
    'dedicated1147p5frac': (85000000,1147500000,27,1,'42.5',27,1),
    'dedicated945frac': (70000000,945000000,27,1,'35.0',27,1),
}
assert clock['cpu_clock_source'] in profiles,'Unreviewed dedicated clock profile'
cpu_hz,vco_hz,divisor,multiplier,feedback,reference_mhz,input_divisor=profiles[clock['cpu_clock_source']]
is60=clock['cpu_clock_source']=='dedicated1080frac' and clock['cpu_divisor']==36
if is60: cpu_hz,divisor=60000000,36
is80=clock['cpu_clock_source']=='dedicated800'
fractional=clock['cpu_clock_source'] in ('dedicated1080frac','dedicated1147p5frac','dedicated945frac')
output='0' if fractional else '3'
if is80:
    assert clock['cpu_reference_hz']==125000000 and a.soc_top,'CPU80 requires explicit reference and SoC source'
if fractional:
    assert clock['cpu_reference_hz']==27000000 and clock['cpu_output_divisor_eighths']==divisor*4 and a.soc_top
assert clock['cpu_hz']==cpu_hz and clock['cpu_pll_vco_hz']==vco_hz
assert clock['sys_hz']==clock['timebase_hz']==49500000 and clock['cpu_divisor']==divisor
physical_period=Decimal(1000000000)/Decimal(cpu_hz)
constraint_period=Decimal('14.282000') if clock['cpu_clock_source']=='dedicated945frac' else Decimal('16.650000') if is60 else Decimal('11.760000') if clock['cpu_clock_source']=='dedicated1147p5frac' else Decimal('12.495000') if is80 or fractional else Decimal('13.320000') if clock['cpu_clock_source']=='dedicated675' else physical_period
assert constraint_period<=physical_period,'Timing target may not relax physical period'
period=str(constraint_period.quantize(Decimal('0.000001'),rounding=ROUND_HALF_UP))
text=a.netlist.read_text()
modules=re.findall(r'(?ms)^module pll_cpu\b(.*?)^endmodule',text)
assert len(modules)==1,'Dedicated CPU PLL module missing or duplicated'
module=modules[0]
clock_annotations=re.findall(r'SDC constraint\s*:\s*\(object CLKOUT'+output+r'\).*?\(clock ([^)]+)\)',module)
assert clock_annotations==['cpu_clk'],('CPU PLL does not carry the declared cpu_clk in native ADS',clock_annotations)
assert '(inferred)' not in module,'Unexpected automatically inferred CPU clock'
fdc=a.fdc.read_text()
assert len(re.findall(r'(?m)^create_clock -name \{cpu_clk\} -period \{'+re.escape(period)+r'\} \[get_nets \{g_dedicated_cpu\.u_cpu_pll/clkout'+output+r'\}\]\s*$',fdc))==1,'FDC CPU clock target mismatch'
sys_period='20.202000' if clock['cpu_clock_source'] in ('dedicated675','dedicated800','dedicated1080frac','dedicated1147p5frac','dedicated945frac') else '20.202020'
assert len(re.findall(r'(?m)^create_clock -name \{sys_clk\} -period \{'+re.escape(sys_period)+r'\} \[get_nets \{u_video_pll/clkout1\}\]\s*$',fdc))==1,'FDC SYS timing grid mismatch'
assert len(re.findall(r'\bGTP_GPLL\b',module))==1
for name,value in [('CLKIN_FREQ',str(reference_mhz)),('STATIC_RATIOI',str(input_divisor)),('STATIC_RATIOM',str(multiplier)),
                   ('STATIC_RATIOF',feedback),('STATIC_RATIO3',str(divisor)),('STATIC_DUTY3',str(divisor))]:
    found=re.findall(r'\.'+name+r'\s*\(\s*([\d.]+)\s*\)',module)
    assert len(found)==1 and float(found[0])==float(value),(name,found)
if fractional:
    for name,value in [('STATIC_RATIO0',str(divisor/2)),('STATIC_DUTY0',str(divisor//2)),('STATIC_CPHASE0','1')]:
        found=re.findall(r'\.'+name+r'\s*\(\s*([\d.]+)\s*\)',module)
        assert len(found)==1 and Decimal(found[0])==Decimal(value),(name,found)
for name,value in [('INTERNAL_FB','CLKOUTF'),('EXTERNAL_FB','DISABLE'),('SSC_MODE','DISABLE'),
                   ('CLK_DPS'+output+'_EN','FALSE'),('CLKOUT'+output+'_SYN_EN','FALSE')]:
    assert re.findall(r'\.'+name+r'\s*\(\s*"([^"]+)"\s*\)',module)==[value],name
for name,net in [('CLKIN1','clkin1'),('CLKOUT'+output,'clkout'+output),('LOCK','lock')]:
    assert len(re.findall(r'\.'+name+r'\s*\(\s*'+net+r'\s*\)',module))==1,name
instances=re.findall(r'(?s)\bpll_cpu\s+\\g_dedicated_cpu\.u_cpu_pll\s*\((.*?)\);',text)
assert len(instances)==1
for name,net in [('clkout'+output,'cpu_clk'),('lock','cpu_pll_lock'),('clkin1','ref_clk' if is80 else 'nt_free_clk')]:
    assert re.findall(r'\.'+name+r'\s*\(\s*([\w]+)\s*\)',instances[0])==[net],name
if is80:
    buffers=re.findall(r'(?s)\bGTP_INBUFDS\b\s*(?:/\*.*?\*/\s*)?(?:#\s*\(.*?\)\s*)?u_refclk\s*\((.*?)\);',text)
    assert len(buffers)==1,'Mapped differential reference buffer missing'
    for pin,net in [('O','ref_clk'),('I','ref_clk_p'),('IB','ref_clk_n')]:
        assert re.findall(r'\.'+pin+r'\s*\(\s*(\w+)\s*\)',buffers[0])==[net],pin
    assert re.search(r'(?m)^create_clock -name \{ref_clk\} \[get_ports \{ref_clk_p\}\] -period \{8\.0+\}',fdc),'125 MHz reference FDC missing'
resource=a.resources.read_text()
assert re.search(r'GTP_GPLL\s+4 uses\b',resource),'Expected four mapped GPLLs'
counts={}
for key,pattern in [('lut',r'Total LUTs:\s+(\d+)'),('ff',r'Total Registers:\s+(\d+)'),
                    ('latch',r'Total Latches:\s+(\d+)'),('drm',r'Total DRM =\s+([\d.]+)'),
                    ('apm',r'Total APMs =\s+([\d.]+)')]:
    counts[key]=float(re.search(pattern,resource).group(1))
from conv_resource_contract import conv_resource_contract
from vision32_resource_contract import vision32_resource_contract
from nnue_voice_resource_contract import nnue_voice_resource_contract
from dense_pe_resource_contract import dense_pe_resource_contract
from pikafish_dedicated_resource_contract import enabled as dedicated_enabled, pikafish_dedicated_resource_contract
top_text=a.soc_top.read_text() if a.soc_top else ''
dedicated=dedicated_enabled(top_text)
h128_enabled=1
conv_enabled=0
if a.soc_top:
    declared=re.findall(r'parameter\s+(?:integer\s+)?ENABLE_H128_SPARSE\s*=\s*([01])\b',a.soc_top.read_text())
    assert len(declared)==1,'Ambiguous H128 enable declaration'
    h128_enabled=int(declared[0])
    conv_declared=re.findall(r'parameter\s+(?:integer\s+)?ENABLE_CONV_CANDIDATE\s*=\s*([01])\b',a.soc_top.read_text())
    assert len(conv_declared)<=1,'Ambiguous convolution enable declaration'
    conv_enabled=int(conv_declared[0]) if conv_declared else 0
    assert len(re.findall(r'(?m)^module xiangqi_sparse_eval\b',text))==h128_enabled,'Legacy H128 mapped presence mismatch'
    for required in (['pikafish_mlp_dedicated','pff1_stagea_gather'] if dedicated else ['MacAccelCore','pff1_stagea_gather']):
        assert re.search(r'(?m)^module '+required+r'\b',text),'Required dense/gather module missing: '+required
vision_declared=re.findall(r'parameter\s+(?:integer\s+)?ENABLE_VISION32_CANDIDATE\s*=\s*([01])\b',top_text)
assert len(vision_declared)<=1,'Ambiguous vision enable'
vision_enabled=vision_declared==['1']
assert not vision_enabled or conv_enabled,'Vision requires enabled conv port'
conv_resources=vision32_resource_contract(text,resource) if vision_enabled else conv_resource_contract(text,resource,conv_enabled)
expected_drm=119.5+h128_enabled+conv_resources['drm']
# The baseline includes12 video DRM. The packed ping-pong implementation
# preserves both lines in four64-bit memories beside four burst memories.
# Recognize that reduction from the actual cells and subtree, never from a
# smaller whole-chip total alone. Older mappings and excerpt fixtures retain
# the original exact resource expectation.
video_resources=None
video_modules=re.findall(r'(?ms)^module video_fb_dma\b.*?^endmodule',text)
assert len(video_modules)<=1,'Ambiguous video DMA module'
if video_modules and re.search(r'\)\s+line_mem_[0-3]\s*\(',video_modules[0]):
    body=video_modules[0]
    cells=re.findall(r'(?s)\bGTP_DRM36K_E1\s*(?:/\*.*?\*/\s*)?#\s*\((.*?)\)\s*(\\?\S+)\s*\((.*?)\);',body)
    names={name for params,name,ports in cells}
    assert len(cells)==8 and names=={'line_mem_'+str(i) for i in range(4)}|{'burst_mem_'+str(i) for i in range(4)},'Packed video memory cells missing/duplicated'
    assert len(re.findall(r'\bGTP_DRM(?:36|18)K_E1\s',body))==8,'Unexpected packed video memory'
    for params,name,ports in cells:
        for key,value in [('DATA_WIDTH_A','64'),('DATA_WIDTH_B','64'),('RAM_MODE','"SIMPLE_DUAL_PORT"'),('DOA_REG','0'),('DOB_REG','0')]:
            assert re.findall(r'\.'+key+r'\s*\(\s*([^()]*)\s*\)',params)==[value],('Packed video RAM mode differs',name,key)
        if name.startswith('line_mem_'):
            for pin in ['CLKA','CLKB']:
                assert re.findall(r'\.'+pin+r'\s*\(\s*([^()]*)\s*\)',ports)==['pix_clk'],('Packed line RAM clock differs',name,pin)
            address=re.findall(r'\.ADDRA\s*\(\s*([^()]*)\s*\)',ports)
            assert len(address)==1 and re.sub(r'\s+','',address[0])=="{1'b1,1'b0,data_bank_ddr,"+','.join('data_word_ddr['+str(i)+']' for i in range(6,-1,-1))+","+','.join(["1'b1"]*6)+"}",'Packed line write bank/row differs'
    rows=[line.split('|') for line in resource.splitlines() if re.match(r'^\|\s*\+ u_fb_dma\s*\|',line)]
    assert len(rows)==1 and float(rows[0][6])==8,'Packed video subtree DRM differs'
    video_resources=dict(profile='packed_two_lines',drm=8,baseline_drm=12,line_cells=4,burst_cells=4)
    expected_drm-=4
dense_resources=dict(profile='pikafish_dedicated',apm=0) if dedicated else dense_pe_resource_contract(resource,top_text)
half_output=dense_resources['profile']==1
expected_apm=11+dense_resources['apm']+6*h128_enabled+conv_resources['apm']
linked_resources=pikafish_dedicated_resource_contract(text,resource,top_text) if dedicated else nnue_voice_resource_contract(text,resource,top_text)
if dedicated:
    assert h128_enabled==0,'Dedicated profile must omit legacy sparse engine'
    expected_drm-=6 # Generic dense input/output banks removed.
    expected_apm-=7 # Generic dense descriptor/accumulator APMs removed.
expected_drm+=linked_resources['drm']
expected_apm+=linked_resources['apm']

assert expected_drm<=140 and expected_apm<=195,'Integrated convolution exceeds resource budget' 
assert counts['latch']==0 and counts['drm']==expected_drm and counts['apm']==expected_apm,counts
record=dict(status='DEDICATED_CPU_PLL_ADS_PASS_NOT_STA_OR_BOARD',cpu_hz=cpu_hz,sys_hz=49500000,
    sta_cpu_period_ns=period,sta_sys_period_ns=sys_period,
    pll_vco_hz=vco_hz,cpu_reference_hz=reference_mhz*1000000,h128_enabled=h128_enabled,conv_enabled=conv_enabled,vision32_enabled=vision_enabled,conv_resources=conv_resources,mapped_gpll=4,resources=counts,
    video_resources=video_resources,linked_resources=linked_resources,linked_contract_sha256=hashlib.sha256(Path(__file__).with_name('nnue_voice_resource_contract.py').read_bytes()).hexdigest(),
    pikafish_dedicated=dedicated,pikafish_contract_sha256=hashlib.sha256(Path(__file__).with_name('pikafish_dedicated_resource_contract.py').read_bytes()).hexdigest(),
    half_output=half_output,dense_resources=dense_resources,dense_pe_apms=dense_resources['apm'],dense_contract_sha256=hashlib.sha256(Path(__file__).with_name('dense_pe_resource_contract.py').read_bytes()).hexdigest(),native_cpu_clock_name='cpu_clk',cpu_pll_output='CLKOUT'+output,cpu_output_divisor=divisor/2 if fractional else divisor,audit_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    inputs={str(path):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [a.netlist,a.clocks,a.resources,a.fdc,Path(__file__)]+([a.soc_top] if a.soc_top else [])})
a.output.write_text(json.dumps(record,indent=2)+'\n')
print(f'DEDICATED_CPU_PLL_ADS_PASS cpu={cpu_hz} sys=49500000 gpll=4 drm={expected_drm} apm={expected_apm} h128={h128_enabled} NOT_STA_OR_BOARD')
