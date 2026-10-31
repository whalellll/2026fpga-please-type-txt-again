# Shared, fail-closed FPGA input/evidence contract. No tools are launched here.
. (Join-Path $PSScriptRoot 'clock_policy.ps1')
. (Join-Path $PSScriptRoot 'timing_scope.ps1')

function Test-FpgaVision32Profile([string]$Root) {
    $path=Join-Path $Root 'rtl/soc/soc_top.v'
    if (!(Test-Path -LiteralPath $path)) { return $false }
    $top=[IO.File]::ReadAllText($path)
    $decl=[regex]::Matches($top,'(?m)^\s*parameter integer ENABLE_VISION32_CANDIDATE = ([01])\b')
    if ($decl.Count -eq 0) { return $false }
    if ($decl.Count -ne 1) { throw 'Ambiguous vision32 profile declaration' }
    if ($decl[0].Groups[1].Value -eq '0') { return $false }
    if ([regex]::Matches($top,'\.ENABLE_VISION32\s*\(\s*ENABLE_VISION32_CANDIDATE\s*\)').Count -ne 1 -or
        [regex]::Matches($top,'(?m)^\s*parameter integer ENABLE_CONV_CANDIDATE = 1\b').Count -ne 1) {
        throw 'Vision32 must be connected to the enabled convolution port'
    }
    return $true
}

# UG042003 section 2.8.5 and the installed HMIC_S 1.10 generator require
# both gate nets for BANK_NUM=2. The blank before [n] is part of the net name.
# Four target measured compact-bank DDR PHY setup paths; the final CPU FTQ
# net targets a measured 30.486 ns route delay. These candidate priorities
# are not vendor-required constraints or a timing pass.
function Get-FpgaDdrRouteLines {
    return @(
        'def_route -prior_net {I_ips_ddr_top/u_ddrphy_top/ddrphy_ioclk_gate [0]}'
        'def_route -prior_net {I_ips_ddr_top/u_ddrphy_top/ddrphy_ioclk_gate [1]}'
        'def_route -prior_net {I_ips_ddr_top/u_ddrphy_top/ddrphy_slice_top/i_dqs_group[1].ddrphy_data_slice/adj_wrdqs [0]}'
        'def_route -prior_net {I_ips_ddr_top/u_ddrphy_top/ddrphy_slice_top/i_dqs_group[0].ddrphy_data_slice/adj_wrdq [61]}'
        'def_route -prior_net {I_ips_ddr_top/u_ddrphy_top/ddrphy_slice_top/i_dqs_group[0].ddrphy_data_slice/adj_wrdq [10]}'
        'def_route -prior_net {I_ips_ddr_top/u_ddrphy_top/ddrphy_slice_top/i_dqs_group[2].ddrphy_data_slice/adj_wrdata_mask [7]}'
        'def_route -prior_net {u_cpu/u_cpu_wrapper/u_cpu/core/frontend/ftqAlloc [3]}'
        'def_route -prior_net {u_cpu/u_cpu_wrapper/u_cpu/core/backend/_u_fu_mdu_io_wbData [0]}'
        'def_route -prior_net {u_cpu/u_cpu_wrapper/u_cpu/core/backend/u_rs_alu1/issueUsesFast}'
        'def_route -prior_net {u_cpu/u_cpu_wrapper/u_cpu/core/backend/_u_fu_alu0_io_wbData [20]}'
        'def_route -prior_net {u_video/s4_fx [1]}'
        'def_route -prior_net {u_cpu/u_cpu_wrapper/u_cpu/core/backend/_u_fu_mdu_io_wbValid}'
        'def_route -prior_net {u_cpu/u_cpu_wrapper/u_cpu/core/backend/_u_rs_alu0_io_issueRobid [1]}'
        'def_route -prior_net {u_eth/tx_pos [5]}'
        'def_route -prior_net {I_ips_ddr_top/u_ddrphy_top/ddrphy_slice_top/i_dqs_group[0].ddrphy_data_slice/adj_wrdq [41]}'
        'def_route -prior_net {I_ips_ddr_top/u_ddrphy_top/ddrphy_slice_top/i_dqs_group[2].ddrphy_data_slice/adj_wrdq [58]}'
        'def_route -prior_net {u_cpu/u_cpu_wrapper/u_cpu/core/backend/u_rob/memShadowRobid [4]}'
        'def_route -prior_net {u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_lsu/stqPa_1 [26]}'
        'def_route -prior_net {u_cpu/u_cpu_wrapper/u_cpu/core/frontend/pdInsts_2 [28]}'
        'def_route -prior_net {u_cpu/u_cpu_wrapper/u_cpu/core/backend/u_rs_alu1/N1294 [0]}'
    )
}

function Assert-FpgaDdrRouteInput([string]$Root, [string]$ProjectText) {
    $path = Get-FpgaSafePath $Root 'pds/ddr3_test.rcf'
    $actual = @([IO.File]::ReadAllLines($path) | ForEach-Object { $_.Trim() } |
        Where-Object { $_ -and !$_.StartsWith('#') })
    $expected = @(Get-FpgaDdrRouteLines)
    if ($actual.Count -ne $expected.Count -or ($actual -join "`n") -cne ($expected -join "`n")) {
        throw 'Route RCF must contain exactly the twenty reviewed priority nets (two vendor gates and eighteen measured candidate nets)'
    }
    # Check the route widget, not a same-named file in an unrelated GUI task.
    $pattern = '(?s)\(_widget\s+wgt_edit_route_cons\s+' +
        '\(_attribute\s+_click_to_run\s+\(_switch\s+ON\)\)\s+' +
        '\(_input\s+\(_file\s+"ddr3_test\.rcf"\s+\(_format\s+rcf\)' +
        '\s+\(_timespec\s+"[^"]*"\)\s*\)\s*\)\s*\)'
    if ([regex]::Matches($ProjectText, $pattern).Count -ne 1 -or
        [regex]::Matches($ProjectText, '\(_file\s+"ddr3_test\.rcf"').Count -ne 1) {
        throw 'DDR RCF is missing from the native PDS route input widget'
    }
}

function Assert-FpgaDdrRouteRegistration {
    param([string]$Root, [string]$ProjectText, [string]$ParseStdoutText,
        [string]$StdoutText, [string]$PnrNetlistText)
    Assert-FpgaDdrRouteInput $Root $ProjectText
    foreach ($name in @('soc.fdc','ddr3_test.rcf')) {
        $pattern = '(?m)^Executing : add_constraint ["{]?' + [regex]::Escape($name) +
            '["}]?\s+successfully\.\s*$'
        if ([regex]::Matches($ParseStdoutText, $pattern).Count -ne 1) {
            throw "DDR RCF/FDC registration has no unique successful native PDS parse record: $name"
        }
    }
    # PDS records add_constraint in the native post-project parser log, not in
    # impl.tcl or the later -project route stdout. Priority nets are checked
    # against the latter and the actual PnR netlist.
    foreach ($line in Get-FpgaDdrRouteLines) {
        $net = $line.Substring('def_route -prior_net {'.Length).TrimEnd('}')
        $commandPattern = [regex]::Escape($line)
        # PDS removes braces around simple Tcl words in its native log.
        # Count both exact spellings together, rejecting mixed duplicates.
        if ($net -cmatch '^[A-Za-z0-9_/]+$') {
            $bare = 'def_route -prior_net ' + $net
            $commandPattern = '(?:' + $commandPattern + '|' + [regex]::Escape($bare) + ')'
        }
        $success = '(?m)^Executing : ' + $commandPattern + ' successfully\.\s*$'
        if ([regex]::Matches($StdoutText, $success).Count -ne 1) {
            throw "DDR RCF has no unique successful PDS priority execution: $line"
        }
        if ($PnrNetlistText -cnotmatch ('(?m)^' + [regex]::Escape($net) + ';\r?$')) {
            throw "DDR RCF target is absent from the actual PnR netlist: $net"
        }
    }
}

function Get-FpgaFirmwareNames {
    return @('bootloader', 'mac_selftest', 'mac_benchmark',
        'xiangqi_sparse_eval_selftest', 'xiangqi_fb_demo')
}

function Get-FpgaStagedAssets {
    return [ordered]@{
        'pds/bootrom.hex' = 'artifacts/bootrom.hex'
        'pds/font8x16.hex' = 'rtl/video/font8x16.hex'
        'pds/header_bitmap.hex' = 'rtl/video/header_bitmap.hex'
        'pds/header_logo_rgb332.hex' = 'rtl/video/header_logo_rgb332.hex'
        'pds/scripts/meminit/zero_1024.hex' = 'rtl/cpu/meminit/zero_1024.hex'
        'pds/scripts/meminit/zero_2048.hex' = 'rtl/cpu/meminit/zero_2048.hex'
        'pds/scripts/meminit/zero_4096.hex' = 'rtl/cpu/meminit/zero_4096.hex'
    }
}

function Assert-SdWriteOwnershipEvidence {
    param([object]$Evidence,[object]$Snapshot,[string]$SnapshotSha256,[string]$NetlistSha256)
    if($Evidence.schema -ne 1 -or $Evidence.status -cne 'SD_WRITE_OWNERSHIP_ADS_PASS_NOT_STA_OR_BOARD' -or
       $Evidence.run_id -cne $Snapshot.run_id -or $Evidence.native_input_binding_verified -ne $true -or
       $Evidence.input_snapshot_sha256 -cne $SnapshotSha256 -or $Evidence.netlist_sha256 -cne $NetlistSha256 -or
       $Evidence.checker_sha256 -cne $Snapshot.inputs.'scripts/audit_sd_write_ownership_ads.py' -or
       $Evidence.source_boundary_cuts -ne $false -or !$Evidence.bank_cpu_ownership_exclusive -or
       !$Evidence.bank_rx_ownership_exclusive -or @($Evidence.banks).Count -ne 2 -or
       ((@($Evidence.banks | ForEach-Object {$_.bank} | Sort-Object) -join ',') -cne '0,1')) {
        throw 'SD ownership evidence does not bind the frozen checker, run, netlist and guard scope'
    }
    foreach($bankProof in $Evidence.banks){
        if($bankProof.capacity_bits_per_view -ne 4096 -or $bankProof.byte_groups -ne 4 -or
           $bankProof.read_views -ne 2 -or !$bankProof.write_guard_proven -or !$bankProof.rx_coverage_proven -or
           !$bankProof.strobes_proven -or !$bankProof.nonvacuous_cpu_and_rx){throw 'Incomplete SD ownership evidence'}
    }
}

function Test-FpgaDedicatedLinearHoldProfile([string]$Root) {
    $top=Join-Path $Root 'rtl/soc/soc_top.v'
    $core=Join-Path $Root 'rtl/mac_accel/pikafish_mlp_dedicated.v'
    return (Test-Path -LiteralPath $top -PathType Leaf) -and (Test-Path -LiteralPath $core -PathType Leaf) -and
        ([IO.File]::ReadAllText($top) -match '\.PIKAFISH_ONLY\s*\(\s*1\s*\)') -and
        ([IO.File]::ReadAllText($core).Contains('u_linear_hold_lut'))
}

