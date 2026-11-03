param([Parameter(Mandatory=$true)][string]$Root,[Parameter(Mandatory=$true)][string]$Bitstream)
$ErrorActionPreference='Stop'
$Root=[IO.Path]::GetFullPath($Root)
$python=Join-Path $Root 'build/picture-tools/python3144/python.exe'
$material=Join-Path $Root ('build/picture-e42-20261025/audit/'+[Guid]::NewGuid().ToString('N'))
$text=& $python -B (Join-Path $PSScriptRoot 'check_published_e42.py') --root $Root --image $Bitstream --materialize $material
if($LASTEXITCODE){throw 'Exact e42 source/image identity failed'}
$identity=$text|ConvertFrom-Json
if($identity.status -cne 'EXACT_PUBLISHED_E42_IDENTITY_PASS_NOT_FORMAL_RELEASE' -or
   $identity.native_input_hashes -ne 498 -or $identity.live_native_inputs -ne 491 -or
   $identity.archived_build_helpers -ne 7 -or $identity.formal_release -or
   $identity.native_database_replay_complete){throw 'Invalid e42 audit scope'}
. (Join-Path $Root 'scripts/build_snapshot.ps1')
. (Join-Path $Root 'scripts/timing_scope_pixel_grid.ps1')
$expected=@($identity.expected_hardware_paths)
$actual=@(Get-FpgaInputPaths $Root | Where-Object {$_ -match '^(rtl/|ip/|pds/|config/|sw/bootloader/)'})
if(@($actual|Where-Object {$_ -notin $expected}).Count -or
   @($expected|Where-Object {$_ -notin $actual}).Count){throw 'Unexpected hardware input inventory'}
$clock=Get-Content (Join-Path $Root 'config/clocks.json') -Raw|ConvertFrom-Json
Assert-SocClockIntent $clock
Assert-SocCpuClockHardware $Root $clock
Assert-SocDisplayClockHardware $Root $clock
if($clock.cpu_hz -ne 60000000 -or $clock.sys_hz -ne 49500000){throw 'Foreign e42 clocks'}
$fdc=Join-Path $Root 'pds/soc.fdc'
$checker=New-FpgaPixelGridScopeVerifier ([IO.File]::ReadAllText((Join-Path $Root 'scripts/timing_scope.ps1')))
$scope=& $checker $identity.raw_xml $fdc (Join-Path $Root 'config/timing_scope_baseline.json')
$skew=Assert-FpgaMaxSkewReport $identity.raw_xml $identity.raw_rtr $fdc
if($scope.summary_rows -ne 116 -or $scope.clocks -ne 18 -or $scope.unconstrained_ports -ne 187 -or
   $skew.rows -ne 20 -or $skew.groups -ne 10){throw 'Incomplete original e42 STA coverage'}
$identity.PSObject.Properties.Remove('expected_hardware_paths')
$identity|Add-Member -NotePropertyName coverage -NotePropertyValue $scope
$identity|Add-Member -NotePropertyName max_skew -NotePropertyValue $skew
$identity|Add-Member -NotePropertyName audit_script_sha256 -NotePropertyValue ((Get-FileHash $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant())
$identity|Add-Member -NotePropertyName identity_checker_sha256 -NotePropertyValue ((Get-FileHash (Join-Path $PSScriptRoot 'check_published_e42.py') -Algorithm SHA256).Hash.ToLowerInvariant())
$identity|ConvertTo-Json -Depth 10 -Compress
