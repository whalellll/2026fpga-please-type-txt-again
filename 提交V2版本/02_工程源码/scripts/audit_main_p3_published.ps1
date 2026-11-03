param([Parameter(Mandatory=$true)][string]$Root,[Parameter(Mandatory=$true)][string]$Bitstream)
$ErrorActionPreference='Stop'
$Root=[IO.Path]::GetFullPath($Root)
$python=Join-Path $Root 'build/picture-tools/python3144/python.exe'
$text=& $python -B (Join-Path $PSScriptRoot 'check_main_p3_published.py') --root $Root --image $Bitstream
if($LASTEXITCODE){throw 'Exact main P3 publication identity failed'}
$identity=$text|ConvertFrom-Json
if($identity.status -cne 'EXACT_MAIN_P3_PUBLISHED_IDENTITY_PASS_NOT_FORMAL_RELEASE' -or
   $identity.formal_release -or $identity.native_database_replay_complete){throw 'Invalid published-image scope'}
. (Join-Path $PSScriptRoot 'build_snapshot.ps1')
. (Join-Path $PSScriptRoot 'timing_scope_pixel_grid.ps1')
$snap=Get-Content (Join-Path $Root 'artifacts/build_snapshot.json') -Raw -Encoding UTF8|ConvertFrom-Json
$expected=@($snap.inputs.PSObject.Properties.Name)
$actual=@(Get-FpgaInputPaths $Root)
$extra=@($actual|Where-Object {$_ -notin $expected})
$missing=@($expected|Where-Object {$_ -notin $actual})
if($missing.Count -or (($extra|Sort-Object)-join "`n") -cne (($identity.extra_software_inputs|Sort-Object)-join "`n")){
 throw 'Unreviewed hardware/source inventory difference'
}
$clock=Get-Content (Join-Path $Root 'config/clocks.json') -Raw|ConvertFrom-Json
Assert-SocClockIntent $clock
Assert-SocCpuClockHardware $Root $clock
Assert-SocDisplayClockHardware $Root $clock
if($clock.cpu_hz -ne 60000000 -or $clock.sys_hz -ne 49500000){throw 'Foreign clocks'}
$xml=Join-Path $Root 'artifacts/final_timing_xml.xml'
$rtr=Join-Path $Root 'artifacts/final_timing_report.txt'
$fdc=Join-Path $Root 'pds/soc.fdc'
$policy=Join-Path $Root 'config/timing_scope_baseline.json'
if([IO.File]::ReadAllText($rtr) -notmatch 'Design Summary : All Constraints Met\.'){throw 'Raw STA fails'}
$checker=New-FpgaPixelGridScopeVerifier ([IO.File]::ReadAllText((Join-Path $Root 'scripts/timing_scope.ps1')))
$scope=& $checker $xml $fdc $policy
$skew=Assert-FpgaMaxSkewReport $xml $rtr $fdc
if($scope.summary_rows -ne 116 -or $scope.clocks -ne 18 -or $scope.unconstrained_ports -ne 187 -or
   $skew.rows -ne 20 -or $skew.groups -ne 10){throw 'Incomplete published STA coverage'}
$identity|Add-Member -NotePropertyName coverage -NotePropertyValue $scope
$identity|Add-Member -NotePropertyName max_skew -NotePropertyValue $skew
$identity|Add-Member -NotePropertyName audit_script_sha256 -NotePropertyValue ((Get-FileHash $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant())
$identity|Add-Member -NotePropertyName identity_checker_sha256 -NotePropertyValue ((Get-FileHash (Join-Path $PSScriptRoot 'check_main_p3_published.py') -Algorithm SHA256).Hash.ToLowerInvariant())
$identity|ConvertTo-Json -Depth 10 -Compress
