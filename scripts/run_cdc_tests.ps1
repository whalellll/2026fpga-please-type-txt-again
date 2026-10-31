param([string]$IcarusBin = 'D:\LJL\WORK\iverilog\bin')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'simulation_tools.ps1')
$iverilog = Join-Path $IcarusBin 'iverilog.exe'
$vvp = Join-Path $IcarusBin 'vvp.exe'
foreach ($tool in @($iverilog, $vvp)) {
    if (!(Test-Path -LiteralPath $tool -PathType Leaf)) { throw "Missing Icarus tool: $tool" }
}
$out = Join-Path $root 'artifacts/selftest'
New-Item -ItemType Directory -Path $out -Force | Out-Null
$bridgeImage = Join-Path $out 'tb_axi_cpu_sys_cdc.vvp'
& $iverilog -g2012 -s tb_axi_cpu_sys_cdc -o $bridgeImage `
    (Join-Path $root 'rtl/soc/axi_cpu_sys_cdc.v') `
    (Join-Path $root 'sim/tb_axi_cpu_sys_cdc.sv')
if ($LASTEXITCODE -ne 0) { throw 'CPU/SYS AXI CDC test compile failed' }
foreach ($case in @(
    @{ cpu = 7; sys = 11; phase = 3; seed = 439041101 },
    @{ cpu = 13; sys = 5; phase = 2; seed = 1515870810 },
    @{ cpu = 10; sys = 10; phase = 4; seed = 305419896 }
)) {
    $name = "cpu_sys_cdc_$($case.cpu)_$($case.sys)_$($case.phase)"
    $args = '"' + $bridgeImage + '"' + " +cpu_half=$($case.cpu) +sys_half=$($case.sys) +sys_phase=$($case.phase) +seed=$($case.seed)"
    Invoke-SimulationCase -Executable $vvp -Root $root -Name $name `
        -Arguments $args -Marker 'AXI_CPU_SYS_CDC_PASS' -TimeoutSeconds 180
}
$irqImage = Join-Path $out 'tb_clint_sys_irq.vvp'
& $iverilog -g2012 -s tb_clint_sys_irq -o $irqImage `
    (Join-Path $root 'rtl/clint.v') `
    (Join-Path $root 'rtl/cpu_top.v') `
    (Join-Path $root 'sim/tb_clint_sys_irq.sv')
if ($LASTEXITCODE -ne 0) { throw 'SYS CLINT and CPU IRQ test compile failed' }
Invoke-SimulationCase -Executable $vvp -Root $root -Name 'clint_sys_irq' `
    -Arguments ('"' + $irqImage + '"') -Marker 'CLINT_SYS_IRQ_PASS' -TimeoutSeconds 60
Write-Output 'SOC_CDC_TESTS_PASS'
