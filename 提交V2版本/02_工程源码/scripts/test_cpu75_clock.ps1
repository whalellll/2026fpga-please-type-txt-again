param([string]$ReportPath='')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'clock_policy.ps1')
$checks=New-Object 'Collections.Generic.List[string]'
$good=[pscustomobject]@{schema=1;input_hz=27000000;pll_vco_hz=891000000;
 cpu_clock_source='dedicated675';cpu_pll_vco_hz=675000000;cpu_divisor=9;
 cpu_hz=75000000;sys_hz=49500000;timebase_hz=49500000;integer_hz_rounding='nearest_half_up'}
Assert-SocClockIntent $good
if((Get-SocCpuClockMode $good) -ne 2 -or (Get-SocCpuPllVcoHz $good) -ne 675000000){throw 'Incorrect CPU75 profile'}
$checks.Add('exact_75mhz_legal_profile')
foreach($case in @(@('cpu_divisor',12),@('cpu_hz',74250000),@('cpu_pll_vco_hz',900000000),
 @('input_hz',25000000),@('sys_hz',75000000),@('timebase_hz',75000000),@('cpu_clock_source','unreviewed'))){
 $bad=$good.PSObject.Copy();$bad.($case[0])=$case[1];$rejected=$false
 try{Assert-SocClockIntent $bad}catch{$rejected=$true}
 if(!$rejected){throw "Invalid CPU75 intent accepted: $($case[0])"}
 $checks.Add('reject_'+$case[0])
}
$period=[decimal]1000000000/75000000
if((Get-SocCdcLimitNs $period ([decimal]1000000000/49500000)) -ne [decimal]12.533){throw 'Incorrect CPU75 CDC bound'}
if($period.ToString('0.000000',[Globalization.CultureInfo]::InvariantCulture) -cne '13.333333'){throw 'Incorrect CPU75 period'}
$checks.Add('rational_period_and_12p533ns_cdc')
$timingPeriod=Get-SocCpuConstraintPeriodNs $good
if($timingPeriod -ne [decimal]13.320 -or $timingPeriod -gt $period){throw 'CPU75 STA period must be the tighter 13.320 ns contract'}
if((Get-SocCdcLimitNs $timingPeriod ([decimal]1000000000/49500000)) -ne [decimal]12.520){throw 'CPU75 conservative STA requires 12.520 ns CDC bound'}
$checks.Add('separate_physical_75mhz_from_tighter_sta_period')
function Get-ExpandCycles([int]$CpuPs,[int]$SysPs){
 $gcdA=$CpuPs;$gcdB=$SysPs
 while($gcdB){$remainder=$gcdA%$gcdB;$gcdA=$gcdB;$gcdB=$remainder}
 return @(($SysPs/$gcdA),($CpuPs/$gcdA))
}
$oldExpansion=Get-ExpandCycles 13333 20202
if(($oldExpansion|Measure-Object -Maximum).Maximum -le 1000){throw 'Old PDS-rounded period should reproduce expansion beyond 1000 cycles'}
$newExpansion=Get-ExpandCycles ([int]($timingPeriod*1000)) 20202
if($newExpansion[0] -ne 91 -or $newExpansion[1] -ne 60){throw 'Tighter CPU75 timing periods must expand in 91 CPU/60 SYS cycles'}
$checks.Add('pds_1ps_grid_common_multiple_within_1000_cycles')
$sysTimingPeriod=Get-SocSysConstraintPeriodNs $good
if($sysTimingPeriod -ne [decimal]20.202000 -or $sysTimingPeriod -gt ([decimal]1000000000/49500000)){throw 'SYS STA target must be the tighter explicit 1ps grid'}
$mixedPrecision=Get-ExpandCycles 13320000 20202020
if(($mixedPrecision|Measure-Object -Maximum).Maximum -le 1000){throw 'Mixed full-precision literals must remain a negative expansion case'}
$fullPrecision=Get-ExpandCycles ([int]($timingPeriod*1000000)) ([int]($sysTimingPeriod*1000000))
if($fullPrecision[0] -ne 91 -or $fullPrecision[1] -ne 60){throw 'Full FDC literals must also expand in 91 CPU/60 SYS cycles'}
$checks.Add('full_precision_cpu_and_sys_literals_expand_without_display_rounding')
$record=[ordered]@{status='CPU75_CLOCK_HOST_PASS_NOT_STA_OR_BOARD';checks=$checks.ToArray();count=$checks.Count}
if($ReportPath){[IO.File]::WriteAllText($ReportPath,($record|ConvertTo-Json -Depth 5)+"`n",[Text.UTF8Encoding]::new($false))}
Write-Output "CPU75_CLOCK_POLICY_PASS checks=$($checks.Count)"
