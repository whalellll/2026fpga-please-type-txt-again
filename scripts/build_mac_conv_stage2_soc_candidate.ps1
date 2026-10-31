param(
    [string]$PdsShell = 'G:\fpga\PDS_2022.2-SP6.4\bin\pds_shell.exe',
    [string]$OutputDir = '',
    [ValidateSet(1,2,3)][int]$PlacementDecongestion = 2,
    [ValidateRange(1,2147483647)][int]$PlacementSeed = 1,
    [ValidateRange(1,2147483647)][int]$RouteSeed = 1,
    [ValidateRange(0,1000)][int]$HoldThresholdPs = 200,
    [ValidateRange(1,30)][int]$HoldFixIterations = 6,
    [switch]$OptimizeMultiCornerTiming,
    [switch]$OptimizeHoldDuringRoute,
    [ValidateRange(0,200)][int]$ClockTreeHoldMarginPs = 0,
    [ValidateRange(0,10)][int]$RouteConstraintIterations = 0,
    [ValidateRange(0,1)][double]$RouteConstraintSlackNs = 0.1,
    [string]$ComputeCoreOverride = '',
    [string]$MacCoreOverride = '',
    [string]$DmaKernelOverride = '',
    [string]$ConvWindowOverride = '',
    [string]$ExtraPlacementFdc = '',
    [string]$ExtraPlacementPcf = '',
    [switch]$StopAfterMap
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if ($ExtraPlacementFdc) {
    if (![IO.Path]::IsPathRooted($ExtraPlacementFdc)) {
        $ExtraPlacementFdc = Join-Path $root $ExtraPlacementFdc
    }
    $ExtraPlacementFdc = [IO.Path]::GetFullPath($ExtraPlacementFdc)
    if (!(Test-Path -LiteralPath $ExtraPlacementFdc -PathType Leaf) -or
        !$ExtraPlacementFdc.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Extra placement constraints must be an existing file within this worktree'
    }
}
if ($ExtraPlacementPcf) {
    if (![IO.Path]::IsPathRooted($ExtraPlacementPcf)) {
        $ExtraPlacementPcf = Join-Path $root $ExtraPlacementPcf
    }
    $ExtraPlacementPcf = [IO.Path]::GetFullPath($ExtraPlacementPcf)
    if (!(Test-Path -LiteralPath $ExtraPlacementPcf -PathType Leaf) -or
        !$ExtraPlacementPcf.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Extra placement PCF must be an existing file within this worktree'
    }
    foreach ($pcfLine in Get-Content -LiteralPath $ExtraPlacementPcf) {
        if ($pcfLine -match '^\s*(#.*)?$') { continue }
        if ($pcfLine -notmatch '^def_inst_site \{I_ips_ddr_top/u_ddrphy_top/[^}]+\} CLM[AS]_\d+_\d+(?: [A-Z0-9]+)?$') {
            throw 'Extra PCF accepts only strict DDR PHY data-path placement commands'
        }
    }
}
$sourceOverride = @{}
if ($ComputeCoreOverride) {
    $overridePath = [IO.Path]::GetFullPath($ComputeCoreOverride)
    if (!(Test-Path -LiteralPath $overridePath -PathType Leaf)) {
        throw "Compute core override missing: $overridePath"
    }
    $sourceOverride['rtl/mac_accel/mac_conv_compute_core.v'] = $overridePath
}
if ($MacCoreOverride) {
    $overridePath = [IO.Path]::GetFullPath($MacCoreOverride)
    if (!(Test-Path -LiteralPath $overridePath -PathType Leaf)) {
        throw "MAC core override missing: $overridePath"
    }
    $sourceOverride['rtl/mac_accel/MacAccelCore.v'] = $overridePath
}
if ($DmaKernelOverride) {
    $overridePath = [IO.Path]::GetFullPath($DmaKernelOverride)
    if (!(Test-Path -LiteralPath $overridePath -PathType Leaf)) {
        throw "DMA kernel override missing: $overridePath"
    }
    $sourceOverride['rtl/mac_accel/mac_accel_dma_kernel.v'] = $overridePath
}
if ($ConvWindowOverride) {
    $overridePath = [IO.Path]::GetFullPath($ConvWindowOverride)
    if (!(Test-Path -LiteralPath $overridePath -PathType Leaf)) {
        throw "Convolution window override missing: $overridePath"
    }
    $sourceOverride['rtl/mac_accel/mac_conv_window.v'] = $overridePath
}
if (!(Test-Path -LiteralPath $PdsShell -PathType Leaf)) {
    throw "PDS shell not found: $PdsShell"
}
if (!$OutputDir) {
    $OutputDir = Join-Path $root ('build\vision\conv_soc_' +
        (Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$OutputDir = (Resolve-Path -LiteralPath $OutputDir).Path
$template = Get-Content -LiteralPath (Join-Path $root 'pds\soc_v2_cpu_v2.tcl')
$newSources = @(
    'rtl/audio/audio_mmio.v',
    'rtl/audio/i2s_audio_duplex.v',
    'rtl/mac_accel/MacAccelCore.v',
    'rtl/mac_accel/mac_accel_dma_kernel.v',
    'rtl/mac_accel/pff1_stagea_gather.v',
    'rtl/mac_accel/mac_conv_descriptor_guard.v',
    'rtl/mac_accel/mac_conv_window.v',
    'rtl/mac_accel/mac_conv_input_dma.v',
    'rtl/mac_accel/mac_weight_double_buffer.v',
    'rtl/mac_accel/mac_conv_weight_dma.v',
    'rtl/mac_accel/mac_conv_read_arbiter2.v',
    'rtl/mac_accel/mac_conv_compute_core.v',
    'rtl/mac_accel/mac_conv_compact_packer.v',
    'rtl/mac_accel/mac_conv_compact_writer.v',
    'rtl/mac_accel/mac_conv_rw_arbiter2.v',
    'rtl/mac_accel/mac_conv_mmio_frontend.v',
    'rtl/mac_accel/mac_accel_ddr_kernel_top.v',
    'rtl/soc/soc_v2_top.v'
)
$commands = [Collections.Generic.List[string]]::new()
foreach ($relative in $newSources) {
    if (!$template.Contains('add_design "../' + $relative + '"')) {
        throw "PDS project is missing stage-2 source: $relative"
    }
}
foreach ($line in $template) {
    if ($line -match '^add_design "\.\./(.+)"$') {
        $relative = $Matches[1]
        $path = if ($sourceOverride.ContainsKey($relative)) {
            $sourceOverride[$relative]
        } else {
            Join-Path $root $relative
        }
        $path = $path.Replace('\', '/')
        if (!(Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Missing PDS source: $path"
        }
        $commands.Add("add_design `"$path`"")
    } elseif ($line -match '^add_constraint ') {
        $commands.Add('add_constraint "cpu_v2_soc.fdc"')
        if ($ExtraPlacementFdc) { $commands.Add('add_constraint "placement_extra.fdc"') }
    } elseif ($line -match '^dev_map\b') {
        $commands.Add($line)
        if ($ExtraPlacementPcf -and !$StopAfterMap) {
            # PDS evaluates plain Tcl while parsing, before dev_map creates PCF.
            # Map first in a separate invocation so parsing can open the file.
            # PDS queues these commands and also executes them after dev_map.
            # Reapply after mapping: override_pcf FALSE alone does not preserve
            # external PCF edits when the script recreates the project.
            $commands.Add('set placement_out [open {device_map/soc_v2_top.pcf} a]')
            $commands.Add('set placement_extra [open {placement_extra.pcf} r]')
            $commands.Add('puts $placement_out [read $placement_extra]')
            $commands.Add('close $placement_extra')
            $commands.Add('close $placement_out')
        }
    } elseif ($line -match '^pnr\b') {
        if (!$StopAfterMap) {
            $pnrCommand = "pnr -plc_decongestion $PlacementDecongestion -gplace_seed $PlacementSeed -groute_seed $RouteSeed -fix_hold_violation -fix_hold_violation_threshold $HoldThresholdPs -fix_hold_violation_threshold_for_clock_path_cross_srb $HoldThresholdPs"
            if ($HoldFixIterations -ne 6) { $pnrCommand += " -fix_hold_violation_iterations $HoldFixIterations" }
            if ($OptimizeMultiCornerTiming) { $pnrCommand += ' -optimize_multi_corner_timing' }
            if ($OptimizeHoldDuringRoute) { $pnrCommand += ' -fix_hold_violation_in_route TRUE' }
            if ($PSBoundParameters.ContainsKey('ClockTreeHoldMarginPs')) {
                $pnrCommand += " -fix_hold_violation_threshold_for_clk_tree $ClockTreeHoldMarginPs"
            }
            if ($RouteConstraintIterations) {
                $routeTarget = $RouteConstraintSlackNs.ToString([Globalization.CultureInfo]::InvariantCulture)
                $pnrCommand += " -enable_route_constraint_iterate -route_constraint_iterate_times $RouteConstraintIterations -route_constraint_slack $routeTarget -route_constraint_max_timing_path 40"
            }
            $commands.Add($pnrCommand)
        }
    } elseif ($line -match '^(set_arch|compile|synthesize|dev_map|pnr|report_timing|gen_bit_stream)\b') {
        if (!$StopAfterMap -or $line -notmatch '^(pnr|report_timing|gen_bit_stream)\b') {
            $commands.Add($line)
        }
    }
}
if (@($commands | Where-Object { $_ -match '^add_design ' }).Count -lt 50) {
    throw 'PDS source list is unexpectedly short'
}
# Native PDS exports impl.tcl regardless of -project_name. Reserve that name
# for the export and keep the Tcl input in a different file.
$commands | Set-Content -LiteralPath (Join-Path $OutputDir 'flow_input.tcl') -Encoding Ascii
if ($ExtraPlacementFdc) {
    Copy-Item -LiteralPath $ExtraPlacementFdc -Destination (Join-Path $OutputDir 'placement_extra.fdc')
}
if ($ExtraPlacementPcf) {
    Copy-Item -LiteralPath $ExtraPlacementPcf -Destination (Join-Path $OutputDir 'placement_extra.pcf')
}
foreach ($name in @('cpu_v2_soc.fdc','bootrom.hex','font8x16.hex',
                    'header_bitmap.hex','header_logo_rgb332.hex')) {
    Copy-Item -LiteralPath (Join-Path $root "pds\$name") -Destination $OutputDir
}
$buildInputs = @($template | ForEach-Object {
    if ($_ -match '^add_design "\.\./(.+)"$') { $Matches[1] }
}) + @('pds/soc_v2_cpu_v2.tcl', 'pds/cpu_v2_soc.fdc',
    'pds/bootrom.hex', 'pds/font8x16.hex', 'pds/header_bitmap.hex',
    'pds/header_logo_rgb332.hex')
if ($ExtraPlacementFdc) { $buildInputs += $ExtraPlacementFdc.Substring($root.Length + 1).Replace('\','/') }
if ($ExtraPlacementPcf) { $buildInputs += $ExtraPlacementPcf.Substring($root.Length + 1).Replace('\','/') }
$hashes = foreach ($relative in $buildInputs) {
    $source = if ($sourceOverride.ContainsKey($relative)) {
        $sourceOverride[$relative]
    } else {
        Join-Path $root $relative
    }
    $hash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $relative"
}
$hashes | Set-Content -LiteralPath (Join-Path $OutputDir 'stage2_sources.sha256') -Encoding Ascii
$sourceHashesAtStart = @{}
foreach ($relative in $buildInputs) {
    $source = if ($sourceOverride.ContainsKey($relative)) {
        $sourceOverride[$relative]
    } else {
        Join-Path $root $relative
    }
    $sourceHashesAtStart[$relative] = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
}

Push-Location $OutputDir
try {
    if ($ExtraPlacementPcf -and !$StopAfterMap) {
        $mapCommands = [Collections.Generic.List[string]]::new()
        foreach ($command in $commands) {
            $mapCommands.Add($command)
            if ($command -match '^dev_map\b') { break }
        }
        $mapCommands | Set-Content -LiteralPath 'impl_map.tcl' -Encoding Ascii
        & $PdsShell -file impl_map.tcl -project_name candidate_map *> 'pds_map_console.log'
        if ($LASTEXITCODE -ne 0) { throw 'PDS mapping invocation failed' }
        if (Select-String -LiteralPath 'pds_map_console.log' -Pattern '^E:' -Quiet) {
            throw 'PDS mapping reported a native error'
        }
        $mappedPcf = Join-Path $OutputDir 'device_map\soc_v2_top.pcf'
        if (!(Test-Path -LiteralPath $mappedPcf -PathType Leaf)) {
            throw 'Native mapping did not create its placement PCF'
        }
    }
    $flowInputHash = (Get-FileHash -LiteralPath 'flow_input.tcl' -Algorithm SHA256).Hash
    & $PdsShell -file flow_input.tcl -project_name candidate_impl *> (Join-Path $OutputDir 'pds_console.log')
    if ($LASTEXITCODE -ne 0) { throw "PDS failed; see $OutputDir" }
    if (Select-String -LiteralPath 'pds_console.log' -Pattern '^E:' -Quiet) {
        throw "PDS reported a native error; see $OutputDir"
    }
    if ((Get-FileHash -LiteralPath 'flow_input.tcl' -Algorithm SHA256).Hash -ne $flowInputHash) {
        throw 'PDS modified its flow input script'
    }
} finally {
    Pop-Location
}
foreach ($relative in $buildInputs) {
    $source = if ($sourceOverride.ContainsKey($relative)) {
        $sourceOverride[$relative]
    } else {
        Join-Path $root $relative
    }
    $currentHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
    if ($currentHash -ne $sourceHashesAtStart[$relative]) {
        throw "PDS source changed during build: $relative"
    }
}
$resource = Get-Content -LiteralPath (Join-Path $OutputDir 'device_map\run.log') -Raw
$fields = @{}
$available = @{}
foreach ($name in @('APM','FF','LUT','DRM')) {
    $match = [regex]::Match($resource,
        '(?m)^\|\s*' + $name + '\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|')
    if (!$match.Success) { throw "Missing PDS resource count: $name" }
    $fields[$name] = $match.Groups[1].Value
    $available[$name] = $match.Groups[2].Value
    if ([double]$fields[$name] -gt [double]$available[$name]) {
        throw "Candidate exceeds $name capacity: $($fields[$name])/$($available[$name])"
    }
}
if ($StopAfterMap) {
    Write-Output "MAC_CONV_SOC_MAP_PASS apm=$($fields.APM) ff=$($fields.FF) lut=$($fields.LUT) drm=$($fields.DRM) report=$OutputDir"
    exit 0
}
if ($ExtraPlacementPcf) {
    $placeLog = [IO.File]::ReadAllText((Join-Path $OutputDir 'place_route\run.log'))
    foreach ($placement in Get-Content -LiteralPath $ExtraPlacementPcf) {
        if ($placement -notmatch '^def_inst_site ') { continue }
        if (!$placeLog.Contains('Executing : ' + $placement + ' successfully')) {
            throw "PDS did not validate requested placement: $placement"
        }
    }
}
$sbit = Join-Path $OutputDir 'generate_bitstream\soc_v2_top.sbit'
if (!(Test-Path -LiteralPath $sbit -PathType Leaf)) {
    throw "Candidate bitstream missing: $sbit"
}
$timing = Get-Content -LiteralPath (
    Join-Path $OutputDir 'report_timing\soc_v2_top.rtr') -Raw
$setup = [regex]::Match($timing,
    '(?s)Setup Summary\(Slow Corner\):(.*?)Hold Summary\(Slow Corner\):')
if (!$setup.Success) { throw 'PDS slow-corner setup summary not found' }
$slacks = @([regex]::Matches($setup.Groups[1].Value,
    '(?m)^\s*\S+\s+\S+\s+(-?\d+\.\d+)\s+-?\d+\.\d+\s+\d+\s+\d+\s*$') |
    ForEach-Object { [double]$_.Groups[1].Value })
if (!$slacks.Count) { throw 'PDS setup slack rows not found' }
$wns = ($slacks | Measure-Object -Minimum).Minimum
if ($timing -notmatch 'Design Summary\s*:\s*All Constraints Met\.' -or $wns -lt 0) {
    throw "Candidate timing failed: global slow-corner WNS=$wns ns"
}
$hash = (Get-FileHash -LiteralPath $sbit -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Output "MAC_CONV_SOC_BUILD_PASS sbit=$sbit sha256=$hash wns_ns=$wns apm=$($fields.APM) ff=$($fields.FF) lut=$($fields.LUT) drm=$($fields.DRM)"
