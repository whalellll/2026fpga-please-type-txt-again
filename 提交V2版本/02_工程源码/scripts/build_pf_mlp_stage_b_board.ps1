param([string]$ToolchainRoot = '')

# Native-toolchain build of the bare-metal Pikafish Stage B (MLP fc0->fc2)
# board acceptance program. Uses the in-repo sw/xiangqi
# xiangqi_nnue_mac.{c,h} copy instead of the historical external sibling
# repository required by build_pf_mlp_stage_b_board_wsl.ps1.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'riscv_toolchain.ps1')
$root = Split-Path -Parent $PSScriptRoot
$here = Join-Path $root 'sw\pikafish_mlp_stage_b'
$macSw = Join-Path $root 'sw\mac_accel'
$nnueSw = Join-Path $root 'sw\xiangqi'

$toolchain = Get-CpuToolchain -ToolchainRoot $ToolchainRoot
$artifactDir = Join-Path $root 'artifacts'
$elfPath = Join-Path $artifactDir 'pf_mlp_stage_b_board.elf'
$binPath = Join-Path $artifactDir 'pf_mlp_stage_b_board.bin'
New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null

$sources = @(
    (Join-Path $here 'start.S'),
    (Join-Path $here 'pf_mlp_board.c'),
    (Join-Path $here 'pf_mlp_stage_b_ref.c'),
    (Join-Path $here 'pf_mlp_stage_b_cases.c'),
    (Join-Path $here 'pf_mlp_mac_fc0.c'),
    (Join-Path $macSw 'mac_accel_kernel.c'),
    (Join-Path $nnueSw 'xiangqi_nnue_mac.c')
)

$cpuOriginalPath = $env:PATH
try {
    $env:PATH = "$($toolchain.Root);$env:PATH"
    & $toolchain.gcc '-std=gnu99' "-march=$CpuMarch" "-mabi=$CpuAbi" `
        '-mcmodel=medany' '-mno-relax' '-msmall-data-limit=0' '-mstrict-align' '-Os' `
        '-ffreestanding' '-fno-builtin' '-fno-common' '-ffunction-sections' `
        '-fdata-sections' '-Wall' '-Wextra' '-nostdlib' '-nostartfiles' `
        '-Wl,--gc-sections' '-Wl,--build-id=none' `
        '-I' $here '-I' $macSw '-I' $nnueSw `
        '-T' (Join-Path $here 'link.ld') `
        @sources '-lgcc' '-o' $elfPath
    if ($LASTEXITCODE -ne 0) { throw "Stage B board build failed: $LASTEXITCODE" }
    & $toolchain.objcopy '-O' 'binary' $elfPath $binPath
    if ($LASTEXITCODE -ne 0) { throw 'objcopy failed' }
    & $toolchain.size $elfPath
} finally {
    $env:PATH = $cpuOriginalPath
}

Write-Output "PF_MLP_STAGE_B_BOARD_BIN $binPath"
Write-Output 'PF_MLP_STAGE_B_BOARD_BUILD_PASS'
