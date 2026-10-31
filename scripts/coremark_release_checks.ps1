# Read-only release gates for the actual GPLL and archived final timing report.
# These checks run before any hours-long CoreMark process starts.
. (Join-Path $PSScriptRoot 'clock_policy.ps1')

function Assert-CoremarkIterationPolicy {
    param($BuildManifest, [int]$ExpectedIterations, [switch]$Production)
    $property = $BuildManifest.PSObject.Properties['coremark_iterations']
    if ($null -eq $property -or
        ($property.Value -isnot [int] -and $property.Value -isnot [long]) -or
        $property.Value -lt 0 -or $property.Value -gt 1000000 -or
        $property.Value -ne $ExpectedIterations) {
        throw 'Firmware build manifest does not explicitly bind the selected CoreMark iteration policy'
    }
    if ($Production -and
        ($null -eq $BuildManifest.coremark_contract -or
         $null -eq $BuildManifest.coremark_contract.preprocessed_macros -or
         $BuildManifest.coremark_contract.preprocessed_macros.ITERATIONS -cne [string]$ExpectedIterations)) {
        throw 'Production CoreMark iteration policy differs from preprocessed GCC macros'
    }
}

function Get-CoremarkPllLiteral {
    param([string]$Text, [string]$Name, [decimal]$Minimum,
          [decimal]$Maximum, [switch]$AllowEighths)
    $pattern = '(?m)^[ \t]*localparam[ \t]+(?<kind>integer|real)[ \t]+' +
        [regex]::Escape($Name) + '[ \t]*=[ \t]*(?<number>[0-9]+(?:\.[0-9]+)?)[ \t]*;'
    $matches = [regex]::Matches($Text, $pattern)
    if ($matches.Count -ne 1) { throw "Unrecognized GPLL literal declaration: $Name" }
    $kind = $matches[0].Groups['kind'].Value
    $value = [decimal]::Parse($matches[0].Groups['number'].Value,
        [Globalization.CultureInfo]::InvariantCulture)
    if ($value -lt $Minimum -or $value -gt $Maximum) {
        throw "GPLL literal out of range: $Name=$value"
    }
    if ($kind -eq 'integer' -and $value -ne [decimal]::Truncate($value)) {
        throw "Fractional GPLL literal was declared integer: $Name=$value"
    }
    $scaled = if ($AllowEighths) { $value * [decimal]8 } else { $value }
    if ($scaled -ne [decimal]::Truncate($scaled)) {
        throw "GPLL literal is not an allowed integer or n/8 fraction: $Name=$value"
    }
    return $value
}

