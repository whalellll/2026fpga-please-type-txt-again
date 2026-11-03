param([string]$ReportPath='')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'clock_policy.ps1')
$good=[pscustomobject]@{schema=1;input_hz=27000000;pll_vco_hz=891000000;
 cpu_clock_source='dedicated800';cpu_pll_vco_hz=800000000;cpu_divisor=10;
 cpu_reference_hz=125000000;cpu_hz=80000000;sys_hz=49500000;timebase_hz=49500000;integer_hz_rounding='nearest_half_up'}
Assert-SocClockIntent $good
if((Get-SocCpuClockMode $good) -ne 3 -or (Get-SocCpuPllVcoHz $good) -ne 800000000){throw 'Incorrect CPU80 profile'}
if((Get-SocCpuConstraintPeriodNs $good) -ne [decimal]12.495){throw 'CPU80 STA must tighten the physical12.5ns period'}
if((Get-SocSysConstraintPeriodNs $good) -ne [decimal]20.202){throw 'CPU80 SYS STA must use the exact1ps grid'}
if((Get-SocCdcLimitNs ([decimal]12.495) ([decimal]20.202)) -ne [decimal]11.695){throw 'Incorrect CPU80 CDC bound'}
$checks=5
foreach($case in @(@('cpu_reference_hz',27000000),@('cpu_hz',81000000),@('cpu_pll_vco_hz',810000000),@('cpu_divisor',9),@('sys_hz',80000000),@('input_hz',125000000),@('cpu_clock_source','unreviewed'))){
 $bad=$good.PSObject.Copy();$bad.($case[0])=$case[1];$rejected=$false
 try{Assert-SocClockIntent $bad}catch{$rejected=$true}
 if(!$rejected){throw "Bad CPU80 intent accepted: $($case[0])"};$checks++
}
$a=12495;$b=20202;while($b){$rem=$a%$b;$a=$b;$b=$rem}
if($a -ne 21 -or 20202/$a -ne 962 -or 12495/$a -ne 595){throw 'CPU80 full-period common multiple exceeds reviewed962/595 cycles'}
$checks++
$record=[ordered]@{status='CPU80_HOST_CLOCK_POLICY_PASS_NOT_STA_OR_BOARD';checks=$checks;cpu_hz=80000000;reference_hz=125000000;pfd_hz=25000000;vco_hz=800000000;idiv=5;mdiv=1;fdiv=32;odiv=10;sta_cpu_ns=12.495;sta_sys_ns=20.202;cdc_ns=11.695}
if($ReportPath){[IO.File]::WriteAllText($ReportPath,($record|ConvertTo-Json -Depth 5)+"`n",[Text.UTF8Encoding]::new($false))}
Write-Output "CPU80_CLOCK_POLICY_PASS checks=$checks"
