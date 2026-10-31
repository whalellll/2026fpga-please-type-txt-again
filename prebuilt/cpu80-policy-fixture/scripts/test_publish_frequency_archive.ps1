param([string]$ReportPath = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$temp = Join-Path ([IO.Path]::GetPathRoot($root)) ('socpub_' + [guid]::NewGuid().ToString('N').Substring(0,8))
$checks = [Collections.Generic.List[string]]::new()
function Write-TestFile([string]$Path, [string]$Text) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $Path) -Force | Out-Null
    [IO.File]::WriteAllText($Path, $Text, [Text.UTF8Encoding]::new($false))
}
function New-ArchiveFixture([string]$Name, [string]$Version, [int]$Divisor, [bool]$Unique, [bool]$Declare) {
    $archive = Join-Path $temp $Name
    $run = [guid]::NewGuid().ToString('N')
    $frozen = "pds/input-snapshots/$run/"
    $record = if ($Unique) { "docs/validation/frequency-search/candidates/V$Version/div$Divisor-20261008T160000Z-$([guid]::NewGuid().ToString('N')).inputs.json" }
              else { "docs/validation/frequency-search/divisor-$Divisor.inputs.json" }
    $clock = [ordered]@{schema=1; input_hz=27000000; pll_vco_hz=891000000; cpu_divisor=$Divisor;
        cpu_hz=[int][Math]::Floor(891000000.0/$Divisor+0.5); sys_hz=49500000; timebase_hz=49500000; integer_hz_rounding='nearest_half_up'}
    $inputs = [ordered]@{}
    foreach ($relative in @('config/clocks.json','rtl/video/pll_video.v','rtl/soc/soc_top.v','pds/soc.fdc',
            'sw/bootloader/soc.h','linux/soc.dts','linux/boot/soc.dtb','scripts/fixture-only.txt')) {
        $body = if ($relative -eq 'config/clocks.json') { $clock | ConvertTo-Json } else { "SYNTHETIC TEST ONLY: $relative" }
        $path = Join-Path $archive $relative
        Write-TestFile $path $body
        Write-TestFile (Join-Path $archive ($frozen+'files/'+$relative)) $body
        $inputs[$relative] = (Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()
    }
    $snapshot = [ordered]@{schema=1; run_id=$run; release="V$Version"; inputs=$inputs; staged_hashes=@{}}
    $snapshotText = $snapshot | ConvertTo-Json -Depth 5
    Write-TestFile (Join-Path $archive ($frozen+'snapshot.json')) $snapshotText
    Write-TestFile (Join-Path $archive 'pds/build_snapshot.json') $snapshotText
    $candidate = [ordered]@{schema=1; kind='soc-cpu-clock-candidate-inputs'; cpu_divisor=$Divisor;
        cpu_hz=$clock.cpu_hz; sys_hz=49500000; timebase_hz=49500000; inputs=$inputs}
    Write-TestFile (Join-Path $archive $record) ($candidate | ConvertTo-Json -Depth 5)
    $files = @(Get-ChildItem -LiteralPath $archive -Recurse -File | ForEach-Object {
        [pscustomobject][ordered]@{path=$_.FullName.Substring($archive.Length+1).Replace('\','/'); bytes=$_.Length;
            sha256=(Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant()}
    })
    $manifest = [ordered]@{schema=1; status='FAIL'; divisor=$Divisor; run_id=$run;
        failure_reason='SYNTHETIC FIXTURE ONLY - no hardware run'; project_root=$archive; source_git_head=('0'*40);
        snapshot_sha256=(Get-FileHash -LiteralPath (Join-Path $archive ($frozen+'snapshot.json'))).Hash.ToLowerInvariant();
        candidate_inputs_sha256=(Get-FileHash -LiteralPath (Join-Path $archive $record)).Hash.ToLowerInvariant();
        file_count=$files.Count; total_bytes=[int64](($files | Measure-Object bytes -Sum).Sum); files=$files}
    if ($Declare) { $manifest.candidate_inputs_path=$record }
    Write-TestFile (Join-Path $archive 'archive_manifest.json') ($manifest | ConvertTo-Json -Depth 7)
    return [pscustomobject]@{path=$archive; run=$run; divisor=$Divisor; record=$record; manifest=$manifest}
}
function Publish-TestFixture($Fixture) {
    & (Join-Path $PSScriptRoot 'publish_frequency_archive.ps1') -ArchiveDirectory $Fixture.path -ProjectRoot $project | Out-Null
    $published = Join-Path $project "docs/validation/frequency-search/div$($Fixture.divisor)-FAIL-$($Fixture.run)"
    $portable = Get-Content -LiteralPath (Join-Path $published 'portable_manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if (@($portable.files | Where-Object {$_.source_path -ceq $Fixture.record}).Count -ne 1 -or
        (Get-FileHash -LiteralPath (Join-Path $published ('raw/'+$Fixture.record))).Hash -cne
        (Get-FileHash -LiteralPath (Join-Path $Fixture.path $Fixture.record)).Hash) { throw 'Publication lost or changed candidate bytes' }
    return $published
}
function Reject-TestFixture([string]$Name, $Fixture, [string]$Message) {
    try { & (Join-Path $PSScriptRoot 'publish_frequency_archive.ps1') -ArchiveDirectory $Fixture.path -ProjectRoot $project -DryRun | Out-Null }
    catch { if ($_.Exception.Message -notlike $Message) { throw "Unexpected ${Name}: $($_.Exception.Message)" }; $checks.Add($Name); return }
    throw "Unsafe publication accepted: $Name"
}
try {
    $project = Join-Path $temp 'project'
    foreach ($directory in @('scripts','docs/validation/frequency-search')) { New-Item -ItemType Directory -Path (Join-Path $project $directory) -Force | Out-Null }
    foreach ($name in @('verify_frequency_archive.ps1','verify_frequency_portable.ps1','build_snapshot.ps1','clock_policy.ps1','timing_scope.ps1')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $project ('scripts/'+$name))
    }
    foreach ($divisor in @(14,15,18)) {
        $fixture = New-ArchiveFixture "unique-$divisor" '6.5' $divisor $true $true
        $null = Publish-TestFixture $fixture
        if (Test-Path -LiteralPath (Join-Path $fixture.path "docs/validation/frequency-search/divisor-$divisor.inputs.json")) { throw 'Unique test accidentally depends on a legacy alias' }
        $checks.Add("v65_unique_div${divisor}_published_without_legacy_alias")
    }
    $legacy = New-ArchiveFixture 'legacy' '6.1' 15 $false $false
    $null = Publish-TestFixture $legacy
    $checks.Add('v61_implicit_legacy_path_preserved')
    Reject-TestFixture 'v65_missing_explicit_path_rejected' (New-ArchiveFixture 'no-path' '6.5' 15 $false $false) '*V6.5 portable publication requires an explicit*'
    $wrong = New-ArchiveFixture 'wrong-divisor' '6.5' 15 $true $true
    $wrong.manifest.candidate_inputs_path = $wrong.record.Replace('/div15-','/div14-')
    Write-TestFile (Join-Path $wrong.path 'archive_manifest.json') ($wrong.manifest | ConvertTo-Json -Depth 7)
    Reject-TestFixture 'foreign_divisor_path_rejected' $wrong '*Invalid or mismatched clock candidate evidence path*'
    $missing = New-ArchiveFixture 'missing-record' '6.5' 15 $true $true
    $missing.manifest.candidate_inputs_path = $missing.record.Replace('20261008T160000Z','20261008T170000Z')
    Write-TestFile (Join-Path $missing.path 'archive_manifest.json') ($missing.manifest | ConvertTo-Json -Depth 7)
    Reject-TestFixture 'missing_declared_record_no_fallback' $missing '*Candidate archive lacks its generated input digest*'
    foreach ($name in @('div15-PASS-6e934e9f84094159bff9a8870e260e8e','div14-FAIL-3da054406b68431b8996ce50ac70c2f7')) {
        & (Join-Path $PSScriptRoot 'verify_frequency_portable.ps1') -PortableDirectory (Join-Path $root ('docs/validation/frequency-search/'+$name)) | Out-Null
        $checks.Add("real_historical_portable_${name}_verified")
    }
    $result = [ordered]@{schema=1; status='PASS'; kind='publication-fixtures-and-real-historical-portable-verification'; checks=@($checks);
        limitation='Original full historical soc_freq_evidence directories are absent; their preserved portable raw bytes were verified, not fabricated into complete native archives.'}
    if ($ReportPath) { Write-TestFile ([IO.Path]::GetFullPath($ReportPath)) ($result | ConvertTo-Json -Depth 5) }
    Write-Output "FREQUENCY_PUBLICATION_TEST_PASS checks=$($checks.Count)"
} finally {
    $resolved=[IO.Path]::GetFullPath($temp)
    $base=[IO.Path]::GetPathRoot($root)
    if (!$resolved.StartsWith($base+'socpub_',[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe publication fixture cleanup' }
    if (Test-Path -LiteralPath $resolved) {
        $nodes = @(Get-Item -LiteralPath $resolved -Force) + @(Get-ChildItem -LiteralPath $resolved -Recurse -Force)
        if (@($nodes | Where-Object {$_.Attributes -band [IO.FileAttributes]::ReparsePoint}).Count) { throw 'Linked publication fixture' }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
