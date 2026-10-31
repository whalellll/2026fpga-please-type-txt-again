param(
    [switch]$ValidateOnly,
    [switch]$VerifyWithPds,
    [string]$PdsShell = ''
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd('\')
& (Join-Path $PSScriptRoot 'sync_cpu.ps1') -Check
$pds = Join-Path $root 'pds'
$projectPath = Join-Path $pds 'soc_gui.pds'
$project = [IO.File]::ReadAllText($projectPath)
$flow = [IO.File]::ReadAllText((Join-Path $pds 'soc.tcl'))
$postFlow = [IO.File]::ReadAllText((Join-Path $pds 'soc_post_synth.tcl'))
. (Join-Path $PSScriptRoot 'build_snapshot.ps1')
Assert-FpgaDdrRouteInput $root $project
if ([regex]::Matches($flow, '(?m)^add_constraint "ddr3_test\.rcf"\s*$').Count -ne 1) {
    throw 'Tcl flow must register the reviewed DDR RCF exactly once'
}
foreach ($constraint in @('soc.fdc','ddr3_test.rcf')) {
    if ([regex]::Matches($postFlow, '(?m)^add_constraint "' +
            [regex]::Escape($constraint) + '"\s*$').Count -ne 1) {
        throw "Post-synthesis Tcl must register $constraint exactly once"
    }
}
if ((Get-Item -LiteralPath $pds).Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'PDS asset staging directory must not be a link'
}

# Check every design, constraint and expanded IP source against this checkout.
$relativeFiles = @([regex]::Matches($project, '\(_(?:file|ip|ip_source_item)\s+"([^"]+)"') |
    ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
foreach ($relative in $relativeFiles) {
    if ([IO.Path]::IsPathRooted($relative) -or $relative -match '^[A-Za-z]:|\\') {
        throw "GUI project contains a machine-specific path: $relative"
    }
    $resolved = [IO.Path]::GetFullPath((Join-Path $pds $relative))
    if (!$resolved.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase) -or
        !(Test-Path -LiteralPath $resolved -PathType Leaf)) {
        throw "GUI source is missing or outside the project: $relative"
    }
    if ((Get-Item -LiteralPath $resolved).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "GUI source must be a regular file: $relative"
    }
}
$guiInputs = @([regex]::Matches($project, '\(_(?:file|ip)\s+"([^"]+)"') |
    ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
$tclInputs = @([regex]::Matches($flow, 'add_(?:design|constraint)\s+"([^"]+)"') |
    ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
if (@(Compare-Object $guiInputs $tclInputs).Count) { throw 'GUI design/IP/constraint list differs from the Tcl flow' }
$fdcPath = Join-Path $pds 'soc.fdc'
$fdcText = [IO.File]::ReadAllText($fdcPath)
$drmBudget = @([regex]::Matches($fdcText,
    '(?m)^\s*define_global_attribute\s+\{syn_allowed_resources\}\s+\{blockrams=(\d+)\}\s*$'))
if ($guiInputs -notcontains 'soc.fdc' -or $drmBudget.Count -ne 1 -or
    $drmBudget[0].Groups[1].Value -ne '140') {
    throw 'GUI and Tcl must share the reviewed FDC global DRM budget of 140'
}
foreach ($marker in @('(_family Logos2)', '(_device PG2L100H)', '(_speedgrade -6)',
    '(_package FBG676)', '(_option top_module (_string "soc_top"))',
    '(_option selected_syn_tool_opt (_integer 2))', '(_option system_verilog (_switch ON))', '(_option plc_decongestion (_integer 4))',
    '(_option gplace_seed (_integer 3))',
    '(_option optimize_multi_corner_timing (_switch ON))',
    '(_option mode (_string "performance"))', '(_option fix_hold_violation_threshold (_integer 200))',
    '(_option fix_hold_violation (_switch ON))', '(_option create_bin_file (_switch ON))',
    '(_option report_max_skew (_switch ON))',
    '(_option prj_work_dir (_string "."))', '(_option prj_impl_dir (_string "."))')) {
    if (!$project.Contains($marker)) { throw "GUI configuration is missing: $marker" }
}
if (!$flow.Contains('set_arch -family Logos2 -device PG2L100H -speedgrade -6 -package FBG676') -or
    !$flow.Contains('compile -top_module soc_top -system_verilog') -or
    !$flow.Contains('synthesize -ads -selected_syn_tool_opt 2') -or
    !$postFlow.Contains('set_arch -family Logos2 -device PG2L100H -speedgrade -6 -package FBG676') -or
    !$postFlow.Contains('dev_map -input_db_file "synthesize/soc_top_syn.adf"') -or
    !$postFlow.Contains('pnr -plc_decongestion 4 -gplace_seed 3 -optimize_multi_corner_timing -fix_hold_violation -mode performance -fix_hold_violation_threshold 200') -or
    !$postFlow.Contains('report_timing -report_max_skew') -or
    !$postFlow.Contains('gen_bit_stream -force_to_run -create_bit_file TRUE -create_bin_file')) {
    throw 'Two-stage Tcl flow changed: regenerate and review the GUI project configuration'
}
foreach ($command in @('compile','synthesize','dev_map','pnr','report_timing','gen_bit_stream')) {
    $before = [regex]::Matches($flow, '(?m)^' + $command + '\b').Count
    $after = [regex]::Matches($postFlow, '(?m)^' + $command + '\b').Count
    if ($before -ne $(if ($command -in @('compile','synthesize')) { 1 } else { 0 }) -or
        $after -ne $(if ($command -in @('compile','synthesize')) { 0 } else { 1 })) {
        throw "PDS $command stage is missing or duplicated"
    }
}
if ([regex]::Matches($postFlow, '(?m)^add_design\b').Count -ne 0) {
    throw 'Post-synthesis project must import only the audited ADF'
}
$assets = [ordered]@{
    'bootrom.hex' = 'artifacts/bootrom.hex'
    'font8x16.hex' = 'rtl/video/font8x16.hex'
    'header_bitmap.hex' = 'rtl/video/header_bitmap.hex'
    'header_logo_rgb332.hex' = 'rtl/video/header_logo_rgb332.hex'
    'scripts/meminit/zero_1024.hex' = 'rtl/cpu/meminit/zero_1024.hex'
    'scripts/meminit/zero_2048.hex' = 'rtl/cpu/meminit/zero_2048.hex'
    'scripts/meminit/zero_4096.hex' = 'rtl/cpu/meminit/zero_4096.hex'
}
foreach ($name in $assets.Keys) {
    $source = Join-Path $root $assets[$name]
    if (!(Test-Path -LiteralPath $source -PathType Leaf)) { throw "Missing ROM asset: $source" }
    if ((Get-Item -LiteralPath $source).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "ROM asset must be a regular file: $source"
    }
    $target = Join-Path $pds $name
    if (Test-Path -LiteralPath $target) {
        $item = Get-Item -LiteralPath $target -Force
        if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Refusing to overwrite a linked or directory asset target: $target"
        }
    }
    if (!$ValidateOnly) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $target -Force
    }
}

if ($VerifyWithPds) {
    if (!$PdsShell) {
        $candidates = @('D:\LJL\WORK\pango\PDS_2022.2-SP6.4\bin\pds_shell.exe',
            'G:\fpga\PDS_2022.2-SP6.4\bin\pds_shell.exe')
        if ($env:PDS_ROOT) { $candidates = @((Join-Path $env:PDS_ROOT 'bin/pds_shell.exe')) + $candidates }
        $PdsShell = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    }
    if (!$PdsShell -or !(Test-Path -LiteralPath $PdsShell -PathType Leaf)) {
        throw 'Pass -PdsShell or set PDS_ROOT for the optional PDS open check'
    }
    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ('soc_pds_open_' + [guid]::NewGuid().ToString('N'))
    $checkout = Join-Path $tempRoot 'portable checkout'
    $checkPds = Join-Path $checkout 'pds'
    try {
        New-Item -ItemType Directory -Path $checkPds -Force | Out-Null
        Copy-Item -LiteralPath $projectPath -Destination $checkPds
        foreach ($relative in $relativeFiles) {
            $source = [IO.Path]::GetFullPath((Join-Path $pds $relative))
            $target = [IO.Path]::GetFullPath((Join-Path $checkPds $relative))
            if (!$target.StartsWith($checkout + '\', [StringComparison]::OrdinalIgnoreCase)) {
                throw 'Portable project copy escaped its temporary checkout'
            }
            New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
            Copy-Item -LiteralPath $source -Destination $target
        }
        foreach ($name in $assets.Keys) {
            New-Item -ItemType Directory -Path (Split-Path -Parent (Join-Path $checkPds $name)) -Force | Out-Null
            Copy-Item -LiteralPath (Join-Path $root $assets[$name]) -Destination (Join-Path $checkPds $name)
        }
        $openPath = (Join-Path $checkPds 'soc_gui.pds').Replace('\', '/')
        $process = New-Object Diagnostics.Process
        $process.StartInfo.FileName = $PdsShell
        $process.StartInfo.Arguments = '-work_dir "' + $checkPds + '"'
        $process.StartInfo.WorkingDirectory = $checkPds
        $process.StartInfo.UseShellExecute = $false
        $process.StartInfo.CreateNoWindow = $true
        $process.StartInfo.RedirectStandardInput = $true
        $process.StartInfo.RedirectStandardOutput = $true
        $process.StartInfo.RedirectStandardError = $true
        try {
            [void]$process.Start()
            $stdoutTask = $process.StandardOutput.ReadToEndAsync()
            $stderrTask = $process.StandardError.ReadToEndAsync()
            $process.StandardInput.WriteLine('open_project "' + $openPath + '"')
            $process.StandardInput.WriteLine('exit')
            $process.StandardInput.Close()
            if (!$process.WaitForExit(30000)) {
                $process.Kill()
                $process.WaitForExit()
                throw 'PDS project open exceeded its 30 second limit'
            }
            $exitCode = $process.ExitCode
            $outputText = $stdoutTask.Result + "`n" + $stderrTask.Result
        } finally { $process.Dispose() }
        # PDS wraps long paths and braces those containing spaces.
        if ($exitCode -ne 0 -or $outputText -match '(?m)^\s*E:' -or
            $outputText -notmatch '(?s)Executing : open_project \{?.*soc_gui\.pds\}?\s+successfully\.') {
            throw "PDS failed to open the portable project: $outputText"
        }
        Write-Output 'PDS_GUI_PORTABLE_COPY_OPEN_PASS (PDS engine; no compile/synthesis/place/route)'
    } finally {
        # Only delete this owned, resolved temporary tree; never traverse links.
        $resolvedTemp = [IO.Path]::GetFullPath($tempRoot)
        $tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
        if ($resolvedTemp.StartsWith($tempBase + '\', [StringComparison]::OrdinalIgnoreCase) -and
            (Test-Path -LiteralPath $resolvedTemp)) {
            $links = @(Get-Item -LiteralPath $resolvedTemp -Force) +
                @(Get-ChildItem -LiteralPath $resolvedTemp -Recurse -Force)
            if (@($links | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
                throw "Refusing to clean linked temporary paths: $resolvedTemp"
            }
            Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
        }
    }
}
Write-Output "PDS_GUI_SOURCE_INPUTS_PASS inputs=$($guiInputs.Count) files=$($relativeFiles.Count)"
if (!$ValidateOnly) { Write-Output "PDS_GUI_READY $projectPath" }
