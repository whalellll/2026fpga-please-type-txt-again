param([string]$NativeRoot='G:/pfpnr4',[Parameter(Mandatory=$true)][string]$OutputRoot)
$ErrorActionPreference='Stop'
if(Test-Path -LiteralPath $OutputRoot){throw 'Use a new fixture directory'}
$null=New-Item -ItemType Directory -Path $OutputRoot
. (Join-Path $NativeRoot 'scripts/build_snapshot.ps1')
. (Join-Path $PSScriptRoot 'timing_scope_pixel_grid.ps1')
$xml=Join-Path $NativeRoot 'pds/report_timing/rtr.db'
$fdc=Join-Path $NativeRoot 'pds/soc.fdc'
$policy=Join-Path $NativeRoot 'config/timing_scope_baseline.json'
$sourcePath=Join-Path $NativeRoot 'scripts/timing_scope.ps1'
$before=@{};foreach($p in @($xml,$fdc,$policy,$sourcePath)){$before[$p]=(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}
$checks=[Collections.Generic.List[string]]::new()
try{$null=Assert-FpgaTimingScope $xml $fdc $policy;throw 'Old precision failure did not reproduce'}catch{
 if($_.Exception.Message -cne 'Native STA clock definition differs: pix_clk'){throw}
 $checks.Add('original_actual_report_pixel_precision_failure_reproduced')
}
$verifier=New-FpgaPixelGridScopeVerifier ([IO.File]::ReadAllText($sourcePath))
$production=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'timing_scope.ps1'))
# Require the tested recovery adapter to have exactly the production tokens.
$anchor=[IO.File]::ReadAllText($sourcePath)
$adapted=$verifier.ToString()
$normalize={param($s) (($s -split "`n" | ForEach-Object {($_ -replace '#.*$','').Trim()} | Where-Object {$_}) -join "`n")}
$expected=& $normalize $production
$actual=& $normalize ($adapted -replace '^param\([^\n]*\)\r?\n','' -replace 'Assert-FpgaTimingScopePixelGrid','Assert-FpgaTimingScope' -replace '(?m)^Assert-FpgaTimingScope \$XmlPath \$FdcPath \$PolicyPath\s*$','')
if($expected -cne $actual){throw 'Tested scope adapter differs from production checker'}
$checks.Add('production_scope_tokens_equal_tested_adapter')
try{$null=& $verifier $xml $fdc $policy;throw 'Actual negative STA was accepted'}catch{
 if($_.Exception.Message -notlike '*slow/setup has a violation*'){throw}
 $checks.Add('actual_negative_setup_still_rejected_after_pixel_fix')
}
# Synthetic positive fixture ONLY: never rewrite the negative native report.
[xml]$positive=[IO.File]::ReadAllText($xml)
foreach($table in $positive.SelectNodes('/tables/table')){
 if($table.id -match '^report_timing_(slow|fast)_(setup|hold|recovery|removal|mpw)$'){
  $offset=if($table.id -like '*_mpw'){1}else{2}
  foreach($row in $table.SelectNodes('./row')){
   if([decimal]$row.data[$offset] -lt 0 -or [decimal]$row.data[$offset+1] -ne 0 -or [int]$row.data[$offset+2] -ne 0){
    $row.SelectNodes('./data')[$offset].InnerText='0.000';$row.SelectNodes('./data')[$offset+1].InnerText='0.000';$row.SelectNodes('./data')[$offset+2].InnerText='0'
   }
  }
 }
}
$fixture=Join-Path $OutputRoot 'SYNTHETIC-positive-scope-only.xml';$positive.Save($fixture)
$accepted=& $verifier $fixture $fdc $policy
$checks.Add('synthetic_positive_scope_pass_with_disclosed_gaps')
function Reject-Grid([string]$Name,[scriptblock]$Mutation,[string]$Expected){
 [xml]$doc=[IO.File]::ReadAllText($fixture);& $Mutation $doc
 $path=Join-Path $OutputRoot ($Name+'.xml');$doc.Save($path)
 try{$null=& $verifier $path $fdc $policy;throw "Unsafe fixture accepted $Name"}catch{
  if($_.Exception.Message -notlike $Expected){throw}
  $checks.Add($Name)
 }
}
Reject-Grid 'wrong_pixel_period_rejected' {param($d) $d.SelectSingleNode('/tables/table[@id="report_timing_clock_summary"]/row[data[1]="pix_clk"]/data[3]').InnerText='13.4690'} '*clock definition differs: pix_clk*'
Reject-Grid 'wrong_cpu_period_rejected' {param($d) $d.SelectSingleNode('/tables/table[@id="report_timing_clock_summary"]/row[data[1]="cpu_clk"]/data[3]').InnerText='16.6500'} '*clock definition differs: cpu_clk*'
Reject-Grid 'new_internal_gap_rejected' {param($d) $d.SelectSingleNode('/tables/table[@id="check_timing_summary"]/row[data[1]="no_clock"]/data[2]').InnerText='1'} '*check_timing gap changed: no_clock*'
Reject-Grid 'negative_fast_hold_rejected' {param($d) $d.SelectSingleNode('/tables/table[@id="report_timing_fast_hold"]/row[1]/data[3]').InnerText='-0.001'} '*fast/hold has a violation*'
$badFdc=Join-Path $OutputRoot 'SYNTHETIC-looser-pixel.fdc'
[IO.File]::WriteAllText($badFdc,[IO.File]::ReadAllText($fdc).Replace('create_clock -name {pix_clk} -period {13.468}','create_clock -name {pix_clk} -period {13.470}'))
try{$null=& $verifier $fixture $badFdc $policy;throw 'Looser pixel accepted'}catch{
 if($_.Exception.Message -notlike '*outside conservative representation grid*'){throw}
 $checks.Add('looser_pixel_constraint_rejected')
}
foreach($p in $before.Keys){if((Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant() -cne $before[$p]){throw 'Native report/input was modified'}}
$record=@{status='PIXEL_SCOPE_ADAPTER_MUTATIONS_PASS_NOT_HARDWARE';checks=$checks.ToArray();original_inputs_sha256=$before;production_sha256=(Get-FileHash (Join-Path $PSScriptRoot 'timing_scope.ps1') -Algorithm SHA256).Hash.ToLowerInvariant();synthetic_scope=$accepted;note='Actual negative report stays negative. Positive fixture edits are synthetic checker tests, not hardware acceptance.'}
[IO.File]::WriteAllText((Join-Path $OutputRoot 'result.json'),($record|ConvertTo-Json -Depth 6)+"`n",[Text.UTF8Encoding]::new($false))
Write-Output "PIXEL_SCOPE_ADAPTER_MUTATIONS_PASS checks=$($checks.Count) NOT_HARDWARE"
