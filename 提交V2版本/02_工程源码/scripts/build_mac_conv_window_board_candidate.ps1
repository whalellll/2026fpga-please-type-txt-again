param(
    [string]$PdsShell = 'G:\fpga\PDS_2022.2-SP6.4\bin\pds_shell.exe',
    [string]$OutputDir = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!(Test-Path -LiteralPath $PdsShell -PathType Leaf)) {
    throw "PDS shell not found: $PdsShell"
}
if (!$OutputDir) {
    $OutputDir = Join-Path $root ('build\vision\window_board_' +
        (Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$OutputDir = (Resolve-Path -LiteralPath $OutputDir).Path
$vectorDir = Join-Path $OutputDir 'sim\vectors'
New-Item -ItemType Directory -Path $vectorDir -Force | Out-Null
foreach ($name in @('yolo_window_board_source.hex', 'yolo_window_board_expected.hex')) {
    Copy-Item -LiteralPath (Join-Path $root "sim\vectors\$name") -Destination $vectorDir
}
$rtl = (Join-Path $root 'rtl\mac_accel\mac_conv_window.v').Replace('\', '/')
$top = (Join-Path $root 'sim\mac_conv_window_board_top.v').Replace('\', '/')
@(
    "add_design `"$rtl`"",
    "add_design `"$top`"",
    'add_constraint "window_board.fdc"',
    'set_arch -family Logos2 -device PG2L100H -speedgrade -6 -package FBG676',
    'compile -top_module mac_conv_window_board_top',
    'synthesize -ads -selected_syn_tool_opt 2',
    'dev_map',
    'pnr',
    'report_timing',
    'gen_bit_stream -force_to_run -create_bin_file'
) | Set-Content -LiteralPath (Join-Path $OutputDir 'impl.tcl') -Encoding Ascii
@(
    'create_clock -name {free_clk} [get_ports {free_clk}] -period {37.037} -waveform {0.000 18.518}',
    'define_attribute {p:free_clk} {PAP_IO_DIRECTION} {INPUT}',
    'define_attribute {p:free_clk} {PAP_IO_LOC} {D18}',
    'define_attribute {p:free_clk} {PAP_IO_VCCIO} {3.3}',
    'define_attribute {p:free_clk} {PAP_IO_STANDARD} {LVCMOS33}',
    'define_attribute {p:rst_board} {PAP_IO_DIRECTION} {INPUT}',
    'define_attribute {p:rst_board} {PAP_IO_LOC} {C22}',
    'define_attribute {p:rst_board} {PAP_IO_VCCIO} {3.3}',
    'define_attribute {p:rst_board} {PAP_IO_STANDARD} {LVCMOS33}',
    'define_attribute {p:uart_txd} {PAP_IO_DIRECTION} {OUTPUT}',
    'define_attribute {p:uart_txd} {PAP_IO_LOC} {C24}',
    'define_attribute {p:uart_txd} {PAP_IO_VCCIO} {3.3}',
    'define_attribute {p:uart_txd} {PAP_IO_STANDARD} {LVCMOS33}',
    'define_attribute {p:uart_txd} {PAP_IO_DRIVE} {8}'
) | Set-Content -LiteralPath (Join-Path $OutputDir 'window_board.fdc') -Encoding Ascii

Push-Location $OutputDir
try {
    & $PdsShell -file impl.tcl *> (Join-Path $OutputDir 'pds_console.log')
    if ($LASTEXITCODE -ne 0) { throw "PDS failed; see $OutputDir" }
} finally {
    Pop-Location
}
$sbit = Join-Path $OutputDir 'generate_bitstream\mac_conv_window_board_top.sbit'
if (!(Test-Path -LiteralPath $sbit -PathType Leaf)) {
    throw "Candidate bitstream missing: $sbit"
}
$timing = Get-Content -LiteralPath (
    Join-Path $OutputDir 'report_timing\mac_conv_window_board_top.rtr') -Raw
$wns = [regex]::Match($timing,
    '(?m)^\s*free_clk\s+free_clk\s+(-?\d+\.\d+)\s+\d+\.\d+\s+\d+\s+\d+')
if (!$wns.Success) { throw 'PDS setup WNS not found' }
if ([double]$wns.Groups[1].Value -lt 0) {
    throw "Board candidate setup failed: WNS=$($wns.Groups[1].Value) ns"
}
$hash = (Get-FileHash -LiteralPath $sbit -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Output "MAC_CONV_WINDOW_BOARD_BUILD_PASS sbit=$sbit sha256=$hash wns_ns=$($wns.Groups[1].Value)"
