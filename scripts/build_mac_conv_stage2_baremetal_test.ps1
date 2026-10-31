param(
    [string]$Distro = 'chiplab_sim',
    [string]$OutputDir = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$OutputDir) { $OutputDir = Join-Path $root 'build\vision\mac-conv-board' }
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$OutputDir = (Resolve-Path -LiteralPath $OutputDir).Path
function Convert-ToWslPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot convert path to WSL: $full"
    }
    return '/mnt/' + $Matches[1].ToLowerInvariant() + '/' +
        $Matches[2].Replace('\', '/')
}
$repo = Convert-ToWslPath $root
$out = Convert-ToWslPath $OutputDir
$command = @"
set -eu
cd '$repo'
riscv64-unknown-elf-gcc -std=gnu11 -march=rv32im -mabi=ilp32 -Os \
  -ffreestanding -fno-builtin -fno-common -ffunction-sections \
  -fdata-sections -nostdlib -nostartfiles -Wl,--gc-sections \
  -Wl,--build-id=none -Wall -Wextra -Werror \
  -T sw/examples/mac_conv_stage2_test/link.ld \
  sw/examples/mac_conv_stage2_test/start.S \
  sw/examples/mac_conv_stage2_test/mac_conv_stage2_test.c \
  -lgcc -o '$out/mac_conv_stage2_test.elf'
riscv64-unknown-elf-objcopy -O binary \
  '$out/mac_conv_stage2_test.elf' '$out/mac_conv_stage2_test.bin'
riscv64-unknown-elf-size '$out/mac_conv_stage2_test.elf'
sha256sum '$out/mac_conv_stage2_test.bin' \
  > '$out/mac_conv_stage2_test.sha256'
printf '%s\n' MAC_CONV_STAGE2_BAREMETAL_BUILD_PASS
"@.Replace("`r`n", "`n")
$script = Join-Path $OutputDir 'build_baremetal.sh'
[IO.File]::WriteAllText($script, $command, [Text.UTF8Encoding]::new($false))
& wsl.exe -d $Distro -- bash (Convert-ToWslPath $script)
if ($LASTEXITCODE -ne 0) { throw 'Convolution bare-metal test build failed' }
Write-Output "Board test image: $(Join-Path $OutputDir 'mac_conv_stage2_test.bin')"
