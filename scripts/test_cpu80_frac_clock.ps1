param([string]$ReportPath='')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'clock_policy.ps1')
$good=[pscustomobject]@{schema=1;input_hz=27000000;pll_vco_hz=891000000;cpu_clock_source='dedicated1080frac';cpu_pll_vco_hz=1080000000;cpu_divisor=27;cpu_output_divisor_eighths=108;cpu_reference_hz=27000000;cpu_hz=80000000;sys_hz=49500000;timebase_hz=49500000;integer_hz_rounding='nearest_half_up'}
Assert-SocClockIntent $good
if((Get-SocCpuClockMode $good) -ne 4 -or (Get-SocCpuConstraintPeriodNs $good) -ne [decimal]12.495){throw 'Wrong fractional80 profile'}
if((Get-SocSysConstraintPeriodNs $good) -ne [decimal]20.202 -or (Get-SocCdcLimitNs 12.495 20.202) -ne [decimal]11.695){throw 'Wrong fractional80 strict STA/CDC grid'}
if([decimal]27000000*40/[decimal]13.5 -ne 80000000 -or 108%2 -ne 0){throw 'Exact80MHz/even fractional duty proof failed'}
$checks=4
foreach($case in @(@('cpu_reference_hz',125000000),@('cpu_hz',40000000),@('cpu_pll_vco_hz',800000000),@('cpu_divisor',10),@('cpu_output_divisor_eighths',107),@('sys_hz',80000000))){
 $bad=$good.PSObject.Copy();$bad.($case[0])=$case[1];$rejected=$false
 try{Assert-SocClockIntent $bad}catch{$rejected=$true}
 if(!$rejected){throw "Unsafe fractional80 profile accepted: $($case[0])"};$checks++
}
if($ReportPath){[IO.File]::WriteAllText($ReportPath,(@{status='PASS';scope='Intent/mutation only, not native STA or board';checks=$checks}|ConvertTo-Json)+"`n",[Text.UTF8Encoding]::new($false))}
Write-Output "CPU80_FRAC_CLOCK_POLICY_PASS checks=$checks"
