param(
    [string]$IcarusBin = 'D:\LJL\WORK\iverilog\bin',
    [string]$ToolchainBin = '',
    [string]$MsysRoot = 'D:\LJL\WORK\msys64',
    [string]$CandidateCpuPath = '',
    [switch]$SkipProductionConsole,
    [ValidateRange(10, 600)][int]$TimeoutSeconds = 180,
    [ValidateRange(1,2)][int]$BuildJobs = 2
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'riscv_toolchain.ps1')
$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path $root 'artifacts/selftest'
New-Item -ItemType Directory -Force -Path $out | Out-Null
if ($CandidateCpuPath) {
    $cpuSource = [IO.Path]::GetFullPath($CandidateCpuPath)
    if (!(Test-Path -LiteralPath $cpuSource -PathType Leaf)) { throw 'Candidate CPU source is missing' }
    Write-Output ('CANDIDATE_CPU_ONLY sha256=' + (Get-FileHash -LiteralPath $cpuSource -Algorithm SHA256).Hash.ToLowerInvariant())
} else {
    & (Join-Path $PSScriptRoot 'sync_cpu.ps1') -Check
    $cpuSource = 'rtl/cpu/CoreTop.sv'
}
$cpuOriginalPath = $env:PATH
try {
$toolchain = Get-CpuToolchain -ToolchainBin $ToolchainBin
$gcc = $toolchain.gcc
$objcopy = $toolchain.objcopy
$iverilog = Join-Path $IcarusBin 'iverilog.exe'
$vvp = Join-Path $IcarusBin 'vvp.exe'
$elf = Join-Path $out 'cpu_integration.elf'
$bin = Join-Path $out 'cpu_integration.bin'
$hex = Join-Path $out 'cpu_integration.hex'
$image = Join-Path $out 'cpu_integration.vvp'
& $gcc -march=rv32ima_zicsr_zifencei -mabi=ilp32 -mno-relax -nostdlib -nostartfiles `
    '-Wl,--build-id=none' -T (Join-Path $root 'sim/cpu_integration.ld') `
    (Join-Path $root 'sim/cpu_integration.S') -o $elf
if ($LASTEXITCODE) { throw 'CPU integration program compilation failed' }
& $objcopy -O binary $elf $bin
if ($LASTEXITCODE) { throw 'CPU integration objcopy failed' }
Write-CpuFirmwareEvidence -Toolchain $toolchain -Elf $elf -Binary $bin `
    -Optimization 'assembly; no libgcc' -IllegalInstructionFixture
& (Join-Path $PSScriptRoot 'bin_to_hex.ps1') -InputBin $bin -OutputHex $hex
# A read-only SPI fixture, not a Flash programming operation. Header layout and
# CRC are the existing eight-word SV2I ABI. The payload checks jump arguments.
if (!$SkipProductionConsole) {
    $flashElf = Join-Path $out 'flash_autoboot_payload.elf'
    $flashBin = Join-Path $out 'flash_autoboot_payload.bin'
    & $gcc -march=rv32ima_zicsr_zifencei -mabi=ilp32 -mno-relax -nostdlib -nostartfiles `
        '-Wl,--build-id=none' -T (Join-Path $root 'sim/flash_autoboot_payload.ld') `
        (Join-Path $root 'sim/flash_autoboot_payload.S') -o $flashElf
    if ($LASTEXITCODE) { throw 'Flash test payload compilation failed' }
    & $objcopy -O binary $flashElf $flashBin
    if ($LASTEXITCODE) { throw 'Flash test payload objcopy failed' }
    Write-CpuFirmwareEvidence -Toolchain $toolchain -Elf $flashElf -Binary $flashBin -Optimization 'assembly; no libgcc'
    function Get-FlashFixtureCrc([byte[]]$Bytes) {
        [uint32]$crc = [uint32]::MaxValue
        foreach ($value in $Bytes) {
            $crc = $crc -bxor $value
            for ($bit = 0; $bit -lt 8; $bit++) {
                if ($crc -band 1) { $crc = ($crc -shr 1) -bxor [uint32]3988292384 }
                else { $crc = $crc -shr 1 }
            }
        }
        return ($crc -bxor [uint32]::MaxValue)
    }
    $payload = [IO.File]::ReadAllBytes($flashBin)
    if ($payload.Length -gt 224) { throw 'Flash startup fixture exceeds the bounded model' }
    [byte[]]$header = @()
    foreach ($word in @([uint32]0x49325653, [uint32]1, [uint32]0x00100000, [uint32]0x00100000,
                      [uint32]$payload.Length, (Get-FlashFixtureCrc $payload), [uint32]1)) {
        $header += [BitConverter]::GetBytes([uint32]$word)
    }
    $header += [BitConverter]::GetBytes([uint32](Get-FlashFixtureCrc $header))
    [IO.File]::WriteAllLines((Join-Path $out 'flash_autoboot.hex'),
        [string[]]@(($header + $payload) | ForEach-Object { $_.ToString('x2') }), [Text.UTF8Encoding]::new($false))
}
. (Join-Path $PSScriptRoot 'simulation_tools.ps1')
$image = Build-VerilatorModel -Root $root -Top 'tb_cpu_integration' -MsysRoot $MsysRoot -BuildJobs $BuildJobs -Sources @(
    $cpuSource, 'rtl/clint.v', 'rtl/cpu_top.v',
    'rtl/soc/axi_1x2.v', 'rtl/soc/axi_boot_periph.v', 'rtl/soc/axi_cpu_sys_cdc.v', 'rtl/soc/uart_tx_fifo.v',
    'sim/tb_cpu_integration.sv')
if (!$SkipProductionConsole -and !(Test-Path -LiteralPath (Join-Path $root 'artifacts/bootrom.hex'))) {
    throw 'Build the production bootloader before running its console integration test'
}
$cases = @(@{Name='integration'; Marker='CPU_AXI_CLINT_UART_DDR_PASS'; Extra=''})
if (!$SkipProductionConsole) {
    $cases += @{Name='production_console'; Marker='CPU_PRODUCTION_CONSOLE_PASS'; Extra='+production_bootloader'}
    foreach ($flashCase in @('cancel','badcrc','valid')) {
        $cases += @{Name="flash_$flashCase"; Marker="CPU_FLASH_AUTOBOOT_PASS case=$flashCase"; Extra="+production_bootloader +flash_case=$flashCase"}
    }
}
foreach ($case in $cases) {
    Invoke-SimulationCase -Executable $image -Root $root -Name "cpu_$($case.Name)" `
        -Arguments $case.Extra -Marker $case.Marker -TimeoutSeconds $TimeoutSeconds
}
if ($CandidateCpuPath) { Write-Output 'CPU_CANDIDATE_TESTS_PASS (not the delivered source)' }
else { Write-Output 'CPU_TESTS_PASS' }
} finally {
    $env:PATH = $cpuOriginalPath
}
