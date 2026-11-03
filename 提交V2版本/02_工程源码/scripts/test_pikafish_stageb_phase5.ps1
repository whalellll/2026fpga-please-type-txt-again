param(
    [string]$PfsbPath,
    [string]$Distro = 'pikafish-verify'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$PfsbPath) {
    $PfsbPath = Join-Path $root 'artifacts\pikafish-stageb-mac.bin'
}
if (!(Test-Path -LiteralPath $PfsbPath -PathType Leaf)) {
    throw "Missing Stage B phase-5 pack: $PfsbPath"
}

function Convert-ToWslPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot convert path to WSL: $full"
    }
    return '/mnt/' + $Matches[1].ToLowerInvariant() + '/' +
        $Matches[2].Replace('\', '/')
}

$wslRoot = Convert-ToWslPath $root
$wslPack = Convert-ToWslPath $PfsbPath
$command = @"
set -eu
g++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic -pthread \
  -DPIKAFISH_STAGEB_ACCEL -DPIKAFISH_MAC_RUNTIME_EMULATED \
  -DPIKAFISH_STAGEB_TESTING \
  -iquote '$wslRoot/linux/pikafish' \
  -iquote '$wslRoot/sw/pikafish_mlp_stage_b' \
  '$wslRoot/linux/pikafish/pikafish_stageb_phase5_test.cpp' \
  '$wslRoot/linux/pikafish/pikafish_stageb_accel.cpp' \
  '$wslRoot/linux/pikafish/pikafish_mac_runtime.cpp' \
  -o /tmp/pikafish-stageb-phase5-test
"@.Replace("`r`n", "`n")

& wsl.exe -d $Distro -- bash -lc $command
if ($LASTEXITCODE -ne 0) {
    throw 'Stage B phase-5 host acceptance build failed'
}

$expected = @{
    soak = @('PIKAFISH_STAGEB_PHASE5_SOAK_PASS rounds=16 evaluations=256 jobs=1024 checkpoints=17')
    'corrupt-model' = @(
        'PIKAFISH_STAGEB_PHASE5_CORRUPTION_PASS fallback=1 checkpoint_failures=1',
        'PIKAFISH_STAGEB_CPU_FALLBACK reason=resident-integrity')
}
foreach ($scenario in @('soak', 'corrupt-model')) {
    $runCommand = "exec /tmp/pikafish-stageb-phase5-test '$scenario' '$wslPack' 2>&1"
    $savedErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    $lines = & wsl.exe -d $Distro -- bash -lc $runCommand 2>$null
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $savedErrorPreference
    $text = ($lines | Out-String)
    Write-Output $text.TrimEnd()
    if ($exitCode -ne 0) {
        throw "Stage B phase-5 scenario failed: $scenario"
    }
    foreach ($needle in $expected[$scenario]) {
        if (!$text.Contains($needle)) {
            throw "Stage B phase-5 marker missing for ${scenario}: $needle"
        }
    }
}

$hash = (Get-FileHash -LiteralPath $PfsbPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Output "PIKAFISH_STAGEB_PHASE5_HOST_PASS pfsb_sha256=$hash"
