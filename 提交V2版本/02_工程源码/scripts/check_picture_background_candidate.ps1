param(
    [Parameter(Mandatory=$true)][string]$HardwareRoot,
    [Parameter(Mandatory=$true)][string]$Output
)
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$candidate=[IO.Path]::GetFullPath($HardwareRoot).TrimEnd('\')
. (Join-Path $PSScriptRoot 'build_snapshot.ps1')
$evidencePath=Join-Path $candidate 'artifacts/build_evidence.json'
$record=[IO.File]::ReadAllText($evidencePath) | ConvertFrom-Json
Assert-FpgaReleaseEvidence $candidate $record
$snapshotPath=Join-Path $candidate 'artifacts/build_snapshot.json'
$snapshot=[IO.File]::ReadAllText($snapshotPath) | ConvertFrom-Json
$inputs=ConvertTo-FpgaMap $snapshot.inputs
if (!$inputs.Contains('rtl/camera/camera_capture_mode.v')) { throw 'Candidate lacks background capture hardware' }
foreach($name in $inputs.Keys) {
    if ($name -like 'artifacts/*') { continue }
    $actual=(Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $repo $name)).Hash.ToLowerInvariant()
    if($actual -cne $inputs[$name]) { throw "Hardware candidate differs from current sources: $name" }
}
$result=[ordered]@{
    status='PASS'; scope='Hardware build gates; NOT board acceptance'
    hardware_root=$candidate; run_id=$snapshot.run_id
    sbit_sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $candidate 'artifacts/soc_top.sbit')).Hash.ToLowerInvariant()
    build_evidence_sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $evidencePath).Hash.ToLowerInvariant()
    input_snapshot_sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $snapshotPath).Hash.ToLowerInvariant()
    background_banks=@('1b800000','1ba00000'); board_validated=$false
}
if(Test-Path -LiteralPath $Output) { throw 'Choose a fresh hardware check result path' }
[IO.File]::WriteAllText([IO.Path]::GetFullPath($Output),($result|ConvertTo-Json -Depth 5)+"`n",[Text.UTF8Encoding]::new($false))
Write-Output 'PICTURE_BACKGROUND_HARDWARE_BUILD_PASS board_validated=false'
