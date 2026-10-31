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
    throw "Missing Stage B phase-4 pack: $PfsbPath"
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
  '$wslRoot/linux/pikafish/pikafish_stageb_phase4_test.cpp' \
  '$wslRoot/linux/pikafish/pikafish_stageb_accel.cpp' \
  '$wslRoot/linux/pikafish/pikafish_mac_runtime.cpp' \
  -o /tmp/pikafish-stageb-phase4-test
g++ -std=c++17 -Wall -Wextra -Werror -pedantic -pthread -fsyntax-only \
  -iquote '$wslRoot/linux/pikafish' \
  -iquote '$wslRoot/sw/pikafish_mlp_stage_b' \
  '$wslRoot/linux/pikafish/pikafish_stageb_phase4_search.cpp'
"@.Replace("`r`n", "`n")

& wsl.exe -d $Distro -- bash -lc $command
if ($LASTEXITCODE -ne 0) {
    throw 'Stage B phase-4 host acceptance build failed'
}

$expected = @{
    disabled = @('PIKAFISH_STAGEB_PHASE4_MODE_PASS mode=0')
    default = @('PIKAFISH_STAGEB_PHASE4_MODE_PASS mode=default-1')
    verify = @('PIKAFISH_STAGEB_PHASE4_MODE_PASS mode=verify')
    enabled = @('PIKAFISH_STAGEB_PHASE4_MODE_PASS mode=1')
    reuse = @('PIKAFISH_STAGEB_PHASE4_RESIDENT_PASS copied_bytes=0 hits=1')
    threads = @('PIKAFISH_STAGEB_PHASE4_THREADS_PASS threads=8 evaluations=256 jobs=1024')
    'fault-busy' = @(
        'PIKAFISH_STAGEB_PHASE4_FAULT_PASS fault=busy',
        'PIKAFISH_MAC_RUNTIME_FUSED client=stageb reason=injected-busy')
    'fault-error' = @(
        'PIKAFISH_STAGEB_PHASE4_FAULT_PASS fault=error',
        'PIKAFISH_MAC_RUNTIME_FUSED client=stageb reason=injected-error')
    'fault-timeout' = @(
        'PIKAFISH_STAGEB_PHASE4_FAULT_PASS fault=timeout',
        'PIKAFISH_MAC_RUNTIME_FUSED client=stageb reason=injected-timeout')
}
foreach ($scenario in @('disabled', 'default', 'verify', 'enabled', 'reuse', 'threads',
                         'fault-busy', 'fault-error', 'fault-timeout')) {
    # Move the test program's stderr onto stdout inside WSL so PowerShell can
    # suppress WSL's unrelated localhost-proxy diagnostic without hiding test
    # diagnostics.
    $runCommand = "exec /tmp/pikafish-stageb-phase4-test '$scenario' " +
        "'$wslPack' 2>&1"
    $savedErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    $lines = & wsl.exe -d $Distro -- bash -lc $runCommand 2>$null
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $savedErrorPreference
    $text = ($lines | Out-String)
    Write-Output $text.TrimEnd()
    if ($exitCode -ne 0) {
        throw "Stage B phase-4 scenario failed: $scenario"
    }
    foreach ($needle in $expected[$scenario]) {
        if (!$text.Contains($needle)) {
            throw "Stage B phase-4 marker missing for ${scenario}: $needle"
        }
    }
}

$hash = (Get-FileHash -LiteralPath $PfsbPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Output "PIKAFISH_STAGEB_PHASE4_HOST_PASS pfsb_sha256=$hash"
