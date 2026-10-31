param([string]$ReportPath='')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'clock_policy.ps1')
$good=[pscustomobject]@{schema=1;input_hz=27000000;pll_vco_hz=891000000;cpu_clock_source='dedicated945frac';cpu_pll_vco_hz=945000000;cpu_divisor=27;cpu_output_divisor_eighths=108;cpu_reference_hz=27000000;cpu_hz=70000000;sys_hz=49500000;timebase_hz=49500000;integer_hz_rounding='nearest_half_up'}
Assert-SocClockIntent $good
if((Get-SocCpuClockMode $good) -ne 6 -or (Get-SocCpuConstraintPeriodNs $good) -ne [decimal]14.282){throw 'Wrong CPU70 profile'}
if([decimal]27000000*35/[decimal]13.5 -ne 70000000){throw 'PLL does not produce exact70MHz'}
if([decimal]14.282*273 -ne [decimal]20.202*193){throw 'STA common-clock expansion differs'}
if((Get-SocCdcLimitNs 14.282 20.202) -ne [decimal]13.482){throw 'CDC timing budget changed'}
$checks=4
foreach($case in @(@('cpu_hz',70875000),@('cpu_hz',60000000),@('cpu_pll_vco_hz',1080000000),@('cpu_divisor',36),@('cpu_reference_hz',125000000),@('cpu_output_divisor_eighths',144),@('sys_hz',60000000))){
 $bad=$good.PSObject.Copy();$bad.($case[0])=$case[1];$rejected=$false
 try{Assert-SocClockIntent $bad}catch{$rejected=$true}
 if(!$rejected){throw "Unsafe CPU70 mutation accepted: $($case[0])"};$checks++
}
if($ReportPath){[IO.File]::WriteAllText($ReportPath,(@{status='CPU70_CLOCK_POLICY_PASS_NOT_NATIVE';checks=$checks}|ConvertTo-Json)+"`n",[Text.UTF8Encoding]::new($false))}
Write-Output "CPU70_CLOCK_POLICY_PASS checks=$checks"
