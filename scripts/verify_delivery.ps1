param(
    [string]$ZipPath,
    [string]$IcarusBin = 'D:\LJL\WORK\iverilog\bin',
    [string]$MsysRoot = 'D:\LJL\WORK\msys64',
    [string]$ToolchainBin = '',
    [string]$PythonPath = 'D:\LJL\WORK\Anaconda3\python.exe',
    [string]$HostGccPath = 'D:\LJL\WORK\msys64\mingw64\bin\gcc.exe',
    [switch]$SoftwareOnly,
    [ValidateSet('Production','ShortPilot','BoardRelease')][string]$CoremarkEvidenceMode = 'Production',
    [string]$ReleaseManifest,
    [string]$CompletionReceipt = ''
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$version = ([IO.File]::ReadAllText((Join-Path $root 'VERSION'))).Trim()
if ($version -ceq '6.5' -and
    ($CoremarkEvidenceMode -cne 'BoardRelease' -or [string]::IsNullOrWhiteSpace($ReleaseManifest))) {
    throw 'SOC_V6_5_REQUIRES_BOARD_RELEASE: V6.5 formal delivery requires BoardRelease and an explicit -ReleaseManifest; incomplete candidates use create_candidate_delivery.ps1.'
}
if ($version -ceq '2.1' -and
    ($CoremarkEvidenceMode -cne 'BoardRelease' -or [string]::IsNullOrWhiteSpace($ReleaseManifest))) {
    throw 'SOC_V2_1_REQUIRES_BOARD_RELEASE: V2.1 formal delivery requires board-only CoreMark evidence and an explicit -ReleaseManifest.'
}
. (Join-Path $PSScriptRoot 'riscv_toolchain.ps1')
$cpuOriginalPath = $env:PATH
try {
$ToolchainBin = (Get-CpuToolchain -ToolchainBin $ToolchainBin).Bin
if (!$ZipPath) { $ZipPath = Join-Path (Split-Path -Parent $root) "SOC_linux_V$version.zip" }
$ZipPath = [IO.Path]::GetFullPath($ZipPath)
if (!(Test-Path -LiteralPath $ZipPath -PathType Leaf)) { throw "Missing archive: $ZipPath" }
$verifiedArchiveSha256 = (Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
if (!$CompletionReceipt) { $CompletionReceipt = $ZipPath + '.verified.json' }
$CompletionReceipt = [IO.Path]::GetFullPath($CompletionReceipt)
if ($CompletionReceipt -ieq $ZipPath) { throw 'Completion receipt cannot overwrite the archive' }
# Invalidate any older success for this receipt before starting a new attempt.
# Failure or interruption leaves this non-success state; cleanup must refuse it.
$pendingCompletion = [ordered]@{
    schema=1;status='INCOMPLETE_OR_RUNNING';started_utc=[DateTime]::UtcNow.ToString('o')
    zip_path=$ZipPath;zip_sha256=$verifiedArchiveSha256
}
[IO.File]::WriteAllText($CompletionReceipt, ($pendingCompletion | ConvertTo-Json) + "`n", [Text.UTF8Encoding]::new($false))
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::OpenRead($ZipPath)
try {
    foreach ($entry in $archive.Entries) {
        if (!$entry.FullName.StartsWith('SOC/') -or $entry.FullName.Contains('..') -or
            $entry.FullName.Contains('\') -or
            $entry.FullName -match '(^|/)(logbackup|__pycache__|debug|\.git)(/|$)|\.(log|db|adf|pvf|o|part|vvp|pyc|lock)$|(^|/)CMOS2_.*\.(png|json)$|(^|/)(IMG|JSN)[0-9]{5}\.(png|json|tmp)$' -or
            ($entry.FullName -match '\.elf$' -and $entry.FullName -notin @(
                'SOC/artifacts/bootloader.elf','SOC/artifacts/mac_selftest.elf',
                'SOC/artifacts/mac_benchmark.elf',
                'SOC/artifacts/xiangqi_sparse_eval_selftest.elf',
                'SOC/artifacts/xiangqi_fb_demo.elf'))) {
            throw "Unsafe or generated archive entry: $($entry.FullName)"
        }
    }
} finally { $archive.Dispose() }
$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
$tempRoot = [IO.Path]::GetFullPath((Join-Path $tempBase ('soc_delivery_' + [guid]::NewGuid().ToString('N').Substring(0, 12))))
if (!$tempRoot.StartsWith($tempBase + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe verification path' }
if (Test-Path -LiteralPath $tempRoot) { throw "Verification directory already exists: $tempRoot" }
try {
    [IO.Compression.ZipFile]::ExtractToDirectory($ZipPath, $tempRoot)
    $package = Join-Path $tempRoot 'SOC'
    $packageVersion = [IO.File]::ReadAllText((Join-Path $package 'VERSION')).Trim()
    if ($packageVersion -ceq '6.5' -and
        ($CoremarkEvidenceMode -cne 'BoardRelease' -or [string]::IsNullOrWhiteSpace($ReleaseManifest))) {
        throw 'SOC_V6_5_REQUIRES_BOARD_RELEASE: Packaged V6.5 requires BoardRelease and an explicit -ReleaseManifest, independent of the invoking project version.'
    }
    if ($packageVersion -ceq '2.1' -and
        ($CoremarkEvidenceMode -cne 'BoardRelease' -or [string]::IsNullOrWhiteSpace($ReleaseManifest))) {
        throw 'SOC_V2_1_REQUIRES_BOARD_RELEASE: Packaged V2.1 requires board-only CoreMark evidence and an explicit -ReleaseManifest.'
    }
    & (Join-Path $package 'scripts/invoke_project_skills.ps1') -Arguments @('verify-delivery', '--package', $package)
    $indexFiles = @('scripts/update_project_index.py','scripts/project_directory_catalog.json',
        'docs/Project_Directory_Index.md','docs/validation/project-directory-inventory.json')
    $indexPresent = @($indexFiles | Where-Object { Test-Path -LiteralPath (Join-Path $package $_) -PathType Leaf })
    if ($indexPresent.Count) {
        if ($indexPresent.Count -ne $indexFiles.Count) { throw 'Incomplete packaged directory index' }
        & $PythonPath -B (Join-Path $package 'scripts/update_project_index.py') --project-root $package --check
        if ($LASTEXITCODE -ne 0) { throw 'Packaged directory index does not match its recorded inventory' }
        $directoryIndexStatus = 'PASS'
    } else { $directoryIndexStatus = 'LEGACY_ARCHIVE_WITHOUT_INDEX' }
    & (Join-Path $package 'scripts/audit_project.ps1') -Root $package -CheckHashes
    & (Join-Path $package 'scripts/verify_delivery_evidence.ps1') -Root $package `
        -CoremarkEvidenceMode $CoremarkEvidenceMode -ReleaseManifest $ReleaseManifest -PythonPath $PythonPath -HostGccPath $HostGccPath
    . (Join-Path $package 'scripts/project_files.ps1')
    $expected = @(Get-ProjectFiles $package) + 'SHA256SUMS.txt'
    $actual = @(Get-ChildItem -LiteralPath $package -Recurse -File -Force | ForEach-Object {
        $_.FullName.Substring($package.Length + 1).Replace('\', '/')
    })
    if (@(Compare-Object ($expected | Sort-Object) ($actual | Sort-Object)).Count) { throw 'Archive differs from release inventory' }
    # Reproduce software and rootfs in an independent extracted directory.
    . (Join-Path $package 'scripts/build_snapshot.ps1')
    $softwarePaths = @('artifacts/bootloader.elf','artifacts/bootloader.bin',
        'artifacts/bootrom.hex', 'artifacts/bootloader.build.json')
    $bootHashes = Get-FpgaHashMap $package $softwarePaths
    $rootfsHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $package 'linux/boot/rootfs.cpio')).Hash
    if ($packageVersion -ceq '2.1') {
        $payloadRoot = Join-Path $package 'linux/boot/v2_1_sd/rootfs_payloads'
        & (Join-Path $package 'scripts/make_rootfs.ps1') `
            -IncludePikafish -ExternalPff1 -SkipDtbUpdate `
            -PikafishModelPath (Join-Path $package 'linux/boot/pikafish.pff') `
            -PikafishGuiPath (Join-Path $payloadRoot 'xiangqi-pikafish-gui') `
            -StageBPackPath (Join-Path $payloadRoot 'pikafish-stageb-mac.bin') `
            -StageBLoaderPath (Join-Path $payloadRoot 'pikafish-stageb-load') `
            -StageBGoldenPath (Join-Path $payloadRoot 'pikafish-stageb-golden.bin') `
            -StageBBoardAcceptPath (Join-Path $payloadRoot 'pikafish-stageb-board-accept') `
            -StageBPositionGoldenPath (Join-Path $payloadRoot 'pikafish-stageb-position-golden.bin') `
            -StageBPositionAcceptPath (Join-Path $payloadRoot 'pikafish-stageb-position-accept')
    } else {
        & (Join-Path $package 'scripts/make_rootfs.ps1')
    }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $package 'linux/boot/rootfs.cpio')).Hash -ne $rootfsHash) {
        throw 'Rootfs cannot be reproduced from bundled baseline and overlay'
    }
    # PDS's local ROM copy is generated during normal builds and is excluded
    # from the archive. Functional RTL tests consume it before rebuilding the
    # bootloader, so restore it from the hash-verified release artifact.
    Copy-Item -LiteralPath (Join-Path $package 'artifacts/bootrom.hex') `
        -Destination (Join-Path $package 'pds/bootrom.hex')
    if ($SoftwareOnly) {
        # Hash-verified extraction plus a fresh compiler run checks portability
        # without claiming that the extracted hardware regression was run.
        & (Join-Path $package 'scripts/build_bootloader.ps1') -ToolchainRoot (Split-Path -Parent $ToolchainBin)
        if ($LASTEXITCODE -ne 0) { throw 'Extracted bootloader rebuild failed' }
    } else {
        & (Join-Path $package 'scripts/run_all_tests.ps1') -IcarusBin $IcarusBin -MsysRoot $MsysRoot -ToolchainBin $ToolchainBin -PythonPath $PythonPath -HostGccPath $HostGccPath
        if ($LASTEXITCODE -ne 0) { throw 'Extracted regression failed' }
    }
    Assert-FpgaMap $bootHashes (Get-FpgaHashMap $package $softwarePaths) 'Rebuilt bootloader BIN/ROM/metadata'
    foreach ($build in @{
        'build_mac_selftest_wsl.ps1' = 'mac_selftest.bin'
        'build_mac_benchmark_wsl.ps1' = 'mac_benchmark.bin'
        'build_xiangqi_sparse_eval_wsl.ps1' = 'xiangqi_sparse_eval_selftest.bin'
        'build_xiangqi_fb_demo_wsl.ps1' = 'xiangqi_fb_demo.bin'
    }.GetEnumerator()) {
        $examplePaths = @(('artifacts/' + [IO.Path]::ChangeExtension($build.Value, 'elf')),
            ('artifacts/' + $build.Value),
            ('artifacts/' + [IO.Path]::ChangeExtension($build.Value, 'build.json')))
        $before = Get-FpgaHashMap $package $examplePaths
        & (Join-Path $package ('scripts/' + $build.Key)) -ToolchainRoot (Split-Path -Parent $ToolchainBin)
        if ($LASTEXITCODE -ne 0) { throw "Example rebuild failed: $($build.Value)" }
        Assert-FpgaMap $before (Get-FpgaHashMap $package $examplePaths) "Rebuilt example $($build.Value) BIN/metadata"
    }
    $song = Join-Path $package 'artifacts/SONG.PCM'
    $songHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $song).Hash
    & (Join-Path $package 'scripts/make_song_pcm.ps1') -ValidateOnly
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $song).Hash -ne $songHash) {
        throw 'Bundled SONG.PCM differs from its fixed input hash'
    }
    Write-Output 'SOC_SOFTWARE_REPRODUCIBLE_PASS'
} finally {
    if (Test-Path -LiteralPath $tempRoot) {
        $resolved = (Get-Item -LiteralPath $tempRoot -Force).FullName
        if (!$resolved.StartsWith($tempBase + '\soc_delivery_', [StringComparison]::OrdinalIgnoreCase) -or
            ((Get-Item -LiteralPath $tempRoot -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'Refusing unsafe verification cleanup'
        }
        if (@(Get-ChildItem -LiteralPath $tempRoot -Recurse -Force | Where-Object {
            $_.Attributes -band [IO.FileAttributes]::ReparsePoint
        }).Count) { throw 'Refusing cleanup through linked verification content' }
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}
if ($SoftwareOnly) {
    Write-Output "SOC_DELIVERY_HASH_AND_SOFTWARE_PASS coremark_evidence=$CoremarkEvidenceMode (hardware regression not rerun)"
} else {
    Write-Output "SOC_CLEAN_DELIVERY_PASS coremark_evidence=$CoremarkEvidenceMode"
}
} finally {
    $env:PATH = $cpuOriginalPath
}
# A receipt is emitted only after the original extraction/rebuild/verification
# and temporary-directory cleanup have returned successfully. Software-only
# receipts cannot authorize the delivery cleanup helper.
if ((Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $verifiedArchiveSha256) {
    throw 'Archive changed during verification; no completion receipt written'
}
$completion = [ordered]@{
    schema=1;status=$(if ($SoftwareOnly) { 'SOC_DELIVERY_HASH_AND_SOFTWARE_PASS' } else { 'SOC_CLEAN_DELIVERY_PASS' })
    completed_utc=[DateTime]::UtcNow.ToString('o');zip_path=$ZipPath;zip_sha256=$verifiedArchiveSha256
    software_only=[bool]$SoftwareOnly;coremark_evidence_mode=$CoremarkEvidenceMode
    directory_index=$directoryIndexStatus
    release_manifest=$ReleaseManifest
    verifier_sha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
}
[IO.File]::WriteAllText([IO.Path]::GetFullPath($CompletionReceipt),
    ($completion | ConvertTo-Json -Depth 8) + "`n", [Text.UTF8Encoding]::new($false))
Write-Output "DELIVERY_COMPLETION_RECEIPT $CompletionReceipt"
Write-Output 'Next: review cleanup_delivery_workspace.ps1 -Action Plan; archive disposable output only after completion, then refresh the directory index.'
