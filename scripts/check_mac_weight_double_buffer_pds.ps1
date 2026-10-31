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
    $OutputDir = Join-Path $root ('build\vision\weight_pds_' +
        (Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$OutputDir = (Resolve-Path -LiteralPath $OutputDir).Path
$rtl = (Join-Path $root 'rtl\mac_accel\mac_weight_double_buffer.v').Replace('\', '/')
$wrapper = (Join-Path $root 'sim\mac_weight_pds_top.v').Replace('\', '/')
@(
    "add_design `"$rtl`"",
    "add_design `"$wrapper`"",
    'add_constraint "weight.fdc"',
    'set_arch -family Logos2 -device PG2L100H -speedgrade -6 -package FBG676',
    'compile -top_module mac_weight_pds_top',
    'synthesize -ads -selected_syn_tool_opt 2',
    'dev_map',
    'pnr',
    'report_timing'
) | Set-Content -LiteralPath (Join-Path $OutputDir 'impl.tcl') -Encoding Ascii
'create_clock -name {clk} [get_ports {clk}] -period {10.000} -waveform {0.000 5.000}' |
    Set-Content -LiteralPath (Join-Path $OutputDir 'weight.fdc') -Encoding Ascii

Push-Location $OutputDir
try {
    & $PdsShell -file impl.tcl *> (Join-Path $OutputDir 'pds_console.log')
    if ($LASTEXITCODE -ne 0) { throw "PDS failed; see $OutputDir" }
} finally {
    Pop-Location
}
$timing = Get-Content -LiteralPath (
    Join-Path $OutputDir 'report_timing\mac_weight_pds_top.rtr') -Raw
$resource = Get-Content -LiteralPath (
    Join-Path $OutputDir 'device_map\run.log') -Raw
$wns = [regex]::Match($timing,
    '(?m)^\s*clk\s+clk\s+(-?\d+\.\d+)\s+\d+\.\d+\s+\d+\s+\d+')
if (!$wns.Success) { throw 'PDS setup WNS not found' }
$fields = @{}
foreach ($name in @('APM', 'FF', 'LUT', 'DRM')) {
    $value = [regex]::Match($resource,
        '(?m)^\|\s*' + $name + '\s*\|\s*([\d.]+)\s*\|')
    if (!$value.Success) { throw "PDS resource count missing: $name" }
    $fields[$name] = $value.Groups[1].Value
}
if ([double]$wns.Groups[1].Value -lt 0) {
    throw "Standalone 100 MHz setup failed: WNS=$($wns.Groups[1].Value) ns"
}
$hash = (Get-FileHash -LiteralPath $rtl -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Output "MAC_WEIGHT_DOUBLE_BUFFER_PDS_PASS rtl_sha256=$hash wns_ns=$($wns.Groups[1].Value) apm=$($fields.APM) ff=$($fields.FF) lut=$($fields.LUT) drm=$($fields.DRM) report=$OutputDir"
