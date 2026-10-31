param([string]$Distro = 'chiplab_sim', [string]$ToolchainRoot = '')
# Compatibility entry: production firmware uses the same verified native
# riscv32-unknown-elf compiler on every Windows build path.
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'build_bootloader.ps1') -ToolchainRoot $ToolchainRoot
