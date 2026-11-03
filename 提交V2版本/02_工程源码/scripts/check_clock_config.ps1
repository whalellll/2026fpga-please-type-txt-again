param([string]$Root = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'clock_policy.ps1')
$Root = [IO.Path]::GetFullPath($Root)
$clock = Get-Content -LiteralPath (Join-Path $Root 'config/clocks.json') -Raw -Encoding UTF8 | ConvertFrom-Json
Assert-SocClockIntent $clock
$socHeader = [IO.File]::ReadAllText((Join-Path $Root 'sw/bootloader/soc.h'))
$coremarkHeader = [IO.File]::ReadAllText((Join-Path $Root 'sw/coremark/core_portme.h'))
$dts = [IO.File]::ReadAllText((Join-Path $Root 'linux/soc.dts'))
$cpuRtl = [IO.File]::ReadAllText((Join-Path $Root 'rtl/cpu/CoreTop.sv'))
$linuxTimeHz = $clock.timebase_hz
if (!$cpuRtl.Contains('SYNTHETIC CPU source')) {
    if ($cpuRtl -notmatch "io_csrRnum == 12'hC01\s*\?\s*cycle\[31:0\]") {
        throw 'CPU TIME CSR is not mapped to CPU cycle as required by the Linux DTS'
    }
    $linuxTimeHz = $clock.cpu_hz
}
foreach ($entry in @(
    @('SYS_CLOCK_HZ', $clock.sys_hz),
    @('CPU_CLOCK_HZ', $clock.cpu_hz),
    @('TIMEBASE_HZ', $clock.timebase_hz)
)) {
    $name = $entry[0]; $hz = $entry[1]
    if ([regex]::Matches($socHeader, '(?m)^#define ' + $name + ' ' + $hz + 'u$').Count -ne 1) {
        throw "Software $name differs from config/clocks.json"
    }
}
if ([regex]::Matches($coremarkHeader, '(?m)^#define CORE_CLOCKS_PER_SEC ' + $clock.timebase_hz + 'ULL$').Count -ne 1) {
    throw 'CoreMark timebase differs from config/clocks.json'
}
if ([regex]::Matches($dts, '(?m)^\s*clock-frequency = <' + $clock.cpu_hz + '>;').Count -ne 1 -or
    [regex]::Matches($dts, '(?m)^\s*timebase-frequency = <' + $linuxTimeHz + '>;').Count -ne 1) {
    throw 'Linux DTS clock properties differ from the CPU TIME CSR and config/clocks.json'
}
$socTop = [IO.File]::ReadAllText((Join-Path $Root 'rtl/soc/soc_top.v'))
$pll = [IO.File]::ReadAllText((Join-Path $Root 'rtl/video/pll_video.v'))
$fdc = [IO.File]::ReadAllText((Join-Path $Root 'pds/soc.fdc'))
foreach ($entry in @(
    @($socTop, 'parameter integer CPU_DIVISOR\s*=\s*' + $clock.cpu_divisor + '\b', 'SoC CPU divisor'),
    @($socTop, "parameter \[31:0\] SYS_HZ\s*=\s*32'd" + $clock.sys_hz + '\b', 'SoC SYS clock'),
    @($socTop, "parameter \[31:0\] TIMEBASE_HZ\s*=\s*32'd" + $clock.timebase_hz + '\b', 'SoC CLINT timebase'),
    @($socTop, '5:sys_rdata=CPU_HZ', 'CPU_HZ MMIO'),
    @($socTop, '6:sys_rdata=TIMEBASE_HZ', 'TIMEBASE_HZ MMIO'),
    @($pll, 'parameter integer CPU_DIVISOR\s*=\s*' + $clock.cpu_divisor + '\b', 'PLL CPU divisor'),
    @($pll, 'STATIC_RATIO3\s*=\s*CPU_DIVISOR', 'PLL CPU output'),
    @($pll, 'STATIC_DUTY3\s*=\s*CPU_DIVISOR', 'PLL CPU duty'),
    @($pll, 'CLKIN_FREQ\s*=\s*27\.0\s*;', 'PLL reference'),
    @($pll, 'STATIC_RATIOI\s*=\s*1\s*;', 'PLL input divider'),
    @($pll, 'STATIC_RATIOM\s*=\s*2\s*;', 'PLL multiplier'),
    @($pll, 'STATIC_RATIOF\s*=\s*16\.5\s*;', 'PLL feedback divider'),
    @($pll, 'STATIC_RATIO0\s*=\s*PIXEL_DIVISOR \* 1\.0\s*;', 'PLL pixel output'),
    @($pll, 'STATIC_RATIO2\s*=\s*126\s*;', 'PLL I2C output'),
    @($pll, 'STATIC_RATIO1\s*=\s*18\b', 'PLL fixed SYS output')
)) {
    if ([regex]::Matches($entry[0], $entry[1]).Count -ne 1) { throw "Clock hardware mismatch: $($entry[2])" }
}
foreach ($name in @('sys_clk','cpu_clk')) {
    $found = [regex]::Matches($fdc, 'create_clock -name \{' + $name + '\} -period \{([0-9.]+)\}')
    if ($found.Count -ne 1) { throw "Missing/duplicate $name FDC clock" }
    $period = if ($name -eq 'cpu_clk') {
        Get-SocCpuConstraintPeriodNs $clock
    } else {
        Get-SocSysConstraintPeriodNs $clock
    }
    $expected = $period.ToString('0.000000', [Globalization.CultureInfo]::InvariantCulture)
    if ($found[0].Groups[1].Value -cne $expected) {
        throw "$name FDC period differs from reviewed timing target: expected $expected"
    }
}
$null = Assert-SocCpuClockHardware $Root $clock
$null = Assert-SocDisplayClockHardware $Root $clock
$scope=Get-Content -LiteralPath (Join-Path $Root 'config/timing_scope_baseline.json') -Raw -Encoding UTF8|ConvertFrom-Json
$cpuTarget=if((Get-SocCpuClockMode $clock) -in @(4,5,6,7,8,9,10,11)){'{ g_dedicated_cpu.u_cpu_pll/u_gpll/gpll_inst/CLKOUT0 }'}elseif((Get-SocCpuClockMode $clock) -ne 0){'{ g_dedicated_cpu.u_cpu_pll/u_gpll/gpll_inst/CLKOUT3 }'}else{'{ u_video_pll/u_gpll/gpll_inst/CLKOUT3 }'}
if($scope.clocks.cpu_clk.target -cne $cpuTarget){throw 'STA scope CPU target differs from actual CPU PLL source'}
$cdcLimit = Assert-SocCdcBounds $fdc
$tb = [IO.File]::ReadAllText((Join-Path $Root 'sim/tb_cpu_integration.sv'))
if ([regex]::Matches($tb, '(?m)^\s*integer coremark_cpu_hz\s*=\s*' + $clock.cpu_hz + ';').Count -ne 1) {
    throw 'CoreMark testbench CPU frequency differs from config/clocks.json'
}
foreach ($relative in @('scripts/coremark_fixed_bootloader.ps1',
        'scripts/run_coremark_production_sim.ps1','scripts/measure_coremark.ps1')) {
    $text = [IO.File]::ReadAllText((Join-Path $Root $relative))
    if ([regex]::Matches($text, '(?m)^\s*\[ValidateRange\(1,\s*1000000000\)\]\[(?:int|long)\]\$CpuHz\s*=\s*' + $clock.cpu_hz + '\b').Count -ne 1) {
        throw "CoreMark script CPU default differs from config/clocks.json: $relative"
    }
}
Write-Output "SOC_CLOCK_CONFIG_PASS cpu_hz=$($clock.cpu_hz) sys_hz=$($clock.sys_hz) clint_timebase_hz=$($clock.timebase_hz) linux_time_hz=$linuxTimeHz cpu_divisor=$($clock.cpu_divisor) cdc_limit_ns=$cdcLimit"
