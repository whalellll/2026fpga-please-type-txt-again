param(
    [string]$Distro = 'pikafish-verify',
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$OutputPath) {
    $OutputPath = Join-Path $root 'build\linux-mac-scheduler\out\pango-mac-scheduler-test'
}
$source = Join-Path $root 'linux\mac_accel\pango_mac_scheduler_test.c'
$headerRoot = Join-Path $root 'linux\mac_accel'
if (!(Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "Missing scheduler test source: $source"
}

function Convert-ToWslPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot convert path to WSL: $full"
    }
    return '/mnt/' + $Matches[1].ToLowerInvariant() + '/' +
        $Matches[2].Replace('\', '/')
}

$outputDirectory = Split-Path -Parent ([IO.Path]::GetFullPath($OutputPath))
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
$wslSource = Convert-ToWslPath $source
$wslHeader = Convert-ToWslPath $headerRoot
$wslOutput = Convert-ToWslPath $OutputPath
$command = @"
set -eu
cc=/opt/toolchain/bin/riscv32-linux-musl-gcc
test -x "`$cc"
"`$cc" -std=gnu11 -march=rv32ima -mabi=ilp32 -Os -static -pthread \
  -ffunction-sections -fdata-sections -Wl,--gc-sections \
  -Wall -Wextra -Werror -I'$wslHeader' '$wslSource' -o '$wslOutput'
/opt/toolchain/bin/riscv32-linux-musl-strip '$wslOutput'
printf '%s\n' PANGO_MAC_SCHEDULER_TEST_BUILD_PASS
"@.Replace("`r`n", "`n")

$command | wsl.exe -d $Distro -- bash -s
if ($LASTEXITCODE -ne 0) {
    throw 'MAC scheduler board test build failed'
}
