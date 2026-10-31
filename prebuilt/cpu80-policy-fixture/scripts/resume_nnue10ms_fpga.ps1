param(
    [string]$MappedDir = 'build/nnue10ms/final_shared_ram_fpga',
    [string]$OutputDir = 'build/nnue10ms/final_timing0_fpga',
    [ValidateRange(0,1000)][int]$HoldThresholdPs = 0,
    [string]$PdsShell = 'G:/fpga/PDS_2022.2-SP6.4/bin/pds_shell.exe'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (![IO.Path]::IsPathRooted($MappedDir)) { $MappedDir = Join-Path $root $MappedDir }
if (![IO.Path]::IsPathRooted($OutputDir)) { $OutputDir = Join-Path $root $OutputDir }
$MappedDir = [IO.Path]::GetFullPath($MappedDir)
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
if ($MappedDir -eq $OutputDir -or (Test-Path -LiteralPath $OutputDir) -or
    [IO.Directory]::GetParent($MappedDir).FullName -ne [IO.Directory]::GetParent($OutputDir).FullName) {
    throw 'Use a new sibling directory so cached project source paths remain valid'
}
$sourceHashFile = Join-Path $MappedDir 'stage2_sources.sha256'
function Test-CachedSources {
    foreach ($line in Get-Content -LiteralPath $sourceHashFile) {
        if ($line -notmatch '^([0-9a-f]{64})  (.+)$') { throw 'Invalid source manifest' }
        $expected = $Matches[1]; $relative = $Matches[2]
        $actual = (Get-FileHash -LiteralPath (Join-Path $root $relative) -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $expected) { throw "Cached source mismatch: $relative" }
    }
}
Test-CachedSources
[IO.Directory]::CreateDirectory($OutputDir) | Out-Null
foreach ($name in @('compile','synthesize','constraint_check','device_map')) {
    Copy-Item -LiteralPath (Join-Path $MappedDir $name) -Destination $OutputDir -Recurse
}
foreach ($name in @('cpu_v2_soc.fdc','bootrom.hex','font8x16.hex','header_bitmap.hex',
                    'header_logo_rgb332.hex','stage2_sources.sha256')) {
    Copy-Item -LiteralPath (Join-Path $MappedDir $name) -Destination $OutputDir
}
$project = [IO.File]::ReadAllText((Join-Path $MappedDir 'impl.pds'))
$project = [regex]::Replace($project,
    '(?s)(\(_command cmd_pnr\s*\(_gci_state \(_integer )\d+(\)\))','${1}0${2}')
foreach ($option in @('fix_hold_violation_threshold','fix_hold_violation_threshold_for_clock_path_cross_srb')) {
    $pattern = '\(_option '+$option+' \(_integer \d+\)\)'
    if ([regex]::Matches($project,$pattern).Count -ne 1) { throw "Missing option: $option" }
    $project = [regex]::Replace($project,$pattern,"(_option $option (_integer $HoldThresholdPs))")
}
[IO.File]::WriteAllText((Join-Path $OutputDir 'impl.pds'),$project,[Text.UTF8Encoding]::new($false))
Push-Location $OutputDir
try {
    & $PdsShell -project impl.pds -run gen_bit_stream *> pds_console.log
    $pdsExit = $LASTEXITCODE
} finally { Pop-Location }
if ($pdsExit -ne 0) { throw "Resumed PDS flow failed: $OutputDir" }
Test-CachedSources
$resource = Get-Content -LiteralPath (Join-Path $OutputDir 'device_map/run.log') -Raw
foreach ($name in @('APM','FF','LUT','DRM')) {
    $match = [regex]::Match($resource,'(?m)^\|\s*'+$name+'\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|')
    if (!$match.Success -or [double]$match.Groups[1].Value -gt [double]$match.Groups[2].Value) {
        throw "Missing or over-capacity resource: $name"
    }
}
$timing = Get-Content -LiteralPath (Join-Path $OutputDir 'report_timing/soc_v2_top.rtr') -Raw
$setup = [regex]::Match($timing,'(?s)Setup Summary\(Slow Corner\):(.*?)Hold Summary\(Slow Corner\):')
$slacks = @([regex]::Matches($setup.Groups[1].Value,
    '(?m)^\s*\S+\s+\S+\s+(-?\d+\.\d+)\s+-?\d+\.\d+\s+\d+\s+\d+\s*$') |
    ForEach-Object { [double]$_.Groups[1].Value })
if (!$setup.Success -or !$slacks.Count -or
    $timing -notmatch 'Design Summary\s*:\s*All Constraints Met\.') { throw 'Timing acceptance failed' }
$wns = ($slacks | Measure-Object -Minimum).Minimum
if ($wns -lt 0) { throw "Setup failed: $wns ns" }
$sbit = Join-Path $OutputDir 'generate_bitstream/soc_v2_top.sbit'
$sha = (Get-FileHash -LiteralPath $sbit -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Output "NNUE10MS_RESUMED_FPGA_PASS wns_ns=$wns sha256=$sha sbit=$sbit hold_margin_ps=$HoldThresholdPs"
