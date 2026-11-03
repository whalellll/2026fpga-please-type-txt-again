param([string]$ReportPath='')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'clock_policy.ps1')
$good=[pscustomobject]@{schema=1;input_hz=27000000;pll_vco_hz=891000000;cpu_clock_source='dedicated950frac';cpu_pll_vco_hz=950000000;cpu_divisor=20;cpu_output_divisor_eighths=80;cpu_reference_hz=125000000;cpu_hz=95000000;sys_hz=49500000;timebase_hz=49500000;integer_hz_rounding='nearest_half_up'}
Assert-SocClockIntent $good
if((Get-SocCpuClockMode $good) -ne 7 -or (Get-SocCpuConstraintPeriodNs $good) -ne [decimal]10.521){throw 'Wrong exact95 profile'}
if((Get-SocSysConstraintPeriodNs $good) -ne [decimal]20.202 -or (Get-SocCdcLimitNs 10.521 20.202) -ne [decimal]9.721){throw 'Wrong strict95 CDC grid'}
if([decimal]125000000/[decimal]5*[decimal]38/[decimal]10 -ne 95000000){throw 'Exact95 PLL arithmetic failed'}
if([decimal]10.521*962 -ne [decimal]20.202*501 -or [decimal]10.521 -gt [decimal]1000000000/95000000){throw 'Strict clock expansion proof failed'}
$checks=5
foreach($case in @(@('cpu_reference_hz',27000000),@('cpu_hz',85050000),@('cpu_pll_vco_hz',1147500000),@('cpu_divisor',10),@('cpu_output_divisor_eighths',107),@('sys_hz',95000000))){
 $bad=$good.PSObject.Copy();$bad.($case[0])=$case[1];$rejected=$false
 try{Assert-SocClockIntent $bad}catch{$rejected=$true}
 if(!$rejected){throw "Unsafe exact95 profile accepted: $($case[0])"};$checks++
}
if($ReportPath){[IO.File]::WriteAllText($ReportPath,(@{status='PASS';scope='Exact95 intent and mutation tests only, not STA/board';checks=$checks}|ConvertTo-Json)+"`n",[Text.UTF8Encoding]::new($false))}
Write-Output "CPU95_FRAC_CLOCK_POLICY_PASS checks=$checks"