function Get-FpgaInputPaths([string]$Root) {
    $paths = @('VERSION', 'config/clocks.json', 'config/timing_scope_baseline.json', 'pds/soc.tcl', 'pds/soc_post_synth.tcl',
        'pds/soc.fdc', 'pds/ddr3_test.rcf', 'pds/soc_gui.pds',
        'pds/audit_cpu_sys_cdc_ads.py',
        'artifacts/bootrom.hex', 'artifacts/SONG.PCM')
    if (Test-Path -LiteralPath (Join-Path $Root 'scripts/audit_pikafish_linear_hold_ads.py')) {
        $paths += 'scripts/audit_pikafish_linear_hold_ads.py'
    }
    if (Test-Path -LiteralPath (Join-Path $Root 'pds/gui1080_tage.pcf') -PathType Leaf) { $paths += 'pds/gui1080_tage.pcf' }
    if (Test-Path -LiteralPath (Join-Path $Root 'pds/cpu75_csr_reference.pcf') -PathType Leaf) {
        $paths += 'pds/cpu75_csr_reference.pcf','pds/cpu75_csr_reference.json','scripts/audit_cpu_csr_placement.py'
    }
    if (Test-Path -LiteralPath (Join-Path $Root 'config/display.json') -PathType Leaf) {
        $paths += 'config/display.json'
    }
    foreach ($directory in @('rtl', 'sw', 'ip')) {
        foreach ($file in Get-ChildItem -LiteralPath (Join-Path $Root $directory) -Recurse -File -Force) {
            $relative = $file.FullName.Substring($Root.TrimEnd('\').Length + 1).Replace('\', '/')
            if ($file.Extension -in @('.log', '.lock', '.elf', '.o', '.obj', '.pyc', '.tmp', '.bak') -or
                $relative -match '(^|/)(logbackup|__pycache__|\.settings|pnr)(/|$)' -or
                $file.Name -eq '.last_generated') { continue }
            $paths += $relative
        }
    }
    foreach ($file in Get-ChildItem -LiteralPath (Join-Path $Root 'scripts') -File) {
        if ($file.Name -match '^(build_|gen_hdmi_header|bin_to_hex)' -or
            $file.Name -in @('riscv_toolchain.ps1', 'prepare_pds_project.ps1',
                'sync_cpu.ps1', 'project_files.ps1', 'audit_project.ps1', 'release_version.ps1',
                'check_clock_config.ps1', 'set_clock_candidate.ps1', 'clock_policy.ps1', 'timing_scope.ps1', 'bounded_process.cs',
                'audit_cpu_ads.py', 'audit_integrated60_ads.py', 'audit_voice_nnue75_ads.py', 'audit_cpu85_half_ads.py', 'audit_conv_weight_hold_ads.py', 'audit_frontend_metadata_ads.py', 'ads_bdd.py', 'audit_cpu_dedicated_pll_ads.py', 'dense_pe_resource_contract.py', 'conv_resource_contract.py', 'vision32_resource_contract.py', 'vision32_cache_contract.py', 'nnue_voice_resource_contract.py', 'pikafish_dedicated_resource_contract.py', 'audit_cpu_prepared_shift_ads.py', 'audit_icache_pad_ads.py', 'audit_rob_owner_ads.py', 'audit_uart_tx_pad_ads.py', 'audit_mac_weight_pad_ads.py', 'audit_rob_vaddr_pad_ads.py', 'audit_sd_write_ownership_ads.py', 'audit_fallback_target_pad_ads.py', 'ads_frontend_ib_cone.py', 'audit_ib_rf_metadata_ads.py')) {
            $paths += 'scripts/' + $file.Name
        }
    }
    foreach ($name in Get-FpgaFirmwareNames) {
        $paths += "artifacts/$name.elf", "artifacts/$name.bin", "artifacts/$name.build.json"
    }
    if ((Test-Path -LiteralPath (Join-Path $Root 'rtl/mac_accel/mac_conv_weight_dma.v')) -and
        ([IO.File]::ReadAllText((Join-Path $Root 'rtl/mac_accel/mac_conv_weight_dma.v'))).Contains('u_line_write_hold_lut')) {
        $paths += 'scripts/gui1080_mul/native_hier_cone.py', 'scripts/gui1080_mul/native_hier_cone_vector_v2.py'
    }
    return @($paths | Sort-Object -Unique)
}

function Get-FpgaOutputPaths {
    param([string]$Root = '')
    $paths = @('artifacts/soc_top.sbit', 'artifacts/soc_top.bin',
        'artifacts/bootrom.hex', 'artifacts/SONG.PCM', 'artifacts/timing_summary.txt',
        'artifacts/build_snapshot.json', 'artifacts/cpu_ads_controls.json', 'artifacts/icache_pad_ads.json',
        'artifacts/preflight_gate.json', 'artifacts/cpu_sys_cdc_ads_pre.json', 'artifacts/cpu_sys_cdc_ads.json',
        'artifacts/pds_synth_history.txt', 'artifacts/pds_post_history.txt',
        'artifacts/pds_synth_project.txt', 'artifacts/pds_post_project.txt',
        'artifacts/pds_synth_parse_stdout.txt', 'artifacts/pds_synth_parse_stderr.txt',
        'artifacts/pds_post_parse_stdout.txt', 'artifacts/pds_post_parse_stderr.txt',
        'artifacts/pds_synth_stdout.txt', 'artifacts/pds_synth_stderr.txt',
        'artifacts/pds_post_stdout.txt', 'artifacts/pds_post_stderr.txt',
        'artifacts/pds_synth_constraints.txt', 'artifacts/pds_post_constraints.txt',
        'artifacts/pds_post_map_constraints.txt',
        'artifacts/pds_synth_flow.txt', 'artifacts/synth_resource_report.txt',
        'artifacts/final_timing_report.txt', 'artifacts/final_timing_xml.xml')
    foreach ($name in Get-FpgaFirmwareNames) {
        $paths += "artifacts/$name.elf", "artifacts/$name.bin", "artifacts/$name.build.json"
    }
    if ($Root -and (Test-Path -LiteralPath (Join-Path $Root 'pds/gui1080_tage.pcf') -PathType Leaf)) {
        $paths += 'artifacts/gui1080_placement.json','artifacts/gui1080_placement_export.pcf'
    }
    if ($Root -and (Test-Path -LiteralPath (Join-Path $Root 'pds/cpu75_csr_reference.pcf') -PathType Leaf)) {
        $paths += 'artifacts/cpu75_csr_placement.json','artifacts/cpu75_csr_placement_export.pcf'
    }
    if ($Root -and !(Test-FpgaVision32Profile $Root) -and (Test-Path -LiteralPath (Join-Path $Root 'rtl/mac_accel/mac_conv_weight_dma.v')) -and
        ([IO.File]::ReadAllText((Join-Path $Root 'rtl/mac_accel/mac_conv_weight_dma.v'))).Contains('u_line_write_hold_lut')) {
        $paths += 'artifacts/conv_weight_hold_ads.json'
    }
    return @($paths | Sort-Object -Unique)
}

function Get-FpgaRecipeInputPaths {
    param([string]$Root, [switch]$AllowHdmiRegeneration)
    # These must stay unchanged while the software builders execute. Only an
    # explicit redraw permits changes to the two generated HDMI image files.
    return @(Get-FpgaInputPaths $Root | Where-Object {
        $_ -notlike 'artifacts/*' -and
        (!$AllowHdmiRegeneration -or
            $_ -notin @('rtl/video/header_bitmap.hex', 'rtl/video/header_logo_rgb332.hex'))
    })
}

function Get-FpgaSafePath([string]$Root, [string]$Relative) {
    if (!$Relative -or $Relative -match '(^|/)\.\.?(/|$)|\\|:' -or [IO.Path]::IsPathRooted($Relative)) {
        throw "Unsafe build snapshot path: $Relative"
    }
    $base = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    $path = [IO.Path]::GetFullPath((Join-Path $base $Relative))
    if (!$path.StartsWith($base + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Build snapshot path escaped root: $Relative"
    }
    $cursor = $path
    while ($cursor.Length -ge $base.Length) {
        if ((Test-Path -LiteralPath $cursor) -and
            ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Build snapshot path contains a link: $Relative"
        }
        if ($cursor -eq $base) { break }
        $cursor = Split-Path -Parent $cursor
    }
    return $path
}

function Get-FpgaHashMap([string]$Root, [string[]]$Paths) {
    $map = [ordered]@{}
    foreach ($relative in $Paths | Sort-Object -Unique) {
        $path = Get-FpgaSafePath $Root $relative
        if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing build input: $relative" }
        $map[$relative] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    return $map
}

function ConvertTo-FpgaMap($Value) {
    $map = [ordered]@{}
    if ($Value -is [Collections.IDictionary]) {
        foreach ($key in $Value.Keys) { $map[[string]$key] = $Value[$key] }
    } elseif ($null -ne $Value) {
        foreach ($property in $Value.PSObject.Properties) { $map[$property.Name] = $property.Value }
    }
    return $map
}

function Assert-FpgaMap($Expected, $Actual, [string]$Label) {
    $left = ConvertTo-FpgaMap $Expected
    $right = ConvertTo-FpgaMap $Actual
    if (!$left.Count -or $left.Count -ne $right.Count) { throw "$Label inventory changed or is incomplete" }
    foreach ($key in $left.Keys) {
        if (!$right.Contains($key) -or $left[$key] -cne $right[$key]) {
            throw "${Label} mismatch: $key"
        }
    }
}

function Assert-FpgaFirmware([string]$Root) {
    . (Join-Path $Root 'scripts/riscv_toolchain.ps1')
    foreach ($name in Get-FpgaFirmwareNames) {
        $metadata = [IO.File]::ReadAllText((Get-FpgaSafePath $Root "artifacts/$name.build.json")) | ConvertFrom-Json
        $hash = (Get-FileHash -LiteralPath (Get-FpgaSafePath $Root "artifacts/$name.bin") -Algorithm SHA256).Hash.ToLowerInvariant()
        $elfHash = (Get-FileHash -LiteralPath (Get-FpgaSafePath $Root "artifacts/$name.elf") -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($metadata.binary -cne "$name.bin" -or $metadata.binary_sha256 -cne $hash -or
            $metadata.compiler_target -cne $CpuTarget -or $metadata.compiler_version -cne $CpuGccVersion -or
            $metadata.march -cne $CpuMarch -or $metadata.abi -cne $CpuAbi -or
            $metadata.compiler_sha256 -notmatch '^[0-9a-f]{64}$' -or
            $metadata.elf_sha256 -cne $elfHash -or !$metadata.optimization -or
            $metadata.elf_metadata.ElfClass -ne 'ELF32' -or
            $metadata.elf_metadata.Flags -notmatch '^0x0(?:\s|$)' -or
            $metadata.code_validation.Result -notlike 'RV32IMA mnemonic/width whitelist*' -or
            $metadata.code_validation.BytesChecked -le 0 -or
            $metadata.code_validation.ExplicitIllegalInstructionFixture -ne $false) {
            throw "Firmware build metadata does not bind the current RV32IMA binary: $name"
        }
    }
    # The FPGA actually consumes HEX, not BIN. Verify the complete padded ROM.
    $bytes = [IO.File]::ReadAllBytes((Join-Path $Root 'artifacts/bootloader.bin'))
    $words = [IO.File]::ReadAllLines((Join-Path $Root 'artifacts/bootrom.hex'))
    if ($bytes.Length -gt 131072 -or $words.Length -ne 32768) { throw 'Invalid 128 KiB boot ROM size' }
    $padded = New-Object byte[] 131072
    [Array]::Copy($bytes, $padded, $bytes.Length)
    for ($i = 0; $i -lt $words.Length; $i++) {
        if ($words[$i] -notmatch '^[0-9a-fA-F]{8}$' -or
            $words[$i] -ine [BitConverter]::ToUInt32($padded, $i * 4).ToString('x8')) {
            throw "Boot ROM does not encode the recorded bootloader binary at word $i"
        }
    }
}

function Get-FpgaGitObjectHash([string]$Kind, [byte[]]$Bytes) {
    $prefix = [Text.Encoding]::ASCII.GetBytes($Kind + ' ' + $Bytes.Length + [char]0)
    $digest = [Security.Cryptography.SHA1]::Create()
    try {
        [void]$digest.TransformBlock($prefix, 0, $prefix.Length, $prefix, 0)
        [void]$digest.TransformFinalBlock($Bytes, 0, $Bytes.Length)
        return [BitConverter]::ToString($digest.Hash).Replace('-','').ToLowerInvariant()
    } finally { $digest.Dispose() }
}

function Read-FpgaGitBytes([string]$Root, [string]$Arguments) {
    $git = (Get-Command git -ErrorAction Stop).Source
    $start = [Diagnostics.ProcessStartInfo]::new($git, '-C "' + $Root + '" ' + $Arguments)
    $start.UseShellExecute = $false; $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true; $start.RedirectStandardError = $true
    $process = [Diagnostics.Process]::new(); $process.StartInfo = $start
    $buffer = [IO.MemoryStream]::new()
    $started = $false
    try {
        if (!$process.Start()) { throw 'Cannot start bounded Git identity reader' }
        $started = $true
        $copy = $process.StandardOutput.BaseStream.CopyToAsync($buffer)
        $errors = $process.StandardError.ReadToEndAsync()
        if (!$copy.Wait(20000) -or !$process.WaitForExit(20000) -or !$errors.Wait(20000)) {
            throw 'Git identity reader exceeded its bounded wait'
        }
        if ($process.ExitCode -ne 0) { throw "Git identity read failed: $($errors.Result)" }
        return ,$buffer.ToArray()
    } finally {
        if ($started -and !$process.HasExited) { $process.Kill(); [void]$process.WaitForExit(5000) }
        $buffer.Dispose(); $process.Dispose()
    }
}

function ConvertFrom-FpgaGitTree([byte[]]$Bytes) {
    $entries = [ordered]@{}; $offset = 0
    while ($offset -lt $Bytes.Length) {
        $end = $offset
        while ($end -lt $Bytes.Length -and $Bytes[$end] -ne 0) { $end++ }
        if ($end + 21 -gt $Bytes.Length) { throw 'Malformed Git tree proof' }
        $header = [Text.Encoding]::UTF8.GetString($Bytes, $offset, $end - $offset)
        if ($header -cnotmatch '^([0-7]+) ([^/\\]+)$') { throw 'Malformed Git tree entry' }
        $mode = $Matches[1]; $name = $Matches[2]
        if ($entries.Contains($name)) { throw 'Duplicate Git tree entry' }
        $oid = [BitConverter]::ToString($Bytes, $end + 1, 20).Replace('-','').ToLowerInvariant()
        $entries[$name] = [pscustomobject]@{mode=$mode;oid=$oid}
        $offset = $end + 21
    }
    return $entries
}

function Assert-FpgaGitIdentity([string]$Root, $Inputs, $Identity) {
    if ($null -eq $Identity -or $Identity.schema -ne 1 -or $Identity.object_format -cne 'sha1' -or
        $Identity.commit_sha1 -cnotmatch '^[0-9a-f]{40}$' -or $Identity.all_frozen_inputs_match_commit -ne $true) {
        throw 'Missing V6.5 frozen-input Git implementation proof'
    }
    $commitBytes = [Convert]::FromBase64String($Identity.commit_object_base64)
    if ((Get-FpgaGitObjectHash 'commit' $commitBytes) -cne $Identity.commit_sha1) { throw 'Git commit proof hash differs' }
    $commit = [Text.Encoding]::UTF8.GetString($commitBytes)
    if ($commit -cnotmatch '^tree ([0-9a-f]{40})\n') { throw 'Git commit proof lacks its root tree' }
    $rootTree = $Matches[1]
    $trees = ConvertTo-FpgaMap $Identity.tree_objects_base64
    $blobs = ConvertTo-FpgaMap $Identity.input_blob_sha1
    $inputsMap = ConvertTo-FpgaMap $Inputs
    if ($blobs.Count -ne $inputsMap.Count) { throw 'Git proof input inventory differs' }
    $decoded = @{}
    foreach ($oid in $trees.Keys) {
        $bytes = [Convert]::FromBase64String($trees[$oid])
        if ((Get-FpgaGitObjectHash 'tree' $bytes) -cne $oid) { throw 'Git tree proof hash differs' }
        $decoded[$oid] = ConvertFrom-FpgaGitTree $bytes
    }
    foreach ($relative in $inputsMap.Keys) {
        $tree = $rootTree; $parts = $relative.Split('/'); $entry = $null
        for ($index=0; $index -lt $parts.Length; $index++) {
            if (!$decoded.ContainsKey($tree) -or !$decoded[$tree].Contains($parts[$index])) { throw "Git proof omits input: $relative" }
            $entry = $decoded[$tree][$parts[$index]]
            if ($index -lt $parts.Length - 1) {
                if ($entry.mode -cne '40000') { throw "Git proof parent is not a tree: $relative" }
                $tree = $entry.oid
            }
        }
        if ($entry.mode -notin @('100644','100755') -or !$blobs.Contains($relative) -or $entry.oid -cne $blobs[$relative]) {
            throw "Git proof input membership differs: $relative"
        }
        if ((Get-FpgaGitObjectHash 'blob' ([IO.File]::ReadAllBytes((Get-FpgaSafePath $Root $relative)))) -cne $entry.oid) {
            throw "Frozen FPGA input differs from implementation commit: $relative"
        }
    }
}

function New-FpgaGitIdentity([string]$Root, $Inputs) {
    $head = [Text.Encoding]::ASCII.GetString((Read-FpgaGitBytes $Root 'rev-parse --verify HEAD')).Trim()
    if ($head -cnotmatch '^[0-9a-f]{40}$') { throw 'V6.5 freeze requires a SHA-1 Git implementation commit' }
    $commitBytes = Read-FpgaGitBytes $Root ('cat-file commit ' + $head)
    $commit = [Text.Encoding]::UTF8.GetString($commitBytes)
    if ($commit -cnotmatch '^tree ([0-9a-f]{40})\n') { throw 'Git implementation commit lacks root tree' }
    $rootTree = $Matches[1]; $trees = [ordered]@{}; $decoded = @{}; $blobs = [ordered]@{}
    foreach ($relative in $Inputs.Keys) {
        $tree = $rootTree; $parts = $relative.Split('/'); $entry = $null
        for ($index=0; $index -lt $parts.Length; $index++) {
            if (!$trees.Contains($tree)) {
                $bytes = Read-FpgaGitBytes $Root ('cat-file tree ' + $tree)
                $trees[$tree] = [Convert]::ToBase64String($bytes)
                $decoded[$tree] = ConvertFrom-FpgaGitTree $bytes
            }
            if (!$decoded[$tree].Contains($parts[$index])) { throw "Frozen input is not in implementation HEAD: $relative" }
            $entry = $decoded[$tree][$parts[$index]]
            if ($index -lt $parts.Length - 1) { $tree = $entry.oid }
        }
        $blobs[$relative] = $entry.oid
    }
    $identity = [pscustomobject][ordered]@{schema=1;object_format='sha1';commit_sha1=$head;
        commit_object_base64=[Convert]::ToBase64String($commitBytes);tree_objects_base64=$trees;
        input_blob_sha1=$blobs;all_frozen_inputs_match_commit=$true}
    Assert-FpgaGitIdentity $Root $Inputs $identity
    return $identity
}

function Assert-FpgaSnapshot([string]$Root, $Snapshot, [switch]$CheckStaged) {
    if ($Snapshot.schema -ne 1 -or $Snapshot.kind -cne 'fpga-inputs-before-pds' -or
        $Snapshot.run_id -notmatch '^[0-9a-f]{32}$' -or
        $Snapshot.started_utc -notmatch '^\d{4}-\d{2}-\d{2}T.*Z$' -or
        $Snapshot.release -cne ('V' + [IO.File]::ReadAllText((Join-Path $Root 'VERSION')).Trim())) {
        throw 'Missing, obsolete, or foreign FPGA start snapshot'
    }
    [void][datetime]::Parse($Snapshot.started_utc)
    Assert-FpgaMap $Snapshot.inputs (Get-FpgaHashMap $Root (Get-FpgaInputPaths $Root)) 'Frozen FPGA inputs'
    if ($Snapshot.release -ceq 'V6.5') { Assert-FpgaGitIdentity $Root $Snapshot.inputs $Snapshot.implementation_git }
    $assets = Get-FpgaStagedAssets
    Assert-FpgaMap $Snapshot.staged_assets $assets 'Staged asset mapping'
    $expectedStaged = [ordered]@{}
    $inputs = ConvertTo-FpgaMap $Snapshot.inputs
    foreach ($relative in $assets.Keys) { $expectedStaged[$relative] = $inputs[$assets[$relative]] }
    Assert-FpgaMap $Snapshot.staged_hashes $expectedStaged 'Frozen staged ROMs'
    if ($CheckStaged) {
        Assert-FpgaMap $Snapshot.staged_hashes (Get-FpgaHashMap $Root @($assets.Keys)) 'Actual staged ROMs'
    }
    Assert-FpgaFirmware $Root
}

function New-FpgaSnapshot([string]$Root) {
    Assert-FpgaFirmware $Root
    $inputs = Get-FpgaHashMap $Root (Get-FpgaInputPaths $Root)
    $implementation = $null
    if ([IO.File]::ReadAllText((Join-Path $Root 'VERSION')).Trim() -ceq '6.5') {
        $implementation = New-FpgaGitIdentity $Root $inputs
    }
    $assets = Get-FpgaStagedAssets
    $staged = Get-FpgaHashMap $Root @($assets.Keys)
    foreach ($relative in $assets.Keys) {
        if ($staged[$relative] -cne $inputs[$assets[$relative]]) { throw "Staged ROM differs from canonical input: $relative" }
    }
    $id = [guid]::NewGuid().ToString('N')
    $directory = Get-FpgaSafePath $Root "pds/input-snapshots/$id"
    New-Item -ItemType Directory -Path $directory | Out-Null
    # Preserve the actual files, not just mutable working-tree names and mtimes.
    foreach ($relative in @($inputs.Keys) + @($staged.Keys)) {
        $target = Get-FpgaSafePath $directory "files/$relative"
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        Copy-Item -LiteralPath (Get-FpgaSafePath $Root $relative) -Destination $target
    }
    Assert-FpgaMap $inputs (Get-FpgaHashMap (Join-Path $directory 'files') @($inputs.Keys)) 'Copied FPGA inputs'
    Assert-FpgaMap $staged (Get-FpgaHashMap (Join-Path $directory 'files') @($staged.Keys)) 'Copied staged ROMs'
    $snapshot = [pscustomobject][ordered]@{
        schema = 1; kind = 'fpga-inputs-before-pds'; run_id = $id
        started_utc = [datetime]::UtcNow.ToString('o')
        release = 'V' + [IO.File]::ReadAllText((Join-Path $Root 'VERSION')).Trim()
        inputs = $inputs; staged_assets = $assets; staged_hashes = $staged
        implementation_git = $implementation
    }
    Assert-FpgaSnapshot $Root $snapshot -CheckStaged
    $json = ($snapshot | ConvertTo-Json -Depth 6) + "`n"
    [IO.File]::WriteAllText((Join-Path $directory 'snapshot.json'), $json, [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Get-FpgaSafePath $Root 'pds/build_snapshot.json'), $json, [Text.UTF8Encoding]::new($false))
    return $snapshot
}

function Read-FpgaActiveSnapshot([string]$Root, [datetime]$ExpectedStartedUtc) {
    $active = Get-FpgaSafePath $Root 'pds/build_snapshot.json'
    $snapshot = [IO.File]::ReadAllText($active) | ConvertFrom-Json
    Assert-FpgaSnapshot $Root $snapshot -CheckStaged
    $started = [datetime]::Parse($snapshot.started_utc).ToUniversalTime()
    if ($started -ne $ExpectedStartedUtc.ToUniversalTime()) { throw 'Original build start UTC does not match its snapshot' }
    $directory = Get-FpgaSafePath $Root ("pds/input-snapshots/" + $snapshot.run_id)
    $archived = Get-FpgaSafePath $directory 'snapshot.json'
    if ((Get-FileHash -LiteralPath $active -Algorithm SHA256).Hash -ne
        (Get-FileHash -LiteralPath $archived -Algorithm SHA256).Hash) { throw 'Active snapshot differs from original saved snapshot' }
    $inputs = ConvertTo-FpgaMap $snapshot.inputs
    $staged = ConvertTo-FpgaMap $snapshot.staged_hashes
    Assert-FpgaMap $inputs (Get-FpgaHashMap (Join-Path $directory 'files') @($inputs.Keys)) 'Saved original FPGA inputs'
    Assert-FpgaMap $staged (Get-FpgaHashMap (Join-Path $directory 'files') @($staged.Keys)) 'Saved original staged ROMs'
    return $snapshot
}

function Assert-IcachePadAdsEvidence($Result, $Snapshot, [string]$SnapshotHash, [string]$NetlistHash) {
    $inputs = ConvertTo-FpgaMap $Snapshot.inputs
    $bindings = [ordered]@{
        source_rtl_sha256 = 'rtl/cpu/CoreTop.sv'
        source_json_sha256 = 'rtl/cpu/source.json'
        emit_config_sha256 = 'rtl/cpu/emit-config.json'
        checker_sha256 = 'scripts/audit_icache_pad_ads.py'
    }
    if ($Result.schema -ne 1 -or $Result.status -cne 'PASS' -or
        $Result.scope -cne 'INTEGRATED_ADS_ONLY' -or $Result.run_id -cne $Snapshot.run_id -or
        $SnapshotHash -cnotmatch '^[0-9a-f]{64}$' -or $Result.input_snapshot_sha256 -cne $SnapshotHash -or
        $NetlistHash -cnotmatch '^[0-9a-f]{64}$' -or $Result.netlist_sha256 -cne $NetlistHash -or
        $Result.hierarchy -cne 'soc_top/u_cpu/u_cpu_wrapper/u_cpu/core/frontend/cache' -or
        $Result.inputs_unchanged -isnot [bool] -or $Result.inputs_unchanged -ne $true -or
        $Result.post_pnr_physical_retention_proven -isnot [bool] -or $Result.post_pnr_physical_retention_proven -ne $false -or
        $Result.routed_hold_margin_proven -isnot [bool] -or $Result.routed_hold_margin_proven -ne $false) {
        throw 'ICache ADS evidence has missing or foreign run, scope, snapshot, netlist or proof boundaries'
    }
    $expected = [ordered]@{ 'pds/build_snapshot.json' = $SnapshotHash; 'pds/synthesize/soc_top_syn.vm' = $NetlistHash }
    foreach ($field in $bindings.Keys) {
        $path = $bindings[$field]
        if ($inputs[$path] -cnotmatch '^[0-9a-f]{64}$' -or $Result.$field -cne $inputs[$path]) {
            throw "ICache ADS evidence does not bind the frozen input: $path"
        }
        $expected[$path] = $inputs[$path]
    }
    Assert-FpgaMap $expected $Result.input_hashes 'ICache ADS evidence input hashes'
    $c = $Result.connectivity
    if ($c.primitive -cne 'GTP_LUT6D' -or $c.pairs -ne 64 -or $c.bits -ne 128 -or
        $c.init -cne 'CCCCCCCC_AAAAAAAA' -or $c.preservation_attribute -cne 'PAP_DONT_TOUCH' -or
        $c.upstream_ff_bits -ne 128 -or $c.unique_driver_and_two_way_loads -isnot [bool] -or
        $c.unique_driver_and_two_way_loads -ne $true -or $c.bypass -isnot [bool] -or $c.bypass -ne $false -or
        $c.pad_module_sha256 -cnotmatch '^[0-9a-f]{64}$' -or $c.icache_module_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
        @($c.ways).Count -ne 2) {
        throw 'ICache ADS evidence lacks the complete 64-pair / 128-bit preserved identity path'
    }
    for ($i = 0; $i -lt 2; $i++) {
        $way = $c.ways[$i]
        $module = @('wayMem_128x256', 'wayMem_128x256_unq4')[$i]
        if ($way.instance -cne "wayMem_${i}_ext" -or $way.module -cne $module -or
            $way.mapping -cnotin @('4_GTP_DRM36K_E1', '256_GTP_RAM128X1SP') -or
            $way.write_bits_checked -ne 256 -or $way.padded_low_bits -ne 128 -or
            $way.module_sha256 -cnotmatch '^[0-9a-f]{64}$') {
            throw "ICache ADS evidence has missing or unsupported actual way $i connections"
        }
    }
}

function Assert-FpgaStageHistory {
    param([string]$Path, [ValidateSet('synthesis','post_synthesis')][string]$Stage)
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) { throw "PDS $Stage history is missing: $Path" }
    $lines = @([IO.File]::ReadAllLines($Path))
    $expected = if ($Stage -eq 'synthesis') {
        [ordered]@{ set_arch=1; compile=1; synthesize=1; dev_map=0;
            pnr=0; report_timing=0; report_power=0; gen_netlist=0; gen_bit_stream=0 }
    } else {
        [ordered]@{ set_arch=0; compile=0; synthesize=0; dev_map=1;
            pnr=1; report_timing=1; report_power=1; gen_netlist=1; gen_bit_stream=1 }
    }
    foreach ($command in $expected.Keys) {
        $count = @($lines | Where-Object { $_ -match ('^' + [regex]::Escape($command) + '\b') }).Count
        if ($count -ne $expected[$command]) {
            throw "PDS $Stage native history has wrong $command count: $count (expected $($expected[$command]))"
        }
    }
    if ($Stage -eq 'post_synthesis' -and
        @($lines | Where-Object { $_ -match '^report_timing\b.*(?:^|\s)-report_max_skew(?:\s|$)' }).Count -ne 1) {
        throw 'PDS post_synthesis native history lacks report_timing -report_max_skew'
    }
}

function Assert-FpgaMaxSkewReport {
    param([string]$XmlPath, [string]$RtrPath, [string]$FdcPath)
    if (!(Test-Path -LiteralPath $XmlPath -PathType Leaf) -or
        !(Test-Path -LiteralPath $RtrPath -PathType Leaf) -or
        !(Test-Path -LiteralPath $FdcPath -PathType Leaf)) {
        throw 'Native Max Skew XML/RTR/FDC evidence is missing'
    }
    $rtr = [IO.File]::ReadAllText($RtrPath)
    # PDS 2022.2-SP6.4 puts Max Skew paths in rtr.db only. The RTR names the
    # command and XML output, but has no textual Max Skew path section.
    if ($rtr -notmatch '(?m)^\|\s*Tcl Command\s*:\s*report_timing -report_max_skew\s*$' -or
        $rtr -notmatch '(?m)^Flow Command:\s*report_timing -report_max_skew\s*$' -or
        $rtr -notmatch '(?m)^Design Summary : All Constraints Met\.\s*$' -or
        $rtr -notmatch '(?m)^\|[^\r\n]*\brtr\.db\s*$') {
        throw 'Final RTR lacks the Max Skew command, XML output, or all-constraints pass'
    }
    $settings = [Xml.XmlReaderSettings]::new()
    $settings.DtdProcessing = [Xml.DtdProcessing]::Prohibit
    $settings.XmlResolver = $null
    $reader = [Xml.XmlReader]::Create($XmlPath, $settings)
    try {
        $doc = [Xml.XmlDocument]::new()
        $doc.XmlResolver = $null
        $doc.Load($reader)
    } catch {
        throw "Native Max Skew XML is malformed: $($_.Exception.Message)"
    } finally { $reader.Close() }
    $fdcLines = @([IO.File]::ReadAllLines($FdcPath))
    $cdcLimit = Assert-SocCdcBounds ($fdcLines -join "`n")
    $pairsByLine = @{}
    foreach ($fifo in @('ar','aw','w','r','b')) {
        foreach ($direction in @('wr','rd')) {
            $source = "u_${fifo}_fifo/${direction}_gray"
            $capture = if ($direction -eq 'wr') { "u_${fifo}_fifo/wr_gray_rd1" } else { "u_${fifo}_fifo/rd_gray_wr1" }
            $pattern = '^set_max_skew -from .*' + [regex]::Escape($source) +
                '.* -to .*' + [regex]::Escape($capture) + '.* ([0-9.]+)\s*$'
            $numbers = @(for ($i = 0; $i -lt $fdcLines.Count; $i++) {
                if ($fdcLines[$i] -match $pattern) { $i + 1 }
            })
            if ($numbers.Count -ne 1) { throw "Reviewed Max Skew FDC pair is missing or ambiguous: ${fifo}_${direction}" }
            $pairsByLine[[string]$numbers[0]] = [pscustomobject]@{
                name = "${fifo}_${direction}"; source = $source; capture = $capture; limit = $cdcLimit
            }
        }
    }
    if ($pairsByLine.Count -ne 10 -or @($fdcLines | Where-Object { $_ -match '^set_max_skew\b' }).Count -ne 10) {
        throw 'Reviewed FDC does not contain exactly ten Max Skew Gray pairs'
    }
    $expectedHeaders = @('Path','Slack','Logic Levels','High Fanout','Start Point','End Point',
        'Launch Clock','Capture Clock','Clock Skew','Data Delay','Required Skew',
        'Actual Skew','Relative Delay','Relative CPR')
    $checked = 0
    foreach ($corner in @('slow','fast')) {
        $id = "report_timing_${corner}_path_max_skew"
        $tables = @($doc.SelectNodes(('/tables/table[@id="' + $id + '"]')))
        if ($tables.Count -ne 1) { throw "Native timing XML lacks one $corner Max Skew table" }
        $table = $tables[0]
        if ($table.GetAttribute('abnormal')) { throw 'Native Max Skew XML marks a table abnormal' }
        $headers = @($table.SelectNodes('./column_headers/data') | ForEach-Object { $_.InnerText.Trim() })
        if ($table.GetAttribute('title') -cne 'Max Skew Path' -or
            ($headers -join '|') -cne ($expectedHeaders -join '|')) {
            throw "Native $corner Max Skew table has unreviewed columns"
        }
        $rows = @($table.SelectNodes('./row'))
        if ($rows.Count -ne 10) { throw "Native $corner Max Skew table does not have ten Gray groups" }
        $seen = @{}
        foreach ($row in $rows) {
            $cells = @($row.SelectNodes('./data') | ForEach-Object { $_.InnerText.Trim() })
            if ($cells.Count -ne 14) {
                throw "Native $corner Max Skew row has no reviewed constraint identity"
            }
            $labelMatch = [regex]::Match($cells[0], '^MaxSkew Path ([0-9.]+)ns, Line Num ([0-9]+)$')
            if (!$labelMatch.Success) {
                throw "Native $corner Max Skew row has no reviewed constraint identity"
            }
            $lineNumber = $labelMatch.Groups[2].Value
            if (!$pairsByLine.ContainsKey($lineNumber) -or $seen.ContainsKey($lineNumber)) {
                throw "Native $corner Max Skew row has an unknown or duplicate FDC line: $lineNumber"
            }
            $pair = $pairsByLine[$lineNumber]
            foreach ($index in @(1,10,11)) {
                if ($cells[$index] -notmatch '^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$') {
                    throw "Native $corner Max Skew row has a nonnumeric timing value"
                }
            }
            $slack = [decimal]::Parse($cells[1], [Globalization.CultureInfo]::InvariantCulture)
            $required = [decimal]::Parse($cells[10], [Globalization.CultureInfo]::InvariantCulture)
            $actual = [decimal]::Parse($cells[11], [Globalization.CultureInfo]::InvariantCulture)
            if ($slack -lt 0 -or $required -ne $pair.limit -or $actual -lt 0 -or
                [decimal]::Parse($labelMatch.Groups[1].Value, [Globalization.CultureInfo]::InvariantCulture) -ne $pair.limit -or
                [Math]::Abs($required - $actual - $slack) -gt [decimal]0.002 -or
                $row.GetAttribute('abnormal') -or $row.InnerText -match '(?i)\bVIOLATED\b') {
                throw "Native $corner Max Skew violation or inconsistent slack: $($pair.name)"
            }
            $branches = @($row.SelectNodes('./row'))
            if ($branches.Count -ne 2) { throw "Native $corner Max Skew group lacks max/min path branches" }
            foreach ($branchName in @('skew for max path','skew for min path')) {
                $branch = @($branches | Where-Object {
                    $_.SelectSingleNode('./data[1]').InnerText.Trim() -ceq $branchName
                })
                if ($branch.Count -ne 1) { throw "Native $corner Max Skew group lacks $branchName" }
                $paths = @($branch[0].SelectNodes('./row'))
                if ($paths.Count -ne 5) { throw "Native $corner Max Skew branch does not cover five Gray bits" }
                $bits = @{}
                foreach ($path in $paths) {
                    $pathCells = @($path.SelectNodes('./data') | ForEach-Object { $_.InnerText.Trim() })
                    if ($pathCells.Count -ne 14 -or $pathCells[1] -notmatch '^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$' -or
                        [decimal]::Parse($pathCells[1], [Globalization.CultureInfo]::InvariantCulture) -lt 0) {
                        throw "Native $corner Max Skew bit path has missing or negative slack"
                    }
                    $launch = [regex]::Match($pathCells[4], [regex]::Escape($pair.source) + '\[([0-4])\]')
                    $capture = [regex]::Match($pathCells[5], [regex]::Escape($pair.capture) + '\[([0-4])\]')
                    if (!$launch.Success -or !$capture.Success -or
                        $launch.Groups[1].Value -cne $capture.Groups[1].Value -or
                        $bits.ContainsKey($launch.Groups[1].Value)) {
                        throw "Native $corner Max Skew bit path misses the reviewed Gray launch/stage1 pair"
                    }
                    $bits[$launch.Groups[1].Value] = $true
                }
                if ($bits.Count -ne 5) { throw "Native $corner Max Skew branch lacks all five Gray bits" }
            }
            $seen[$lineNumber] = $true
            $checked++
        }
        if ($seen.Count -ne 10) { throw "Native $corner Max Skew report does not cover all ten FDC pairs" }
    }
    return [pscustomobject]@{ groups = 10; rows = $checked }
}

function Assert-FpgaPostMapConstraints([string]$Root, [string]$DmrPath) {
    if (!(Test-Path -LiteralPath $DmrPath -PathType Leaf)) { throw 'Native post-map DMR is missing' }
    $fdc = [IO.File]::ReadAllText((Get-FpgaSafePath $Root 'pds/soc.fdc'))
    $dmr = [IO.File]::ReadAllText($DmrPath)
    $fdcLines = @($fdc -split '\r?\n')
    $clocks = @($fdcLines | Where-Object { $_ -match '^create_clock -name \{(?:sys|cpu)_clk\} ' })
    $directives = @($fdcLines | Where-Object {
        $_ -match '^set_(?:max_delay|max_skew|false_path)\b' -and
        ($_.Contains('u_axi_cdc') -or $_.Contains('u_irq_sync'))
    })
    if ($clocks.Count -ne 2 -or $directives.Count -ne 48 -or
        @($directives | Sort-Object -Unique).Count -ne 48) {
        throw 'Reviewed FDC must have two CPU/SYS clocks and 48 unique CDC directives'
    }
    $expectedKinds = [ordered]@{ max_delay=19; max_skew=10; false_path=19 }
    foreach ($kind in $expectedKinds.Keys) {
        if (@($directives | Where-Object { $_ -match ('^set_' + $kind + '\b') }).Count -ne $expectedKinds[$kind]) {
            throw "Reviewed FDC CDC directive count differs: $kind"
        }
    }
    foreach ($line in @($clocks) + @($directives)) {
        $pattern = '(?m)^' + [regex]::Escape($line) + '\r?$'
        if ([regex]::Matches($dmr, $pattern).Count -ne 1) {
            throw "Native post-map DMR lacks one exact FDC directive: $line"
        }
    }
    if ($dmr -match '(?m)^set_clock_groups[^\r\n]*cpu_clk[^\r\n]*sys_clk|^set_clock_groups[^\r\n]*sys_clk[^\r\n]*cpu_clk') {
        throw 'Post-map DMR incorrectly groups CPU and SYS clocks asynchronously'
    }
}

function Assert-FpgaCdcEvidenceRecords($Cdc, [string]$Stage) {
    if ($Cdc.constraints.total_constraints -ne 1171 -or
        $Cdc.constraints.cdc_directives -ne 48 -or
        $Cdc.constraints.gray_directives -ne 30 -or
        $Cdc.constraints.payload_directives -ne 10 -or
        $Cdc.constraints.first_stage_directives -ne 8 -or
        $Cdc.constraints.mapped_endpoint_tags -ne 300 -or
        $Cdc.constraints.mapped_payload_output_tags -ne 298 -or
        $Cdc.constraints.mapped_first_stage_tags -ne 8 -or
        $Cdc.constraints.mapped_second_stage_tags -ne 4 -or
        $Cdc.constraints.errors -ne 0 -or
        $Cdc.constraints.critical_warnings -ne 39 -or
        $Cdc.constraints.warnings -ne 0 -or
        @($Cdc.fifos).Count -ne 10 -or
        @($Cdc.payloads).Count -ne 5 -or
        @($Cdc.first_stage_crossings).Count -ne 4 -or
        @($Cdc.single_bit_synchronizers).Count -ne 5) {
        throw "CPU/SYS CDC $Stage mapped evidence counts are incomplete"
    }
    $fifoKeys = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($record in $Cdc.fifos) {
        if ($record.fifo -notin @('ar','aw','w','r','b') -or
            $record.direction -notin @('wr','rd') -or
            !$fifoKeys.Add("$($record.fifo)/$($record.direction)") -or
            $record.mapped_launch_ff -ne 5 -or $record.mapped_stage1_ff -ne 5 -or
            $record.mapped_stage2_ff -ne 5 -or $record.pap_preserve -ne $true) {
            throw "CPU/SYS CDC $Stage mapped Gray FIFO evidence is incomplete"
        }
        $base = "u_cpu/u_cpu_wrapper/u_axi_cdc/u_$($record.fifo)_fifo"
        $sourceObject = "$base/$($record.direction)_gray[4:0]"
        $captureName = if ($record.direction -eq 'wr') { 'wr_gray_rd1' } else { 'rd_gray_wr1' }
        $captureObject = "$base/$captureName[4:0]"
        foreach ($kind in @('max_delay','max_skew','hold_cut')) {
            $match = $record.fdc_matches.$kind
            if ($match.launch_vector_objects -ne 1 -or
                $match.capture_vector_objects -ne 1 -or
                $match.launch_object -cne $sourceObject -or
                $match.capture_object -cne $captureObject) {
                throw "CPU/SYS CDC $Stage Gray FDC cardinality evidence is incomplete"
            }
        }
    }
    $payloadSpecs = [ordered]@{
        ar = @{ launch='cpu_clk'; clock='sys_clk'; x1=0; x2=19; outputs=38 }
        aw = @{ launch='cpu_clk'; clock='sys_clk'; x1=1; x2=18; outputs=37 }
        w  = @{ launch='cpu_clk'; clock='sys_clk'; x1=1; x2=18; outputs=37 }
        r  = @{ launch='sys_clk'; clock='cpu_clk'; x1=0; x2=18; outputs=36 }
        b  = @{ launch='sys_clk'; clock='cpu_clk'; x1=1; x2=0; outputs=1 }
    }
    $payloadKeys = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($record in $Cdc.payloads) {
        if ($record.fifo -notin @('ar','aw','w','r','b') -or
            !$payloadKeys.Add($record.fifo)) {
            throw "CPU/SYS CDC $Stage payload FIFO identity is incomplete"
        }
        $spec = $payloadSpecs[$record.fifo]
        $instances = @($record.mapped_ram_instances)
        if ($record.launch_clock -cne $spec.launch -or
            $record.capture_clock -cne $spec.clock -or
            $record.mapped_ram_cells -ne ($spec.x1 + $spec.x2) -or
            $record.mapped_ram_x1dp -ne $spec.x1 -or
            $record.mapped_ram_x2dp -ne $spec.x2 -or
            $record.mapped_do_outputs -ne $spec.outputs -or
            $instances.Count -ne $record.mapped_ram_cells -or
            @($instances | Sort-Object -Unique).Count -ne $instances.Count -or
            @($instances | Where-Object { $_ -match '^storage(?:_[0-9_]+)?$' }).Count -ne $instances.Count) {
            throw "CPU/SYS CDC $Stage mapped payload RAM evidence is incomplete"
        }
        $sourceObject = "u_cpu/u_cpu_wrapper/u_axi_cdc/u_$($record.fifo)_fifo/storage"
        foreach ($kind in @('max_delay','hold_cut')) {
            $match = $record.fdc_matches.$kind
            if ($match.launch_array_objects -ne 1 -or
                $match.launch_object -cne $sourceObject -or
                $match.capture_clock -cne $spec.clock) {
                throw "CPU/SYS CDC $Stage payload FDC logical selector is incomplete"
            }
        }
    }
    $syncSpecs = [ordered]@{
        cpu_ready_sys0 = @{ source='cpu_clk'; capture='sys_clk';
            object='u_cpu/u_cpu_wrapper/u_axi_cdc/cpu_ready_sys[1:0]'; second_tags=2 }
        sys_ready_cpu0 = @{ source='sys_clk'; capture='cpu_clk';
            object='u_cpu/u_cpu_wrapper/u_axi_cdc/sys_ready_cpu[1:0]'; second_tags=2 }
        timer_c1 = @{ source='sys_clk'; capture='cpu_clk';
            object='u_cpu/u_cpu_wrapper/u_irq_sync/timer_c1'; second_tags=0 }
        software_c1 = @{ source='sys_clk'; capture='cpu_clk';
            object='u_cpu/u_cpu_wrapper/u_irq_sync/software_c1'; second_tags=0 }
    }
    $syncKeys = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($record in $Cdc.first_stage_crossings) {
        if ($record.name -notin @('cpu_ready_sys0','sys_ready_cpu0','timer_c1','software_c1') -or
            !$syncKeys.Add($record.name)) {
            throw "CPU/SYS CDC $Stage first-stage identity is incomplete"
        }
        $spec = $syncSpecs[$record.name]
        if ($record.source_clock -cne $spec.source -or
            $record.capture_clock -cne $spec.capture -or
            $record.capture_object -cne $spec.object -or
            $record.mapped_first_stage_ff -ne 1 -or
            $record.mapped_second_stage_ff -ne 1 -or
            $record.mapped_second_stage_tags -ne $spec.second_tags -or
            $record.second_stage_source_clock_filtered -ne $true) {
            throw "CPU/SYS CDC $Stage mapped first-stage evidence is incomplete"
        }
        foreach ($kind in @('max_delay','hold_cut')) {
            $match = $record.fdc_matches.$kind
            if ($match.capture_ff_objects -ne 1 -or
                $match.capture_object -cne $spec.object -or
                $match.source_clock -cne $spec.source) {
                throw "CPU/SYS CDC $Stage first-stage FDC selector is incomplete"
            }
        }
    }
}

function Assert-FpgaUartTxPadContract($CpuAds, $Snapshot) {
    $inputs = ConvertTo-FpgaMap $Snapshot.inputs
    # The checker is a frozen recipe input for the UART hold fix. Historical
    # snapshots, including early V6.5 candidates, do not claim this new proof.
    if (!$inputs.Contains('scripts/audit_uart_tx_pad_ads.py')) { return }
    $uart = $CpuAds.uart_tx_pad_contract
    if (!$uart -or $uart.schema -ne 1 -or $uart.status -cne 'PASS' -or
        $uart.scope -cne 'MAPPED_UART_TX_WADDR_PADS' -or $uart.hierarchy -cne 'soc_top/u_local/u_tx' -or
        $uart.run_id -cne $Snapshot.run_id -or $uart.input_snapshot_sha256 -cne $CpuAds.input_snapshot_sha256 -or
        $uart.vm_sha256 -cne $CpuAds.netlist_sha256 -or
        $uart.checker_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
        $uart.checker_sha256 -cne $inputs['scripts/audit_uart_tx_pad_ads.py'] -or
        $uart.parser_sha256 -cne $inputs['scripts/audit_icache_pad_ads.py'] -or
        $uart.uart_rtl_sha256 -cne $inputs['rtl/soc/uart_tx_fifo.v'] -or
        $uart.primitive -cne 'GTP_LUT6D' -or $uart.init -cne 'CCCCCCCC_AAAAAAAA' -or
        $uart.preservation_attribute -cne 'PAP_DONT_TOUCH' -or
        $uart.address_bits -ne 4 -or $uart.upstream_ff_bits -ne 4 -or $uart.memory_cells -ne 4 -or
        $uart.data_bits -ne 8 -or $uart.waddr_pins_checked -ne 16 -or
        @($uart.pairs).Count -ne 2 -or @($uart.memories).Count -ne 4 -or
        $uart.module_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
        $uart.unique_drivers -isnot [bool] -or $uart.unique_drivers -ne $true -or
        $uart.bypass -isnot [bool] -or $uart.bypass -ne $false -or
        $uart.post_pnr_physical_retention_proven -isnot [bool] -or $uart.post_pnr_physical_retention_proven -ne $false -or
        $uart.routed_hold_margin_proven -isnot [bool] -or $uart.routed_hold_margin_proven -ne $false) {
        throw 'UART TX pad ADS contract is missing, foreign, incomplete, or overstates its scope'
    }
    if (@($uart.pairs[0].inputs).Count -ne 2 -or
        $uart.pairs[0].inputs[0] -cnotmatch '^(wr_ptr|pad_address_in)\[0\]$') {
        throw 'UART TX pad ADS write pointer mapping is incomplete'
    }
    $pointerBus = $Matches[1]
    $outputs = @()
    for ($pair = 0; $pair -lt 2; $pair++) {
        $item = $uart.pairs[$pair]
        if ($item.pair -ne $pair -or $item.instance -cne "\write_address_pad[$pair].u_hold_dual_lut" -or
            @($item.inputs).Count -ne 2 -or $item.inputs[0] -cne ($pointerBus + '[' + (2*$pair) + ']') -or
            $item.inputs[1] -cne ($pointerBus + '[' + (2*$pair+1) + ']') -or @($item.outputs).Count -ne 2) {
            throw 'UART TX pad ADS pair mapping is incomplete'
        }
        $outputs += @($item.outputs)
    }
    if (@($outputs | Sort-Object -Unique).Count -ne 4 -or
        @($outputs | Where-Object { $_ -cnotmatch '^[A-Za-z_][\w$]*(?:\[\d+\])?$' -or
            ($_ -split '\[')[0] -cin @('wr_ptr','pad_address_in') }).Count) {
        throw 'UART TX pad ADS outputs overlap or bypass the pads'
    }
    $instances = @(); $data = @(); $waddr = $null
    foreach ($ram in $uart.memories) {
        $order = @($ram.waddr_low_to_high_pointer_bits)
        if ($ram.primitive -cne 'GTP_RAM32X2DP' -or !$ram.instance -or
            $order.Count -ne 4 -or (($order | Sort-Object) -join ',') -cne '0,1,2,3' -or
            @($ram.data_bits).Count -ne 2) { throw 'UART TX pad ADS RAM mapping is incomplete' }
        $expected = "{1'b0," + (($order[3..0] | ForEach-Object { $outputs[$_] }) -join ',') + '}'
        if ($ram.waddr -cne $expected -or ($null -ne $waddr -and $ram.waddr -cne $waddr)) {
            throw 'UART TX pad ADS RAM write-address fanout is incomplete'
        }
        $waddr = $ram.waddr; $instances += $ram.instance; $data += @($ram.data_bits)
    }
    if (@($instances | Sort-Object -Unique).Count -ne 4 -or (($data | Sort-Object) -join ',') -cne '0,1,2,3,4,5,6,7') {
        throw 'UART TX pad ADS RAM data coverage is incomplete'
    }
}

function Assert-FpgaRobOwnerContract($CpuAds, $Snapshot) {
    # New hardware acceptance is explicit by snapshot version. Historical V6.1
    # evidence retains its original checks and cannot satisfy a V6.5 snapshot.
    if ([version]$Snapshot.release.TrimStart('V','v') -lt [version]'6.5') { return }
    $rob = $CpuAds.rob_owner_contract
    $inputs = ConvertTo-FpgaMap $Snapshot.inputs
    if (!$rob -or $rob.schema -ne 1 -or $rob.status -cne 'PASS' -or
        $rob.scope -cne 'MAPPED_ROB_C1_LIMITED' -or
        $rob.run_id -cne $Snapshot.run_id -or
        $rob.input_snapshot_sha256 -cne $CpuAds.input_snapshot_sha256 -or
        $rob.vm_sha256 -cne $CpuAds.netlist_sha256 -or
        $rob.checker_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
        $rob.checker_sha256 -cne $inputs['scripts/audit_rob_owner_ads.py'] -or
        $rob.cpu_rtl_sha256 -cne $inputs['rtl/cpu/CoreTop.sv'] -or
        $rob.cpu_source_json_sha256 -cne $inputs['rtl/cpu/source.json'] -or
        $rob.cpu_emit_config_sha256 -cne $inputs['rtl/cpu/emit-config.json'] -or
        $rob.tag_live_ff -ne 32 -or $rob.result_valid_ff -ne 32 -or
        $rob.owner_tags -ne 32 -or $rob.owner_ff -ne 96 -or
        @($rob.banks).Count -ne 4 -or $rob.disabled_interface_port -ne 3 -or
        @($rob.owner_cones).Count -ne 96 -or
        $rob.owner_clear_dependency_absent -isnot [bool] -or $rob.owner_clear_dependency_absent -ne $true -or
        $rob.owner_hierarchy_nodes -le 0 -or @($rob.owner_hierarchy_boundary_leaves).Count -eq 0 -or
        @($rob.read_port_bindings).Count -ne 28 -or @($rob.local_read_checks).Count -ne 2 -or
        $rob.full_sequential_equivalence_proven -isnot [bool] -or
        $rob.full_sequential_equivalence_proven -ne $false -or
        $rob.routed_timing_or_board_proven -isnot [bool] -or
        $rob.routed_timing_or_board_proven -ne $false) {
        throw 'ROB ADS contract is missing, foreign, incomplete, or overstates its proof scope'
    }
    for ($index = 0; $index -lt 4; $index++) {
        $bank = $rob.banks[$index]
        if ($bank.bank -ne $index -or $bank.source_port -ne @(0,1,2,4)[$index] -or
            $bank.checked_vectors -ne 1536 -or !$bank.write_enable) {
            throw 'ROB ADS bank write-enable proof is incomplete'
        }
    }
    for ($index = 0; $index -lt 2; $index++) {
        $read = $rob.local_read_checks[$index]
        if ($read.tag_lane -ne @(2,4)[$index] -or $read.bank_read_port -ne @(4,2)[$index] -or
            $read.tested_data_bit -ne 0 -or $read.checked_vectors -ne 512 -or $read.nonconstant_bits -ne 32) {
            throw 'ROB ADS selected read/valid-mask proof is incomplete'
        }
    }
}

function Assert-FpgaCpuPmaContract($CpuAds) {
    $pma = $CpuAds.pma_contract
    if (!$pma -or $pma.address_cases -ne 2144 -or
        @($pma.consumers).Count -ne 2 -or
        !$pma.mapped_outputs -or !$pma.consumer_pma_inputs -or !$pma.output_values) {
        throw 'CPU ADS PMA contract is incomplete'
    }
    $names = @($pma.mapped_outputs.PSObject.Properties.Name)
    foreach ($name in $names) {
        if ([string]::Join(',', @($pma.output_values.$name)) -cne '0,1') {
            throw 'CPU ADS PMA contract lacks both output values'
        }
    }
    if ($pma.variant -ceq 'supervisor_fused_single_output') {
        $shared = 'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/attributes/N7'
        if ($pma.consumers[0] -cne 'Lsu.N23' -or $pma.consumers[1] -cne 'Lsu.N972' -or
            $pma.control_combinations -ne 16 -or $pma.consumer_cases -ne 68608 -or
            $names.Count -ne 1 -or $names[0] -cne 'N7' -or
            @($pma.consumer_pma_inputs.N23).Count -ne 1 -or
            @($pma.consumer_pma_inputs.N972).Count -ne 1 -or
            $pma.consumer_pma_inputs.N23[0] -cne $shared -or
            $pma.consumer_pma_inputs.N972[0] -cne $shared) {
            throw 'CPU ADS supervisor PMA contract is incomplete'
        }
    } elseif ($pma.variant -ceq 'fused_single_output') {
        $shared = 'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/attributes/N7'
        if ($pma.consumers[0] -cne 'Lsu.N13' -or $pma.consumers[1] -cne 'Lsu.N965' -or
            $pma.control_combinations -ne 16 -or $pma.consumer_cases -ne 68608 -or
            $names.Count -ne 1 -or $names[0] -cne 'N7' -or
            @($pma.consumer_pma_inputs.N13).Count -ne 1 -or
            @($pma.consumer_pma_inputs.N965).Count -ne 1 -or
            $pma.consumer_pma_inputs.N13[0] -cne $shared -or
            $pma.consumer_pma_inputs.N965[0] -cne $shared) {
            throw 'CPU ADS fused PMA contract is incomplete'
        }
    } elseif (!$pma.variant) {
        $storeInputs = @($pma.consumer_pma_inputs.N13)
        $loadInputs = @($pma.consumer_pma_inputs.N965)
        if ($pma.consumers[0] -cne 'Lsu.N13' -or $pma.consumers[1] -cne 'Lsu.N965' -or
            $pma.consumer_cases -ne 4288 -or $names.Count -ne 4 -or
            $storeInputs.Count -ne 3 -or $loadInputs.Count -ne 1 -or
            @($storeInputs + $loadInputs | Sort-Object -Unique).Count -ne 4 -or
            @($names | Where-Object { $_ -notin ($storeInputs + $loadInputs) }).Count -ne 0) {
            throw 'CPU ADS four-output PMA contract is incomplete'
        }
    } else {
        throw 'CPU ADS PMA contract has an unknown variant'
    }
}

function Assert-FpgaReleaseEvidence([string]$Root, $Evidence) {
    $snapshotPath = Get-FpgaSafePath $Root 'artifacts/build_snapshot.json'
    $snapshot = [IO.File]::ReadAllText($snapshotPath) | ConvertFrom-Json
    Assert-FpgaSnapshot $Root $snapshot
    $snapshotHash = (Get-FileHash -LiteralPath $snapshotPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Evidence.schema -ne 3 -or $Evidence.input_snapshot_sha256 -cne $snapshotHash -or
        $Evidence.run_id -cne $snapshot.run_id -or $Evidence.started_utc -cne $snapshot.started_utc -or
        [datetime]::Parse($Evidence.completed_utc) -le [datetime]::Parse($snapshot.started_utc)) {
        throw 'Build evidence is not bound to the original FPGA input snapshot'
    }
    Assert-FpgaMap $Evidence.inputs $snapshot.inputs 'Build evidence input coverage'
    Assert-FpgaMap $Evidence.outputs (Get-FpgaHashMap $Root (Get-FpgaOutputPaths $Root)) 'Build evidence output coverage'
    $cpuAds = [IO.File]::ReadAllText((Get-FpgaSafePath $Root 'artifacts/cpu_ads_controls.json')) | ConvertFrom-Json
    $inputs = ConvertTo-FpgaMap $snapshot.inputs
    $outputs = ConvertTo-FpgaMap $Evidence.outputs
    $reports = ConvertTo-FpgaMap $Evidence.report_hashes
    $runPath = 'pds/input-snapshots/' + $snapshot.run_id + '/'
    $preflightPath = Get-FpgaSafePath $Root 'artifacts/preflight_gate.json'
    $preflight = [IO.File]::ReadAllText($preflightPath) | ConvertFrom-Json
    $preflightHash = (Get-FileHash -LiteralPath $preflightPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Evidence.ordered_post_synthesis_stages_verified -ne $true -or
        $Evidence.preflight_gate_sha256 -cne $preflightHash -or
        $reports[$runPath + 'preflight_gate.json'] -cne $preflightHash -or
        $preflight.schema -ne 1 -or $preflight.status -cne 'PASS' -or
        $preflight.run_id -cne $snapshot.run_id -or
        $preflight.input_snapshot_sha256 -cne $snapshotHash -or
        $preflight.cdc_summary.total_constraints -ne 1171 -or
        $preflight.cdc_summary.errors -ne 0 -or
        $preflight.cdc_summary.critical_warnings -ne 39 -or
        $preflight.cdc_summary.warnings -ne 0 -or
        $preflight.cdc_summary.mapped_directions -ne 10 -or
        $preflight.cdc_summary.payload_ram_cells -ne 76 -or
        $preflight.cdc_summary.payload_do_outputs -ne 149 -or
        $preflight.cdc_summary.first_stage_crossings -ne 4 -or
        $preflight.cdc_summary.vector_match_each -ne 1 -or
        $preflight.cdc_summary.mapped_ff_each -ne 5) {
        throw 'Post-synthesis stage evidence is missing or not bound to the run'
    }
    foreach ($name in @('adf','vm','snr')) {
        $path = switch ($name) {
            'adf' { 'pds/synthesize/soc_top_syn.adf' }
            'vm' { 'pds/synthesize/soc_top_syn.vm' }
            'snr' { 'pds/synthesize/soc_top.snr' }
        }
        $field = 'synth_' + $name + '_sha256'
        if ($Evidence.$field -notmatch '^[0-9a-f]{64}$' -or
            $preflight.synth_hashes.$path -cne $Evidence.$field -or
            $reports[$path] -cne $Evidence.$field) {
            throw "Post-synthesis ADS $name fingerprint is not bound to the preflight and native report"
        }
    }
    if ($preflight.synth_history_sha256 -cne $reports[$runPath + 'synth.impl.tcl'] -or
        $preflight.synth_project_sha256 -cne $reports[$runPath + 'soc_pre_synth.pds'] -or
        $preflight.cpu_ads_sha256 -cne $reports[$runPath + 'cpu-pre-pnr.json'] -or
        $preflight.icache_ads_sha256 -cne $reports[$runPath + 'icache-pad-pre-pnr.json'] -or
        $preflight.cdc_ads_sha256 -cne $reports[$runPath + 'cpu-sys-cdc-ads.json'] -or
        $preflight.synth_hashes.($runPath + 'synth.constraint_check.ccr') -cne
            $reports[$runPath + 'synth.constraint_check.ccr']) {
        throw 'Post-synthesis preflight proof or native project history differs from the recorded stage'
    }
    $published = [ordered]@{
        'preflight_gate.json' = $runPath + 'preflight_gate.json'
        'cpu_sys_cdc_ads_pre.json' = $runPath + 'cpu-sys-cdc-ads.json'
        'cpu_sys_cdc_ads.json' = $runPath + 'cpu-sys-cdc-post-route.json'
        'pds_synth_history.txt' = $runPath + 'synth.impl.tcl'
        'pds_post_history.txt' = 'pds/impl.tcl'
        'pds_synth_project.txt' = $runPath + 'soc_pre_synth.pds'
        'pds_post_project.txt' = 'pds/soc.pds'
        'pds_synth_parse_stdout.txt' = $runPath + 'pds.parse-synth.stdout.log'
        'pds_synth_parse_stderr.txt' = $runPath + 'pds.parse-synth.stderr.log'
        'pds_post_parse_stdout.txt' = $runPath + 'pds.parse-post.stdout.log'
        'pds_post_parse_stderr.txt' = $runPath + 'pds.parse-post.stderr.log'
        'pds_synth_stdout.txt' = $runPath + 'pds.synth.stdout.log'
        'pds_synth_stderr.txt' = $runPath + 'pds.synth.stderr.log'
        'pds_post_stdout.txt' = $runPath + 'pds.stdout.log'
        'pds_post_stderr.txt' = $runPath + 'pds.stderr.log'
        'pds_synth_constraints.txt' = $runPath + 'synth.constraint_check.ccr'
        'pds_post_constraints.txt' = 'pds/constraint_check/constraint_check.ccr'
        'pds_synth_flow.txt' = $runPath + 'synth.flow.log'
        'pds_post_map_constraints.txt' = 'pds/device_map/soc_top.dmr'
        'synth_resource_report.txt' = 'pds/synthesize/soc_top.snr'
        'final_timing_report.txt' = 'pds/report_timing/soc_top.rtr'
        'final_timing_xml.xml' = 'pds/report_timing/rtr.db'
    }
    foreach ($entry in $published.GetEnumerator()) {
        $actualHash = $outputs['artifacts/' + $entry.Key]
        if ($actualHash -notmatch '^[0-9a-f]{64}$' -or $reports[$entry.Value] -cne $actualHash) {
            throw "Published native PDS stage file differs from report evidence: $($entry.Key)"
        }
    }
    if ($Evidence.post_map_constraints_verified -ne $true -or
        $Evidence.post_map_dmr_sha256 -cne $outputs['artifacts/pds_post_map_constraints.txt'] -or
        $reports[$runPath + 'post.soc_top.dmr'] -cne $Evidence.post_map_dmr_sha256) {
        throw 'Post-map DMR evidence is missing or not bound to the release'
    }
    Assert-FpgaPostMapConstraints $Root (Get-FpgaSafePath $Root 'artifacts/pds_post_map_constraints.txt')
    Assert-FpgaStageHistory (Get-FpgaSafePath $Root 'artifacts/pds_synth_history.txt') 'synthesis'
    Assert-FpgaStageHistory (Get-FpgaSafePath $Root 'artifacts/pds_post_history.txt') 'post_synthesis'
    if ($Evidence.max_skew_verified -ne $true -or $Evidence.max_skew_groups -ne 10 -or
        $Evidence.max_skew_rtr_sha256 -cne $outputs['artifacts/final_timing_report.txt'] -or
        $Evidence.max_skew_xml_sha256 -cne $outputs['artifacts/final_timing_xml.xml']) {
        throw 'Max Skew release evidence is missing or not bound to both native timing report hashes'
    }
    $maxSkew = Assert-FpgaMaxSkewReport `
        (Get-FpgaSafePath $Root 'artifacts/final_timing_xml.xml') `
        (Get-FpgaSafePath $Root 'artifacts/final_timing_report.txt') `
        (Get-FpgaSafePath $Root 'pds/soc.fdc')
    if ($Evidence.max_skew_rows -ne $maxSkew.rows) {
        throw 'Max Skew release evidence row count differs from the published native report'
    }
    if ([version]([IO.File]::ReadAllText((Get-FpgaSafePath $Root 'VERSION')).Trim()) -ge [version]'6.5') {
        if ($Evidence.timing_scope_verified -ne $true) { throw 'V6.5 release lacks complete native timing scope verification' }
        $null = Assert-FpgaTimingScope (Get-FpgaSafePath $Root 'artifacts/final_timing_xml.xml') `
            (Get-FpgaSafePath $Root 'pds/soc.fdc') (Get-FpgaSafePath $Root 'config/timing_scope_baseline.json')
    }
    foreach ($stage in @('synth','post')) {
        $parser = [IO.File]::ReadAllText((Get-FpgaSafePath $Root ("artifacts/pds_${stage}_parse_stdout.txt")))
        foreach ($constraint in @('soc.fdc','ddr3_test.rcf')) {
            $pattern = '(?m)^Executing : add_constraint ' + [regex]::Escape($constraint) + ' successfully\.\s*$'
            if ([regex]::Matches($parser, $pattern).Count -ne 1) {
                throw "PDS $stage parser did not register $constraint exactly once"
            }
        }
    }
    foreach ($stage in @(
            @{ name='preflight'; artifact='cpu_sys_cdc_ads_pre.json';
                expected=$Evidence.cdc_ads_pre_sha256; ccr='pds_synth_constraints.txt' },
            @{ name='post-route'; artifact='cpu_sys_cdc_ads.json';
                expected=$Evidence.cdc_ads_post_sha256; ccr='pds_post_constraints.txt' }
        )) {
        $artifactRelative = 'artifacts/' + $stage.artifact
        $cdc = [IO.File]::ReadAllText((Get-FpgaSafePath $Root $artifactRelative)) | ConvertFrom-Json
        if ($stage.expected -cne $outputs[$artifactRelative] -or
            $cdc.schema -ne 1 -or $cdc.status -cne 'PASS' -or
            $cdc.run_id -cne $snapshot.run_id -or $cdc.snapshot_sha256 -cne $snapshotHash -or
            $cdc.vm_sha256 -cne $Evidence.synth_vm_sha256 -or
            $cdc.adf_sha256 -cne $Evidence.synth_adf_sha256 -or
            $cdc.ccr_sha256 -cne $outputs[('artifacts/' + $stage.ccr)] -or
            $cdc.fdc_sha256 -cne $inputs['pds/soc.fdc']) {
            throw "CPU/SYS CDC $($stage.name) ADS/CCR evidence is missing or foreign"
        }
        Assert-FpgaCdcEvidenceRecords $cdc $stage.name
    }

    if ($inputs.Contains('pds/gui1080_tage.pcf')) {
        $placement=[IO.File]::ReadAllText((Join-Path $Root 'artifacts/gui1080_placement.json'))|ConvertFrom-Json
        if($placement.status -cne 'NATIVE_FINAL_TAGE_PLACEMENT_EXACT_PASS_NOT_BOARD' -or
           $placement.run_id -cne $snapshot.run_id -or $placement.snapshot_sha256 -cne $snapshotHash -or
           $placement.constraint_sha256 -cne $inputs['pds/gui1080_tage.pcf'] -or
           $placement.export_sha256 -cne $outputs['artifacts/gui1080_placement_export.pcf'] -or
           $placement.pnr_adf_sha256 -cne $reports['pds/place_route/soc_top_pnr.adf'] -or
           $placement.pnr_adf_sha256 -cne (Get-FileHash -LiteralPath (Join-Path $Root 'pds/place_route/soc_top_pnr.adf') -Algorithm SHA256).Hash.ToLowerInvariant()){throw 'Foreign or incomplete GUI1080 final placement evidence'}
        Assert-FpgaGui1080PlacementNative $Root ([IO.File]::ReadAllText((Join-Path $Root 'artifacts/pds_post_stdout.txt'))) `
            ([IO.File]::ReadAllText((Join-Path $Root 'pds/device_map/soc_top.pcf'))) `
            ([IO.File]::ReadAllText((Join-Path $Root 'artifacts/gui1080_placement_export.pcf')))
        if([regex]::Matches([IO.File]::ReadAllText((Join-Path $Root 'pds/place_route/soc_top_pnr.netlist')),
            '(?m)^u_cpu/u_cpu_wrapper/u_cpu/core/frontend/tage/tagMem_2_ext/Memory_1/gopdrm_18k;gopDRM18K\r?$').Count -ne 1){throw 'GUI1080 relocated primitive is not the exact native gopDRM18K instance'}
    }
    if ($Evidence.ddr_route_registration_verified -ne $true -or
        $Evidence.ddr_route_constraint_sha256 -cne $inputs['pds/ddr3_test.rcf'] -or
        $Evidence.ddr_route_target_count -ne @(Get-FpgaDdrRouteLines).Count) {
        throw 'DDR route registration evidence is missing or does not bind the current RCF'
    }
    foreach ($report in @('pds/soc.pds', 'pds/impl.tcl',
        ('pds/input-snapshots/' + $snapshot.run_id + '/pds.stdout.log'),
        'pds/place_route/soc_top_pnr.netlist')) {
        if ($reports[$report] -notmatch '^[0-9a-f]{64}$') {
            throw "DDR route registration evidence lacks an actual report fingerprint: $report"
        }
    }
    if ($Evidence.cpu_ads_controls_verified -ne $true -or $cpuAds.schema_version -ne 1 -or
        $cpuAds.status -cne 'PASS' -or $cpuAds.frontend_cases -ne 85760 -or
        $cpuAds.pma_address_cases -ne 2144 -or $cpuAds.rsmem_hint_cases -ne 17152 -or
        $cpuAds.input_snapshot_sha256 -cne $snapshotHash -or
        $cpuAds.input_snapshot_run_id -cne $snapshot.run_id -or
        $cpuAds.cpu_rtl_sha256 -cne $inputs['rtl/cpu/CoreTop.sv'] -or
        $cpuAds.cpu_emit_config_sha256 -cne $inputs['rtl/cpu/emit-config.json'] -or
        $cpuAds.production_rom_sha256 -cne $inputs['artifacts/bootrom.hex'] -or
        $cpuAds.audit_script_sha256 -cne $inputs['scripts/audit_cpu_ads.py'] -or
        $cpuAds.netlist_sha256 -notmatch '^[0-9a-f]{64}$' -or
        $cpuAds.netlist_sha256 -cne $reports['pds/synthesize/soc_top_syn.vm']) {
        throw 'CPU ADS evidence is missing, incomplete, or does not bind the current snapshot and synthesized netlist'
    }
    Assert-FpgaCpuPmaContract $cpuAds
    Assert-FpgaRobOwnerContract $cpuAds $snapshot
    Assert-FpgaUartTxPadContract $cpuAds $snapshot
    $icachePath = Get-FpgaSafePath $Root 'artifacts/icache_pad_ads.json'
    $icacheHash = (Get-FileHash -LiteralPath $icachePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Evidence.icache_pad_ads_verified -isnot [bool] -or $Evidence.icache_pad_ads_verified -ne $true -or
        $Evidence.icache_pad_ads_sha256 -cne $icacheHash) {
        throw 'ICache ADS evidence flag or artifact hash is missing or mismatched'
    }
    $icacheAds = [IO.File]::ReadAllText($icachePath) | ConvertFrom-Json
    Assert-IcachePadAdsEvidence $icacheAds $snapshot $snapshotHash $reports['pds/synthesize/soc_top_syn.vm']
}

# One exact native packed macro only. No guessed alias, no -no_check.
function Get-FpgaGui1080PlacementLine {
    return 'def_inst_site {u_cpu/u_cpu_wrapper/u_cpu/core/frontend/tage/tagMem_2_ext/Memory_1/gopdrm_18k} DRM_256_30 DRM0'
}
function Assert-FpgaGui1080PlacementInput([string]$Root) {
    $actual = @([IO.File]::ReadAllLines((Join-Path $Root 'pds/gui1080_tage.pcf')) |
        ForEach-Object {$_.Trim()} | Where-Object {$_ -and !$_.StartsWith('#')})
    if($actual.Count -ne 1 -or $actual[0] -cne (Get-FpgaGui1080PlacementLine)) {
        throw 'GUI1080 placement requires exactly the reviewed strict TAGE macro/site/slot'
    }
}
function Assert-FpgaGui1080PlacementNative([string]$Root,[string]$Stdout,[string]$Mapped,[string]$Export) {
    Assert-FpgaGui1080PlacementInput $Root
    $line=Get-FpgaGui1080PlacementLine
    $success='(?m)^Executing : '+[regex]::Escape($line)+' successfully\.?\s*$'
    if([regex]::Matches($Stdout,$success).Count -ne 1 -or
       [regex]::Matches($Stdout,'(?m)^GUI1080_STRICT_PLACEMENT_REAPPLIED_AFTER_MAP\s*$').Count -ne 1){
        throw 'GUI1080 strict placement lacks unique actual native execution after dev_map'
    }
    if(@($Mapped -split '\r?\n' | Where-Object { $_.Trim() -ceq $line }).Count -ne 1){
        throw 'GUI1080 strict placement absent or duplicated in actual mapped PCF'
    }
    $target='(?m)^def_inst_site \{u_cpu/u_cpu_wrapper/u_cpu/core/frontend/tage/tagMem_2_ext/Memory_1/gopdrm_18k\} DRM_256_30 DRM0(?: -no_check)?\s*$'
    $anyTarget='(?m)^def_inst_site \{u_cpu/u_cpu_wrapper/u_cpu/core/frontend/tage/tagMem_2_ext/Memory_1/gopdrm_18k\} .*$'
    if([regex]::Matches($Export,$target).Count -ne 1 -or [regex]::Matches($Export,$anyTarget).Count -ne 1){
        throw 'GUI1080 final PnR database exported a different or missing macro/site/slot'
    }
}
