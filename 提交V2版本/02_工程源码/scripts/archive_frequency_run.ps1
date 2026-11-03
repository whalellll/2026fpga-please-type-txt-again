param(
    [Parameter(Mandatory=$true)][string]$ProjectRoot,
    [Parameter(Mandatory=$true)][ValidateSet(18,17,16,15,14,13,12)][int]$Divisor,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{32}$')][string]$RunId,
    [Parameter(Mandatory=$true)][ValidateSet('PASS','FAIL')][string]$Status,
    [string]$FailureReason = '',
    [string]$ArchiveRoot = '',
    [string]$CandidateInputs = ''
)

$ErrorActionPreference = 'Stop'
$project = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')
$workspace = [IO.Path]::GetFullPath((Split-Path -Parent $project)).TrimEnd('\')
if (!$ArchiveRoot) { $ArchiveRoot = Join-Path $workspace 'soc_freq_evidence' }
$archiveRoot = [IO.Path]::GetFullPath($ArchiveRoot).TrimEnd('\')
if (!$archiveRoot.StartsWith($workspace + '\', [StringComparison]::OrdinalIgnoreCase) -or
    $archiveRoot -eq $project -or $archiveRoot.StartsWith($project + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw "Archive root must be a sibling within $workspace"
}
if ($Status -eq 'FAIL' -and !$FailureReason) { throw 'FAIL requires -FailureReason' }
if ($Status -eq 'PASS' -and $FailureReason) { throw 'PASS cannot have -FailureReason' }
if (!(Test-Path -LiteralPath (Join-Path $project 'scripts/build_snapshot.ps1') -PathType Leaf)) {
    throw "Not a SoC checkout: $project"
}
$destination = [IO.Path]::GetFullPath((Join-Path $archiveRoot ("div{0}-{1}-{2}" -f $Divisor,$Status,$RunId)))
if (!$destination.StartsWith($archiveRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or
    (Test-Path -LiteralPath $destination)) { throw "Archive target is unsafe or already exists: $destination" }
foreach ($cursor in @($workspace,$archiveRoot)) {
    if ((Test-Path -LiteralPath $cursor) -and
        ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Archive parent is a link: $cursor"
    }
}
. (Join-Path $project 'scripts/build_snapshot.ps1')
$snapshotRelative = "pds/input-snapshots/$RunId/snapshot.json"
$snapshotFile = Get-FpgaSafePath $project $snapshotRelative
if (!(Test-Path -LiteralPath $snapshotFile -PathType Leaf)) { throw "Missing frozen snapshot: $snapshotFile" }
$snapshot = [IO.File]::ReadAllText($snapshotFile) | ConvertFrom-Json
if ($snapshot.run_id -cne $RunId) { throw 'Snapshot run ID mismatch' }
$snapshotDir = Get-FpgaSafePath $project "pds/input-snapshots/$RunId"
$frozenFiles = @(Get-ChildItem -LiteralPath $snapshotDir -Recurse -File -Force)
if ($frozenFiles.Count -gt 2000 -or
    @($frozenFiles | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
    throw 'Frozen input tree is too large or contains a link'
}
if (($frozenFiles | Measure-Object Length -Sum).Sum -gt 1073741824) { throw 'Frozen input tree exceeds 1 GiB' }
$inputHashes = ConvertTo-FpgaMap $snapshot.inputs
$stagedHashes = ConvertTo-FpgaMap $snapshot.staged_hashes
foreach ($entry in $inputHashes.GetEnumerator()) {
    $path = Get-FpgaSafePath $snapshotDir ("files/" + $entry.Key)
    if (!(Test-Path -LiteralPath $path -PathType Leaf) -or
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value) {
        throw "Frozen input mismatch: $($entry.Key)"
    }
}
foreach ($entry in $stagedHashes.GetEnumerator()) {
    $path = Get-FpgaSafePath $snapshotDir ("files/" + $entry.Key)
    if (!(Test-Path -LiteralPath $path -PathType Leaf) -or
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value) {
        throw "Frozen staged asset mismatch: $($entry.Key)"
    }
}

$candidateInputsHash = $null
$candidateRelative = $null
$candidateHashes = [ordered]@{}
if ($Divisor -ne 18 -or $CandidateInputs) {
    if (!$CandidateInputs -and [version]$snapshot.release.TrimStart('V','v') -ge [version]'6.5') {
        throw 'V6.5 candidate archive requires -CandidateInputs with its explicit unique record path'
    }
    $candidateRelative = Get-SocCandidateEvidenceRelative $Divisor $CandidateInputs
    $candidatePath = Get-FpgaSafePath $project $candidateRelative
    if (!(Test-Path -LiteralPath $candidatePath -PathType Leaf)) {
        throw "Missing generated candidate input record: $candidateRelative"
    }
    $candidate = [IO.File]::ReadAllText($candidatePath) | ConvertFrom-Json
    $frozenClock = [IO.File]::ReadAllText((Get-FpgaSafePath $snapshotDir 'files/config/clocks.json')) | ConvertFrom-Json
    if ($candidate.schema -ne 1 -or $candidate.kind -cne 'soc-cpu-clock-candidate-inputs' -or
        $candidate.cpu_divisor -ne $Divisor -or $frozenClock.cpu_divisor -ne $Divisor -or
        $candidate.cpu_hz -ne $frozenClock.cpu_hz -or
        $candidate.sys_hz -ne $frozenClock.sys_hz -or
        $candidate.timebase_hz -ne $frozenClock.timebase_hz) {
        throw 'Candidate input record identity differs from frozen PDS snapshot'
    }
    $candidateHashes = ConvertTo-FpgaMap $candidate.inputs
    if ($candidateHashes.Count -lt 8) { throw 'Candidate input record is incomplete' }
    foreach ($entry in $candidateHashes.GetEnumerator()) {
        $path = Get-FpgaSafePath $project $entry.Key
        if (!(Test-Path -LiteralPath $path -PathType Leaf) -or
            (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value -or
            ($inputHashes.Contains($entry.Key) -and $inputHashes[$entry.Key] -cne $entry.Value)) {
            throw "Candidate input record differs from current/frozen bytes: $($entry.Key)"
        }
    }
    $candidateInputsHash = (Get-FileHash -LiteralPath $candidatePath -Algorithm SHA256).Hash.ToLowerInvariant()
}

$copyPaths = @($frozenFiles | ForEach-Object {
    $_.FullName.Substring($project.Length + 1).Replace('\','/')
})
if ($candidateRelative) { $copyPaths += $candidateRelative }
if ($candidateRelative) { $copyPaths += @($candidateHashes.Keys) }
$activeSnapshot = Get-FpgaSafePath $project 'pds/build_snapshot.json'
if ((Test-Path -LiteralPath $activeSnapshot -PathType Leaf) -and
    (Get-FileHash -LiteralPath $activeSnapshot -Algorithm SHA256).Hash -eq
    (Get-FileHash -LiteralPath $snapshotFile -Algorithm SHA256).Hash) {
    $copyPaths += 'pds/build_snapshot.json'
}
$evidence = $null
if ($Status -eq 'PASS') {
    $evidencePath = Get-FpgaSafePath $project 'artifacts/build_evidence.json'
    if (!(Test-Path -LiteralPath $evidencePath -PathType Leaf)) { throw 'PASS needs build_evidence.json' }
    $evidence = [IO.File]::ReadAllText($evidencePath) | ConvertFrom-Json
    if ($evidence.run_id -cne $RunId) { throw 'Build evidence run ID mismatch' }
    Assert-FpgaReleaseEvidence $project $evidence
    $reportHashes = ConvertTo-FpgaMap $evidence.report_hashes
    foreach ($entry in $reportHashes.GetEnumerator()) {
        $path = Get-FpgaSafePath $project $entry.Key
        if (!(Test-Path -LiteralPath $path -PathType Leaf) -or
            (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value) {
            throw "PDS report differs from release evidence: $($entry.Key)"
        }
    }
    $copyPaths += @((Get-FpgaOutputPaths $root) + @($reportHashes.Keys) +
        @('artifacts/build_evidence.json','artifacts/SHA256SUMS.txt'))
} else {
    # A failed attempt has no release evidence. Keep only its frozen inputs,
    # same-run top-level files, and a fixed list of fresh partial reports.
    $copyPaths += @('pds/flow.log','pds/soc_pre_synth.pds','pds/soc.pds','pds/impl.tcl',
        'pds/stdout.log','pds/stderr.log','pds/run.log','pds/pds.log',
        'pds/synthesize/soc_top.snr','pds/synthesize/soc_top_syn.vm',
        'pds/synthesize/soc_top_syn.adf',
        'pds/constraint_check/constraint_check.ccr',
        'pds/device_map/soc_top.dmr',
        'pds/device_map/soc_top_dmr.prt',
        'pds/place_route/soc_top_pnr.adf',
        'pds/place_route/soc_top_prr.prt',
        'pds/place_route/soc_top_timing_summary_after_hold_fix.txt',
        'pds/report_timing/soc_top.rtr',
        'pds/report_timing/rtr.db',
        'pds/generate_bitstream/soc_top.sbit',
        'pds/generate_bitstream/soc_top.bin') | Where-Object {
            $path = Get-FpgaSafePath $project $_
            (Test-Path -LiteralPath $path -PathType Leaf) -and
            (Get-Item -LiteralPath $path).LastWriteTimeUtc -ge [datetime]::Parse($snapshot.started_utc).ToUniversalTime()
        }
}
$copyPaths = @($copyPaths | Sort-Object -Unique)
if ($copyPaths.Count -gt 2050) { throw 'Archive file inventory exceeds 2050' }
$totalBytes = [int64]0
foreach ($relative in $copyPaths) {
    $source = Get-FpgaSafePath $project $relative
    if (!(Test-Path -LiteralPath $source -PathType Leaf)) { throw "Archive source missing: $relative" }
    $size = (Get-Item -LiteralPath $source).Length
    if ($size -gt 2147483648) { throw "Archive source exceeds 2 GiB: $relative" }
    $totalBytes += $size
}
if ($totalBytes -gt 8589934592) { throw 'Archive exceeds 8 GiB total' }

New-Item -ItemType Directory -Path $destination -Force | Out-Null
$items = @()
foreach ($relative in $copyPaths) {
    $source = Get-FpgaSafePath $project $relative
    $target = Get-FpgaSafePath $destination $relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    $before = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    Copy-Item -LiteralPath $source -Destination $target
    $after = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    $copyHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($before -cne $after -or $before -cne $copyHash) { throw "Source changed during archive: $relative" }
    $items += [pscustomobject][ordered]@{ path=$relative; bytes=(Get-Item -LiteralPath $target).Length; sha256=$copyHash }
}
$manifest = [pscustomobject][ordered]@{
    schema = 1; status = $Status; divisor = $Divisor; run_id = $RunId
    failure_reason = $FailureReason
    project_root = $project
    source_git_head = (& git -C $project rev-parse HEAD).Trim()
    archive_script_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    snapshot_sha256 = (Get-FileHash -LiteralPath $snapshotFile -Algorithm SHA256).Hash.ToLowerInvariant()
    candidate_inputs_sha256 = $candidateInputsHash
    candidate_inputs_path = $candidateRelative
    archived_utc = [datetime]::UtcNow.ToString('o')
    file_count = $items.Count; total_bytes = $totalBytes
    files = $items
}
[IO.File]::WriteAllText((Join-Path $destination 'archive_manifest.json'),
    ($manifest | ConvertTo-Json -Depth 5) + "`n", [Text.UTF8Encoding]::new($false))
Write-Output "FREQUENCY_ARCHIVE_$Status run=$RunId divisor=$Divisor files=$($items.Count) bytes=$totalBytes path=$destination"
