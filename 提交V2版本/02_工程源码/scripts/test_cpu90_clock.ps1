param([string]$ReportPath='')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'clock_policy.ps1')
$good=[pscustomobject]@{schema=1;input_hz=27000000;pll_vco_hz=891000000;cpu_clock_source='dedicated1080frac';cpu_pll_vco_hz=1080000000;cpu_divisor=24;cpu_output_divisor_eighths=96;cpu_reference_hz=27000000;cpu_hz=90000000;sys_hz=49500000;timebase_hz=49500000;integer_hz_rounding='nearest_half_up'}
Assert-SocClockIntent $good
if((Get-SocCpuClockMode $good) -ne 4 -or (Get-SocCpuConstraintPeriodNs $good) -ne [decimal]11.100){throw 'Wrong exact90 profile'}
if((Get-SocSysConstraintPeriodNs $good) -ne [decimal]20.202 -or (Get-SocCdcLimitNs 11.100 20.202) -ne [decimal]10.300){throw 'Wrong strict90 CDC grid'}
if([decimal]27000000*[decimal]40/[decimal]12 -ne 90000000){throw 'Exact90 PLL arithmetic failed'}
if([decimal]11.100*91 -ne [decimal]20.202*50 -or [decimal]11.100 -gt [decimal]1000000000/90000000){throw 'Strict clock expansion proof failed'}
$checks=5
foreach($case in @(@('cpu_reference_hz',125000000),@('cpu_hz',85050000),@('cpu_pll_vco_hz',1147500000),@('cpu_divisor',10),@('cpu_output_divisor_eighths',107),@('sys_hz',90000000))){
 $bad=$good.PSObject.Copy();$bad.($case[0])=$case[1];$rejected=$false
 try{Assert-SocClockIntent $bad}catch{$rejected=$true}
 if(!$rejected){throw "Unsafe exact90 profile accepted: $($case[0])"};$checks++
}
if($ReportPath){[IO.File]::WriteAllText($ReportPath,(@{status='PASS';scope='Exact90 intent and mutation tests only, not STA/board';checks=$checks}|ConvertTo-Json)+"`n",[Text.UTF8Encoding]::new($false))}
Write-Output "CPU90_FRAC_CLOCK_POLICY_PASS checks=$checks"
