param(
    [Parameter(Mandatory=$true)][string]$ArchiveDirectory,
    [Parameter(Mandatory=$true)][string]$ProjectRoot,
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$archive = [IO.Path]::GetFullPath($ArchiveDirectory).TrimEnd('\')
$project = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')
$verifier = Join-Path $project 'scripts/verify_frequency_archive.ps1'
if (!(Test-Path -LiteralPath $verifier -PathType Leaf)) { throw "Missing archive verifier: $verifier" }
& $verifier -ArchiveDirectory $archive | Out-Host
$manifestFile = Join-Path $archive 'archive_manifest.json'
$manifest = [IO.File]::ReadAllText($manifestFile) | ConvertFrom-Json
$sourceCount = if ($null -ne $manifest.file_count) { [int]$manifest.file_count } else { @($manifest.files).Count }
$sourceBytes = if ($null -ne $manifest.total_bytes) { [int64]$manifest.total_bytes } else {
    [int64](@($manifest.files | Measure-Object bytes -Sum)[0].Sum)
}
$runId = [string]$manifest.run_id
$stem = 'div{0}-{1}-{2}' -f $manifest.divisor,$manifest.status,$runId
$outputRoot = Join-Path $project 'docs/validation/frequency-search'
$destination = [IO.Path]::GetFullPath((Join-Path $outputRoot $stem))
if (!$destination.StartsWith([IO.Path]::GetFullPath($outputRoot).TrimEnd('\') + '\',
        [StringComparison]::OrdinalIgnoreCase) -or
    (!$DryRun -and (Test-Path -LiteralPath $destination))) {
    throw "Unsafe or existing portable evidence directory: $destination"
}
foreach ($parent in @($project, (Join-Path $project 'docs'),
        (Join-Path $project 'docs/validation'), $outputRoot)) {
    if (!(Test-Path -LiteralPath $parent -PathType Container) -or
        ((Get-Item -LiteralPath $parent -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Missing or linked portable evidence parent: $parent"
    }
}
$frozen = "pds/input-snapshots/$runId/"
$candidateInputPath = $null
$candidateMirrorPaths = @()
if ($manifest.divisor -ne 18 -or $manifest.candidate_inputs_path) {
    . (Join-Path $PSScriptRoot 'clock_policy.ps1')
    $snapshot = [IO.File]::ReadAllText((Join-Path $archive ($frozen + 'snapshot.json'))) | ConvertFrom-Json
    if ([version]$snapshot.release.TrimStart('V','v') -ge [version]'6.5' -and
        [string]::IsNullOrWhiteSpace([string]$manifest.candidate_inputs_path)) {
        throw 'V6.5 portable publication requires an explicit candidate_inputs_path; legacy fallback is historical only'
    }
    $candidateInputPath = Get-SocCandidateEvidenceRelative $manifest.divisor $manifest.candidate_inputs_path
    $candidateRecord = [IO.File]::ReadAllText((Join-Path $archive $candidateInputPath)) | ConvertFrom-Json
    $candidateMirrorPaths = @($candidateRecord.inputs.PSObject.Properties | ForEach-Object { $_.Name })
}
$clockInputs = @(
    'config/clocks.json', 'rtl/video/pll_video.v', 'rtl/soc/soc_top.v',
    'pds/soc.fdc', 'pds/soc.tcl', 'pds/soc_post_synth.tcl',
    'sw/bootloader/soc.h', 'linux/soc.dts', 'linux/boot/soc.dtb',
    'artifacts/bootloader.build.json', 'artifacts/mac_selftest.build.json',
    'artifacts/mac_benchmark.build.json',
    'artifacts/xiangqi_sparse_eval_selftest.build.json',
    'artifacts/xiangqi_fb_demo.build.json'
)
$selected = @($manifest.files | Where-Object {
    $path = [string]$_.path
    $path -eq 'pds/build_snapshot.json' -or
    ($candidateInputPath -and $path -eq $candidateInputPath) -or
    $path -cin $candidateMirrorPaths -or
    $path -eq $frozen + 'snapshot.json' -or
    ($path.StartsWith($frozen, [StringComparison]::Ordinal) -and
        $path.Substring($frozen.Length) -notmatch '/' -and
        $path -match '\.(?:json|log|tcl|pds|ccr|snr|dmr|rtr|txt)$') -or
    ($path.StartsWith($frozen + 'files/', [StringComparison]::Ordinal) -and
        $path.Substring(($frozen + 'files/').Length) -cin $clockInputs) -or
    $path -match '^pds/(?:synthesize/[^/]+\.(?:snr|vm)|constraint_check/[^/]+\.ccr|device_map/[^/]+\.(?:dmr|prt)|place_route/[^/]+\.(?:prt|txt)|report_timing/[^/]+\.rtr)$' -or
    $path -match '^pds/(?:flow\.log|impl\.tcl|soc(?:_pre_synth)?\.pds)$' -or
    $path -match '^artifacts/(?:build_snapshot|build_evidence|preflight_gate|cpu_ads_controls|icache_pad_ads|cpu_sys_cdc_ads(?:_pre)?|timing_summary)\.(?:json|txt)$' -or
    $path -match '^artifacts/(?:pds_.*|synth_resource_report|final_timing_report|SHA256SUMS)\.txt$' -or
    $path -eq 'artifacts/final_timing_xml.xml'
} | Sort-Object path)
if ($selected.Count -lt 3 -or !($selected.path -contains 'pds/build_snapshot.json') -or
    !($selected.path -contains ($frozen + 'snapshot.json'))) {
    throw 'Portable selection lacks frozen run identity'
}
$selectedBytes = [int64](@($selected | Measure-Object bytes -Sum)[0].Sum)
if ($selected.Count -gt 500 -or $selectedBytes -gt 1073741824) {
    throw 'Portable selection exceeds its count or byte bound'
}
if ($manifest.status -ceq 'PASS') {
    foreach ($pair in @(
        @('artifacts/final_timing_report.txt','pds/report_timing/soc_top.rtr'),
        @('artifacts/final_timing_xml.xml','pds/report_timing/rtr.db')
    )) {
        $copy = @($manifest.files | Where-Object { $_.path -ceq $pair[0] })
        $native = @($manifest.files | Where-Object { $_.path -ceq $pair[1] })
        if ($copy.Count -ne 1 -or $native.Count -ne 1 -or
            !($selected.path -contains $pair[0]) -or
            $copy[0].sha256 -cne $native[0].sha256 -or
            $copy[0].bytes -ne $native[0].bytes) {
            throw "PASS source archive lacks a byte-identical native timing report: $($pair[0])"
        }
    }
}
$records = [Collections.Generic.List[object]]::new()
foreach ($item in $selected) {
    $relative = [string]$item.path
    $published = if ($relative.EndsWith('.log', [StringComparison]::OrdinalIgnoreCase)) {
        'raw/' + $relative + '.txt'
    } else { 'raw/' + $relative }
    $sourceFile = Join-Path $archive $relative
    if (!(Test-Path -LiteralPath $sourceFile -PathType Leaf) -or
        (Get-Item -LiteralPath $sourceFile).Length -ne [int64]$item.bytes -or
        (Get-FileHash -LiteralPath $sourceFile -Algorithm SHA256).Hash.ToLowerInvariant() -cne [string]$item.sha256) {
        throw "Source archive report differs from manifest: $relative"
    }
    $records.Add([pscustomobject][ordered]@{
        source_path=$relative; published_path=$published; bytes=[int64]$item.bytes;
        sha256=[string]$item.sha256
    })
}
$omittedDatabases = @($manifest.files | Where-Object { $_.path -match '\.(?:adf|db|pvf)$' } |
    ForEach-Object { [pscustomobject][ordered]@{path=$_.path; bytes=[int64]$_.bytes; sha256=$_.sha256} })
$failedBitstreams = @($manifest.files | Where-Object {
    $manifest.status -eq 'FAIL' -and $_.path -match '^pds/generate_bitstream/soc_top\.(?:sbit|bin)$'
} | ForEach-Object { [pscustomobject][ordered]@{path=$_.path; bytes=[int64]$_.bytes; sha256=$_.sha256} })
$portable = [pscustomobject][ordered]@{
    schema=1; status=[string]$manifest.status; divisor=[int]$manifest.divisor;
    failure_reason=[string]$manifest.failure_reason;
    run_id=$runId; source_git_head=[string]$manifest.source_git_head;
    source_project_root=[string]$manifest.project_root;
    source_archive_directory=$archive;
    source_archive_manifest_sha256=(Get-FileHash -LiteralPath $manifestFile -Algorithm SHA256).Hash.ToLowerInvariant();
    snapshot_sha256=[string]$manifest.snapshot_sha256;
    candidate_inputs_sha256=[string]$manifest.candidate_inputs_sha256;
    candidate_inputs_path=[string]$manifest.candidate_inputs_path;
    source_archive_file_count=$sourceCount;
    source_archive_total_bytes=$sourceBytes;
    note='The full source archive was verified separately; this delivery subset preserves raw report bytes. .log files are published with .txt suffix. A PASS run includes the byte-identical native Max Skew XML copy as artifacts/final_timing_xml.xml. Native databases and failed-run bitstreams remain in the full archive and are bound by SHA-256.';
    files=@($records.ToArray()); omitted_databases=$omittedDatabases;
    omitted_failed_bitstreams=$failedBitstreams
}
if ($DryRun) {
    Write-Output "FREQUENCY_PORTABLE_DRY_RUN destination=$destination files=$($records.Count) bytes=$(($records | Measure-Object bytes -Sum).Sum)"
    return
}
New-Item -ItemType Directory -Path $destination -Force | Out-Null
foreach ($item in $records) {
    $target = Join-Path $destination $item.published_path
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $archive $item.source_path) -Destination $target
    if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -cne $item.sha256) {
        throw "Published raw report hash mismatch: $($item.published_path)"
    }
}
Copy-Item -LiteralPath $manifestFile -Destination (Join-Path $destination 'archive_manifest.json')
$portablePath = Join-Path $destination 'portable_manifest.json'
[IO.File]::WriteAllText($portablePath, ($portable | ConvertTo-Json -Depth 10) + "`n",
    [Text.UTF8Encoding]::new($false))
& (Join-Path $PSScriptRoot 'verify_frequency_portable.ps1') -PortableDirectory $destination | Out-Host
Write-Output "FREQUENCY_PORTABLE_PASS destination=$destination files=$($records.Count) manifest_sha256=$((Get-FileHash -LiteralPath $portablePath -Algorithm SHA256).Hash.ToLowerInvariant())"
