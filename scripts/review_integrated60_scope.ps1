param([Parameter(Mandatory=$true)][string]$NativeRoot,
      [Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
$NativeRoot=[IO.Path]::GetFullPath($NativeRoot)
. (Join-Path $NativeRoot 'scripts/build_snapshot.ps1')
. (Join-Path $PSScriptRoot 'timing_scope_pixel_grid.ps1')
$snapshotPath=Join-Path $NativeRoot 'pds/build_snapshot.json'
$snapshot=Get-Content -LiteralPath $snapshotPath -Raw|ConvertFrom-Json
$receiptPath=Join-Path $NativeRoot 'physical-launch.json'
$receipt=Get-Content -LiteralPath $receiptPath -Raw|ConvertFrom-Json
$receiptHash=(Get-FileHash -LiteralPath $receiptPath -Algorithm SHA256).Hash.ToLowerInvariant()
if($receipt.status -cne 'FAILED' -or $receipt.error -cne 'Native STA clock definition differs: pix_clk' -or $receipt.run_id -cne $snapshot.run_id){throw 'Expected immutable pixel-only failure receipt'}
foreach($entry in $receipt.reports.PSObject.Properties){
 if((Get-FileHash -LiteralPath (Join-Path $NativeRoot ('pds/'+$entry.Name)) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value){throw "Native output changed: $($entry.Name)"}
}
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
$runDir=Join-Path $NativeRoot ('pds/input-snapshots/'+$snapshot.run_id)
$gatePaths=@((Join-Path $runDir 'preflight_gate.json'),(Join-Path $NativeRoot 'artifacts/cpu_ads_controls.json'),(Join-Path $NativeRoot 'artifacts/gui1080_placement.json'),(Join-Path $runDir 'cpu-sys-cdc-post-route.json'))
$gates=[ordered]@{}
foreach($p in $gatePaths){
 $proof=Get-Content -LiteralPath $p -Raw|ConvertFrom-Json
 if($proof.status -notmatch 'PASS|PROVED'){throw "Native final gate not passed: $p"}
 $gates[$p]=$proof.status
}
$nativeLog=[IO.File]::ReadAllText((Join-Path $runDir 'pds.stdout.log'))
if($nativeLog -match '(?m)^E:' -or $nativeLog -notmatch 'Executing : gen_bit_stream .* successfully\.'){throw 'Native PDS operation did not complete without errors'}
$testPath=Join-Path (Split-Path -Parent $PSScriptRoot) 'build/integrated-pixel-scope-01/result.json'
$test=Get-Content -LiteralPath $testPath -Raw|ConvertFrom-Json
if($test.status -cne 'INTEGRATED60_PIXEL_SCOPE_MUTATIONS_PASS_NOT_BOARD' -or $test.checks.Count -ne 13){throw 'Pixel checker mutations not passed'}
$hashes=[ordered]@{}
foreach($path in (@($snapshotPath,$xml,$rtr,$fdc,$policy,$receiptPath,$testPath,(Join-Path $NativeRoot 'scripts/timing_scope.ps1'),(Join-Path $PSScriptRoot 'timing_scope_pixel_grid.ps1'),$MyInvocation.MyCommand.Path)+$gatePaths)){
 $hashes[$path]=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
}
if((Get-FileHash -LiteralPath $receiptPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $receiptHash){throw 'Frozen failure receipt changed'}
$record=[ordered]@{schema=1;status='ROUTED_STA_AND_REVIEWED_PIXEL_SCOPE_PASS_NOT_BOARD';run_id=$snapshot.run_id;native_root=$NativeRoot;cpu_hz=$clock.cpu_hz;original_scope_error=$originalError;original_flow_status=$receipt.status;original_frozen_receipt_unchanged=$true;native_pds_operations_without_errors=$true;frozen_snapshot_inputs_checked=@($snapshot.inputs.PSObject.Properties).Count;scope=$scope;max_skew=$skew;final_gates=$gates;inputs_sha256=$hashes;note='Independent read-only review. Original failed flow/receipt remains unchanged. Native STA passes, including existing disclosed I/O gaps only. Not board, model latency, strict original-flow success or delivery acceptance.'}
[IO.File]::WriteAllText([IO.Path]::GetFullPath($OutputPath),($record|ConvertTo-Json -Depth 10)+"`n",[Text.UTF8Encoding]::new($false))
Write-Output 'ROUTED_STA_AND_REVIEWED_PIXEL_SCOPE_PASS_NOT_BOARD'
