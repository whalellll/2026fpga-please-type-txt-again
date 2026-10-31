param([Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
$native='G:/i60pnr4'
. (Join-Path $native 'scripts/build_snapshot.ps1')
$launch=Get-Content (Join-Path $native 'physical-launch.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if($launch.status -cne 'ROUTED_STA_FAILED_NOT_BOARD' -or $launch.error -cne 'Final PDS report_timing constraints are not met' -or $launch.run_id -cne 'dc951f8b1b7f4cf9962e5f509f165d0f'){throw 'Require completed, preserved native4 timing failure'}
$run=Join-Path $native ('pds/input-snapshots/'+$launch.run_id)
$xml=Join-Path $native 'pds/report_timing/rtr.db'
$rtr=Join-Path $native 'pds/report_timing/soc_top.rtr'
$fdc=Join-Path $native 'pds/soc.fdc'
$policy=Join-Path $native 'config/timing_scope_baseline.json'
# The strict checker and native reports remain unchanged. This explicitly
# named trial adapter retains clock/exception/coverage checks and permits only
# small CPU/SYS same-clock hold failures for the user's functional CRAM trial.
$source=[IO.File]::ReadAllText((Join-Path $native 'scripts/timing_scope.ps1'))
$anchor='if ($numbers[0] -lt 0 -or $numbers[1] -ne 0 -or $numbers[2] -ne 0 -or $numbers[3] -le 0) {'
if([regex]::Matches($source,[regex]::Escape($anchor)).Count -ne 1){throw 'Unknown frozen timing checker'}
$replacement=@'
if ($numbers[3] -le 0 -or (($numbers[0] -lt 0 -or $numbers[1] -ne 0 -or $numbers[2] -ne 0) -and
                    !($kind -ceq 'hold' -and $cells[0] -ceq $cells[1] -and $cells[0] -cin @('cpu_clk','sys_clk') -and
                      $numbers[0] -ge -0.05 -and $numbers[0] -lt 0 -and $numbers[1] -lt 0 -and $numbers[2] -gt 0 -and $numbers[2] -le 8))) {
'@
$source=$source.Replace($anchor,$replacement).Replace('function Assert-FpgaTimingScope(','function Assert-FunctionalTrialCoverage(')
$source=$source.Replace("status = 'PASS_WITH_DISCLOSED_BASELINE_IO_GAPS'","status = 'COVERAGE_ONLY_ACTUAL_HOLD_FAILURE_RETAINED'")
$check=[scriptblock]::Create('param($XmlPath,$FdcPath,$PolicyPath)'+"`n"+$source+"`nAssert-FunctionalTrialCoverage `$XmlPath `$FdcPath `$PolicyPath")
$skewSource=${function:Assert-FpgaMaxSkewReport}.ToString()
$skewNeedle='Design Summary : All Constraints Met\.'
if([regex]::Matches($skewSource,[regex]::Escape($skewNeedle)).Count -ne 1){throw 'Unknown frozen Max Skew checker'}
# Require the actual failed summary header; all twenty skew groups, five-bit
# paths, FDC identities and nonnegative skew margins remain strictly checked.
$trialSkew=[scriptblock]::Create($skewSource.Replace($skewNeedle,'Design Summary : Some Constraints Violated\.'))
$scope=& $check $xml $fdc $policy
$skew=& $trialSkew $xml $rtr $fdc
$clock=Get-Content (Join-Path $native 'config/clocks.json') -Raw | ConvertFrom-Json
Assert-SocClockIntent $clock
Assert-SocCpuClockHardware $native $clock
Assert-SocDisplayClockHardware $native $clock
$gates=[ordered]@{}
foreach($p in @((Join-Path $run 'preflight_gate.json'),(Join-Path $native 'artifacts/cpu_ads_controls.json'),(Join-Path $native 'artifacts/gui1080_placement.json'),(Join-Path $run 'cpu-sys-cdc-post-route.json'))){
 $d=Get-Content $p -Raw | ConvertFrom-Json
 if($d.status -notmatch 'PASS|PROVED'){throw "Incomplete physical gate: $p"}
 $gates[$p]=(Get-FileHash $p -Algorithm SHA256).Hash.ToLowerInvariant()
}
$hashes=[ordered]@{}
foreach($p in @($xml,$rtr,$fdc,$policy,(Join-Path $native 'physical-launch.json'),(Join-Path $native 'pds/build_snapshot.json'),(Join-Path $native 'scripts/timing_scope.ps1'),$MyInvocation.MyCommand.Path)){
 $hashes[$p]=(Get-FileHash $p -Algorithm SHA256).Hash.ToLowerInvariant()
}
$record=[ordered]@{status='FUNCTIONAL_TRIAL_COVERAGE_CHECKED_STA_FAILED_NOT_RELEASE';run_id=$launch.run_id;timing_pass=$false;scope=$scope;max_skew=$skew;final_gates_sha256=$gates;inputs_sha256=$hashes;authorization='User: 确认未通过先上板测功能，如果功能过了就行; later requests joint streaming voice and image fix board test';flash_written=$false;formal_delivery=$false}
[IO.File]::WriteAllText([IO.Path]::GetFullPath($OutputPath),($record|ConvertTo-Json -Depth 10)+"`n",[Text.UTF8Encoding]::new($false))
Write-Output $record.status
