param(
    [string]$Distro = 'pikafish-verify',
    [string]$ToolchainPrefix = '/opt/toolchain/bin/riscv32-linux-musl'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$workspace = Split-Path -Parent $root
$packer = Join-Path $root 'sw\pikafish_official_decode\pack_stageb_mac.py'
$nnue = Join-Path $workspace 'xiangqi_oss\Pikafish\pikafish.nnue'
$pff1 = Join-Path $root 'linux\boot\pikafish.pff'
$pack = Join-Path $root 'artifacts\pikafish-stageb-mac.bin'
$loader = Join-Path $root 'artifacts\pikafish-stageb-load'
$golden = Join-Path $root 'artifacts\pikafish-stageb-golden.bin'
$boardAccept = Join-Path $root 'artifacts\pikafish-stageb-board-accept'
$goldenTest = Join-Path $root 'scripts\test_pikafish_stageb_golden.ps1'

function Convert-ToWslPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot convert path to WSL: $full"
    }
    return '/mnt/' + $Matches[1].ToLowerInvariant() + '/' +
        $Matches[2].Replace('\', '/')
}

foreach ($path in @($packer, $nnue, $pff1)) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing Stage B build input: $path"
    }
}
if (!(Test-Path -LiteralPath $goldenTest -PathType Leaf)) {
    throw "Missing Stage B golden generator: $goldenTest"
}
New-Item -ItemType Directory -Path (Split-Path -Parent $pack) -Force | Out-Null

$wslPacker = Convert-ToWslPath $packer
$wslNnue = Convert-ToWslPath $nnue
$wslPff1 = Convert-ToWslPath $pff1
$wslPack = Convert-ToWslPath $pack
$wslGolden = Convert-ToWslPath $golden
$wslRoot = Convert-ToWslPath $root

& wsl.exe -d $Distro -- python3 $wslPacker `
    --pff1 $wslPff1 --nnue $wslNnue --output $wslPack
if ($LASTEXITCODE -ne 0) { throw 'Stage B MAC pack generation failed' }

& $goldenTest -PfsbPath $pack -GoldenPath $golden -Distro $Distro
if ($LASTEXITCODE -ne 0) { throw 'Stage B golden vector generation failed' }

$command = @"
set -eu
test -x '${ToolchainPrefix}-gcc'
'${ToolchainPrefix}-gcc' -std=gnu11 -march=rv32ima -mabi=ilp32 -Os -flto \
  -ffunction-sections -fdata-sections -fno-asynchronous-unwind-tables \
  -static -Wl,--gc-sections -Wall -Wextra -Werror \
  -iquote '$wslRoot/sw/pikafish_mlp_stage_b' \
  '$wslRoot/linux/pikafish/pikafish_stageb_load.c' \
  -o '$wslRoot/artifacts/pikafish-stageb-load'
'${ToolchainPrefix}-strip' '$wslRoot/artifacts/pikafish-stageb-load'
'${ToolchainPrefix}-gcc' -std=gnu11 -march=rv32ima -mabi=ilp32 -O2 -flto \
  -ffunction-sections -fdata-sections -fno-asynchronous-unwind-tables \
  -static -Wl,--gc-sections -Wall -Wextra -Werror \
  -iquote '$wslRoot/sw/pikafish_mlp_stage_b' \
  -iquote '$wslRoot/sw/mac_accel' \
  '$wslRoot/linux/pikafish/pikafish_stageb_board_accept.c' \
  '$wslRoot/sw/pikafish_mlp_stage_b/pf_mlp_stage_b_ref.c' \
  '$wslRoot/sw/mac_accel/mac_accel_kernel.c' \
  -o '$wslRoot/artifacts/pikafish-stageb-board-accept'
'${ToolchainPrefix}-strip' '$wslRoot/artifacts/pikafish-stageb-board-accept'
'${ToolchainPrefix}-readelf' -h -A '$wslRoot/artifacts/pikafish-stageb-load'
'${ToolchainPrefix}-readelf' -h -A '$wslRoot/artifacts/pikafish-stageb-board-accept'
gcc -std=gnu11 -O2 -Wall -Wextra -Werror \
  -iquote '$wslRoot/sw/pikafish_mlp_stage_b' \
  '$wslRoot/linux/pikafish/pikafish_stageb_load.c' \
  -o /tmp/pikafish-stageb-load-host
/tmp/pikafish-stageb-load-host \
  '$wslRoot/artifacts/pikafish-stageb-mac.bin' --verify-only
gcc -std=gnu11 -O2 -Wall -Wextra -Werror \
  -iquote '$wslRoot/sw/pikafish_mlp_stage_b' \
  -iquote '$wslRoot/sw/mac_accel' \
  '$wslRoot/linux/pikafish/pikafish_stageb_board_accept.c' \
  '$wslRoot/sw/pikafish_mlp_stage_b/pf_mlp_stage_b_ref.c' \
  '$wslRoot/sw/mac_accel/mac_accel_kernel.c' \
  -o /tmp/pikafish-stageb-board-accept-host
/tmp/pikafish-stageb-board-accept-host \
  '$wslRoot/artifacts/pikafish-stageb-mac.bin' \
  '$wslGolden' --verify-only
"@
$command = $command.Replace("`r`n", "`n")
& wsl.exe -d $Distro -- bash -lc $command
if ($LASTEXITCODE -ne 0) { throw 'Stage B Linux loader build failed' }

$packLength = (Get-Item -LiteralPath $pack).Length
if ($packLength -ne 0x91000) {
    throw "Unexpected Stage B pack size: $packLength"
}
$goldenLength = (Get-Item -LiteralPath $golden).Length
if ($goldenLength -ne 12928) {
    throw "Unexpected Stage B golden size: $goldenLength"
}
Write-Output "PIKAFISH_STAGEB_LINUX_BUILD_PASS pack_bytes=$packLength golden_bytes=$goldenLength"
Get-FileHash -Algorithm SHA256 -LiteralPath $pack, $golden, $loader, $boardAccept
