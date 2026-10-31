param([string]$ToolchainRoot = '')
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'riscv_toolchain.ps1')
$root = Split-Path -Parent $PSScriptRoot
$src = Join-Path $root 'sw/examples/hello'
$cpuOriginalPath = $env:PATH
try {
$toolchain = Get-CpuToolchain -ToolchainRoot $ToolchainRoot
$gcc = $toolchain.gcc
$objcopy = $toolchain.objcopy
$elf = Join-Path $root 'artifacts/hello.elf'
$bin = Join-Path $root 'artifacts/hello.bin'
$libgcc = $toolchain.Libgcc
$compileArgs = @("-march=$CpuMarch", "-mabi=$CpuAbi", '-Os', '-ffreestanding', '-fno-builtin')
$objects = @(Build-CpuObjects -Toolchain $toolchain -Directory (Join-Path $root 'artifacts/hello_obj') `
    -Sources @((Join-Path $src 'start.S'), (Join-Path $src 'hello.c')) -CompilerArguments $compileArgs)
& $gcc @compileArgs -nostdlib -nostartfiles '-Wl,--build-id=none' -T (Join-Path $src 'link.ld') @objects $libgcc -o $elf
if ($LASTEXITCODE) { throw 'Example GCC failed' }
& $objcopy -O binary $elf $bin
if ($LASTEXITCODE) { throw 'Example objcopy failed' }
Write-CpuFirmwareEvidence -Toolchain $toolchain -Elf $elf -Binary $bin `
    -Optimization '-Os' -UsesLibgcc
Write-Host "Example: $bin"
} finally {
    $env:PATH = $cpuOriginalPath
}
