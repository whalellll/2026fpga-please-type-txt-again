param([Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
$native='G:/i60pnr4'
. (Join-Path $native 'scripts/build_snapshot.ps1')
$xml=Join-Path $native 'pds/report_timing/rtr.db'
$rtr=Join-Path $native 'pds/report_timing/soc_top.rtr'
$fdc=Join-Path $native 'pds/soc.fdc'
$policy=Join-Path $native 'config/timing_scope_baseline.json'
$text=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'review_integrated60_functional_trial.ps1'))
$begin=$text.IndexOf('$source=[IO.File]::ReadAllText(')
$end=$text.IndexOf('$scope=& $check ')
if($begin -lt 0 -or $end -le $begin){throw 'Trial checker source layout changed'}
Invoke-Expression $text.Substring($begin,$end-$begin)
$checks=[Collections.Generic.List[string]]::new()
$temp=Join-Path ([IO.Path]::GetTempPath()) ('joint60-scope-'+[guid]::NewGuid().ToString('N')+'.xml')
try {
 try {$null=Assert-FpgaTimingScope $xml $fdc $policy;throw 'Strict checker accepted actual failed STA'} catch {
  if($_.Exception.Message -notlike '*has a violation*'){throw}
  $checks.Add('strict_original_still_rejects_failed_STA')
 }
 $actual=& $check $xml $fdc $policy
 if($actual.status -cne 'COVERAGE_ONLY_ACTUAL_HOLD_FAILURE_RETAINED'){throw 'Trial result must not claim timing passed'}
 $checks.Add('actual_known_hold_failure_only_trial_coverage')
 $skew=& $trialSkew $xml $rtr $fdc
 if($skew.groups -ne 10 -or $skew.rows -ne 20){throw 'Incomplete trial Max Skew check'}
 $checks.Add('actual_all_twenty_max_skew_rows_checked_despite_failed_summary')
 function Reject([string]$Name,[scriptblock]$Mutation){
  [xml]$doc=[IO.File]::ReadAllText($xml)
  & $Mutation $doc
  $doc.Save($temp)
  $failed=$false
  try {$null=& $check $temp $fdc $policy;$null=& $trialSkew $temp $rtr $fdc}catch{$failed=$true}
  if(!$failed){throw "Unsafe trial fixture accepted: $Name"}
  $checks.Add($Name)
 }
 Reject 'setup_failure_rejected' {param($d);$r=$d.SelectSingleNode('/tables/table[@id="report_timing_slow_setup"]/row[data[1]="cpu_clk" and data[2]="cpu_clk"]');$r.SelectSingleNode('data[3]').InnerText='-0.001';$r.SelectSingleNode('data[4]').InnerText='-0.001';$r.SelectSingleNode('data[5]').InnerText='1'}
 Reject 'excessive_hold_rejected' {param($d);$d.SelectSingleNode('/tables/table[@id="report_timing_slow_hold"]/row[data[1]="sys_clk"]/data[3]').InnerText='-0.100'}
 Reject 'wrong_clock_period_rejected' {param($d);$d.SelectSingleNode('/tables/table[@id="report_timing_clock_summary"]//row[data[1]="cpu_clk"]/data[3]').InnerText='17.000'}
 Reject 'new_internal_untimed_endpoint_rejected' {param($d);$d.SelectSingleNode('/tables/table[@id="check_timing_summary"]/row[data[1]="no_clock"]/data[2]').InnerText='1'}
 Reject 'missing_clock_pair_rejected' {param($d);$r=$d.SelectSingleNode('/tables/table[@id="report_timing_fast_hold"]/row[data[1]="sys_clk"]');$null=$r.ParentNode.RemoveChild($r)}
 Reject 'max_skew_violation_rejected' {param($d);$d.SelectSingleNode('/tables/table[@id="report_timing_fast_path_max_skew"]/row/data[2]').InnerText='-0.001'}
 $record=[ordered]@{status='FUNCTIONAL_SCOPE_ACTUAL_FAILURE_AND_SIX_FAULTS_CHECKED_NO_BOARD_ACCESS';checks=@($checks);timing_pass=$false;source_sha256=(Get-FileHash (Join-Path $PSScriptRoot 'review_integrated60_functional_trial.ps1') -Algorithm SHA256).Hash.ToLowerInvariant()}
 [IO.File]::WriteAllText([IO.Path]::GetFullPath($OutputPath),($record|ConvertTo-Json -Depth 4)+"`n",[Text.UTF8Encoding]::new($false))
 Write-Output $record.status
} finally {if(Test-Path -LiteralPath $temp){Remove-Item -LiteralPath $temp}}
