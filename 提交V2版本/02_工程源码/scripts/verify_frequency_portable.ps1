param([Parameter(Mandatory=$true)][string]$PortableDirectory)
$ErrorActionPreference = 'Stop'
$directory = [IO.Path]::GetFullPath($PortableDirectory).TrimEnd('\')
if (!(Test-Path -LiteralPath $directory -PathType Container) -or
    ((Get-Item -LiteralPath $directory -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw "Missing or linked portable evidence directory: $directory"
}
$portablePath = Join-Path $directory 'portable_manifest.json'
$sourceManifestPath = Join-Path $directory 'archive_manifest.json'
foreach ($path in @($portablePath, $sourceManifestPath)) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing portable manifest: $path" }
}
$portable = [IO.File]::ReadAllText($portablePath) | ConvertFrom-Json
$source = [IO.File]::ReadAllText($sourceManifestPath) | ConvertFrom-Json
$sourceCount = if ($null -ne $source.file_count) { [int]$source.file_count } else { @($source.files).Count }
$sourceBytes = if ($null -ne $source.total_bytes) { [int64]$source.total_bytes } else {
    [int64](@($source.files | Measure-Object bytes -Sum)[0].Sum)
}
if ($sourceCount -ne @($source.files).Count -or
    $sourceBytes -ne [int64](@($source.files | Measure-Object bytes -Sum)[0].Sum)) {
    throw 'Full source archive manifest count or bytes are inconsistent'
}
if ($portable.schema -ne 1 -or $source.schema -ne 1 -or
    $portable.divisor -notin @(18,17,16,15,14,13,12) -or
    $portable.status -notin @('PASS','FAIL') -or
    $portable.status -cne $source.status -or $portable.divisor -ne $source.divisor -or
    $portable.run_id -cne $source.run_id -or
    $portable.source_git_head -cne $source.source_git_head -or
    $portable.snapshot_sha256 -cne $source.snapshot_sha256 -or
    ([string]$portable.candidate_inputs_sha256) -cne ([string]$source.candidate_inputs_sha256) -or
    $portable.failure_reason -cne $source.failure_reason -or
    $portable.source_archive_file_count -ne $sourceCount -or
    $portable.source_archive_total_bytes -ne $sourceBytes -or
    $portable.source_archive_manifest_sha256 -cne
        (Get-FileHash -LiteralPath $sourceManifestPath -Algorithm SHA256).Hash.ToLowerInvariant()) {
    throw 'Portable manifest is not bound to the full source archive manifest'
}
function Assert-Relative([string]$Value) {
    if ($Value -notmatch '^[^\\/:]+(?:/[^\\/:]+)*$' -or
        $Value -match '(^|/)\.\.?(/|$)') { throw "Unsafe portable path: $Value" }
}
$sourceMap = [Collections.Generic.Dictionary[string,object]]::new([StringComparer]::Ordinal)
foreach ($item in $source.files) {
    Assert-Relative ([string]$item.path)
    if ($sourceMap.ContainsKey([string]$item.path)) {
        throw "Duplicate source archive entry: $($item.path)"
    }
    $sourceMap.Add([string]$item.path, $item)
}
$seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$wanted = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$null = $wanted.Add('portable_manifest.json')
$null = $wanted.Add('archive_manifest.json')
$count = 0
$bytes = [int64]0
foreach ($item in $portable.files) {
    $sourcePath = [string]$item.source_path
    $published = [string]$item.published_path
    Assert-Relative $sourcePath
    Assert-Relative $published
    $expected = if ($sourcePath.EndsWith('.log', [StringComparison]::OrdinalIgnoreCase)) {
        'raw/' + $sourcePath + '.txt'
    } else { 'raw/' + $sourcePath }
    if ($published -cne $expected -or !$seen.Add($sourcePath) -or
        !$wanted.Add($published) -or !$sourceMap.ContainsKey($sourcePath)) {
        throw "Invalid or duplicate portable entry: $published"
    }
    $original = $sourceMap[$sourcePath]
    if ($item.sha256 -cnotmatch '^[0-9a-f]{64}$' -or
        $item.sha256 -cne $original.sha256 -or $item.bytes -ne $original.bytes) {
        throw "Portable entry disagrees with source archive manifest: $sourcePath"
    }
    $path = Join-Path $directory $published
    if (!(Test-Path -LiteralPath $path -PathType Leaf) -or
        ((Get-Item -LiteralPath $path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        (Get-Item -LiteralPath $path).Length -ne [int64]$item.bytes -or
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne [string]$item.sha256) {
        throw "Portable entry bytes differ: $published"
    }
    $count++
    $bytes += [int64]$item.bytes
}
if ($count -lt 3 -or $count -gt 500 -or $bytes -gt 1073741824 -or
    !$seen.Contains('pds/build_snapshot.json') -or
    !$seen.Contains("pds/input-snapshots/$($portable.run_id)/snapshot.json")) {
    throw 'Portable evidence lacks frozen identity or exceeds its bounds'
}
if ($portable.status -ceq 'PASS') {
    foreach ($pair in @(
        @('artifacts/final_timing_report.txt','pds/report_timing/soc_top.rtr'),
        @('artifacts/final_timing_xml.xml','pds/report_timing/rtr.db')
    )) {
        $publishedCopy = [string]$pair[0]
        $native = [string]$pair[1]
        if (!$seen.Contains($publishedCopy) -or !$sourceMap.ContainsKey($native) -or
            $sourceMap[$publishedCopy].sha256 -cne $sourceMap[$native].sha256 -or
            $sourceMap[$publishedCopy].bytes -ne $sourceMap[$native].bytes) {
            throw "Portable PASS evidence lacks a byte-identical native timing report: $publishedCopy"
        }
    }
}
if ($portable.divisor -ne 18 -or $portable.candidate_inputs_path) {
    . (Join-Path $PSScriptRoot 'clock_policy.ps1')
    if ([string]$portable.candidate_inputs_path -cne [string]$source.candidate_inputs_path) { throw 'Portable candidate path differs from source manifest' }
    $candidatePath = Get-SocCandidateEvidenceRelative $portable.divisor $portable.candidate_inputs_path
    if ($portable.candidate_inputs_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
        !$seen.Contains($candidatePath) -or
        $sourceMap[$candidatePath].sha256 -cne $portable.candidate_inputs_sha256) {
        throw 'Portable evidence lacks its generated candidate input digest'
    }
    $candidate = [IO.File]::ReadAllText((Join-Path $directory ('raw/' + $candidatePath))) | ConvertFrom-Json
    $snapshotPath = "pds/input-snapshots/$($portable.run_id)/snapshot.json"
    $clockPath = "pds/input-snapshots/$($portable.run_id)/files/config/clocks.json"
    if (!$seen.Contains($clockPath)) { throw 'Portable evidence lacks frozen clock configuration' }
    $snapshot = [IO.File]::ReadAllText((Join-Path $directory ('raw/' + $snapshotPath))) | ConvertFrom-Json
    $clock = [IO.File]::ReadAllText((Join-Path $directory ('raw/' + $clockPath))) | ConvertFrom-Json
    if ($candidate.schema -ne 1 -or $candidate.kind -cne 'soc-cpu-clock-candidate-inputs' -or
        $candidate.cpu_divisor -ne $portable.divisor -or $clock.cpu_divisor -ne $portable.divisor -or
        $candidate.cpu_hz -ne $clock.cpu_hz -or
        $candidate.sys_hz -ne $clock.sys_hz -or $candidate.timebase_hz -ne $clock.timebase_hz) {
        throw 'Portable candidate record differs from frozen clock configuration'
    }
    $candidateFields = @($candidate.inputs.PSObject.Properties)
    if ($candidateFields.Count -lt 8) { throw 'Portable candidate input record is incomplete' }
    foreach ($field in $candidateFields) {
        $path = [string]$field.Name
        if (!$seen.Contains($path) -or !$sourceMap.ContainsKey($path) -or
            $sourceMap[$path].sha256 -cne $field.Value -or
            ($null -ne $snapshot.inputs.PSObject.Properties[$path] -and
             $snapshot.inputs.PSObject.Properties[$path].Value -cne $field.Value)) {
            throw "Portable candidate mirror differs from record or snapshot: $path"
        }
    }
}
$omitted = @($source.files | Where-Object { $_.path -match '\.(?:adf|db|pvf)$' })
if ($portable.omitted_databases.Count -ne $omitted.Count) {
    throw 'Omitted database list differs from full source archive'
}
$omittedMap = [Collections.Generic.Dictionary[string,object]]::new([StringComparer]::Ordinal)
foreach ($item in $omitted) { $omittedMap.Add([string]$item.path, $item) }
$seenOmitted = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
foreach ($item in $portable.omitted_databases) {
    if (!$seenOmitted.Add([string]$item.path) -or
        !$omittedMap.ContainsKey([string]$item.path) -or
        $item.sha256 -cne $omittedMap[[string]$item.path].sha256 -or
        $item.bytes -ne $omittedMap[[string]$item.path].bytes) {
        throw "Omitted database record differs: $($item.path)"
    }
}
$failedNativeBitstreams = @($source.files | Where-Object {
    $source.status -eq 'FAIL' -and $_.path -match '^pds/generate_bitstream/soc_top\.(?:sbit|bin)$'
})
$listedFailedBitstreams = @($portable.omitted_failed_bitstreams | Where-Object { $null -ne $_ })
if ($listedFailedBitstreams.Count -ne $failedNativeBitstreams.Count) {
    throw 'Failed native bitstream exclusion list differs from full archive'
}
$failedMap = [Collections.Generic.Dictionary[string,object]]::new([StringComparer]::Ordinal)
foreach ($item in $failedNativeBitstreams) { $failedMap.Add([string]$item.path, $item) }
$seenFailed = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
foreach ($item in $listedFailedBitstreams) {
    if (!$seenFailed.Add([string]$item.path) -or !$failedMap.ContainsKey([string]$item.path) -or
        $seen.Contains([string]$item.path) -or
        $item.sha256 -cne $failedMap[[string]$item.path].sha256 -or
        $item.bytes -ne $failedMap[[string]$item.path].bytes) {
        throw "Failed native bitstream record differs: $($item.path)"
    }
}
$nodes = @(Get-ChildItem -LiteralPath $directory -Recurse -Force)
if (@($nodes | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
    throw 'Portable evidence contains a linked file or directory'
}
$actual = @($nodes | Where-Object { !$_.PSIsContainer } | ForEach-Object {
    $_.FullName.Substring($directory.Length + 1).Replace('\','/')
})
if ($actual.Count -ne $wanted.Count -or
    @($actual | Where-Object { !$wanted.Contains($_) }).Count) {
    throw 'Portable evidence contains missing or unlisted files'
}
Write-Output "FREQUENCY_PORTABLE_VERIFY_PASS status=$($portable.status) run=$($portable.run_id) files=$count bytes=$bytes"
