param(
    [string]$PdsShell = 'G:\fpga\PDS_2022.2-SP6.4\bin\pds_shell.exe',
    [string]$OutputDir = ''
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$OutputDir) { $OutputDir = Join-Path $root ('build\vision\apm_pair_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff')) }
if (![IO.Path]::IsPathRooted($OutputDir)) { $OutputDir = Join-Path $root $OutputDir }
if ((Test-Path -LiteralPath $OutputDir) -and @(Get-ChildItem -LiteralPath $OutputDir).Count) {
    throw 'Use an empty output directory for the standalone probe'
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$OutputDir = (Resolve-Path -LiteralPath $OutputDir).Path
$source = Join-Path $root 'sim\mac_apm_s8_pair_probe.sv'
$sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
@(
    ('add_design "' + $source.Replace('\','/') + '"'),
    'set_arch -family Logos2 -device PG2L100H -speedgrade -6 -package FBG676',
    'compile -top_module mac_apm_s8_pair_probe',
    'synthesize -ads -selected_syn_tool_opt 2',
    'dev_map'
) | Set-Content -LiteralPath (Join-Path $OutputDir 'impl.tcl') -Encoding Ascii
Push-Location $OutputDir
try {
    & $PdsShell -file impl.tcl *> (Join-Path $OutputDir 'pds_console.log')
    if ($LASTEXITCODE -ne 0) { throw 'Standalone APM probe PDS failed' }
} finally { Pop-Location }
if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sourceHash) {
    throw 'Standalone probe source changed during mapping'
}
$report = Get-Content -LiteralPath (Join-Path $OutputDir 'device_map\run.log') -Raw
$fields = @{}
foreach ($name in @('APM','LUT','FF','DRM')) {
    $match = [regex]::Match($report,'(?m)^\|\s*'+$name+'\s*\|\s*([\d.]+)\s*\|')
    if (!$match.Success) { throw "Missing standalone resource field: $name" }
    $fields[$name] = [double]$match.Groups[1].Value
}
if ($fields.APM -ne 1 -or $fields.LUT -gt 128 -or $fields.FF -gt 32 -or $fields.DRM -ne 0) {
    throw ('Standalone pair probe resource budget failed: ' + ($fields | ConvertTo-Json -Compress))
}
$evidence = @{
    schema_version=1; source_sha256=$sourceHash; resources=$fields
    source='sim/mac_apm_s8_pair_probe.sv'; standalone_arithmetic_only=$true
    array_integrated=$false; board_pass=$false; physical_timing_pass=$false
}
$evidence | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $OutputDir 'resource_evidence.json') -Encoding UTF8
Write-Output "APM_S8_PAIR_MAP_PASS apm=$($fields.APM) lut=$($fields.LUT) ff=$($fields.FF) drm=$($fields.DRM) array_integrated=False"
