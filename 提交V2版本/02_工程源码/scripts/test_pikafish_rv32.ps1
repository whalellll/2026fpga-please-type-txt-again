param(
    [string]$ModelPath,
    [string]$RuntimeModelPath,
    [int]$Nodes = 1000,
    [int]$TimeoutSeconds = 300,
    [switch]$SkipBuild,
    [string]$Distro = 'pikafish-verify'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$workspace = Split-Path -Parent $root
$portRoot = Join-Path $root 'linux\pikafish'
$artifactRoot = Join-Path $root 'artifacts'
$logRoot = Join-Path $root 'build\pikafish-rv32\test-logs'
$expectedModelHash = '3cd15292bf8c979884262f57fc723959fc0dea43b4d8d544f88db5ceb2479e24'
$expectedRuntimeModelHash = 'de0906fa1bea82248523eb39fc6b2956613b02ae675ccf67eef3f392de939260'
$attackTablePath = Join-Path $root 'linux\boot\pikafish.atk'
$expectedAttackHash = '2235f0b1cca2e447a828bf1c7c7247237580603026d6152954da07efca2d474c'

function Convert-ToWslPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot convert path to WSL: $full"
    }
    return '/mnt/' + $Matches[1].ToLowerInvariant() + '/' +
        $Matches[2].Replace('\', '/')
}

if (!$ModelPath) {
    $ModelPath = Join-Path $workspace 'xiangqi_oss\Pikafish\pikafish.nnue'
}
if (!$RuntimeModelPath) {
    $RuntimeModelPath = Join-Path $artifactRoot 'pikafish.nnue.flat'
}
if (!$SkipBuild) {
    & (Join-Path $PSScriptRoot 'build_pikafish_rv32.ps1') `
        -ModelPath $ModelPath -Distro $Distro
    if ($LASTEXITCODE -ne 0) { throw 'Pikafish RV32 build failed before regression' }
}

$required = @(
    (Join-Path $artifactRoot 'pikafish-rv32'),
    (Join-Path $artifactRoot 'pikafish-reference-x86_64'),
    (Join-Path $artifactRoot 'xiangqi-pikafish-gui'),
    (Join-Path $artifactRoot 'xiangqi-input-test'),
    (Join-Path $artifactRoot 'pikafish-stagea-pack-test-x86_64'),
    (Join-Path $artifactRoot 'pikafish-stagea-pack-test-rv32'),
    (Join-Path $artifactRoot 'pikafish-attacks-test-x86_64'),
    (Join-Path $artifactRoot 'pikafish-attacks-test-rv32'),
    $attackTablePath,
    $ModelPath,
    $RuntimeModelPath
)
foreach ($path in $required) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing regression input: $path"
    }
}
$modelHash = (Get-FileHash -LiteralPath $ModelPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($modelHash -ne $expectedModelHash) {
    throw "Pikafish model SHA-256 mismatch: $modelHash"
}
$runtimeModelHash = (Get-FileHash -LiteralPath $RuntimeModelPath `
    -Algorithm SHA256).Hash.ToLowerInvariant()
if ($runtimeModelHash -ne $expectedRuntimeModelHash) {
    throw "Pikafish PFF1 model SHA-256 mismatch: $runtimeModelHash"
}
$attackHash = (Get-FileHash -LiteralPath $attackTablePath `
    -Algorithm SHA256).Hash.ToLowerInvariant()
if ($attackHash -ne $expectedAttackHash) {
    throw "Pikafish attack-table SHA-256 mismatch: $attackHash"
}

$wslPort = Convert-ToWslPath $portRoot
$wslArtifacts = Convert-ToWslPath $artifactRoot
$null = New-Item -ItemType Directory -Force -Path $logRoot
$wslLogs = Convert-ToWslPath $logRoot
$wslModel = Convert-ToWslPath $RuntimeModelPath
$wslReferenceModel = Convert-ToWslPath $ModelPath
$wslAttackTable = Convert-ToWslPath $attackTablePath
$command = @"
set -e
PIKAFISH_PORT='$wslPort' \
PIKAFISH_ARTIFACTS='$wslArtifacts' \
PIKAFISH_LOG_DIR='$wslLogs' \
PIKAFISH_MODEL='$wslModel' \
PIKAFISH_REFERENCE_MODEL='$wslReferenceModel' \
PIKAFISH_ATTACKS='$wslAttackTable' \
PIKAFISH_TEST_NODES='$Nodes' \
PIKAFISH_TEST_TIMEOUT='$TimeoutSeconds' \
sh '$wslPort/test_in_wsl.sh'
"@.Replace("`r`n", "`n")
& wsl.exe -d $Distro -- bash -lc $command
if ($LASTEXITCODE -ne 0) { throw 'Pikafish RV32 WSL regression failed' }

Copy-Item -Force -LiteralPath (Join-Path $logRoot 'pikafish-native-uci.log') `
    -Destination (Join-Path $artifactRoot 'pikafish-native-uci.log')
Copy-Item -Force -LiteralPath (Join-Path $logRoot 'pikafish-rv32-uci.log') `
    -Destination (Join-Path $artifactRoot 'pikafish-rv32-uci.log')

Write-Output "PIKAFISH_RV32_TEST_PASS nodes=$Nodes model_sha256=$expectedRuntimeModelHash stage_a=mac"
