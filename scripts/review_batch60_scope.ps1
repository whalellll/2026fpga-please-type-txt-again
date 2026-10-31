param([Parameter(Mandatory=$true)][string]$NativeRoot,
      [Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
$NativeRoot=[IO.Path]::GetFullPath($NativeRoot)
. (Join-Path $NativeRoot 'scripts/build_snapshot.ps1')
. (Join-Path $PSScriptRoot 'timing_scope_pixel_grid.ps1')
$snapshotPath=Join-Path $NativeRoot 'pds/build_snapshot.json'
$snapshot=Get-Content -LiteralPath $snapshotPath -Raw|ConvertFrom-Json
foreach($entry in $snapshot.inputs.PSObject.Properties){
 if((Get-FileHash -LiteralPath (Join-Path $NativeRoot $entry.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value){throw "Frozen native input changed: $($entry.Name)"}
}
$fdc=Join-Path $NativeRoot 'pds/soc.fdc'
$xml=Join-Path $NativeRoot 'pds/report_timing/rtr.db'
$rtr=Join-Path $NativeRoot 'pds/report_timing/soc_top.rtr'
$policy=Join-Path $NativeRoot 'config/timing_scope_baseline.json'
if([IO.File]::ReadAllText($rtr) -notmatch 'Design Summary : All Constraints Met\.'){throw 'Actual final STA has violations; scope review cannot change that result'}
$clock=Get-Content -LiteralPath (Join-Path $NativeRoot 'config/clocks.json') -Raw|ConvertFrom-Json
Assert-SocClockIntent $clock
Assert-SocCpuClockHardware $NativeRoot $clock
Assert-SocDisplayClockHardware $NativeRoot $clock
$originalError=''
try{$null=Assert-FpgaTimingScope $xml $fdc $policy}catch{$originalError=$_.Exception.Message}
if($originalError -and $originalError -cne 'Native STA clock definition differs: pix_clk'){throw "Unreviewed original scope failure: $originalError"}
$source=[IO.File]::ReadAllText((Join-Path $NativeRoot 'scripts/timing_scope.ps1'))
$verifier=New-FpgaPixelGridScopeVerifier $source
$scope=& $verifier $xml $fdc $policy
$skew=Assert-FpgaMaxSkewReport $xml $rtr $fdc
$hashes=[ordered]@{}
foreach($path in @($snapshotPath,$xml,$rtr,$fdc,$policy,(Join-Path $NativeRoot 'scripts/timing_scope.ps1'),(Join-Path $PSScriptRoot 'timing_scope_pixel_grid.ps1'),$MyInvocation.MyCommand.Path)){
 $hashes[$path]=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
}
$record=[ordered]@{schema=1;status='ROUTED_STA_AND_REVIEWED_PIXEL_SCOPE_PASS_NOT_BOARD';run_id=$snapshot.run_id;native_root=$NativeRoot;cpu_hz=$clock.cpu_hz;original_scope_error=$originalError;original_frozen_receipt_unchanged=$true;scope=$scope;max_skew=$skew;inputs_sha256=$hashes;note='Independent read-only review. Original flow/receipt remains unchanged. Not board, model latency or delivery acceptance.'}
[IO.File]::WriteAllText([IO.Path]::GetFullPath($OutputPath),($record|ConvertTo-Json -Depth 10)+"`n",[Text.UTF8Encoding]::new($false))
Write-Output 'ROUTED_STA_AND_REVIEWED_PIXEL_SCOPE_PASS_NOT_BOARD'