function Assert-CoremarkPllClock {
    param([string]$Root, [int]$CpuHz)
    $pllText = [IO.File]::ReadAllText((Join-Path $Root 'rtl/video/pll_video.v'))
    $socText = [IO.File]::ReadAllText((Join-Path $Root 'rtl/soc/soc_top.v'))
    $fdcText = [IO.File]::ReadAllText((Join-Path $Root 'pds/soc.fdc'))
    $clkinMHz = Get-CoremarkPllLiteral $pllText 'CLKIN_FREQ' 10 500 -AllowEighths
    $idiv = Get-CoremarkPllLiteral $pllText 'STATIC_RATIOI' 1 80
    $mdiv = Get-CoremarkPllLiteral $pllText 'STATIC_RATIOM' 1 128
    $fdiv = Get-CoremarkPllLiteral $pllText 'STATIC_RATIOF' 1 128 -AllowEighths
    $odiv1 = Get-CoremarkPllLiteral $pllText 'STATIC_RATIO1' 1 128
    $clock = Get-Content -LiteralPath (Join-Path $Root 'config/clocks.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-SocClockIntent $clock
    Assert-SocCpuClockHardware $Root $clock
    if ($CpuHz -ne $clock.cpu_hz -or
        [regex]::Matches($pllText, 'parameter integer CPU_DIVISOR = ' + $clock.cpu_divisor + '\b').Count -ne 1 -or
        [regex]::Matches($pllText, 'STATIC_RATIO3\s*=\s*CPU_DIVISOR').Count -ne 1) {
        throw 'CPU PLL divider differs from configured clock intent'
    }
    if ($clkinMHz -ne [decimal]27) { throw "GPLL input is not the 27 MHz board clock: $clkinMHz MHz" }
    foreach ($name in @('STATIC_RATIOI','STATIC_RATIOM','STATIC_RATIOF','STATIC_RATIO1','STATIC_RATIO3')) {
        $mapping = '\.' + $name + '[ \t\r\n]*\([ \t\r\n]*' + $name + '[ \t\r\n]*\)'
        if ([regex]::Matches($pllText, $mapping).Count -ne 1) {
            throw "GPLL primitive no longer consumes the checked $name literal"
        }
    }
    foreach ($mapping in @('\.CLKIN1\s*\(\s*clkin1\s*\)',
                          '\.CLKOUT1\s*\(\s*clkout1\s*\)',
                          '\.CLKOUT3\s*\(\s*clkout3\s*\)')) {
        if ([regex]::Matches($pllText, $mapping).Count -ne 1) {
            throw 'GPLL input or SYS/CPU output primitive mapping changed'
        }
    }
    foreach ($setting in @('INTERNAL_FB','EXTERNAL_FB','SSC_MODE',
                           'CLK_DPS1_EN','CLKOUT1_SYN_EN')) {
        $expected = switch ($setting) {
            'INTERNAL_FB' { 'CLKOUTF' }
            'EXTERNAL_FB' { 'DISABLE' }
            'SSC_MODE' { 'DISABLE' }
            default { 'FALSE' }
        }
        $pattern = '(?m)^[ \t]*localparam[ \t]+' + $setting +
            '[ \t]*=[ \t]*"' + $expected + '"[ \t]*;'
        if ([regex]::Matches($pllText, $pattern).Count -ne 1) {
            throw "Unsupported GPLL feedback, modulation, or CLKOUT1 mode: $setting"
        }
    }
    if ($pllText -notmatch "assign\s+clkin_sel\s*=\s*1'b0\s*;" -or
        $pllText -notmatch "assign\s+dps_en\s*=\s*1'b0\s*;") {
        throw 'Unsupported GPLL input selection or dynamic phase mode'
    }
    $instance = [regex]::Matches($socText,
        '(?s)\bpll_video\s*#\s*\(\s*\.CPU_DIVISOR\s*\(\s*CPU_DIVISOR\s*\)\s*\)\s+u_video_pll\s*\((?<connections>.*?)\)\s*;')
    if ($instance.Count -ne 1 -or
        $instance[0].Groups['connections'].Value -notmatch '\.clkin1\s*\(\s*free_clk\s*\)' -or
        $instance[0].Groups['connections'].Value -notmatch '\.clkout1\s*\(\s*sys_clk\s*\)' -or
        $instance[0].Groups['connections'].Value -notmatch '\.clkout3\s*\(\s*(?:video_cpu_clk|cpu_clk)\s*\)') {
        throw 'CPU/SYS clocks no longer come from independent GPLL outputs'
    }
    $freeClock = [regex]::Matches($fdcText,
        '(?m)^create_clock -name \{free_clk\} \[get_ports \{free_clk\}\] -period \{([0-9.]+)\}')
    if ($freeClock.Count -ne 1) { throw 'Missing 27 MHz free_clk input constraint' }
    $inputPeriodNs = [decimal]::Parse($freeClock[0].Groups[1].Value,
        [Globalization.CultureInfo]::InvariantCulture)
    if ([math]::Abs([double]($inputPeriodNs - [decimal](1000.0 / 27.0))) -gt 0.001) {
        throw 'GPLL free_clk FDC period is not the rounded 27 MHz board input'
    }
    $vcoHz = ([decimal]27000000 * $mdiv * $fdiv) / $idiv
    $sysHz = $vcoHz / $odiv1
    $cpuVcoHz = Get-SocCpuPllVcoHz $clock
    $actualHz = $cpuVcoHz * $(if((Get-SocCpuClockMode $clock) -eq 4){2}else{1}) / $clock.cpu_divisor
    $roundedHz = [decimal]::Floor($actualHz + [decimal]0.5)
    $deltaHz = [math]::Abs([double]($actualHz - [decimal]$CpuHz))
    if ($vcoHz -ne $clock.pll_vco_hz -or $sysHz -ne $clock.sys_hz -or $roundedHz -ne $CpuHz) {
        throw "GPLL SYS/CPU outputs disagree with declared clocks (CPU exact $actualHz Hz, rounded $roundedHz Hz)"
    }
    return [pscustomobject][ordered]@{
        input_hz = 27000000; idiv = $idiv; mdiv = $mdiv
        fdiv = $fdiv; sys_divisor = $odiv1; cpu_divisor = $clock.cpu_divisor
        cpu_clock_mode = (Get-SocCpuClockMode $clock); cpu_pll_vco_hz = $cpuVcoHz
        clkout1_sys_hz = $sysHz; clkout3_cpu_exact_hz = $actualHz; cpu_rounded_hz = $roundedHz; delta_hz = $deltaHz
    }
}

function Assert-CoremarkFinalTiming {
    param([string]$Root)
    $path = Join-Path $Root 'artifacts/timing_summary.txt'
    $lines = [IO.File]::ReadAllLines($path)
    $first = @($lines | Where-Object { $_.Trim() } | Select-Object -First 1)
    if ($first.Count -ne 1 -or $first[0].Trim() -cne 'Design Summary : All Constraints Met.') {
        throw 'Final PDS timing summary does not state All Constraints Met'
    }
    $sysClock = [ordered]@{}
    foreach ($corner in @('Slow','Fast')) {
        foreach ($type in @('Setup','Hold','Recovery','Removal','Minimum Pulse Width')) {
            $heading = "$type Summary($corner Corner):"
            $starts = @(for ($i = 0; $i -lt $lines.Length; $i++) {
                if ($lines[$i].Trim() -ceq $heading) { $i }
            })
            if ($starts.Count -ne 1) { throw "Missing or duplicate final PDS timing table: $heading" }
            $index = $starts[0] + 1
            while ($index -lt $lines.Length -and $lines[$index] -notmatch '^\s*-{10,}\s*$') { $index++ }
            if ($index -ge $lines.Length) { throw "Missing timing table divider: $heading" }
            $index++
            $rowCount = 0
            $hasSysClock = $false
            $hasCpuClock = $false
            while ($index -lt $lines.Length -and $lines[$index] -notmatch '^\s*={10,}\s*$') {
                $row = $lines[$index].Trim()
                if ($row) {
                    $fields = @($row -split '\s+')
                    $expectedFields = if ($type -eq 'Minimum Pulse Width') { 5 } else { 6 }
                    if ($fields.Count -ne $expectedFields) {
                        throw "Unrecognized final PDS timing row: $heading / $row"
                    }
                    $offset = if ($type -eq 'Minimum Pulse Width') { 1 } else { 2 }
                    try {
                        $slack = [decimal]::Parse($fields[$offset], [Globalization.CultureInfo]::InvariantCulture)
                        $totalNegative = [decimal]::Parse($fields[$offset + 1], [Globalization.CultureInfo]::InvariantCulture)
                        $failing = [int]::Parse($fields[$offset + 2], [Globalization.CultureInfo]::InvariantCulture)
                        $total = [int]::Parse($fields[$offset + 3], [Globalization.CultureInfo]::InvariantCulture)
                    } catch {
                        throw "Non-numeric final PDS timing row: $heading / $row"
                    }
                    if ($slack -lt 0 -or $totalNegative -ne 0 -or $failing -ne 0 -or $total -le 0) {
                        throw "Final PDS timing violations in $heading / $row"
                    }
                    if ($type -in @('Setup','Hold') -and $fields[0] -ceq 'sys_clk' -and $fields[1] -ceq 'sys_clk') {
                        $hasSysClock = $true
                        $sysClock["$($type.ToLowerInvariant())_$($corner.ToLowerInvariant())_slack_ns"] = $slack
                    }
                    if ($type -in @('Setup','Hold') -and $fields[0] -ceq 'cpu_clk' -and $fields[1] -ceq 'cpu_clk') {
                        $hasCpuClock = $true
                        $sysClock["cpu_$($type.ToLowerInvariant())_$($corner.ToLowerInvariant())_slack_ns"] = $slack
                    }
                    $rowCount++
                }
                $index++
            }
            if ($index -ge $lines.Length -or $rowCount -eq 0) {
                throw "Incomplete final PDS timing table: $heading"
            }
            if ($type -in @('Setup','Hold') -and (!$hasSysClock -or !$hasCpuClock)) {
                throw "Final PDS timing table lacks CPU or SYS clock paths: $heading"
            }
        }
    }
    return [pscustomobject]$sysClock
}

function Resolve-CoremarkReleaseEvidencePath {
    param([string]$Root, [string]$Requested)
    $validation = [IO.Path]::GetFullPath((Join-Path $Root 'docs/validation')).TrimEnd('\')
    if (!(Test-Path -LiteralPath $validation -PathType Container) -or
        ((Get-Item -LiteralPath $validation).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Release evidence parent must be a regular docs/validation directory'
    }
    $candidate = if ([IO.Path]::IsPathRooted($Requested)) { $Requested } else { Join-Path $Root $Requested }
    $resolved = [IO.Path]::GetFullPath($candidate).TrimEnd('\')
    if (!(Split-Path -Parent $resolved).Equals($validation, [StringComparison]::OrdinalIgnoreCase) -or
        !(Split-Path -Leaf $resolved) -or (Test-Path -LiteralPath $resolved)) {
        throw 'Release evidence must be a new direct child directory of docs/validation'
    }
    return $resolved
}

function Publish-CoremarkReleaseEvidence {
    param([string]$Root, [string]$OutputDirectory, [string]$Destination,
          $Cases, [string]$Model, [string]$SummaryPath)
    $scratch = [IO.Path]::GetFullPath((Join-Path $Root 'artifacts/selftest')).TrimEnd('\')
    $out = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\')
    if (!$out.StartsWith($scratch + '\', [StringComparison]::OrdinalIgnoreCase) -or
        !(Test-Path -LiteralPath $out -PathType Container)) {
        throw 'Release promotion requires a new artifacts/selftest output directory inside this checkout'
    }
    $dest = Resolve-CoremarkReleaseEvidencePath -Root $Root -Requested $Destination
    if ([IO.Path]::GetPathRoot($out) -cne [IO.Path]::GetPathRoot($dest)) {
        throw 'Release evidence staging and destination must share a filesystem for atomic promotion'
    }
    $summary = Get-Content -LiteralPath $SummaryPath -Raw -Encoding utf8 | ConvertFrom-Json
    if ($summary.status -cne 'RTL_3_PLUS_1_TIMED_PASS_NOT_BOARD' -or
        $summary.kind -cne 'Long' -or @($summary.cases).Count -ne 4 -or
        $summary.cpu_cycle_observation_scope -cne 'Observed CPU edges from real timer release through the returned console prompt; includes UART/command overhead, not exact CoreMark timed-interval cycles.' -or
        @($Cases).Count -ne 4 -or $summary.pds_snapshot_sha256 -notmatch '^[0-9a-f]{64}$' -or
        $summary.released_bitstream_sha256 -notmatch '^[0-9a-f]{64}$') {
        throw 'Only four completely validated production timed runs can enter release evidence'
    }
    $expectedModes = @('performance','performance','performance','validation')
    for ($index = 0; $index -lt 4; $index++) {
        $case = $summary.cases[$index]
        $liveCase = $Cases[$index]
        if ($case.name -cne $liveCase.name -or $case.mode -cne $expectedModes[$index] -or
            $liveCase.mode -cne $expectedModes[$index] -or
            $case.result.seed_mode -cne $expectedModes[$index] -or
            $case.result.status -cne 'RTL_TIMED_PASS_NOT_BOARD' -or
            $case.result.cpu_hz -ne $summary.cpu_hz -or
            $case.result.sys_hz -ne $summary.sys_hz -or
            $case.result.timebase_hz -ne $summary.timebase_hz -or
            $case.result.timer_seconds -lt 10 -or
            $case.result.ticks -lt 10 * $summary.timebase_hz -or
            $case.result.observed_cpu_cycles_timer_release_to_prompt -le 0 -or
            $case.result.firmware_binary_sha256 -cne $summary.executed_firmware_sha256 -or
            $case.result.rom_sha256 -cne $summary.executed_rom_sha256 -or
            $case.result.cpu_rtl_sha256 -cne $summary.cpu_rtl_sha256 -or
            $case.result.timer_stimulus_scale_during_command -ne 1) {
            throw 'Release evidence contains an incomplete or short CoreMark run'
        }
    }
    $modelDir = Split-Path -Parent $Model
    $files = [ordered]@{}
    foreach ($case in $Cases) {
        $files["$($case.name).uart.txt"] = $case.log
        $files["$($case.name).stderr.txt"] = $case.log + '.stderr.log'
        $files["$($case.name).json"] = $case.result_path
    }
    $files['summary.json'] = $SummaryPath
    $files['verilator_model.json'] = Join-Path $modelDir 'model.json'
    $files['verilator_build.txt'] = Join-Path $modelDir 'build.log'
    $files['verilator_build_script.txt'] = Join-Path $modelDir 'build.sh'
    $files['verilator_generated_makefile.txt'] = Join-Path $modelDir 'Vtb_cpu_integration.mk'
    $files['bootloader.build.json'] = Join-Path $Root 'artifacts/bootloader.build.json'
    $files['cpu_source.json'] = Join-Path $Root 'rtl/cpu/source.json'
    $files['fpga_input_snapshot.json'] = Join-Path $Root 'artifacts/build_snapshot.json'
    $files['fpga_build_evidence.json'] = Join-Path $Root 'artifacts/build_evidence.json'
    $files['timing_summary.txt'] = Join-Path $Root 'artifacts/timing_summary.txt'
    $stage = Join-Path $out 'release-package-stage'
    if (Test-Path -LiteralPath $stage) { throw 'Release evidence staging directory already exists' }
    New-Item -ItemType Directory -Path $stage | Out-Null
    $hashes = [ordered]@{}
    foreach ($name in $files.Keys) {
        $source = $files[$name]
        if (!(Test-Path -LiteralPath $source -PathType Leaf)) { throw "Missing release evidence source: $source" }
        $target = Join-Path $stage $name
        Copy-Item -LiteralPath $source -Destination $target
        $hashes[$name] = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $snapshot = Get-Content -LiteralPath (Join-Path $stage 'fpga_input_snapshot.json') -Raw | ConvertFrom-Json
    $evidence = Get-Content -LiteralPath (Join-Path $stage 'fpga_build_evidence.json') -Raw | ConvertFrom-Json
    $build = Get-Content -LiteralPath (Join-Path $stage 'bootloader.build.json') -Raw | ConvertFrom-Json
    $cpuSource = Get-Content -LiteralPath (Join-Path $stage 'cpu_source.json') -Raw | ConvertFrom-Json
    $modelRecord = Get-Content -LiteralPath (Join-Path $stage 'verilator_model.json') -Raw | ConvertFrom-Json
    if ($hashes['fpga_input_snapshot.json'] -cne $summary.pds_snapshot_sha256 -or
        $hashes['fpga_build_evidence.json'] -cne $summary.pds_build_evidence_sha256 -or
        $snapshot.run_id -cne $summary.pds_snapshot_run_id -or
        $evidence.input_snapshot_sha256 -cne $summary.pds_snapshot_sha256 -or
        $evidence.outputs.'artifacts/soc_top.sbit' -cne $summary.released_bitstream_sha256 -or
        $evidence.outputs.'artifacts/timing_summary.txt' -cne $hashes['timing_summary.txt'] -or
        $snapshot.inputs.'artifacts/bootloader.bin' -cne $summary.executed_firmware_sha256 -or
        $snapshot.inputs.'artifacts/bootrom.hex' -cne $summary.executed_rom_sha256 -or
        $snapshot.inputs.'artifacts/bootloader.build.json' -cne $hashes['bootloader.build.json'] -or
        $snapshot.inputs.'rtl/cpu/source.json' -cne $hashes['cpu_source.json'] -or
        $snapshot.inputs.'rtl/cpu/CoreTop.sv' -cne $summary.cpu_rtl_sha256 -or
        $build.binary_sha256 -cne $summary.executed_firmware_sha256 -or
        $cpuSource.sha256 -cne $summary.cpu_rtl_sha256 -or
        $cpuSource.isa -cne $summary.isa -or
        $hashes['verilator_model.json'] -cne $summary.model_manifest_sha256 -or
        $hashes['verilator_build.txt'] -cne $summary.host_model_compilation.build_log_sha256 -or
        $hashes['verilator_build_script.txt'] -cne $summary.host_model_compilation.build_script_sha256 -or
        $hashes['verilator_generated_makefile.txt'] -cne $summary.host_model_compilation.generated_makefile_sha256 -or
        $hashes['bootloader.build.json'] -cne $summary.target_firmware_compilation.build_manifest_sha256 -or
        $modelRecord.host_cpp.explicit_cflags -cne '-Os' -or
        !$modelRecord.host_cpp.compiler_argv_observed -or
        $modelRecord.host_cpp.compile_command_count -ne $summary.host_model_compilation.observed_cpp_command_count -or
        $modelRecord.host_cpp.generated_makefile_sha256 -cne $hashes['verilator_generated_makefile.txt'] -or
        $modelRecord.host_cpp.build_log_sha256 -cne $hashes['verilator_build.txt'] -or
        $modelRecord.host_cpp.verilated_mk_sha256 -cne $summary.host_model_compilation.verilated_mk_sha256 -or
        $modelRecord.model_sha256 -cne $summary.model_sha256 -or
        $modelRecord.source_files.'rtl/cpu/CoreTop.sv' -cne $summary.cpu_rtl_sha256 -or
        (Get-FileHash -LiteralPath $Model -Algorithm SHA256).Hash.ToLowerInvariant() -cne $summary.model_sha256) {
        throw 'Release evidence files do not bind the executed firmware, model, CPU, FPGA snapshot, and timing output'
    }
    foreach ($case in $summary.cases) {
        $result = Get-Content -LiteralPath (Join-Path $stage "$($case.name).json") -Raw | ConvertFrom-Json
        if ($hashes["$($case.name).uart.txt"] -cne $case.result.log_sha256 -or
            $result.log_sha256 -cne $case.result.log_sha256 -or
            $result.sim_clock_quantization.cpu_half_fs -ne $summary.sim_clock_quantization.cpu_half_fs -or
            $result.sim_clock_quantization.sys_half_fs -ne $summary.sim_clock_quantization.sys_half_fs -or
            $result.ticks -ne $case.result.ticks -or
            $result.observed_cpu_cycles_timer_release_to_prompt -ne
                 $case.result.observed_cpu_cycles_timer_release_to_prompt -or
            $result.iterations -ne $case.result.iterations -or
            $result.crc.'[0]crcfinal' -cne $case.result.crc.'[0]crcfinal') {
            throw "Release UART or result file changed after validation: $($case.name)"
        }
    }
    $release = [ordered]@{
        schema_version = 1
        status = 'RTL_3_PLUS_1_TIMED_PASS_NOT_BOARD'
        created_utc = [datetime]::UtcNow.ToString('o')
        board_acceptance = $false
        cpu_hz = $summary.cpu_hz
        sys_hz = $summary.sys_hz
        timebase_hz = $summary.timebase_hz
        isa = $summary.isa
        pds_snapshot_run_id = $summary.pds_snapshot_run_id
        pds_snapshot_sha256 = $summary.pds_snapshot_sha256
        released_bitstream_sha256 = $summary.released_bitstream_sha256
        firmware_binary_sha256 = $summary.executed_firmware_sha256
        bootrom_sha256 = $summary.executed_rom_sha256
        verilator_model_sha256 = $summary.model_sha256
        verilator_model_manifest_sha256 = $summary.model_manifest_sha256
        host_model_compilation = $summary.host_model_compilation
        target_firmware_compilation = $summary.target_firmware_compilation
        sim_clock_quantization = $summary.sim_clock_quantization
        cpu_cycle_observation_scope = $summary.cpu_cycle_observation_scope
        performance_score = $summary.performance_score
        files_sha256 = $hashes
        scope = 'Four real-CLINT production-console RTL runs; actual board frequency and peripherals are not established.'
    }
    [IO.File]::WriteAllText((Join-Path $stage 'release_evidence.json'),
        ($release | ConvertTo-Json -Depth 12) + "`n", [Text.UTF8Encoding]::new($false))
    foreach ($name in $hashes.Keys) {
        if ((Get-FileHash -LiteralPath (Join-Path $stage $name) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $hashes[$name]) {
            throw "Release evidence staging changed before promotion: $name"
        }
    }
    if (Test-Path -LiteralPath $dest) { throw 'Release evidence destination was created during staging' }
    [IO.Directory]::Move($stage, $dest)
    return $dest
}
