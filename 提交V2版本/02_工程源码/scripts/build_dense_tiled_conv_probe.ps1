param(
    [string]$Distro = 'pikafish-verify',
    [string]$OutputDir = ''
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$OutputDir) { $OutputDir = Join-Path $root 'build/vision/dense_tiled_20261005' }
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
function Convert-ToWslPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') { throw "Cannot convert path: $full" }
    return '/mnt/' + $Matches[1].ToLowerInvariant() + '/' + $Matches[2].Replace('\', '/')
}
$repo = Convert-ToWslPath $root
$out = Convert-ToWslPath $OutputDir
$command = @"
set -eu
cd '$repo'
/opt/toolchain/bin/riscv32-linux-musl-gcc -std=c11 -march=rv32ima -mabi=ilp32 \
  -Os -static -Wall -Wextra -Werror -ffunction-sections -fdata-sections \
  -Wl,--gc-sections linux/mac_accel/pango_mac_tiled_conv_test.c \
  -o '$out/pango-mac-tiled-conv-test'
/opt/toolchain/bin/riscv32-linux-musl-strip '$out/pango-mac-tiled-conv-test'
file '$out/pango-mac-tiled-conv-test'
sha256sum '$out/pango-mac-tiled-conv-test' '$out/cases.bin'
printf '%s\n' DENSE_TILED_RV32_BUILD_PASS
"@.Replace("`r`n", "`n")
$command | wsl.exe -d $Distro -- bash -s
if ($LASTEXITCODE -ne 0) { throw 'Dense tiled RV32 build failed' }
