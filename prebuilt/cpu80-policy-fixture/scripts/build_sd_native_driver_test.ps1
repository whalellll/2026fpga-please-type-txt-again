param(
    [string]$IcarusBin = 'D:\LJL\WORK\iverilog\bin',
    [string]$MsysRoot = 'D:\LJL\WORK\msys64',
    [string]$CandidateCpuPath = '',
    [string]$ToolchainBin = '',
    [switch]$AppGuardOnly,
    [ValidateRange(1,2)][int]$BuildJobs = 2
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'riscv_toolchain.ps1')
$sim = Join-Path $root 'sim'
$bootloader = Join-Path $root 'sw\bootloader'
$out = Join-Path $root 'artifacts\selftest'
New-Item -ItemType Directory -Force -Path $out | Out-Null

$cpuOriginalPath = $env:PATH
try {
$toolchain = Get-CpuToolchain -ToolchainBin $ToolchainBin
$gcc = $toolchain.gcc
$objcopy = $toolchain.objcopy
$size = $toolchain.size
foreach ($tool in @($gcc, $objcopy, $size)) {
    if (!(Test-Path -LiteralPath $tool -PathType Leaf)) {
        throw "Missing tool: $tool"
    }
}

$elf = Join-Path $out 'sd_native_driver_test.elf'
$bin = Join-Path $out 'sd_native_driver_test.bin'
$hex = Join-Path $out 'sd_native_driver_test.hex'
$map = Join-Path $out 'sd_native_driver_test.map'
$sdhcLog = Join-Path $out 'sd_native_driver_sdhc.log'
$sdscLog = Join-Path $out 'sd_native_driver_sdsc.log'

$libgcc = $toolchain.Libgcc
$gccArgs = @(
    '-std=gnu99', '-Os',
    "-march=$CpuMarch", "-mabi=$CpuAbi",
    '-mcmodel=medany', '-mno-relax', '-msmall-data-limit=0', '-mstrict-align',
    '-ffreestanding', '-fno-builtin', '-fno-common', '-ffunction-sections',
    '-fdata-sections', '-Wall', '-Wextra', '-Werror',
    (Join-Path $sim 'fat_ro_test.S'),
    (Join-Path $bootloader 'runtime.c'),
    (Join-Path $bootloader 'sd_native.c'),
    (Join-Path $sim 'sd_native_driver_test.c'),
    '-I', $bootloader, '-nostartfiles', '-nostdlib',
    "-T$(Join-Path $sim 'fat_ro_test.ld')", '-Wl,--gc-sections',
    '-Wl,--build-id=none', "-Wl,-Map,$map", $libgcc, '-o', $elf
)
& $gcc @gccArgs
if ($LASTEXITCODE -ne 0) { throw "GCC failed: $LASTEXITCODE" }
& $objcopy -O binary $elf $bin
if ($LASTEXITCODE -ne 0) { throw "objcopy failed: $LASTEXITCODE" }
if ((Get-Item -LiteralPath $bin).Length -gt 131072) {
    throw 'Native SD driver test firmware exceeds 128 KiB simulation RAM'
}
Write-CpuFirmwareEvidence -Toolchain $toolchain -Elf $elf -Binary $bin `
    -Optimization '-Os' -UsesLibgcc
& (Join-Path $PSScriptRoot 'bin_to_hex.ps1') -InputBin $bin `
    -OutputHex $hex -MemoryBytes 131072
& $size -A $elf
if ($LASTEXITCODE -ne 0) { throw "size failed: $LASTEXITCODE" }

. (Join-Path $PSScriptRoot 'simulation_tools.ps1')
if ($CandidateCpuPath) {
    $cpuSource = [IO.Path]::GetFullPath($CandidateCpuPath)
    Write-Output ('CANDIDATE_CPU_ONLY sha256=' + (Get-FileHash -LiteralPath $cpuSource -Algorithm SHA256).Hash.ToLowerInvariant())
} else {
    & (Join-Path $PSScriptRoot 'sync_cpu.ps1') -Check
    $cpuSource = 'rtl/cpu/CoreTop.sv'
}
$model = Build-VerilatorModel -Root $root -MsysRoot $MsysRoot -Top 'tb_sd_native_driver' -BuildJobs $BuildJobs -Sources @(
    $cpuSource, 'rtl/clint.v', 'rtl/cpu_top.v', 'rtl/soc/axi_cpu_sys_cdc.v',
    'rtl/soc/sd_native_mmio.v', 'sim/tb_sd_native_driver.sv')
if (!$AppGuardOnly) {
    Invoke-SimulationCase -Executable $model -Root $root -Name 'sd_native_driver_sdhc' `
        -Marker 'SD_NATIVE_DRIVER_PASS mode=SDHC blocks=32 retry=1' -TimeoutSeconds 180
    Invoke-SimulationCase -Executable $model -Root $root -Name 'sd_native_driver_sdsc' `
        -Arguments '+sdsc' -Marker 'SD_NATIVE_DRIVER_PASS mode=SDSC blocks=32 retry=1' -TimeoutSeconds 180
}
foreach ($appMode in @('missing_cmd55_app','missing_acmd23_app')) {
    Invoke-SimulationCase -Executable $model -Root $root -Name "sd_native_driver_$appMode" `
        -Arguments "+$appMode" -Marker 'SD_NATIVE_DRIVER_APP_CMD_MISSING_REJECT_PASS' -TimeoutSeconds 180
}
if ($AppGuardOnly) {
    Write-Output 'SD_NATIVE_CPU_APP_CMD_GUARD_TEST_PASS'
    return
}
$sdhcPassed = Select-String -LiteralPath $sdhcLog -SimpleMatch `
    'SD_NATIVE_DRIVER_PASS mode=SDHC blocks=32 retry=1'
if (!$sdhcPassed) {
    throw 'SDHC native pass marker not found'
}
if (!(Select-String -LiteralPath $sdhcLog -SimpleMatch `
    'SD_NATIVE_DRIVER_WRITE_ALIGNED_UNALIGNED_512_BYTES_CRC_BUSY_PASS')) {
    throw 'SDHC aligned/unaligned full-sector write pass marker not found'
}
if (!(Select-String -LiteralPath $sdhcLog -SimpleMatch `
    'SD_NATIVE_DRIVER_CMD25_EIGHT_SECTORS_REFILL_ALIGN_CANCEL_READY_PASS')) {
    throw 'SDHC CMD25 stream/refill/cancel READY pass marker not found'
}
$sdscPassed = Select-String -LiteralPath $sdscLog -SimpleMatch `
    'SD_NATIVE_DRIVER_PASS mode=SDSC blocks=32 retry=1'
if (!$sdscPassed) {
    throw 'SDSC native pass marker not found'
}
Write-Output 'SD_NATIVE_CPU_DRIVER_TEST_PASS'
} finally {
    $env:PATH = $cpuOriginalPath
}
