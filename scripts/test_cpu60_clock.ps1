param([string]$ReportPath='')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'clock_policy.ps1')
$good=[pscustomobject]@{schema=1;input_hz=27000000;pll_vco_hz=891000000;cpu_clock_source='dedicated1080frac';cpu_pll_vco_hz=1080000000;cpu_divisor=36;cpu_output_divisor_eighths=144;cpu_reference_hz=27000000;cpu_hz=60000000;sys_hz=49500000;timebase_hz=49500000;integer_hz_rounding='nearest_half_up'}
Assert-SocClockIntent $good
if((Get-SocCpuClockMode $good) -ne 4 -or (Get-SocCpuConstraintPeriodNs $good) -ne [decimal]16.650){throw 'Wrong CPU60 profile'}
if((Get-SocSysConstraintPeriodNs $good) -ne [decimal]20.202 -or (Get-SocCdcLimitNs 16.650 20.202) -ne [decimal]15.850){throw 'Wrong CPU60 strict STA/CDC grid'}
if([decimal]27000000*40/18 -ne 60000000 -or [decimal]16.650*91 -ne [decimal]20.202*75){throw 'Exact60 PLL/common clock expansion proof failed'}
$checks=4
foreach($case in @(@('cpu_reference_hz',125000000),@('cpu_hz',59400000),@('cpu_pll_vco_hz',800000000),@('cpu_divisor',27),@('cpu_output_divisor_eighths',108),@('sys_hz',60000000))){
 $bad=$good.PSObject.Copy();$bad.($case[0])=$case[1];$rejected=$false
 try{Assert-SocClockIntent $bad}catch{$rejected=$true}
 if(!$rejected){throw "Unsafe CPU60 profile accepted: $($case[0])"};$checks++
}
if($ReportPath){[IO.File]::WriteAllText($ReportPath,(@{status='CPU60_CLOCK_POLICY_PASS_NOT_NATIVE';checks=$checks}|ConvertTo-Json)+"`n",[Text.UTF8Encoding]::new($false))}
Write-Output "CPU60_CLOCK_POLICY_PASS checks=$checks"
