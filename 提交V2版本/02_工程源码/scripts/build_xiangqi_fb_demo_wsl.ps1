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
$elfPath = Join-Path $artifactDir 'xiangqi_fb_demo.elf'
$binPath = Join-Path $artifactDir 'xiangqi_fb_demo.bin'
New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null

$gcc = $toolchain.gcc
$libgcc = $toolchain.Libgcc
$objcopy = $toolchain.objcopy
$size = $toolchain.size
$compileArgs = @(
    "-march=$CpuMarch", "-mabi=$CpuAbi", '-Os',
    '-ffreestanding', '-fno-builtin', '-fno-common',
    '-ffunction-sections', '-fdata-sections',
    '-I', (Join-Path $root 'sw\video')
)
$sources = @(
    (Join-Path $root 'sw\examples\xiangqi_fb_demo\start.S'),
    (Join-Path $root 'sw\examples\xiangqi_fb_demo\xiangqi_fb_demo.c')
)
$objects = @(Build-CpuObjects -Toolchain $toolchain -Directory (Join-Path $artifactDir 'xiangqi_fb_demo_obj') -Sources $sources -CompilerArguments $compileArgs)
& $gcc @compileArgs -nostdlib -nostartfiles '-Wl,--gc-sections' '-Wl,--build-id=none' `
    -T (Join-Path $root 'sw\examples\xiangqi_fb_demo\link.ld') @objects $libgcc -o $elfPath
if ($LASTEXITCODE -ne 0) {
    throw "Native Xiangqi framebuffer demo build failed: $LASTEXITCODE"
}

& $objcopy '-O' 'binary' $elfPath $binPath
if ($LASTEXITCODE -ne 0) {
    throw "Native Xiangqi framebuffer demo objcopy failed: $LASTEXITCODE"
}

& $size $elfPath
if ($LASTEXITCODE -ne 0) {
    throw "Native Xiangqi framebuffer demo size failed: $LASTEXITCODE"
}
Write-CpuFirmwareEvidence -Toolchain $toolchain -Elf $elfPath -Binary $binPath `
    -Optimization '-Os' -UsesLibgcc
Write-Output "Xiangqi framebuffer demo: $(Join-Path $root 'artifacts\xiangqi_fb_demo.bin')"
} finally {
    $env:PATH = $cpuOriginalPath
}
