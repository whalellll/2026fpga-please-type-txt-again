param(
    [string]$IcarusBin = 'D:\LJL\WORK\iverilog\bin',
    [string]$MsysRoot = 'D:\LJL\WORK\msys64',
    [string]$CandidateCpuPath = '',
    [string]$ToolchainBin = '',
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
    if (!(Test-Path -LiteralPath $tool -PathType Leaf)) { throw "Missing tool: $tool" }
}

$elf = Join-Path $out 'fat_ro_test.elf'
$bin = Join-Path $out 'fat_ro_test.bin'
$hex = Join-Path $out 'fat_ro_test.hex'
$map = Join-Path $out 'fat_ro_test.map'
$log = Join-Path $out 'fat_ro_test.log'

$libgcc = $toolchain.Libgcc
$gccArgs = @(
    '-std=gnu99', '-Os', "-march=$CpuMarch", "-mabi=$CpuAbi",
    '-mcmodel=medany', '-mno-relax', '-msmall-data-limit=0', '-mstrict-align',
    '-ffreestanding', '-fno-builtin', '-fno-common', '-ffunction-sections',
    '-fdata-sections', '-Wall', '-Wextra', '-Werror',
    (Join-Path $sim 'fat_ro_test.S'),
    (Join-Path $sim 'fat_ro_test.c'),
    (Join-Path $bootloader 'fat_ro.c'),
    '-I', $bootloader, '-nostartfiles', '-nostdlib',
    "-T$(Join-Path $sim 'fat_ro_test.ld')", '-Wl,--gc-sections',
    '-Wl,--build-id=none', "-Wl,-Map,$map", $libgcc, '-o', $elf
)
& $gcc @gccArgs
if ($LASTEXITCODE -ne 0) { throw "GCC failed: $LASTEXITCODE" }
& $objcopy -O binary $elf $bin
if ($LASTEXITCODE -ne 0) { throw "objcopy failed: $LASTEXITCODE" }
if ((Get-Item -LiteralPath $bin).Length -gt 131072) {
    throw 'FAT test firmware exceeds 128 KiB simulation RAM'
}

Write-CpuFirmwareEvidence -Toolchain $toolchain -Elf $elf -Binary $bin `
    -Optimization '-Os' -UsesLibgcc
$bytes = [IO.File]::ReadAllBytes($bin)
$lines = [Collections.Generic.List[string]]::new()
for ($offset = 0; $offset -lt $bytes.Length; $offset += 4) {
    $b0 = if ($offset -lt $bytes.Length) { $bytes[$offset] } else { 0 }
    $b1 = if ($offset + 1 -lt $bytes.Length) { $bytes[$offset + 1] } else { 0 }
    $b2 = if ($offset + 2 -lt $bytes.Length) { $bytes[$offset + 2] } else { 0 }
    $b3 = if ($offset + 3 -lt $bytes.Length) { $bytes[$offset + 3] } else { 0 }
    $word = [uint32]$b0 -bor ([uint32]$b1 -shl 8) -bor `
            ([uint32]$b2 -shl 16) -bor ([uint32]$b3 -shl 24)
    $lines.Add($word.ToString('x8'))
}
while ($lines.Count -lt 32768) { $lines.Add('00000000') }
[IO.File]::WriteAllLines($hex, $lines, [Text.UTF8Encoding]::new($false))

& $size -A $elf
if ($LASTEXITCODE -ne 0) { throw "size failed: $LASTEXITCODE" }
# Run the same generated current CPU that is compiled into the FPGA project.
. (Join-Path $PSScriptRoot 'simulation_tools.ps1')
if ($CandidateCpuPath) {
    $cpuSource = [IO.Path]::GetFullPath($CandidateCpuPath)
    Write-Output ('CANDIDATE_CPU_ONLY sha256=' + (Get-FileHash -LiteralPath $cpuSource -Algorithm SHA256).Hash.ToLowerInvariant())
} else {
    & (Join-Path $PSScriptRoot 'sync_cpu.ps1') -Check
    $cpuSource = 'rtl/cpu/CoreTop.sv'
}
$model = Build-VerilatorModel -Root $root -MsysRoot $MsysRoot -Top 'tb_fat_ro' -BuildJobs $BuildJobs -Sources @(
    $cpuSource, 'rtl/clint.v', 'rtl/cpu_top.v', 'rtl/soc/axi_cpu_sys_cdc.v', 'sim/tb_fat_ro.sv')
Invoke-SimulationCase -Executable $model -Root $root -Name 'fat_ro_test' -Marker 'FAT_RO_PASS' -TimeoutSeconds 180
Write-Output 'FAT_RO_CPU_TEST_PASS'
} finally {
    $env:PATH = $cpuOriginalPath
}
