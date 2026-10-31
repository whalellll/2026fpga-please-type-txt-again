param(
 [Parameter(Mandatory=$true)][string]$Root,
 [Parameter(Mandatory=$true)][string]$TrialDirectory,
 [Parameter(Mandatory=$true)][string]$Bitstream
)
$ErrorActionPreference='Stop'
$Root=[IO.Path]::GetFullPath($Root)
$TrialDirectory=[IO.Path]::GetFullPath($TrialDirectory)
$python=Join-Path $Root 'build/picture-tools/python3144/python.exe'
$identityText=& $python -X utf8 -B (Join-Path $PSScriptRoot 'check_cpu60_functional_trial.py') --root $Root --trial-directory $TrialDirectory --image $Bitstream
if($LASTEXITCODE -ne 0){throw 'Exact CPU60 trial identity audit failed'}
$identity=$identityText | ConvertFrom-Json
$native=Join-Path $TrialDirectory 'source'
. (Join-Path $native 'scripts/build_snapshot.ps1')
$xml=Join-Path $TrialDirectory 'archive/rtr.db'
$rtr=Join-Path $TrialDirectory 'archive/soc_top.rtr'
$fdc=Join-Path $native 'pds/soc.fdc'
$policy=Join-Path $native 'config/timing_scope_baseline.json'
# Identity verification above authenticates every byte of this original checker.
# Reuse only its explicit functional coverage adapter, not its missing-gate claims.
$text=[IO.File]::ReadAllText((Join-Path $native 'scripts/review_integrated60_functional_trial.ps1'))
$begin=$text.IndexOf('$source=[IO.File]::ReadAllText(')
$end=$text.IndexOf('$scope=& $check ')
if($begin -lt 0 -or $end -le $begin){throw 'Unknown original trial checker layout'}
Invoke-Expression $text.Substring($begin,$end-$begin)
$scope=& $check $xml $fdc $policy
$skew=& $trialSkew $xml $rtr $fdc
if($scope.status -cne 'COVERAGE_ONLY_ACTUAL_HOLD_FAILURE_RETAINED' -or $skew.rows -ne 20){throw 'Incomplete original functional coverage/skew'}
$clock=Get-Content (Join-Path $native 'config/clocks.json') -Raw -Encoding UTF8 | ConvertFrom-Json
Assert-SocClockIntent $clock
Assert-SocCpuClockHardware $native $clock
Assert-SocDisplayClockHardware $native $clock
if($clock.cpu_hz -ne 60000000 -or $clock.sys_hz -ne 49500000){throw 'Wrong hardware clock identity'}
# All fields explicitly retain the original incomplete native preflight and STA failure.
$identity | Add-Member -NotePropertyName coverage -NotePropertyValue $scope
$identity | Add-Member -NotePropertyName max_skew -NotePropertyValue $skew
$identity | Add-Member -NotePropertyName audit_script_sha256 -NotePropertyValue ((Get-FileHash $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant())
$identity | Add-Member -NotePropertyName identity_checker_sha256 -NotePropertyValue ((Get-FileHash (Join-Path $PSScriptRoot 'check_cpu60_functional_trial.py') -Algorithm SHA256).Hash.ToLowerInvariant())
$identity | ConvertTo-Json -Depth 10 -Compress
