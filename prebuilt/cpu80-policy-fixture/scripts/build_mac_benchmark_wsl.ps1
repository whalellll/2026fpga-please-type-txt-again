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
$elfPath = Join-Path $artifactDir 'mac_benchmark.elf'
$binPath = Join-Path $artifactDir 'mac_benchmark.bin'
$disasmPath = Join-Path $artifactDir 'mac_benchmark.disasm.txt'
New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null

$gcc = $toolchain.gcc
$libgcc = $toolchain.Libgcc
$objcopy = $toolchain.objcopy
$objdump = $toolchain.objdump
$size = $toolchain.size
$compileArgs = @(
    "-march=$CpuMarch", "-mabi=$CpuAbi", '-O2',
    '-Wall', '-Wextra', '-Werror', '-ffreestanding', '-fno-builtin',
    '-fno-common', '-ffunction-sections', '-fdata-sections',
    '-msmall-data-limit=0', '-I', (Join-Path $root 'sw\mac_accel')
)
$sources = @(
    (Join-Path $root 'sw\examples\mac_benchmark\start.S'),
    (Join-Path $root 'sw\examples\mac_benchmark\mac_benchmark.c'),
    (Join-Path $root 'sw\mac_accel\mac_accel_kernel.c')
)
$objects = @(Build-CpuObjects -Toolchain $toolchain -Directory (Join-Path $artifactDir 'mac_benchmark_obj') -Sources $sources -CompilerArguments $compileArgs)
& $gcc @compileArgs -nostdlib -nostartfiles '-Wl,--gc-sections' '-Wl,--build-id=none' `
    -T (Join-Path $root 'sw\examples\mac_benchmark\link.ld') @objects $libgcc -o $elfPath
if ($LASTEXITCODE -ne 0) {
    throw "Native MAC benchmark build failed: $LASTEXITCODE"
}

& $objcopy '-O' 'binary' $elfPath $binPath
if ($LASTEXITCODE -ne 0) {
    throw "Native MAC benchmark objcopy failed: $LASTEXITCODE"
}

$disassembly = & $objdump '-d' '-S' $elfPath
if ($LASTEXITCODE -ne 0) {
    throw "Native MAC benchmark objdump failed: $LASTEXITCODE"
}
$disassembly | Set-Content -LiteralPath $disasmPath -Encoding Ascii

& $size $elfPath
if ($LASTEXITCODE -ne 0) {
    throw "Native MAC benchmark size failed: $LASTEXITCODE"
}
Write-CpuFirmwareEvidence -Toolchain $toolchain -Elf $elfPath -Binary $binPath `
    -Optimization '-O2' -UsesLibgcc
$bootDirectory = Join-Path $root 'linux\boot'
New-Item -ItemType Directory -Force -Path $bootDirectory | Out-Null
Copy-Item -LiteralPath $binPath -Destination (Join-Path $bootDirectory 'mac_benchmark.bin') -Force
Write-Output "MAC benchmark: $(Join-Path $root 'artifacts\mac_benchmark.bin')"
} finally {
    $env:PATH = $cpuOriginalPath
}
