param(
    [ValidateSet('Pilot','Long')][string]$Kind = 'Pilot',
    [ValidateSet('performance','validation','both')][string]$PilotModes = 'both',
    [string]$ToolchainRoot = '',
    [string]$MsysRoot = 'D:\LJL\WORK\msys64',
    [string]$OutputDirectory = '',
    [string]$ReleaseEvidenceDirectory = '',
    [ValidateRange(60,86400)][int]$TimeoutSeconds = 600,
    [ValidateRange(1000,1500000000)][int]$MaxCycles = 12000000,
    [ValidateRange(0,1000000)][int]$Iterations = 0,
    [ValidateRange(1,1000000000)][int]$CpuHz = 125000000,
    [ValidateRange(1,2)][int]$BuildJobs = 2,
    [switch]$ReuseModel,
    [string]$ReuseModelDirectory = '',
    [switch]$PreflightOnly
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'simulation_tools.ps1')
. (Join-Path $PSScriptRoot 'coremark_release_checks.ps1')
if ($Kind -eq 'Long' -and $MaxCycles -eq 12000000) { $MaxCycles = 1200000000 }
if ($Kind -eq 'Pilot' -and $Iterations -notin @(0,10)) {
    throw 'The bounded pilot is fixed at ten iterations; use Long after the production binary is rebuilt.'
}
if ($PreflightOnly -and $Kind -ne 'Long') { throw 'PreflightOnly checks the released long-run inputs.' }
if ($ReuseModelDirectory -and !$ReuseModel) { throw 'ReuseModelDirectory requires -ReuseModel.' }
if ($Kind -eq 'Long' -and !$PreflightOnly -and ($TimeoutSeconds -lt 3600 -or $MaxCycles -lt 600000000)) {
    throw 'Long runs require at least a one-hour host timeout and 600M target-cycle cap; this guard prevents accidental short-run claims.'
}
if (!$OutputDirectory) {
    $OutputDirectory = Join-Path $root ('artifacts/selftest/production_coremark_' + $Kind.ToLowerInvariant() + '_' + [guid]::NewGuid().ToString('N'))
}
$out = [IO.Path]::GetFullPath($OutputDirectory)
if ($out.Contains('"')) { throw 'Output path cannot contain a quote.' }
if (Test-Path -LiteralPath $out) { throw 'Use a new output directory so previous evidence is never overwritten.' }
$releasePath = $null
if ($ReleaseEvidenceDirectory) {
    if ($Kind -ne 'Long') { throw 'Only four complete timed production runs may be promoted as release evidence.' }
    $releasePath = Resolve-CoremarkReleaseEvidencePath -Root $root -Requested $ReleaseEvidenceDirectory
    $scratchRoot = [IO.Path]::GetFullPath((Join-Path $root 'artifacts/selftest')).TrimEnd('\')
    if (!$out.StartsWith($scratchRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Release promotion requires OutputDirectory beneath artifacts/selftest in this checkout.'
    }
}
$source = Get-Content -LiteralPath (Join-Path $root 'rtl/cpu/source.json') -Raw -Encoding utf8 | ConvertFrom-Json
$cpu = Join-Path $root 'rtl/cpu/CoreTop.sv'
if ($source.sha256 -cne (Get-FileHash -LiteralPath $cpu -Algorithm SHA256).Hash.ToLowerInvariant() -or
    $source.isa -cne 'rv32ima_zicsr_zifencei' -or $source.compressed_instructions -ne $false) {
    throw 'Current CPU does not match its RV32IMA/no-C source manifest.'
}
& (Join-Path $PSScriptRoot 'sync_cpu.ps1') -Check
$productionBin = Join-Path $root 'artifacts/bootloader.bin'
$productionBuild = Join-Path $root 'artifacts/bootloader.build.json'
$productionRom = Join-Path $root 'artifacts/bootrom.hex'
$productionRecord = Get-Content -LiteralPath $productionBuild -Raw -Encoding utf8 | ConvertFrom-Json
if ($productionRecord.binary_sha256 -cne (Get-FileHash -LiteralPath $productionBin -Algorithm SHA256).Hash.ToLowerInvariant() -or
    $productionRecord.march -cne $source.isa -or $productionRecord.abi -cne 'ilp32') {
    throw 'Production bootloader hash or ISA changed.'
}
if ($Kind -eq 'Long') {
    Assert-CoremarkIterationPolicy -BuildManifest $productionRecord -ExpectedIterations $Iterations -Production
}
if ($Kind -eq 'Long' -and $Iterations -eq 0) {
    $coremarkPort = [IO.File]::ReadAllText((Join-Path $root 'sw/coremark/core_portme.h'))
    $productionBuilder = [IO.File]::ReadAllText((Join-Path $root 'scripts/build_bootloader.ps1'))
    if ($coremarkPort -cnotmatch '(?m)^#define ITERATIONS 0$' -or
        $productionBuilder -match '-DITERATIONS=' -or
        $productionRecord.optimization -match '-DITERATIONS=') {
        throw 'Released automatic calibration must be the upstream port default, with no fixed-iteration compiler override.'
    }
}
$pllClock = Assert-CoremarkPllClock -Root $root -CpuHz $CpuHz
$timingReport = if ($Kind -eq 'Long') { Assert-CoremarkFinalTiming -Root $root } else { $null }
$snapshot = $null
$snapshotHash = $null
$evidenceHash = $null
$releasedBitstreamHash = $null
if ($Kind -eq 'Long') {
    . (Join-Path $PSScriptRoot 'build_snapshot.ps1')
    $snapshotPath = Join-Path $root 'artifacts/build_snapshot.json'
    $evidencePath = Join-Path $root 'artifacts/build_evidence.json'
    $snapshot = Get-Content -LiteralPath $snapshotPath -Raw -Encoding utf8 | ConvertFrom-Json
    $releaseEvidence = Get-Content -LiteralPath $evidencePath -Raw -Encoding utf8 | ConvertFrom-Json
    Assert-FpgaReleaseEvidence $root $releaseEvidence
    $snapshotHash = (Get-FileHash -LiteralPath $snapshotPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $evidenceHash = (Get-FileHash -LiteralPath $evidencePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $snapshotInputs = ConvertTo-FpgaMap $snapshot.inputs
    foreach ($name in @('artifacts/bootloader.bin','artifacts/bootrom.hex',
                       'rtl/cpu/CoreTop.sv','rtl/soc/soc_top.v',
                       'rtl/video/pll_video.v',
                       'sw/bootloader/soc.h','sw/coremark/core_portme.h',
                       'pds/soc.fdc')) {
        if ($snapshotInputs[$name] -cne (Get-FileHash -LiteralPath (Join-Path $root $name) -Algorithm SHA256).Hash.ToLowerInvariant()) {
            throw "Timed firmware or clock source differs from the final PDS input snapshot: $name"
        }
    }
    $releasedBitstreamHash = (Get-FileHash -LiteralPath (Join-Path $root 'artifacts/soc_top.sbit') -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($releaseEvidence.outputs.'artifacts/soc_top.sbit' -cne $releasedBitstreamHash) {
        throw 'Timed firmware does not belong to the final released PDS bitstream evidence.'
    }
    & (Join-Path $PSScriptRoot 'audit_project.ps1') -Root $root
}
& (Join-Path $PSScriptRoot 'check_clock_config.ps1') -Root $root | Out-Null
$clock = Get-Content -LiteralPath (Join-Path $root 'config/clocks.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($CpuHz -ne $clock.cpu_hz) { throw 'Requested CPU_HZ differs from config/clocks.json' }
$hashLine = @([IO.File]::ReadAllLines((Join-Path $root 'artifacts/SHA256SUMS.txt')) |
    Where-Object { $_ -match '\s+bootrom\.hex$' })
if ($hashLine.Count -ne 1 -or ($hashLine[0] -split '\s+')[0] -cne
    (Get-FileHash -LiteralPath $productionRom -Algorithm SHA256).Hash.ToLowerInvariant()) {
    throw 'Production ROM differs from artifact SHA256SUMS.'
}
if ($PreflightOnly) {
    Write-Output "PRODUCTION_COREMARK_RELEASE_PREFLIGHT_PASS cpu_hz=$CpuHz pll_clkout3_exact_hz=$($pllClock.clkout3_cpu_exact_hz) timebase_hz=$($clock.timebase_hz) iterations=$Iterations snapshot=$($snapshot.run_id) bitstream_sha256=$releasedBitstreamHash"
    return
}
if ($Kind -eq 'Long') { [string[]]$runModes = @('performance','performance','performance','validation') }
elseif ($PilotModes -eq 'both') { [string[]]$runModes = @('performance','validation') }
else { [string[]]$runModes = @($PilotModes) }
Write-Output "Production CoreMark ${Kind}: model build may take 3-10 minutes; each pilot run typically 1-3 minutes, each long run may take hours. Ctrl+C stops the owner; all four concurrent long runs share one $TimeoutSeconds-second Windows Job deadline."
New-Item -ItemType Directory -Path $out -Force | Out-Null
$originalPath = $env:PATH
try {
    $rom = $productionRom
    $bin = $productionBin
    $build = $productionBuild
    if ($Kind -eq 'Pilot') {
        $pilotDir = Join-Path $out 'pilot_firmware'
        & (Join-Path $PSScriptRoot 'coremark_fixed_bootloader.ps1') `
            -Iterations 10 -Purpose Pilot -CpuHz $CpuHz -ToolchainRoot $ToolchainRoot -OutputDirectory $pilotDir
        $rom = Join-Path $pilotDir 'fixed_bootrom.hex'
        $bin = Join-Path $pilotDir 'fixed_bootloader.bin'
        $build = Join-Path $pilotDir 'fixed_bootloader.build.json'
    }
    $rtl = @('rtl/cpu/CoreTop.sv','rtl/clint.v','rtl/cpu_top.v',
        'rtl/soc/axi_1x2.v','rtl/soc/axi_boot_periph.v','rtl/soc/axi_cpu_sys_cdc.v','rtl/soc/uart_tx_fifo.v',
        'sim/tb_cpu_integration.sv')
    if ($ReuseModel) {
        $modelDir = if ($ReuseModelDirectory) {
            [IO.Path]::GetFullPath($ReuseModelDirectory)
        } else {
            Join-Path $root 'artifacts/selftest/verilator_tb_cpu_integration'
        }
        $model = Join-Path $modelDir 'Vtb_cpu_integration.exe'
        $record = Get-Content -LiteralPath (Join-Path $modelDir 'model.json') -Raw -Encoding utf8 | ConvertFrom-Json
        if ($record.top -cne 'tb_cpu_integration' -or
            $record.model_sha256 -cne (Get-FileHash -LiteralPath $model -Algorithm SHA256).Hash.ToLowerInvariant()) {
            throw 'Reusable Verilator model metadata or hash differs.'
        }
        foreach ($name in $rtl) {
            if ($record.source_files.$name -cne (Get-FileHash -LiteralPath (Join-Path $root $name) -Algorithm SHA256).Hash.ToLowerInvariant()) {
                throw "Reusable model input differs: $name"
            }
        }
    } else {
        $model = Build-VerilatorModel -Root $root -Top 'tb_cpu_integration' `
            -MsysRoot $MsysRoot -Sources $rtl -TimeoutSeconds 1200 -BuildJobs $BuildJobs `
            -ModelDirectory (Join-Path $out 'verilator_model')
    }
    $modelDir = Split-Path -Parent $model
    $modelRecordPath = Join-Path $modelDir 'model.json'
    $modelRecord = Get-Content -LiteralPath $modelRecordPath -Raw -Encoding utf8 | ConvertFrom-Json
    if ($modelRecord.schema_version -ne 2 -or
        $modelRecord.host_cpp.explicit_cflags -cne '-Os' -or
        !$modelRecord.host_cpp.compiler_argv_observed -or
        $modelRecord.host_cpp.compile_command_count -lt 1 -or
        $modelRecord.host_cpp.final_optimization_per_observed_command -cne '-Os') {
        throw 'Production model lacks a fresh, observed host C++ -Os build'
    }
    foreach ($item in @{
        'build.sh' = $modelRecord.build_script_sha256
        "Vtb_cpu_integration.mk" = $modelRecord.host_cpp.generated_makefile_sha256
        'build.log' = $modelRecord.host_cpp.build_log_sha256
    }.GetEnumerator()) {
        if ((Get-FileHash -LiteralPath (Join-Path $modelDir $item.Key) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $item.Value) {
            throw "Production model build evidence changed: $($item.Key)"
        }
    }
    if ($Kind -eq 'Long') {
        foreach ($name in $rtl | Where-Object { $_ -like 'rtl/*' }) {
            if ($modelRecord.source_files.PSObject.Properties[$name].Value -cne $snapshotInputs[$name]) {
                throw "Verilator model and final PDS snapshot disagree: $name"
            }
        }
    }
    $modelHash = (Get-FileHash -LiteralPath $model -Algorithm SHA256).Hash.ToLowerInvariant()
    $romHash = (Get-FileHash -LiteralPath $rom -Algorithm SHA256).Hash.ToLowerInvariant()
    $firmwareHash = (Get-FileHash -LiteralPath $bin -Algorithm SHA256).Hash.ToLowerInvariant()
    $env:PATH = (Join-Path $MsysRoot 'mingw64/bin') + ';' + (Join-Path $MsysRoot 'usr/bin') + ';' + $env:PATH
    $python = Join-Path $MsysRoot 'mingw64/bin/python3.exe'
    if (!(Test-Path -LiteralPath $python -PathType Leaf)) { throw "Missing MinGW Python: $python" }
    $cases = New-Object 'Collections.Generic.List[object]'
    $groupWallSeconds = $null
    for ($index = 0; $index -lt $runModes.Count; $index++) {
        $mode = $runModes[$index]
        $stem = ('run{0:D2}-{1}' -f ($index + 1),$mode)
        $log = Join-Path $out "$stem.log"
        $resultPath = Join-Path $out "$stem.json"
        $arguments = "+production_coremark +coremark_mode=$mode +cpu_hz=$CpuHz +max_cycles=$MaxCycles"
        if ($Kind -eq 'Pilot') {
            $slashRom = $rom.Replace('\','/')
            $arguments += ' +coremark_pilot "+coremark_rom=' + $slashRom + '"'
        }
        $cases.Add([pscustomobject]@{
            name = $stem; mode = $mode; log = $log; result_path = $resultPath
            arguments = $arguments; wall_seconds = $null
        })
    }
    if ($Kind -eq 'Long') {
        if (!('CpuSimulation.GroupProcess' -as [type])) {
            Add-Type -Path (Join-Path $PSScriptRoot 'coremark_simulation_group.cs')
        }
        $groupWatch = [Diagnostics.Stopwatch]::StartNew()
        [CpuSimulation.GroupProcess]::RunGroup(
            $model, [string[]]@($cases | ForEach-Object { $_.arguments }), $root,
            [string[]]@($cases | ForEach-Object { $_.log }),
            [string[]]@($cases | ForEach-Object { $_.log + '.stderr.log' }),
            [string[]]@($cases | ForEach-Object { $_.name }),
            $TimeoutSeconds, (Join-Path $out 'active-processes.txt'))
        $groupWatch.Stop()
        $groupWallSeconds = $groupWatch.Elapsed.TotalSeconds
    } else {
        foreach ($case in $cases) {
            $watch = [Diagnostics.Stopwatch]::StartNew()
            $null = Invoke-BoundedProcess -Executable $model -Arguments $case.arguments `
                -Directory $root -Log $case.log -TimeoutSeconds $TimeoutSeconds
            $watch.Stop()
            $case.wall_seconds = $watch.Elapsed.TotalSeconds
        }
    }
    $results = @()
    foreach ($case in $cases) {
        $mode = $case.mode
        $stem = $case.name
        & $python (Join-Path $PSScriptRoot 'check_coremark_production_sim.py') `
            --log $case.log --mode $mode --kind $Kind.ToLowerInvariant() --rom $rom --binary $bin `
            --build-manifest $build --cpu-source (Join-Path $root 'rtl/cpu/source.json') `
            --cpu-rtl $cpu --cpu-hz $CpuHz --expected-iterations $(if ($Kind -eq 'Pilot') { 10 } else { $Iterations }) `
            --output $case.result_path
        if ($LASTEXITCODE) { throw "CoreMark simulation validation failed: $stem" }
        $result = Get-Content -LiteralPath $case.result_path -Raw -Encoding utf8 | ConvertFrom-Json
        $results += [ordered]@{ name = $stem; mode = $mode; result = $result; wall_seconds = $case.wall_seconds }
        $wallLabel = if ($Kind -eq 'Long') { "group_wall_seconds=$([math]::Round($groupWallSeconds,3))" } else { "wall_seconds=$([math]::Round($case.wall_seconds,3))" }
        Write-Output "PRODUCTION_COREMARK_SIM_$($Kind.ToUpperInvariant())_PASS $stem ticks=$($result.ticks) cycles=$($result.simulator_total_cycles) $wallLabel"
    }
    if ((Get-FileHash -LiteralPath $model -Algorithm SHA256).Hash.ToLowerInvariant() -cne $modelHash -or
        (Get-FileHash -LiteralPath $rom -Algorithm SHA256).Hash.ToLowerInvariant() -cne $romHash -or
        (Get-FileHash -LiteralPath $bin -Algorithm SHA256).Hash.ToLowerInvariant() -cne $firmwareHash -or
        (Get-FileHash -LiteralPath $cpu -Algorithm SHA256).Hash.ToLowerInvariant() -cne $source.sha256) {
        throw 'Model, firmware, ROM or CPU changed during simulation.'
    }
    if ($Kind -eq 'Long' -and
        ((Get-FileHash -LiteralPath (Join-Path $root 'artifacts/build_snapshot.json') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $snapshotHash -or
         (Get-FileHash -LiteralPath (Join-Path $root 'artifacts/build_evidence.json') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $evidenceHash -or
         (Get-FileHash -LiteralPath (Join-Path $root 'artifacts/soc_top.sbit') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $releasedBitstreamHash)) {
        throw 'Final PDS snapshot, evidence or bitstream changed during timed simulation.'
    }
    if ($Kind -eq 'Long') {
        $pllClock = Assert-CoremarkPllClock -Root $root -CpuHz $CpuHz
        $timingReport = Assert-CoremarkFinalTiming -Root $root
        & (Join-Path $PSScriptRoot 'audit_project.ps1') -Root $root
    }
    $performanceScore = $null
    if ($Kind -eq 'Long') {
        $performance = @($results | Where-Object { $_.mode -eq 'performance' })
        $validation = @($results | Where-Object { $_.mode -eq 'validation' })
        if ($performance.Count -ne 3 -or $validation.Count -ne 1) {
            throw 'Timed result set is not the required three performance runs plus one validation run.'
        }
        $finalCrcs = @($performance | ForEach-Object { $_.result.crc.'[0]crcfinal' } | Select-Object -Unique)
        if ($finalCrcs.Count -ne 1) {
            throw 'The three performance runs did not produce the same final CRC.'
        }
        [double[]]$scores = @($performance | ForEach-Object { [double]$_.result.coremark_per_mhz } | Sort-Object)
        $performanceScore = [ordered]@{
            minimum = $scores[0]
            mean = ($scores[0] + $scores[1] + $scores[2]) / 3.0
            median = $scores[1]
            maximum = $scores[2]
            range = $scores[2] - $scores[0]
            final_crc = $finalCrcs[0]
            unit = 'CoreMark/MHz'
        }
    }
    $targetObjectFlags = [ordered]@{}
    $hotBootloader = @('sw/bootloader/camera.c','sw/bootloader/crc32_fast.c',
        'sw/bootloader/png_rgb565.c')
    $coremarkObjects = 0
    $hotObjects = 0
    $otherObjects = 0
    foreach ($command in @($productionRecord.build_commands | Where-Object {
        $_.kind -in @('compile_bootloader','compile_coremark')
    })) {
        $sourceArgs = @($command.argv | Where-Object { $_ -match '^@SOC_ROOT@[\\/].*\.(?:c|S)$' })
        $optimizationArgs = @($command.argv | Where-Object { $_ -match '^-O(?:[0-3sgz]|fast)$' })
        if ($sourceArgs.Count -ne 1 -or $optimizationArgs.Count -ne 1) {
            throw 'Target firmware compiler argv lacks a unique source or optimization flag'
        }
        $sourceName = $sourceArgs[0].Substring('@SOC_ROOT@\'.Length).Replace('\','/')
        if ($targetObjectFlags.Contains($sourceName)) { throw "Duplicate target object recipe: $sourceName" }
        $expectedFlag = if ($command.kind -eq 'compile_coremark') {
            $coremarkObjects++; '-O2'
        } elseif ($sourceName -cin $hotBootloader) {
            $hotObjects++; '-O2'
        } else {
            $otherObjects++; '-Os'
        }
        if ($optimizationArgs[0] -cne $expectedFlag) {
            throw "Target firmware optimization differs from actual argv: $sourceName"
        }
        $targetObjectFlags[$sourceName] = $optimizationArgs[0]
    }
    if ($coremarkObjects -ne 6 -or $hotObjects -ne 3 -or $otherObjects -ne 13) {
        throw 'Target firmware object optimization inventory changed'
    }
    $clockQuantization = $results[0].result.sim_clock_quantization
    foreach ($case in $results) {
        if ($case.result.sim_clock_quantization.cpu_half_fs -ne $clockQuantization.cpu_half_fs -or
            $case.result.sim_clock_quantization.sys_half_fs -ne $clockQuantization.sys_half_fs) {
            throw 'CoreMark cases used different simulated clock quantization'
        }
    }
    $summary = [ordered]@{
        status = if ($Kind -eq 'Pilot') { 'PILOT_ONLY_NOT_A_SCORE' } else { 'RTL_3_PLUS_1_TIMED_PASS_NOT_BOARD' }
        kind = $Kind; cpu_hz = $CpuHz; sys_hz = $clock.sys_hz; timebase_hz = $clock.timebase_hz; isa = $source.isa
        pll_clock = $pllClock
        final_timing = $timingReport
        iteration_policy = if ($Kind -eq 'Pilot') { 'fixed_ten_pilot' } elseif ($Iterations -eq 0) { 'production_automatic_calibration' } else { 'fixed_release_candidate' }
        fixed_iterations = if ($Kind -eq 'Pilot') { 10 } elseif ($Iterations -eq 0) { $null } else { $Iterations }
        concurrent_runs = $Kind -eq 'Long'
        cpu_rtl_sha256 = $source.sha256
        production_bootloader_sha256 = $productionRecord.binary_sha256
        executed_firmware_sha256 = $firmwareHash
        executed_rom_sha256 = $romHash
        model_sha256 = $modelHash
        model_manifest_sha256 = (Get-FileHash -LiteralPath $modelRecordPath -Algorithm SHA256).Hash.ToLowerInvariant()
        host_model_compilation = [ordered]@{
            explicit_cpp_flags = '-Os'
            observed_cpp_command_count = $modelRecord.host_cpp.compile_command_count
            generated_makefile_sha256 = $modelRecord.host_cpp.generated_makefile_sha256
            verilated_mk_sha256 = $modelRecord.host_cpp.verilated_mk_sha256
            build_script_sha256 = $modelRecord.build_script_sha256
            build_log_sha256 = $modelRecord.host_cpp.build_log_sha256
        }
        target_firmware_compilation = [ordered]@{
            compiler = $productionRecord.compiler
            compiler_version = $productionRecord.compiler_version
            build_manifest_sha256 = (Get-FileHash -LiteralPath $productionBuild -Algorithm SHA256).Hash.ToLowerInvariant()
            coremark_o2_objects = $coremarkObjects
            hot_bootloader_o2_objects = $hotObjects
            other_bootloader_os_objects = $otherObjects
            object_flags = $targetObjectFlags
        }
        sim_clock_quantization = $clockQuantization
        cpu_cycle_observation_scope = 'Observed CPU edges from real timer release through the returned console prompt; includes UART/command overhead, not exact CoreMark timed-interval cycles.'
        pds_snapshot_run_id = if ($Kind -eq 'Long') { $snapshot.run_id } else { $null }
        pds_snapshot_sha256 = $snapshotHash
        pds_build_evidence_sha256 = $evidenceHash
        released_bitstream_sha256 = $releasedBitstreamHash
        run_plan = $runModes
        cases = $results
        group_wall_seconds = $groupWallSeconds
        performance_score = $performanceScore
        scope = 'Unaccelerated CLINT during production console CoreMark command; pre-console PHY wait accelerated only. No board or maximum-frequency claim.'
    }
    $summaryPath = Join-Path $out 'summary.json'
    [IO.File]::WriteAllText($summaryPath, ($summary | ConvertTo-Json -Depth 12) + "`n", [Text.UTF8Encoding]::new($false))
    if ($releasePath) {
        $published = Publish-CoremarkReleaseEvidence -Root $root -OutputDirectory $out `
            -Destination $releasePath -Cases $cases -Model $model -SummaryPath $summaryPath
        Write-Output "PRODUCTION_COREMARK_RELEASE_EVIDENCE_PASS path=$published"
    }
    Write-Output "PRODUCTION_COREMARK_SIM_$($Kind.ToUpperInvariant())_COMPLETE evidence=$out"
} finally {
    $env:PATH = $originalPath
}
