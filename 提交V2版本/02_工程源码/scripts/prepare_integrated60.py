"""Prepare the existing 1080MHz CPU PLL for an exact 60MHz output.

Encoded divisor36 means physical CLKOUT0 divider18; preserve all old profiles.
"""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def edit(name,old,new,count=1):
 p=ROOT/name;s=p.read_bytes().decode('utf-8');assert s.count(old)==count,(name,old,s.count(old));p.write_bytes(s.replace(old,new).encode())
for f in ['scripts/set_clock_candidate.ps1','scripts/stage_cpu_timing_candidate.ps1']:
 p=ROOT/f;s=p.read_bytes().decode();s=s.replace('27,18,17,16,15,14,13,12,10,9','36,27,18,17,16,15,14,13,12,10,9').replace('9,10,12,13,14,15,16,17,18,27','9,10,12,13,14,15,16,17,18,27,36');p.write_bytes(s.encode())
edit('scripts/set_clock_candidate.ps1',"if($targetMode -in @(4,5) -and $Divisor -ne 27){throw 'Fractional CPU80 profile requires encoded divisor27 (CLKOUT0=13.5)'}", "if(($targetMode -eq 5 -and $Divisor -ne 27) -or ($targetMode -eq 4 -and $Divisor -notin @(27,36))){throw 'CPU PLL mode4 permits encoded27/36 (80/60MHz); mode5 requires27'}")
edit('scripts/set_clock_candidate.ps1','$(if($targetMode -in @(4,5)){108}else{$Divisor*8})','$(if($targetMode -in @(4,5)){$Divisor*4}else{$Divisor*8})')
edit('scripts/clock_policy.ps1',"if ((Get-SocCpuClockMode $Clock) -in @(3,4)) { return [decimal]12.495 }", "if ((Get-SocCpuClockMode $Clock) -eq 4 -and $Clock.cpu_divisor -eq 36) { return [decimal]16.650 }\n    if ((Get-SocCpuClockMode $Clock) -in @(3,4)) { return [decimal]12.495 }")
edit('scripts/clock_policy.ps1',"($Clock.cpu_pll_vco_hz -ne 1080000000 -or $Clock.cpu_divisor -ne 27 -or $Clock.cpu_reference_hz -ne 27000000 -or $Clock.cpu_output_divisor_eighths -ne 108)","($Clock.cpu_pll_vco_hz -ne 1080000000 -or $Clock.cpu_divisor -notin @(27,36) -or $Clock.cpu_reference_hz -ne 27000000 -or $Clock.cpu_output_divisor_eighths -ne $Clock.cpu_divisor*4)")
edit('scripts/clock_policy.ps1','@(27,18,17,16,15,14,13,12,10,9)','@(36,27,18,17,16,15,14,13,12,10,9)')
edit('scripts/clock_policy.ps1',"($mode -notin @(4,5) -and $Clock.cpu_divisor -eq 27)","($mode -notin @(4,5) -and $Clock.cpu_divisor -eq 27) -or ($Clock.cpu_divisor -eq 36 -and $mode -ne 4)")
edit('scripts/audit_cpu_dedicated_pll_ads.py',"is80=clock['cpu_clock_source']=='dedicated800'", "is60=clock['cpu_clock_source']=='dedicated1080frac' and clock['cpu_divisor']==36\nif is60: cpu_hz,divisor=60000000,36\nis80=clock['cpu_clock_source']=='dedicated800'")
edit('scripts/audit_cpu_dedicated_pll_ads.py',"clock['cpu_output_divisor_eighths']==108", "clock['cpu_output_divisor_eighths']==divisor*4")
edit('scripts/audit_cpu_dedicated_pll_ads.py',"constraint_period=Decimal('11.760000')", "constraint_period=Decimal('16.650000') if is60 else Decimal('11.760000')")
edit('scripts/audit_cpu_dedicated_pll_ads.py',"[('STATIC_RATIO0','13.5'),('STATIC_DUTY0','13'),('STATIC_CPHASE0','1')]", "[('STATIC_RATIO0',str(divisor/2)),('STATIC_DUTY0',str(divisor//2)),('STATIC_CPHASE0','1')]")
edit('scripts/audit_cpu_dedicated_pll_ads.py','cpu_output_divisor=13.5 if fractional else divisor','cpu_output_divisor=divisor/2 if fractional else divisor')
print('CPU60_CLOCK_TOOLS_PREPARED')
