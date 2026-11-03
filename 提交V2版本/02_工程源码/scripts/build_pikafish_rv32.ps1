param(
    [string]$PikafishSource,
    [string]$ModelPath,
    [int]$Jobs = 2,
    [string]$Distro = 'pikafish-verify',
    [switch]$PrepareOnly
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$workspace = Split-Path -Parent $root

if (!$PikafishSource) {
    $PikafishSource = Join-Path $workspace 'xiangqi_oss\Pikafish'
}
if (!$ModelPath) {
    $ModelPath = Join-Path $PikafishSource 'pikafish.nnue'
}

$expectedCommit = '56be6f65c21c6a3c7f9b884a976fc85d31d03287'
$expectedModelHash = '3cd15292bf8c979884262f57fc723959fc0dea43b4d8d544f88db5ceb2479e24'
$portRoot = Join-Path $root 'linux\pikafish'
$buildRoot = Join-Path $root 'build\pikafish-rv32'
$sourceStage = Join-Path $buildRoot 'source'
$stagedOutput = Join-Path $buildRoot 'out'
$archivePath = Join-Path $buildRoot 'source.tar'
$artifactRoot = Join-Path $root 'artifacts'

function Convert-ToWslPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot convert path to WSL: $full"
    }
    return '/mnt/' + $Matches[1].ToLowerInvariant() + '/' +
        $Matches[2].Replace('\', '/')
}

$actualCommit = (& git -C $PikafishSource rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $actualCommit -ne $expectedCommit) {
    throw "Pikafish source commit mismatch: expected $expectedCommit, got $actualCommit"
}
if (!(Test-Path -LiteralPath $ModelPath -PathType Leaf)) {
    throw "Missing Pikafish model: $ModelPath"
}
$actualModelHash = (Get-FileHash -LiteralPath $ModelPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualModelHash -ne $expectedModelHash) {
    throw "Pikafish model SHA-256 mismatch: $actualModelHash"
}

