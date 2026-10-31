param([string]$ReportPath='')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'clock_policy.ps1')
$good=[pscustomobject]@{schema=1;input_hz=27000000;pll_vco_hz=891000000;cpu_clock_source='dedicated1147p5frac';cpu_pll_vco_hz=1147500000;cpu_divisor=27;cpu_output_divisor_eighths=108;cpu_reference_hz=27000000;cpu_hz=85000000;sys_hz=49500000;timebase_hz=49500000;integer_hz_rounding='nearest_half_up'}
Assert-SocClockIntent $good
if((Get-SocCpuClockMode $good) -ne 5 -or (Get-SocCpuConstraintPeriodNs $good) -ne [decimal]11.760){throw 'Wrong exact85 profile'}
if((Get-SocSysConstraintPeriodNs $good) -ne [decimal]20.202 -or (Get-SocCdcLimitNs 11.760 20.202) -ne [decimal]10.960){throw 'Wrong strict85 CDC grid'}
if([decimal]27000000*[decimal]42.5/[decimal]13.5 -ne 85000000){throw 'Exact85 PLL arithmetic failed'}
if([decimal]11.760*481 -ne [decimal]20.202*280 -or [decimal]11.760 -gt [decimal]1000000000/85000000){throw 'Strict clock expansion proof failed'}
$checks=5
foreach($case in @(@('cpu_reference_hz',125000000),@('cpu_hz',85050000),@('cpu_pll_vco_hz',1080000000),@('cpu_divisor',10),@('cpu_output_divisor_eighths',107),@('sys_hz',85000000))){
 $bad=$good.PSObject.Copy();$bad.($case[0])=$case[1];$rejected=$false
 try{Assert-SocClockIntent $bad}catch{$rejected=$true}
 if(!$rejected){throw "Unsafe exact85 profile accepted: $($case[0])"};$checks++
}
if($ReportPath){[IO.File]::WriteAllText($ReportPath,(@{status='PASS';scope='Exact85 intent and mutation tests only, not STA/board';checks=$checks}|ConvertTo-Json)+"`n",[Text.UTF8Encoding]::new($false))}
Write-Output "CPU85_FRAC_CLOCK_POLICY_PASS checks=$checks"
