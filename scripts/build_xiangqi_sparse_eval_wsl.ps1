param(
    [string]$Distro = 'chiplab_sim',
    [string]$ToolchainRoot = ''
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'riscv_toolchain.ps1')
$root = Split-Path -Parent $PSScriptRoot

# Historical filename/Distro argument retained; all builds use the verified native compiler.
$cpuOriginalPath = $env:PATH
try {
$toolchain = Get-CpuToolchain -ToolchainRoot $ToolchainRoot
$artifactDir = Join-Path $root 'artifacts'
$elfPath = Join-Path $artifactDir 'xiangqi_sparse_eval_selftest.elf'
$binPath = Join-Path $artifactDir 'xiangqi_sparse_eval_selftest.bin'
New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null

$gcc = $toolchain.gcc
$libgcc = $toolchain.Libgcc
$objcopy = $toolchain.objcopy
$size = $toolchain.size
$compileArgs = @(
    "-march=$CpuMarch", "-mabi=$CpuAbi", '-O2',
    '-ffreestanding', '-fno-builtin', '-fno-common',
    '-ffunction-sections', '-fdata-sections',
    '-I', (Join-Path $root 'sw\mac_accel')
)
$sources = @(
    (Join-Path $root 'sw\examples\xiangqi_sparse_eval\start.S'),
    (Join-Path $root 'sw\examples\xiangqi_sparse_eval\xiangqi_sparse_eval_selftest.c')
)
$objects = @(Build-CpuObjects -Toolchain $toolchain -Directory (Join-Path $artifactDir 'xiangqi_sparse_eval_obj') -Sources $sources -CompilerArguments $compileArgs)
& $gcc @compileArgs -nostdlib -nostartfiles '-Wl,--gc-sections' '-Wl,--build-id=none' `
    -T (Join-Path $root 'sw\examples\xiangqi_sparse_eval\link.ld') @objects $libgcc -o $elfPath
if ($LASTEXITCODE -ne 0) {
    throw "Native Xiangqi sparse evaluator self-test build failed: $LASTEXITCODE"
}

& $objcopy '-O' 'binary' $elfPath $binPath
if ($LASTEXITCODE -ne 0) {
    throw "Native Xiangqi sparse evaluator self-test objcopy failed: $LASTEXITCODE"
}

& $size $elfPath
if ($LASTEXITCODE -ne 0) {
    throw "Native Xiangqi sparse evaluator self-test size failed: $LASTEXITCODE"
}
Write-CpuFirmwareEvidence -Toolchain $toolchain -Elf $elfPath -Binary $binPath `
    -Optimization '-O2' -UsesLibgcc
$bootDirectory = Join-Path $root 'linux\boot'
New-Item -ItemType Directory -Force -Path $bootDirectory | Out-Null
Copy-Item -LiteralPath $binPath -Destination (Join-Path $bootDirectory 'xiangqi_sparse_eval_selftest.bin') -Force
Write-Output "Xiangqi sparse evaluator self-test: $(Join-Path $root `
    'artifacts\xiangqi_sparse_eval_selftest.bin')"
} finally {
    $env:PATH = $cpuOriginalPath
}
