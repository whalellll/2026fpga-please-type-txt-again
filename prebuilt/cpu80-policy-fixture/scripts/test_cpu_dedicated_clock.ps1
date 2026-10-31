param([string]$ReportPath='')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'clock_policy.ps1')
$checks=New-Object 'Collections.Generic.List[string]'
function New-Intent {
    return [pscustomobject][ordered]@{schema=1;input_hz=27000000;pll_vco_hz=891000000;
        cpu_clock_source='dedicated850p5';cpu_pll_vco_hz=850500000;cpu_divisor=12;
        cpu_hz=70875000;sys_hz=49500000;timebase_hz=49500000;integer_hz_rounding='nearest_half_up'}
}
$valid=New-Intent
Assert-SocClockIntent $valid
if((Get-SocCpuPllVcoHz $valid) -ne 850500000){throw 'Dedicated CPU VCO differs'}
if((Get-SocCpuClockMode $valid) -ne 1){throw 'Dedicated CPU profile differs'}
$checks.Add('dedicated_70875000_legal_and_exact')
foreach($case in @(
    @('cpu_hz',74250000),@('cpu_pll_vco_hz',891000000),@('cpu_clock_source','unknown'),
    @('cpu_divisor',13),@('pll_vco_hz',850500000),@('sys_hz',47250000),
    @('timebase_hz',70875000),@('input_hz',25000000)
)){
    $bad=New-Intent;$bad.($case[0])=$case[1];$rejected=$false
    try{Assert-SocClockIntent $bad}catch{$rejected=$true}
    if(!$rejected){throw "Changed intent accepted: $($case[0])"}
    $checks.Add('reject_'+$case[0])
}
foreach($divisor in 12..18){
    $old=[pscustomobject]@{schema=1;input_hz=27000000;pll_vco_hz=891000000;
        cpu_divisor=$divisor;cpu_hz=[int][Math]::Floor(891000000.0/$divisor+0.5);
        sys_hz=49500000;timebase_hz=49500000;integer_hz_rounding='nearest_half_up'}
    Assert-SocClockIntent $old
    if((Get-SocCpuPllVcoHz $old) -ne 891000000 -or (Get-SocCpuClockMode $old) -ne 0){throw 'Legacy profile changed'}
    $checks.Add('legacy_div'+$divisor)
}
$period=[decimal]1000000000*12/[decimal]850500000
$limit=Get-SocCdcLimitNs $period ([decimal]1000000000/49500000)
if($period.ToString('0.000000',[Globalization.CultureInfo]::InvariantCulture) -cne '14.109347' -or $limit -ne [decimal]13.309){throw 'Dedicated CPU timing derivation differs'}
$checks.Add('actual_period_and_conservative_cdc_limit')
$record=[ordered]@{status='HOST_CLOCK_POLICY_PASS';checks=$checks.ToArray();count=$checks.Count;board_tested=$false}
if($ReportPath){[IO.File]::WriteAllText($ReportPath,($record|ConvertTo-Json -Depth 5)+"`n",[Text.UTF8Encoding]::new($false))}
Write-Output "DEDICATED_CPU_CLOCK_POLICY_PASS checks=$($checks.Count) board_tested=false"