$buildFull = [IO.Path]::GetFullPath($buildRoot)
$allowedBase = [IO.Path]::GetFullPath((Join-Path $root 'build'))
if (!$buildFull.StartsWith($allowedBase, [StringComparison]::OrdinalIgnoreCase) -or
    [IO.Path]::GetFileName($buildFull) -ne 'pikafish-rv32') {
    throw "Unsafe build staging path: $buildFull"
}
if (Test-Path -LiteralPath $buildRoot) {
    Remove-Item -LiteralPath $buildRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $sourceStage -Force | Out-Null
New-Item -ItemType Directory -Path $stagedOutput -Force | Out-Null
New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null

& git -C $PikafishSource archive --format=tar -o $archivePath $expectedCommit
if ($LASTEXITCODE -ne 0) { throw 'Failed to export the pinned Pikafish source' }
& tar.exe -xf $archivePath -C $sourceStage
if ($LASTEXITCODE -ne 0) { throw 'Failed to extract the pinned Pikafish source' }
Remove-Item -LiteralPath $archivePath -Force

foreach ($file in @(
    'portable_u128.h',
    'pikafish_attack_tables.h',
    'pikafish_attack_tables.cpp',
    'pikafish_mac_runtime.h',
    'pikafish_mac_runtime.cpp',
    'pikafish_mmio_shadow.h',
    'pango_mac_uapi.h',
    'pikafish_stagea_accel.h',
    'pikafish_stagea_accel.cpp',
    'pikafish_feature_updates.h',
    'pikafish_stageb_accel.h',
    'pikafish_stageb_accel.cpp',
    'pikafish_stageb_position_accept.cpp',
    'pikafish_pff1_view.h',
    'pikafish_embedded.h',
    'pikafish_embedded.cpp')) {
    $source = if ($file -eq 'pango_mac_uapi.h') {
        Join-Path $root 'linux\mac_accel\pango_mac_uapi.h'
    } else {
        Join-Path $portRoot $file
    }
    Copy-Item -LiteralPath $source `
        -Destination (Join-Path $sourceStage "src\$file") -Force
}
foreach ($file in @(
    (Join-Path $root 'sw\mac_accel\mac_accel_kernel.h'),
    (Join-Path $root 'sw\pikafish_mlp_stage_b\pf_mlp_mac_pack.h'),
    (Join-Path $root 'sw\pikafish_mlp_stage_b\pf_mlp_stage_b.h'),
    (Join-Path $root 'sw\pikafish_mlp_stage_b\pf_stageb_position_golden.h'))) {
    Copy-Item -LiteralPath $file -Destination (Join-Path $sourceStage 'src') -Force
}
Copy-Item -LiteralPath (Join-Path $portRoot 'pikafish_flat_nnue.inc') `
    -Destination (Join-Path $sourceStage 'src\nnue\pikafish_flat_nnue.inc') -Force
Copy-Item -LiteralPath $ModelPath `
    -Destination (Join-Path $sourceStage 'src\pikafish.nnue') -Force

foreach ($patch in @('pikafish-rv32.patch', 'pikafish-attacks.patch',
                     'pikafish-stagea.patch',
                     'pikafish-flat.patch', 'pikafish-view.patch',
                     'pikafish-embedded.patch',
                     'pikafish-embedded-memory.patch',
                     'pikafish-startup-memory.patch',
                     'pikafish-zero-state-history.patch',
                     'pikafish-stageb-position-accept.patch',
                     'pikafish-stageb.patch', 'pikafish-pipeline.patch')) {
    & git -C $root apply --ignore-space-change --ignore-whitespace `
        "--directory=build/pikafish-rv32/source" `
        (Join-Path $portRoot $patch)
    if ($LASTEXITCODE -ne 0) { throw "Failed to apply $patch" }
}

& 'G:/py/ana/python.exe' -X utf8 (Join-Path $portRoot 'apply_nnue_pipeline.py') `
    $sourceStage (Join-Path $portRoot 'pikafish-pipeline.patch') (Join-Path $buildRoot 'pipeline-integration.json')
if ($LASTEXITCODE -ne 0) { throw 'Pipeline hook verification failed' }
& 'G:/py/ana/python.exe' -X utf8 (Join-Path $portRoot 'apply_feature_updates.py') `
    $sourceStage (Join-Path $buildRoot 'feature-updates-integration.json')
if ($LASTEXITCODE -ne 0) { throw 'Direct descriptor source integration failed' }
if ($PrepareOnly) { Write-Output "PIKAFISH_SOURCE_READY path=$sourceStage"; return }

$normalizedDriver = Join-Path $buildRoot 'build_in_wsl.normalized.sh'
$driverText = [IO.File]::ReadAllText((Join-Path $portRoot 'build_in_wsl.sh'))
$driverText = $driverText.Replace("`r`n", "`n").Replace("`r", "`n")
[IO.File]::WriteAllText(
    $normalizedDriver, $driverText, [Text.UTF8Encoding]::new($false))

$wslRoot = Convert-ToWslPath $root
$wslSource = Convert-ToWslPath $sourceStage
$wslOutput = Convert-ToWslPath $stagedOutput
$wslPort = Convert-ToWslPath $portRoot
$wslDriver = Convert-ToWslPath $normalizedDriver
$command = @"
set -e
test -x /opt/toolchain/bin/riscv32-linux-musl-g++
PIKAFISH_REPO='$wslRoot' \
PIKAFISH_WORK='$wslSource' \
PIKAFISH_OUT='$wslOutput' \
PIKAFISH_PORT='$wslPort' \
PIKAFISH_BUILD_JOBS='$Jobs' \
sh '$wslDriver'
"@.Replace("`r`n", "`n")
& wsl.exe -d $Distro -- bash -lc $command
if ($LASTEXITCODE -ne 0) { throw 'Pikafish RV32 WSL build failed' }

foreach ($name in @(
    'pikafish-rv32',
    'pikafish-reference-x86_64',
    'pikafish-view-reference-x86_64',
    'xiangqi-pikafish-gui',
    'xiangqi-input-test',
    'pff1-linux-probe',
    'pikafish-stagea-pack-test-x86_64',
    'pikafish-stagea-pack-test-rv32',
    'pikafish-stageb-golden-test-x86_64',
    'pikafish-stageb-position-reference-x86_64',
    'pikafish-stageb-position-view-x86_64',
    'pikafish-stageb-position-accept',
    'pikafish-stageb-phase4-search',
    'pikafish-stageb-phase4-search-x86_64',
    'pikafish-stageb-phase5-search',
    'pikafish-stageb-phase5-search-x86_64',
    'pikafish-devmem-copy',
    'pikafish-history-zero-test-x86_64',
    'pikafish-history-zero-test-rv32',
    'pikafish-attacks-test-x86_64',
    'pikafish-attacks-test-rv32')) {
    Copy-Item -LiteralPath (Join-Path $stagedOutput $name) `
        -Destination (Join-Path $artifactRoot $name) -Force
}

$rv32 = Join-Path $artifactRoot 'pikafish-rv32'
$native = Join-Path $artifactRoot 'pikafish-reference-x86_64'
$viewNative = Join-Path $artifactRoot 'pikafish-view-reference-x86_64'
$gui = Join-Path $artifactRoot 'xiangqi-pikafish-gui'
$inputTest = Join-Path $artifactRoot 'xiangqi-input-test'
$pff1Probe = Join-Path $artifactRoot 'pff1-linux-probe'
$devmemCopy = Join-Path $artifactRoot 'pikafish-devmem-copy'
$stageATests = @(
    (Join-Path $artifactRoot 'pikafish-stagea-pack-test-x86_64'),
    (Join-Path $artifactRoot 'pikafish-stagea-pack-test-rv32'))
$stageBPositionTests = @(
    (Join-Path $artifactRoot 'pikafish-stageb-position-reference-x86_64'),
    (Join-Path $artifactRoot 'pikafish-stageb-position-view-x86_64'),
    (Join-Path $artifactRoot 'pikafish-stageb-position-accept'))
$stageBPhase4Tests = @(
    (Join-Path $artifactRoot 'pikafish-stageb-phase4-search'),
    (Join-Path $artifactRoot 'pikafish-stageb-phase4-search-x86_64'))
$stageBPhase5Tests = @(
    (Join-Path $artifactRoot 'pikafish-stageb-phase5-search'),
    (Join-Path $artifactRoot 'pikafish-stageb-phase5-search-x86_64'))
$stageBGoldenTest = Join-Path $artifactRoot 'pikafish-stageb-golden-test-x86_64'
$historyTests = @(
    (Join-Path $artifactRoot 'pikafish-history-zero-test-x86_64'),
    (Join-Path $artifactRoot 'pikafish-history-zero-test-rv32'))
$attackTests = @(
    (Join-Path $artifactRoot 'pikafish-attacks-test-x86_64'),
    (Join-Path $artifactRoot 'pikafish-attacks-test-rv32'))
foreach ($path in @($rv32, $native, $viewNative, $gui, $inputTest, $pff1Probe,
        $devmemCopy) +
        $stageATests + @($stageBGoldenTest) + $stageBPositionTests +
        $stageBPhase4Tests + $stageBPhase5Tests + $historyTests + $attackTests) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Pikafish build output missing: $path"
    }
}

$wslRv32 = Convert-ToWslPath $rv32
& wsl.exe -d $Distro -- /opt/toolchain/bin/riscv32-linux-musl-readelf -h -A $wslRv32
if ($LASTEXITCODE -ne 0) { throw 'Failed to inspect the RV32 ELF' }

Write-Output "PIKAFISH_RV32_BUILD_PASS commit=$expectedCommit stage_a=mac"
Write-Output "PIKAFISH_RV32_MODEL_SHA256=$expectedModelHash"
Get-Item -LiteralPath (@($rv32, $native, $viewNative, $gui, $inputTest, $pff1Probe) +
    $stageATests + @($stageBGoldenTest) + $stageBPositionTests +
    $stageBPhase4Tests + $stageBPhase5Tests + @($devmemCopy) + $historyTests + $attackTests) |
    Select-Object FullName, Length
