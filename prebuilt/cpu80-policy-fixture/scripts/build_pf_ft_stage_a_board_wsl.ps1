param(
    [string]$Distro = 'chiplab_sim',
    [string]$ToolchainRoot = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$here = Join-Path $root 'sw\pikafish_ft_stage_a'
$macSw = Join-Path $root 'sw\mac_accel'
$nnueSw = Join-Path (Split-Path $root) 'mac_accel\simple_system_kernel\sw'
if (!(Test-Path -LiteralPath (Join-Path $nnueSw 'xiangqi_nnue_mac.c'))) {
    $nnueSw = 'g:\fpga\mac_accel\simple_system_kernel\sw'
}

$toolchainCandidates = @()
if (-not [string]::IsNullOrWhiteSpace($ToolchainRoot)) {
    $toolchainCandidates += $ToolchainRoot
}
$toolchainCandidates += 'D:\LJL\WORK\xpack-riscv-none-elf-gcc-13.2.0-1'

$nativeRoot = $null
foreach ($candidate in $toolchainCandidates) {
    $candidateRoot = [IO.Path]::GetFullPath($candidate)
    $requiredTools = @(
        'bin\riscv-none-elf-gcc.exe',
        'bin\riscv-none-elf-objcopy.exe',
        'bin\riscv-none-elf-size.exe'
    )
    $missingTool = $requiredTools | Where-Object {
        -not (Test-Path -LiteralPath (Join-Path $candidateRoot $_) -PathType Leaf)
    } | Select-Object -First 1
    if ($null -eq $missingTool) {
        $nativeRoot = $candidateRoot
        break
    }
}

$artifactDir = Join-Path $root 'artifacts'
$elfPath = Join-Path $artifactDir 'pf_ft_stage_a_board.elf'
$binPath = Join-Path $artifactDir 'pf_ft_stage_a_board.bin'
New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null

$sources = @(
    (Join-Path $here 'start.S'),
    (Join-Path $here 'pf_ft_board.c'),
    (Join-Path $here 'pf_ft_stage_a_ref.c'),
    (Join-Path $here 'pf_ft_stage_a_cases.c'),
    (Join-Path $macSw 'mac_accel_kernel.c'),
    (Join-Path $nnueSw 'xiangqi_nnue_mac.c')
)

if ($null -ne $nativeRoot) {
    $gcc = Join-Path $nativeRoot 'bin\riscv-none-elf-gcc.exe'
    $objcopy = Join-Path $nativeRoot 'bin\riscv-none-elf-objcopy.exe'
    $size = Join-Path $nativeRoot 'bin\riscv-none-elf-size.exe'

    & $gcc '-march=rv32im' '-mabi=ilp32' '-Os' '-std=gnu99' `
        '-ffreestanding' '-fno-builtin' '-fno-common' '-ffunction-sections' `
        '-fdata-sections' '-nostdlib' '-nostartfiles' '-Wl,--gc-sections' `
        '-Wl,--build-id=none' `
        '-I' $here '-I' $macSw '-I' $nnueSw `
        '-T' (Join-Path $here 'link.ld') `
        @sources '-lgcc' '-o' $elfPath
    if ($LASTEXITCODE -ne 0) {
        throw "Native Stage A board build failed: $LASTEXITCODE"
    }
    & $objcopy '-O' 'binary' $elfPath $binPath
    if ($LASTEXITCODE -ne 0) { throw "objcopy failed: $LASTEXITCODE" }
    & $size $elfPath
} else {
    $drive = $root.Substring(0, 1).ToLowerInvariant()
    $tail = $root.Substring(2).Replace('\', '/')
    $wslRoot = "/mnt/$drive$tail"
    $nnueDrive = $nnueSw.Substring(0, 1).ToLowerInvariant()
    $nnueTail = $nnueSw.Substring(2).Replace('\', '/')
    $wslNnue = "/mnt/$nnueDrive$nnueTail"
    $command = @"
set -e
cd '$wslRoot'
mkdir -p artifacts
riscv64-unknown-elf-gcc -march=rv32im -mabi=ilp32 -Os -std=gnu99 \
  -ffreestanding -fno-builtin -fno-common -ffunction-sections \
  -fdata-sections -nostdlib -nostartfiles -Wl,--gc-sections \
  -Wl,--build-id=none \
  -I sw/pikafish_ft_stage_a -I sw/mac_accel -I '$wslNnue' \
  -T sw/pikafish_ft_stage_a/link.ld \
  sw/pikafish_ft_stage_a/start.S \
  sw/pikafish_ft_stage_a/pf_ft_board.c \
  sw/pikafish_ft_stage_a/pf_ft_stage_a_ref.c \
  sw/pikafish_ft_stage_a/pf_ft_stage_a_cases.c \
  sw/mac_accel/mac_accel_kernel.c \
  '$wslNnue/xiangqi_nnue_mac.c' -lgcc \
  -o artifacts/pf_ft_stage_a_board.elf
riscv64-unknown-elf-objcopy -O binary artifacts/pf_ft_stage_a_board.elf \
  artifacts/pf_ft_stage_a_board.bin
riscv64-unknown-elf-size artifacts/pf_ft_stage_a_board.elf
"@
    $command = $command.Replace("`r`n", "`n")
    & wsl.exe -d $Distro -- bash -lc $command
    if ($LASTEXITCODE -ne 0) {
        throw "WSL Stage A board build failed: $LASTEXITCODE"
    }
}

Write-Output "PF_FT_STAGE_A_BOARD_BIN $binPath"
