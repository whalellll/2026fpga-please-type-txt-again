param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [ValidateSet('Production','ShortPilot','BoardRelease')][string]$CoremarkEvidenceMode = 'Production',
    [string]$ReleaseManifest,
    [string]$PythonPath = 'D:\LJL\WORK\msys64\mingw64\bin\python3.exe',
    [string]$HostGccPath = 'D:\LJL\WORK\msys64\mingw64\bin\gcc.exe'
)
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath($Root).TrimEnd('\')
$version = [IO.File]::ReadAllText((Join-Path $Root 'VERSION')).Trim()
if ($version -ceq '6.5' -and
    ($CoremarkEvidenceMode -cne 'BoardRelease' -or [string]::IsNullOrWhiteSpace($ReleaseManifest))) {
    throw 'SOC_V6_5_REQUIRES_BOARD_RELEASE: V6.5 formal delivery requires BoardRelease and an explicit -ReleaseManifest; incomplete candidates use create_candidate_delivery.ps1.'
}
if ($version -ceq '2.1' -and
    ($CoremarkEvidenceMode -cne 'BoardRelease' -or [string]::IsNullOrWhiteSpace($ReleaseManifest))) {
    throw 'SOC_V2_1_REQUIRES_BOARD_RELEASE: V2.1 formal delivery requires timed board CoreMark 3+1 and an explicit -ReleaseManifest; RTL CoreMark is not release evidence.'
}

function Get-DeliveryHash([string]$Path) {
    if (!(Test-Path -LiteralPath $Path -PathType Leaf) -or
        ((Get-Item -LiteralPath $Path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Missing or linked delivery evidence file: $Path"
    }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Test-DeliveryFrequencyMatch($Portable, $Source, [int]$Divisor,
    [string]$RunId, [string]$SnapshotSha256, [string]$BitstreamSha256,
    [string]$BuildEvidenceSha256) {
    if ($Portable.status -cne 'PASS' -or $Source.status -cne 'PASS' -or
        $Portable.divisor -ne $Divisor -or $Source.divisor -ne $Divisor -or
        $Portable.run_id -cne $RunId -or $Source.run_id -cne $RunId -or
        $Portable.snapshot_sha256 -cne $SnapshotSha256 -or
        $Source.snapshot_sha256 -cne $SnapshotSha256) { return $false }
    $bitstreams = @($Source.files | Where-Object { $_.path -ceq 'artifacts/soc_top.sbit' })
    $builds = @($Source.files | Where-Object { $_.path -ceq 'artifacts/build_evidence.json' })
    return ($bitstreams.Count -eq 1 -and $builds.Count -eq 1 -and
        $bitstreams[0].sha256 -ceq $BitstreamSha256 -and
        $builds[0].sha256 -ceq $BuildEvidenceSha256)
}

$clock = [IO.File]::ReadAllText((Join-Path $Root 'config/clocks.json')) | ConvertFrom-Json
$frequencyRoot = Join-Path $Root 'docs/validation/frequency-search'
$portableCount = 0
$matchingPassCount = 0
$currentSnapshot = $null
$currentSnapshotHash = $null
$currentBitstreamHash = $null
$currentBuildEvidenceHash = $null
foreach ($directory in Get-ChildItem -LiteralPath $frequencyRoot -Directory -Force) {
    if ($directory.Name -cnotmatch '^div([0-9]+)-(PASS|FAIL)-([0-9a-f]{32})$') { continue }
    $divisor = [int]$Matches[1]
    $status = $Matches[2]
    $runId = $Matches[3]
    if ($directory.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Linked frequency evidence directory: $($directory.FullName)"
    }
    $portablePath = Join-Path $directory.FullName 'portable_manifest.json'
    $archivePath = Join-Path $directory.FullName 'archive_manifest.json'
    [void](Get-DeliveryHash $portablePath)
    [void](Get-DeliveryHash $archivePath)
    & (Join-Path $Root 'scripts/verify_frequency_portable.ps1') -PortableDirectory $directory.FullName | Out-Null
    $portable = [IO.File]::ReadAllText($portablePath) | ConvertFrom-Json
    if ($portable.divisor -ne $divisor -or $portable.status -cne $status -or
        $portable.run_id -cne $runId) {
        throw "Frequency evidence directory name disagrees with its verified manifest: $($directory.Name)"
    }
    $portableCount++
    if ($status -ceq 'PASS' -and $divisor -eq $clock.cpu_divisor) {
        if ($null -eq $currentSnapshot) {
            $snapshotPath = Join-Path $Root 'artifacts/build_snapshot.json'
            $currentSnapshotHash = Get-DeliveryHash $snapshotPath
            $currentSnapshot = [IO.File]::ReadAllText($snapshotPath) | ConvertFrom-Json
            $currentBitstreamHash = Get-DeliveryHash (Join-Path $Root 'artifacts/soc_top.sbit')
            $currentBuildEvidenceHash = Get-DeliveryHash (Join-Path $Root 'artifacts/build_evidence.json')
        }
        $source = [IO.File]::ReadAllText($archivePath) | ConvertFrom-Json
        if (Test-DeliveryFrequencyMatch $portable $source $clock.cpu_divisor `
                $currentSnapshot.run_id $currentSnapshotHash $currentBitstreamHash `
                $currentBuildEvidenceHash) { $matchingPassCount++ }
    }
}
if ($matchingPassCount -lt 1) {
    throw "Delivery requires a verified PASS frequency archive for the final main PDS run at CPU divisor $($clock.cpu_divisor)"
}

$validationRoot = Join-Path $Root 'docs/validation'
if ($ReleaseManifest) {
    if ([IO.Path]::IsPathRooted($ReleaseManifest) -or $ReleaseManifest -match '(^|[/\\])\.\.([/\\]|$)') {
        throw 'ReleaseManifest must be a portable repository-relative path'
    }
    $manifestPath = [IO.Path]::GetFullPath((Join-Path $Root $ReleaseManifest))
    if (!$manifestPath.StartsWith($validationRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Release manifest must be archived below docs/validation'
    }
    [void](Get-DeliveryHash $manifestPath)
    $selection = [IO.File]::ReadAllText($manifestPath) | ConvertFrom-Json
    if ($selection.release_version -cne $version -or $selection.evidence_mode -cne $CoremarkEvidenceMode) {
        throw 'Explicit release evidence manifest has the wrong version or mode'
    }
} elseif ($CoremarkEvidenceMode -ceq 'BoardRelease') {
    throw 'BoardRelease requires -ReleaseManifest; no implicit or historical evidence selection is allowed'
}
if ($CoremarkEvidenceMode -ceq 'BoardRelease') {
    if ($version -ceq '2.1') {
        & $PythonPath -B (Join-Path $Root 'scripts/verify_v2_1_board_release.py') `
            --root $Root --manifest $manifestPath --host-gcc $HostGccPath
        if ($LASTEXITCODE -ne 0) { throw 'V2.1 board identity, timing, CoreMark or GUI acceptance failed' }
        Write-Output "SOC_DELIVERY_EVIDENCE_BOARD_RELEASE_PASS portable=$portableCount matching_frequency_pass=$matchingPassCount board_runs=4 gui_boots=3 rtl_coremark=none"
        return
    }
    & $PythonPath -B (Join-Path $Root 'scripts/verify_board_release.py') `
        --root $Root --manifest $manifestPath --host-gcc $HostGccPath
    if ($LASTEXITCODE -ne 0) { throw 'BoardRelease identity, timing or CoreMark acceptance failed' }
    $pilotPath = [IO.Path]::GetFullPath((Join-Path $Root $selection.short_pilot.path))
    & (Join-Path $Root 'scripts/verify_coremark_short_pilot_evidence.ps1') `
        -Root $Root -EvidenceDirectory (Split-Path -Parent $pilotPath) -PythonPath $PythonPath
    Write-Output "SOC_DELIVERY_EVIDENCE_BOARD_RELEASE_PASS portable=$portableCount matching_frequency_pass=$matchingPassCount rtl_short=2 board_runs=4 control_runs=4"
    return
}
if ($ReleaseManifest) {
    $relativeEvidence = $selection.coremark_directory
    if (!$relativeEvidence -or [IO.Path]::IsPathRooted($relativeEvidence) -or $relativeEvidence -match '(^|[/\\])\.\.([/\\]|$)') {
        throw 'Manifest coremark_directory must be a portable path'
    }
    $selectedDirectory = [IO.Path]::GetFullPath((Join-Path $Root $relativeEvidence))
    if (!(Split-Path -Parent $selectedDirectory).Equals($validationRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Selected CoreMark evidence must be a direct docs/validation child'
    }
} elseif ($CoremarkEvidenceMode -ceq 'ShortPilot') {
    $selectedDirectory = Join-Path $validationRoot ('v' + $version.Replace('.', '_') + '-short-pilot')
} else {
    # Preserve unambiguous legacy Production selection while allowing an explicit
    # version manifest when historical release directories coexist.
    $legacy = @(Get-ChildItem -LiteralPath $validationRoot -Directory -Force | Where-Object {
        $record = Join-Path $_.FullName 'release_evidence.json'
        (Test-Path -LiteralPath $record) -and
            (([IO.File]::ReadAllText($record) | ConvertFrom-Json).status -ceq 'RTL_3_PLUS_1_TIMED_PASS_NOT_BOARD')
    })
    if ($legacy.Count -ne 1) { throw 'Production requires an explicit release manifest when evidence is ambiguous' }
    $selectedDirectory = $legacy[0].FullName
}
$coremarkDir = Get-Item -LiteralPath $selectedDirectory
if ($coremarkDir.Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'CoreMark evidence directory is linked'
}
if ($CoremarkEvidenceMode -ceq 'ShortPilot') {
    & (Join-Path $Root 'scripts/verify_coremark_short_pilot_evidence.ps1') `
        -Root $Root -EvidenceDirectory $coremarkDir.FullName -PythonPath $PythonPath
    Write-Output "SOC_DELIVERY_EVIDENCE_SHORT_PILOT_PASS portable=$portableCount matching_frequency_pass=$matchingPassCount coremark_runs=2 formal_score=false"
    return
}
$release = [IO.File]::ReadAllText((Join-Path $coremarkDir.FullName 'release_evidence.json')) | ConvertFrom-Json
$summary = [IO.File]::ReadAllText((Join-Path $coremarkDir.FullName 'summary.json')) | ConvertFrom-Json
if ($release.schema_version -ne 1 -or
    $release.status -cne 'RTL_3_PLUS_1_TIMED_PASS_NOT_BOARD' -or
    $release.board_acceptance -ne $false -or
    $summary.status -cne $release.status -or $summary.kind -cne 'Long' -or
    @($summary.cases).Count -ne 4 -or
    $summary.concurrent_runs -ne $true -or
    $summary.iteration_policy -cne 'production_automatic_calibration' -or
    (@($summary.run_plan) -join ',') -cne 'performance,performance,performance,validation' -or
    $release.cpu_hz -ne $clock.cpu_hz -or $release.sys_hz -ne $clock.sys_hz -or
    $release.timebase_hz -ne $clock.timebase_hz -or
    $summary.cpu_hz -ne $release.cpu_hz -or $summary.sys_hz -ne $release.sys_hz -or
    $summary.timebase_hz -ne $release.timebase_hz -or
    $release.pds_snapshot_run_id -cne $summary.pds_snapshot_run_id -or
    $release.pds_snapshot_sha256 -cne $summary.pds_snapshot_sha256 -or
    $release.released_bitstream_sha256 -cne $summary.released_bitstream_sha256 -or
    $release.firmware_binary_sha256 -cne $summary.executed_firmware_sha256 -or
    $release.bootrom_sha256 -cne $summary.executed_rom_sha256 -or
    $release.verilator_model_sha256 -cne $summary.model_sha256 -or
    $release.verilator_model_manifest_sha256 -cne $summary.model_manifest_sha256 -or
    $summary.host_model_compilation.explicit_cpp_flags -cne '-Os' -or
    $summary.host_model_compilation.observed_cpp_command_count -lt 1) {
    throw 'Promoted production CoreMark evidence has missing or foreign 3+1 identity'
}
foreach ($binding in @(
    @('pds_snapshot_sha256','artifacts/build_snapshot.json'),
    @('released_bitstream_sha256','artifacts/soc_top.sbit'),
    @('firmware_binary_sha256','artifacts/bootloader.bin'),
    @('bootrom_sha256','artifacts/bootrom.hex')
)) {
    if ($release.($binding[0]) -cne (Get-DeliveryHash (Join-Path $Root $binding[1]))) {
        throw "Promoted production CoreMark evidence differs from final release: $($binding[1])"
    }
}
if ($summary.pds_build_evidence_sha256 -cne
    (Get-DeliveryHash (Join-Path $Root 'artifacts/build_evidence.json'))) {
    throw 'Promoted production CoreMark evidence differs from final FPGA build evidence'
}
$caseNames = @('run01-performance','run02-performance','run03-performance','run04-validation')
$expectedFiles = [Collections.Generic.List[string]]::new()
foreach ($name in $caseNames) {
    $expectedFiles.Add("$name.uart.txt")
    $expectedFiles.Add("$name.stderr.txt")
    $expectedFiles.Add("$name.json")
}
foreach ($name in @('summary.json','verilator_model.json','verilator_build.txt',
    'verilator_build_script.txt','verilator_generated_makefile.txt',
    'bootloader.build.json','cpu_source.json','fpga_input_snapshot.json',
    'fpga_build_evidence.json','timing_summary.txt')) { $expectedFiles.Add($name) }
$hashFields = @($release.files_sha256.PSObject.Properties)
if ($hashFields.Count -ne $expectedFiles.Count -or
    @(Compare-Object ($expectedFiles | Sort-Object) ($hashFields.Name | Sort-Object)).Count) {
    throw 'Promoted production CoreMark file hash inventory is incomplete'
}
foreach ($field in $hashFields) {
    if ($field.Value -cnotmatch '^[0-9a-f]{64}$' -or
        (Get-DeliveryHash (Join-Path $coremarkDir.FullName $field.Name)) -cne $field.Value) {
        throw "Promoted production CoreMark file differs: $($field.Name)"
    }
}
$nodes = @(Get-ChildItem -LiteralPath $coremarkDir.FullName -Recurse -Force)
if (@($nodes | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count -or
    @($nodes | Where-Object { $_.PSIsContainer }).Count) {
    throw 'Promoted production CoreMark evidence contains a directory or link'
}
$actualFiles = @($nodes | ForEach-Object { $_.Name })
if ($actualFiles.Count -ne $expectedFiles.Count + 1 -or
    @(Compare-Object (($expectedFiles.ToArray() + 'release_evidence.json') | Sort-Object)
        ($actualFiles | Sort-Object)).Count) {
    throw 'Promoted production CoreMark evidence contains missing or unlisted files'
}
if ($release.files_sha256.'summary.json' -cne
        (Get-DeliveryHash (Join-Path $coremarkDir.FullName 'summary.json')) -or
    $release.files_sha256.'fpga_input_snapshot.json' -cne $release.pds_snapshot_sha256 -or
    $release.files_sha256.'fpga_build_evidence.json' -cne $summary.pds_build_evidence_sha256 -or
    $release.files_sha256.'bootloader.build.json' -cne
        (Get-DeliveryHash (Join-Path $Root 'artifacts/bootloader.build.json')) -or
    $release.files_sha256.'bootloader.build.json' -cne
        $summary.target_firmware_compilation.build_manifest_sha256 -or
    $release.files_sha256.'cpu_source.json' -cne
        (Get-DeliveryHash (Join-Path $Root 'rtl/cpu/source.json')) -or
    $release.files_sha256.'timing_summary.txt' -cne
        (Get-DeliveryHash (Join-Path $Root 'artifacts/timing_summary.txt')) -or
    $release.files_sha256.'verilator_model.json' -cne $summary.model_manifest_sha256 -or
    $release.files_sha256.'verilator_build.txt' -cne
        $summary.host_model_compilation.build_log_sha256 -or
    $release.files_sha256.'verilator_build_script.txt' -cne
        $summary.host_model_compilation.build_script_sha256 -or
    $release.files_sha256.'verilator_generated_makefile.txt' -cne
        $summary.host_model_compilation.generated_makefile_sha256 -or
    $release.performance_score.minimum -ne $summary.performance_score.minimum -or
    $release.performance_score.mean -ne $summary.performance_score.mean -or
    $release.performance_score.median -ne $summary.performance_score.median -or
    $release.performance_score.maximum -ne $summary.performance_score.maximum) {
    throw 'Promoted production CoreMark evidence does not bind its summary and FPGA receipts'
}
for ($index = 0; $index -lt 4; $index++) {
    $name = $caseNames[$index]
    $mode = if ($index -eq 3) { 'validation' } else { 'performance' }
    $case = $summary.cases[$index]
    $result = [IO.File]::ReadAllText((Join-Path $coremarkDir.FullName "$name.json")) | ConvertFrom-Json
    if ($case.name -cne $name -or $case.mode -cne $mode -or
        $case.result.seed_mode -cne $mode -or
        $case.result.status -cne 'RTL_TIMED_PASS_NOT_BOARD' -or
        $case.result.timer_seconds -lt 10 -or
        $case.result.ticks -lt (10 * $summary.timebase_hz) -or
        $case.result.iterations -lt 1 -or
        $case.result.coremark_per_mhz -le 0 -or
        $case.result.observed_cpu_cycles_timer_release_to_prompt -le 0 -or
        $case.result.timer_stimulus_scale_during_command -ne 1 -or
        $result.status -cne $case.result.status -or
        $result.ticks -ne $case.result.ticks -or
        $result.iterations -ne $case.result.iterations -or
        $result.coremark_per_mhz -ne $case.result.coremark_per_mhz -or
        $result.log_sha256 -cne $case.result.log_sha256 -or
        $release.files_sha256."$name.uart.txt" -cne $result.log_sha256) {
        throw "Promoted production CoreMark run is missing, short, or changed: $name"
    }
}
Write-Output "SOC_DELIVERY_EVIDENCE_PASS portable=$portableCount matching_frequency_pass=$matchingPassCount coremark_runs=4"
