param([string]$NativeRoot='G:/i60pnr3',[Parameter(Mandatory=$true)][string]$OutputRoot)
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
$adapted=$verifier.ToString()
$normalize={param($s) (($s -split "`n" | ForEach-Object {($_ -replace '#.*$','').Trim()} | Where-Object {$_}) -join "`n")}
$expected=& $normalize $production
$actual=& $normalize ($adapted -replace '^param\([^\n]*\)\r?\n','' -replace 'Assert-FpgaTimingScopePixelGrid','Assert-FpgaTimingScope' -replace '(?m)^Assert-FpgaTimingScope \$XmlPath \$FdcPath \$PolicyPath\s*$','')
if($expected -cne $actual){throw 'Tested scope adapter differs from production checker'}
$checks.Add('production_scope_tokens_equal_tested_adapter')
$accepted=& $verifier $xml $fdc $policy
$checks.Add('actual_positive_native_scope_pass_with_disclosed_gaps')
function Reject-Grid([string]$Name,[scriptblock]$Mutation,[string]$Expected){
 [xml]$doc=[IO.File]::ReadAllText($xml);& $Mutation $doc
 $path=Join-Path $OutputRoot ($Name+'.xml');$doc.Save($path)
 try{$null=& $verifier $path $fdc $policy;throw "Unsafe fixture accepted $Name"}catch{
  if($_.Exception.Message -notlike $Expected){throw}
  $checks.Add($Name)
 }
}
Reject-Grid 'wrong_pixel_period_rejected' {param($d) $d.SelectSingleNode('/tables/table[@id="report_timing_clock_summary"]/row[data[1]="pix_clk"]/data[3]').InnerText='13.4690'} '*clock definition differs: pix_clk*'
Reject-Grid 'wrong_cpu_period_rejected' {param($d) $d.SelectSingleNode('/tables/table[@id="report_timing_clock_summary"]/row[data[1]="cpu_clk"]/data[3]').InnerText='16.6510'} '*clock definition differs: cpu_clk*'
Reject-Grid 'new_internal_gap_rejected' {param($d) $d.SelectSingleNode('/tables/table[@id="check_timing_summary"]/row[data[1]="no_clock"]/data[2]').InnerText='1'} '*check_timing gap changed: no_clock*'
Reject-Grid 'negative_fast_hold_rejected' {param($d) $d.SelectSingleNode('/tables/table[@id="report_timing_fast_hold"]/row[1]/data[3]').InnerText='-0.001'} '*fast/hold has a violation*'
Reject-Grid 'negative_slow_setup_rejected' {param($d) $d.SelectSingleNode('/tables/table[@id="report_timing_slow_setup"]/row[1]/data[3]').InnerText='-0.001'} '*slow/setup has a violation*'
Reject-Grid 'missing_clock_rejected' {param($d) $n=$d.SelectSingleNode('/tables/table[@id="report_timing_clock_summary"]/row[data[1]="pix_clk"]');$null=$n.ParentNode.RemoveChild($n)} '*eighteen reviewed clocks*'
Reject-Grid 'missing_setup_pair_rejected' {param($d) $n=$d.SelectSingleNode('/tables/table[@id="report_timing_slow_setup"]/row[1]');$null=$n.ParentNode.RemoveChild($n)} '*slow/setup clock-pair coverage changed*'
foreach($variant in @(@('looser','13.470'),@('over_tightened','13.467'),@('duplicate','13.468'))){
 $badFdc=Join-Path $OutputRoot ($variant[0]+'.fdc')
 $s=[IO.File]::ReadAllText($fdc)
 if($variant[0] -eq 'duplicate'){$s+="`ncreate_clock -name {pix_clk} -period {13.468} [get_pins {u_video_pll/u_gpll/gpll_inst/CLKOUT0}]`n"}
 else{$s=$s.Replace('create_clock -name {pix_clk} -period {13.468}',('create_clock -name {pix_clk} -period {'+$variant[1]+'}'))}
 [IO.File]::WriteAllText($badFdc,$s,[Text.UTF8Encoding]::new($false))
 try{$null=& $verifier $xml $badFdc $policy;throw 'Unsafe pixel FDC accepted'}catch{
  $message=if($variant[0] -eq 'duplicate'){'*Pixel STA clock missing or duplicated*'}else{'*outside conservative representation grid*'}
  if($_.Exception.Message -notlike $message){throw}
  $checks.Add($variant[0]+'_pixel_fdc_rejected')
 }
}
foreach($p in $before.Keys){if((Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant() -cne $before[$p]){throw 'Native report/input was modified'}}
$record=@{status='INTEGRATED60_PIXEL_SCOPE_MUTATIONS_PASS_NOT_BOARD';checks=$checks.ToArray();original_inputs_sha256=$before;production_sha256=(Get-FileHash (Join-Path $PSScriptRoot 'timing_scope.ps1') -Algorithm SHA256).Hash.ToLowerInvariant();actual_scope=$accepted;note='Native reports unchanged. Mutation files are synthetic and are never hardware evidence.'}
[IO.File]::WriteAllText((Join-Path $OutputRoot 'result.json'),($record|ConvertTo-Json -Depth 6)+"`n",[Text.UTF8Encoding]::new($false))
Write-Output "INTEGRATED60_PIXEL_SCOPE_MUTATIONS_PASS checks=$($checks.Count)"
