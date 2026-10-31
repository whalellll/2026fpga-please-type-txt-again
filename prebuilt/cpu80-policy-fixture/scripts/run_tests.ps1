param(
    [string]$IcarusBin = 'D:\LJL\WORK\iverilog\bin',
    [string]$MsysRoot = 'D:\LJL\WORK\msys64',
    [string]$ToolchainBin = ''
)
$ErrorActionPreference = 'Stop'
# This release tests current CPU machine-mode integration, not historical Sv32 boot.
& (Join-Path $PSScriptRoot 'run_cpu_tests.ps1') -IcarusBin $IcarusBin -ToolchainBin $ToolchainBin -MsysRoot $MsysRoot
