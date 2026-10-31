param([Parameter(Mandatory=$true)][string]$ArchiveDirectory)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'build_snapshot.ps1')
$archive = [IO.Path]::GetFullPath($ArchiveDirectory).TrimEnd('\')
if (!(Test-Path -LiteralPath $archive -PathType Container) -or
    ((Get-Item -LiteralPath $archive -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'Archive directory is missing or linked'
}
$manifestPath = Join-Path $archive 'archive_manifest.json'
if (!(Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw 'Archive manifest is missing' }
$manifest = [IO.File]::ReadAllText($manifestPath) | ConvertFrom-Json
if ($manifest.schema -ne 1 -or $manifest.status -notin @('PASS','FAIL') -or
    $manifest.divisor -notin @(18,17,16,15,14,13,12) -or
    $manifest.run_id -notmatch '^[0-9a-f]{32}$' -or
    $manifest.snapshot_sha256 -notmatch '^[0-9a-f]{64}$' -or
    ($manifest.status -eq 'FAIL' -and !$manifest.failure_reason) -or
    ($manifest.status -eq 'PASS' -and $manifest.failure_reason)) {
    throw 'Archive manifest header is invalid'
}
$files = @($manifest.files)
if ($files.Count -lt 1 -or $files.Count -gt 2050) { throw 'Archive file count is outside bound' }
if ($null -ne $manifest.file_count -and $manifest.file_count -ne $files.Count) {
    throw 'Archive manifest file count differs'
}
$seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$bytes = [int64]0
foreach ($item in $files) {
    if ($item.path -notmatch '^[^\\/]+(?:/[^\\/]+)*$' -or
        $item.path -match '(^|/)\.\.?(/|$)|:' -or
        $item.sha256 -notmatch '^[0-9a-f]{64}$' -or
        !$seen.Add($item.path)) { throw "Unsafe or duplicate archive entry: $($item.path)" }
    $path = Get-FpgaSafePath $archive $item.path
    if (!(Test-Path -LiteralPath $path -PathType Leaf) -or
        ((Get-Item -LiteralPath $path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Archive entry is missing or linked: $($item.path)"
    }
    $size = (Get-Item -LiteralPath $path).Length
    if ($size -ne $item.bytes -or $size -gt 2147483648 -or
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $item.sha256) {
        throw "Archive entry differs: $($item.path)"
    }
    $bytes += $size
}
if ($bytes -gt 8589934592 -or
    ($null -ne $manifest.total_bytes -and $manifest.total_bytes -ne $bytes)) {
    throw 'Archive byte count differs or exceeds bound'
}
$entries = @(Get-ChildItem -LiteralPath $archive -Recurse -Force)
if (@($entries | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
    throw 'Archive contains a linked file or directory'
}
$actual = @($entries | Where-Object { !$_.PSIsContainer } | ForEach-Object {
    $_.FullName.Substring($archive.Length + 1).Replace('\','/')
})
if ($actual.Count -ne ($files.Count + 1) -or
    @($actual | Where-Object { $_ -ne 'archive_manifest.json' -and !$seen.Contains($_) }).Count) {
    throw 'Archive contains unlisted files'
}
$snapshotRelative = 'pds/input-snapshots/' + $manifest.run_id + '/snapshot.json'
if (!$seen.Contains($snapshotRelative) -or
    (Get-FileHash -LiteralPath (Get-FpgaSafePath $archive $snapshotRelative) -Algorithm SHA256).Hash.ToLowerInvariant() -cne
        $manifest.snapshot_sha256) {
    throw 'Archived input snapshot differs from manifest'
}
if ($manifest.divisor -ne 18 -or $manifest.candidate_inputs_path) {
    $candidateRelative = Get-SocCandidateEvidenceRelative $manifest.divisor $manifest.candidate_inputs_path
    if (!$seen.Contains($candidateRelative) -or
        $manifest.candidate_inputs_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
        (Get-FileHash -LiteralPath (Get-FpgaSafePath $archive $candidateRelative) -Algorithm SHA256).Hash.ToLowerInvariant() -cne
            $manifest.candidate_inputs_sha256) {
        throw 'Candidate archive lacks its generated input digest'
    }
    $candidate = [IO.File]::ReadAllText((Get-FpgaSafePath $archive $candidateRelative)) | ConvertFrom-Json
    $snapshot = [IO.File]::ReadAllText((Get-FpgaSafePath $archive $snapshotRelative)) | ConvertFrom-Json
    $clockPath = "pds/input-snapshots/$($manifest.run_id)/files/config/clocks.json"
    if (!$seen.Contains($clockPath)) { throw 'Candidate archive lacks frozen clock configuration' }
    $clock = [IO.File]::ReadAllText((Get-FpgaSafePath $archive $clockPath)) | ConvertFrom-Json
    if ($candidate.schema -ne 1 -or $candidate.kind -cne 'soc-cpu-clock-candidate-inputs' -or
        $candidate.cpu_divisor -ne $manifest.divisor -or $clock.cpu_divisor -ne $manifest.divisor -or
        $candidate.cpu_hz -ne $clock.cpu_hz -or
        $candidate.sys_hz -ne $clock.sys_hz -or $candidate.timebase_hz -ne $clock.timebase_hz) {
        throw 'Candidate archive record differs from frozen clock configuration'
    }
    $candidateHashes = ConvertTo-FpgaMap $candidate.inputs
    $frozenHashes = ConvertTo-FpgaMap $snapshot.inputs
    if ($candidateHashes.Count -lt 8) { throw 'Candidate archive record is incomplete' }
    foreach ($entry in $candidateHashes.GetEnumerator()) {
        if (!$seen.Contains($entry.Key) -or
            (Get-FileHash -LiteralPath (Get-FpgaSafePath $archive $entry.Key) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value -or
            ($frozenHashes.Contains($entry.Key) -and $frozenHashes[$entry.Key] -cne $entry.Value)) {
            throw "Candidate mirror differs from its record or frozen snapshot: $($entry.Key)"
        }
    }
}
if ($manifest.status -eq 'PASS') {
    foreach ($required in @('artifacts/build_evidence.json','artifacts/build_snapshot.json',
            'artifacts/preflight_gate.json','artifacts/cpu_sys_cdc_ads_pre.json',
            'artifacts/cpu_sys_cdc_ads.json','artifacts/pds_post_map_constraints.txt',
            'pds/device_map/soc_top.dmr',
            ('pds/input-snapshots/' + $manifest.run_id + '/post.soc_top.dmr'),
            'artifacts/soc_top.sbit','artifacts/soc_top.bin','artifacts/timing_summary.txt')) {
        if (!$seen.Contains($required)) { throw "PASS archive lacks $required" }
    }
    $evidence = [IO.File]::ReadAllText((Get-FpgaSafePath $archive 'artifacts/build_evidence.json')) | ConvertFrom-Json
    if ($evidence.run_id -cne $manifest.run_id -or $evidence.schema -ne 3 -or
        $evidence.input_snapshot_sha256 -cne
            (Get-FileHash -LiteralPath (Get-FpgaSafePath $archive 'artifacts/build_snapshot.json') -Algorithm SHA256).Hash.ToLowerInvariant()) {
        throw 'PASS archive build evidence does not bind its snapshot'
    }
}
Write-Output "FREQUENCY_ARCHIVE_VERIFY_PASS status=$($manifest.status) run=$($manifest.run_id) files=$($files.Count) bytes=$bytes"
