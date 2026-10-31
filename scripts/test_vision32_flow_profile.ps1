param([Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'build_snapshot.ps1')
$fixture=Join-Path ([IO.Path]::GetTempPath()) ('vision-profile-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $fixture 'rtl/soc') -Force|Out-Null
New-Item -ItemType Directory -Path (Join-Path $fixture 'rtl/mac_accel') -Force|Out-Null
[IO.File]::WriteAllText((Join-Path $fixture 'rtl/mac_accel/mac_conv_weight_dma.v'),'u_line_write_hold_lut')
$rows=@()
foreach($vision in @(0,1)) {
 foreach($conv in @(0,1)) {
  foreach($connected in @(0,1)) {
   $text="parameter integer ENABLE_VISION32_CANDIDATE = $vision,`nparameter integer ENABLE_CONV_CANDIDATE = $conv,`n"
   if($connected){$text+='.ENABLE_VISION32(ENABLE_VISION32_CANDIDATE)'}
   [IO.File]::WriteAllText((Join-Path $fixture 'rtl/soc/soc_top.v'),$text)
   $rejected=$false;$actual=$null
   try{$actual=Test-FpgaVision32Profile $fixture}catch{$rejected=$true}
   $bad=$vision -eq 1 -and (!$conv -or !$connected)
   if($rejected -ne $bad -or (!$bad -and $actual -ne ($vision -eq 1))){throw 'Vision profile incorrectly bypassed the legacy hold contract'}
   if(!$bad){
    $legacyOutput=@(Get-FpgaOutputPaths $fixture) -contains 'artifacts/conv_weight_hold_ads.json'
    if($legacyOutput -ne ($vision -eq 0)){throw 'Output evidence belongs to the wrong physical convolution profile'}
   }
   $rows+=@{vision=$vision;conv=$conv;connected=$connected;rejected=$rejected;replacement=$actual}
  }
 }
}
foreach($name in @('build_cpu_ads_gate.ps1','build_fpga.ps1')) {
 $text=[IO.File]::ReadAllText((Join-Path $PSScriptRoot $name))
 $expected=if($name -eq 'build_cpu_ads_gate.ps1'){1}else{2}
 if([regex]::Matches($text,[regex]::Escape("if (!(Test-FpgaVision32Profile `$root) -and (Get-Content -Raw -LiteralPath (Join-Path `$root 'rtl/mac_accel/mac_conv_weight_dma.v')).Contains('u_line_write_hold_lut')) {")).Count -ne $expected){throw 'Legacy hold check is not consistently selected at preflight/finalization'}
}
$record=@{status='VISION32_ACTUAL_PROFILE_AND_LEGACY_HOLD_GATE_SELECTION_PASS_NOT_PDS';cases=$rows;fixture=$fixture;script_sha256=(Get-FileHash (Join-Path $PSScriptRoot 'build_snapshot.ps1')).Hash.ToLowerInvariant()}
[IO.File]::WriteAllText($Output,($record|ConvertTo-Json -Depth 5)+"`n",[Text.UTF8Encoding]::new($false))
Write-Output 'VISION32_ACTUAL_PROFILE_AND_LEGACY_HOLD_GATE_SELECTION_PASS cases=8'
