param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [string]$EvidenceDirectory,
    [string]$PythonPath = 'D:\LJL\WORK\msys64\mingw64\bin\python3.exe'
)
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath($Root).TrimEnd('\')
if (!$EvidenceDirectory) {
    $version = [IO.File]::ReadAllText((Join-Path $Root 'VERSION')).Trim()
    $EvidenceDirectory = 'docs/validation/v' + $version.Replace('.', '_') + '-short-pilot'
}
$directory = if ([IO.Path]::IsPathRooted($EvidenceDirectory)) {
    [IO.Path]::GetFullPath($EvidenceDirectory).TrimEnd('\')
} else {
    [IO.Path]::GetFullPath((Join-Path $Root $EvidenceDirectory)).TrimEnd('\')
}
if (!(Test-Path -LiteralPath $directory -PathType Container)) { throw "Missing short pilot evidence: $directory" }

function Get-ShortHash([string]$Path) {
    if (!(Test-Path -LiteralPath $Path -PathType Leaf) -or
        ((Get-Item -LiteralPath $Path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Missing or linked short pilot file: $Path"
    }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Assert-ShortEqual($Actual, $Expected, [string]$Label) {
    if ($Actual -cne $Expected) { throw "Short pilot evidence mismatch: $Label" }
}

$names = @(
    'summary.json', 'run01-performance.json', 'run01-performance.uart.txt',
    'run01-performance.stderr.txt', 'run02-validation.json',
    'run02-validation.uart.txt', 'run02-validation.stderr.txt',
    'verilator_model.json', 'verilator_model.exe', 'verilator_build.txt',
    'verilator_build_script.txt', 'verilator_generated_makefile.txt',
    'pilot_firmware_build.json', 'pilot_bootloader.build.json',
    'pilot_bootloader.bin', 'pilot_bootrom.hex',
    'production_bootloader.build.json', 'cpu_source.json',
    'fpga_input_snapshot.json', 'fpga_build_evidence.json', 'timing_summary.txt'
)
$nodes = @(Get-ChildItem -LiteralPath $directory -Recurse -Force)
if ((Get-Item -LiteralPath $directory -Force).Attributes -band [IO.FileAttributes]::ReparsePoint -or
    @($nodes | Where-Object { $_.PSIsContainer -or ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) }).Count -or
    @(Compare-Object (@($names + 'release_evidence.json') | Sort-Object) (@($nodes.Name) | Sort-Object)).Count) {
    throw 'Short pilot evidence has missing, extra, directory, or linked entries'
}
$release = [IO.File]::ReadAllText((Join-Path $directory 'release_evidence.json')) | ConvertFrom-Json
$summary = [IO.File]::ReadAllText((Join-Path $directory 'summary.json')) | ConvertFrom-Json
$clock = [IO.File]::ReadAllText((Join-Path $Root 'config/clocks.json')) | ConvertFrom-Json
if ($release.schema_version -ne 1 -or $release.evidence_kind -cne 'short_pilot' -or
    $release.status -cne 'RTL_SHORT_PILOT_ESTIMATE_NOT_A_SCORE_NOT_BOARD' -or
    $release.formal_coremark_score_valid -ne $false -or $release.board_acceptance -ne $false -or
    $release.iterations_per_mode -ne 10 -or $release.target_minimum_seconds -ne 10 -or
    (@($release.run_plan) -join ',') -cne 'performance,validation' -or
    $release.firmware_matches_released_bitstream -ne $false -or
    $release.cpu_hz -ne $clock.cpu_hz -or $release.sys_hz -ne $clock.sys_hz -or
    $release.timebase_hz -ne $clock.timebase_hz -or
    $summary.status -cne 'PILOT_ONLY_NOT_A_SCORE' -or $summary.kind -cne 'Pilot' -or
    $summary.iteration_policy -cne 'fixed_ten_pilot' -or $summary.fixed_iterations -ne 10 -or
    $summary.concurrent_runs -ne $false -or
    $summary.cpu_hz -ne $clock.cpu_hz -or $summary.sys_hz -ne $clock.sys_hz -or
    $summary.timebase_hz -ne $clock.timebase_hz -or
    (@($summary.run_plan) -join ',') -cne 'performance,validation' -or
    @($summary.cases).Count -ne 2 -or $null -ne $summary.performance_score -or
    $null -ne $summary.pds_snapshot_sha256 -or $null -ne $summary.released_bitstream_sha256) {
    throw 'Short pilot marker, clock, or explicit non-score policy is invalid'
}
$hashFields = @($release.files_sha256.PSObject.Properties)
if ($hashFields.Count -ne $names.Count -or
    @(Compare-Object ($names | Sort-Object) ($hashFields.Name | Sort-Object)).Count) {
    throw 'Short pilot hash inventory is incomplete'
}
foreach ($field in $hashFields) {
    if ($field.Value -cnotmatch '^[0-9a-f]{64}$') { throw "Malformed short pilot hash: $($field.Name)" }
    Assert-ShortEqual (Get-ShortHash (Join-Path $directory $field.Name)) $field.Value $field.Name
}
$file = { param($Name) Join-Path $directory $Name }
$source = [IO.File]::ReadAllText((& $file 'cpu_source.json')) | ConvertFrom-Json
$snapshot = [IO.File]::ReadAllText((& $file 'fpga_input_snapshot.json')) | ConvertFrom-Json
$fpga = [IO.File]::ReadAllText((& $file 'fpga_build_evidence.json')) | ConvertFrom-Json
$model = [IO.File]::ReadAllText((& $file 'verilator_model.json')) | ConvertFrom-Json
$pilotBuild = [IO.File]::ReadAllText((& $file 'pilot_firmware_build.json')) | ConvertFrom-Json
$pilotManifest = [IO.File]::ReadAllText((& $file 'pilot_bootloader.build.json')) | ConvertFrom-Json
$productionManifest = [IO.File]::ReadAllText((& $file 'production_bootloader.build.json')) | ConvertFrom-Json
foreach ($binding in @(
    @('pds_snapshot_sha256', 'artifacts/build_snapshot.json'),
    @('pds_build_evidence_sha256', 'artifacts/build_evidence.json'),
    @('released_bitstream_sha256', 'artifacts/soc_top.sbit'),
    @('release_firmware_binary_sha256', 'artifacts/bootloader.bin'),
    @('release_bootrom_sha256', 'artifacts/bootrom.hex')
)) {
    Assert-ShortEqual $release.($binding[0]) (Get-ShortHash (Join-Path $Root $binding[1])) $binding[0]
}
foreach ($binding in @(
    @('fpga_input_snapshot.json', 'artifacts/build_snapshot.json'),
    @('fpga_build_evidence.json', 'artifacts/build_evidence.json'),
    @('timing_summary.txt', 'artifacts/timing_summary.txt'),
    @('cpu_source.json', 'rtl/cpu/source.json'),
    @('production_bootloader.build.json', 'artifacts/bootloader.build.json')
)) {
    Assert-ShortEqual $release.files_sha256.($binding[0]) (Get-ShortHash (Join-Path $Root $binding[1])) $binding[0]
}
Assert-ShortEqual $snapshot.run_id $release.pds_snapshot_run_id 'PDS run ID'
Assert-ShortEqual $fpga.input_snapshot_sha256 $release.pds_snapshot_sha256 'PDS input snapshot'
Assert-ShortEqual $fpga.timing 'All Constraints Met' 'PDS timing acceptance'
Assert-ShortEqual $fpga.outputs.'artifacts/soc_top.sbit' $release.released_bitstream_sha256 'PDS bitstream'
Assert-ShortEqual $fpga.outputs.'artifacts/timing_summary.txt' $release.files_sha256.'timing_summary.txt' 'PDS timing summary'
Assert-ShortEqual $snapshot.inputs.'config/clocks.json' (Get-ShortHash (Join-Path $Root 'config/clocks.json')) 'clock snapshot'
Assert-ShortEqual $snapshot.inputs.'artifacts/bootloader.bin' $release.release_firmware_binary_sha256 'release firmware snapshot'
Assert-ShortEqual $snapshot.inputs.'artifacts/bootrom.hex' $release.release_bootrom_sha256 'release ROM snapshot'
Assert-ShortEqual $productionManifest.binary_sha256 $release.release_firmware_binary_sha256 'production manifest'
Assert-ShortEqual $pilotBuild.production_bootloader_sha256 $release.release_firmware_binary_sha256 'pilot-to-production build link'
Assert-ShortEqual $summary.production_bootloader_sha256 $release.release_firmware_binary_sha256 'summary-to-production link'
Assert-ShortEqual $summary.target_firmware_compilation.build_manifest_sha256 $release.files_sha256.'production_bootloader.build.json' 'summary target build manifest'
Assert-ShortEqual $pilotBuild.fixed_bin_sha256 $release.pilot_firmware_binary_sha256 'pilot build binary'
Assert-ShortEqual $pilotBuild.fixed_rom_sha256 $release.pilot_bootrom_sha256 'pilot build ROM'
Assert-ShortEqual $pilotManifest.binary_sha256 $release.pilot_firmware_binary_sha256 'pilot manifest binary'
Assert-ShortEqual $pilotManifest.coremark_iterations 10 'pilot manifest iterations'
Assert-ShortEqual $pilotBuild.iterations 10 'pilot build iterations'
Assert-ShortEqual $pilotBuild.status 'PILOT_ONLY_NOT_RELEASE_FIRMWARE' 'pilot firmware status'
Assert-ShortEqual $pilotBuild.cpu_hz $clock.cpu_hz 'pilot firmware clock'
Assert-ShortEqual $release.pilot_firmware_binary_sha256 (Get-ShortHash (& $file 'pilot_bootloader.bin')) 'pilot binary'
Assert-ShortEqual $release.pilot_bootrom_sha256 (Get-ShortHash (& $file 'pilot_bootrom.hex')) 'pilot ROM'
if ($release.pilot_firmware_binary_sha256 -ceq $release.release_firmware_binary_sha256 -or
    $release.pilot_bootrom_sha256 -ceq $release.release_bootrom_sha256) {
    throw 'Short pilot firmware must be explicitly distinct from released bitstream firmware'
}
Assert-ShortEqual $source.sha256 (Get-ShortHash (Join-Path $Root 'rtl/cpu/CoreTop.sv')) 'CPU source manifest'
Assert-ShortEqual $summary.cpu_rtl_sha256 $source.sha256 'summary CPU RTL'
Assert-ShortEqual $release.cpu_rtl_sha256 $source.sha256 'release CPU RTL'
Assert-ShortEqual $snapshot.inputs.'rtl/cpu/CoreTop.sv' $source.sha256 'PDS CPU RTL'
Assert-ShortEqual $pilotBuild.cpu_rtl_sha256 $source.sha256 'pilot build CPU RTL'
if ($source.isa -cne 'rv32ima_zicsr_zifencei' -or $source.compressed_instructions -ne $false -or
    $pilotManifest.march -cne $source.isa -or $pilotManifest.abi -cne 'ilp32' -or
    $pilotManifest.compiler_version -cne '16.2.0' -or
    $pilotManifest.elf_metadata.ElfClass -cne 'ELF32' -or
    $pilotManifest.elf_metadata.Flags -notmatch 'no RVC' -or
    $pilotManifest.optimization -notmatch 'CoreMark -O2 -DITERATIONS=10') {
    throw 'Pilot target compilation differs from the claimed RV32IMA fixed-ten recipe'
}
foreach ($entry in @($pilotBuild.source_files.PSObject.Properties)) {
    Assert-ShortEqual $entry.Value (Get-ShortHash (Join-Path $Root $entry.Name)) "pilot target source $($entry.Name)"
}
foreach ($entry in @($model.source_files.PSObject.Properties)) {
    $actual = Get-ShortHash (Join-Path $Root $entry.Name)
    Assert-ShortEqual $entry.Value $actual "model RTL source $($entry.Name)"
    if ($null -ne $snapshot.inputs.PSObject.Properties[$entry.Name]) {
        Assert-ShortEqual $snapshot.inputs.($entry.Name) $actual "PDS RTL source $($entry.Name)"
    }
}
Assert-ShortEqual $release.verilator_model_sha256 (Get-ShortHash (& $file 'verilator_model.exe')) 'Verilator executable'
Assert-ShortEqual $release.verilator_model_manifest_sha256 $release.files_sha256.'verilator_model.json' 'Verilator manifest hash'
Assert-ShortEqual $model.model_sha256 $release.verilator_model_sha256 'Verilator model record'
Assert-ShortEqual $summary.model_sha256 $release.verilator_model_sha256 'summary model'
Assert-ShortEqual $summary.model_manifest_sha256 $release.verilator_model_manifest_sha256 'summary model manifest'
Assert-ShortEqual $model.build_script_sha256 $release.files_sha256.'verilator_build_script.txt' 'model build script'
Assert-ShortEqual $model.host_cpp.build_log_sha256 $release.files_sha256.'verilator_build.txt' 'model build log'
Assert-ShortEqual $model.host_cpp.generated_makefile_sha256 $release.files_sha256.'verilator_generated_makefile.txt' 'model makefile'
if ($model.host_cpp.explicit_cflags -cne '-Os' -or $model.host_cpp.compiler_argv_observed -ne $true -or
    $model.host_cpp.compile_command_count -lt 1 -or
    @($model.host_cpp.compile_commands).Count -ne $model.host_cpp.compile_command_count -or
    $summary.host_model_compilation.explicit_cpp_flags -cne '-Os' -or
    $summary.host_model_compilation.observed_cpp_command_count -ne $model.host_cpp.compile_command_count) {
    throw 'Short pilot Verilator -Os compiler provenance is incomplete'
}
foreach ($command in @($model.host_cpp.compile_commands)) {
    $options = @([regex]::Matches($command, '(?<!\S)-O(?:[0-3sgz]|fast)(?!\S)') | ForEach-Object { $_.Value })
    if (!$options.Count -or $options[-1] -cne '-Os') { throw 'Verilator C++ command does not end with -Os optimization' }
}
$modes = @('performance','validation')
$caseNames = @('run01-performance','run02-validation')
$scores = @($release.performance_estimate_coremark_per_mhz, $release.validation_estimate_coremark_per_mhz)
$seconds = @($release.performance_target_seconds, $release.validation_target_seconds)
for ($index = 0; $index -lt 2; $index++) {
    $name = $caseNames[$index]; $mode = $modes[$index]; $case = $summary.cases[$index]
    $result = [IO.File]::ReadAllText((& $file "$name.json")) | ConvertFrom-Json
    if ($case.name -cne $name -or $case.mode -cne $mode -or
        $case.result.status -cne 'PILOT_PASS_NOT_A_SCORE' -or
        $case.result.kind -cne 'pilot' -or $case.result.seed_mode -cne $mode -or
        $case.result.iterations -ne 10 -or $case.result.build_manifest_fixed_iterations -ne 10 -or
        $case.result.timer_seconds -ge 10 -or $case.result.timer_seconds -le 0 -or
        $case.result.ticks -le 0 -or $case.result.timer_stimulus_scale_during_command -ne 1 -or
        $case.result.boot_only_acceleration -ne $true -or
        $case.result.cpu_hz -ne $clock.cpu_hz -or $case.result.sys_hz -ne $clock.sys_hz -or
        $case.result.timebase_hz -ne $clock.timebase_hz -or
        $case.result.firmware_binary_sha256 -cne $release.pilot_firmware_binary_sha256 -or
        $case.result.rom_sha256 -cne $release.pilot_bootrom_sha256 -or
        $case.result.cpu_rtl_sha256 -cne $source.sha256 -or
        $case.result.log_sha256 -cne $release.files_sha256."$name.uart.txt" -or
        $result.log_sha256 -cne $case.result.log_sha256 -or
        $result.ticks -ne $case.result.ticks -or
        $result.coremark_per_mhz -ne $case.result.coremark_per_mhz -or
        $result.crc.'[0]crcfinal' -cne $case.result.crc.'[0]crcfinal' -or
        $scores[$index] -ne $result.coremark_per_mhz -or $seconds[$index] -ne $result.timer_seconds) {
        throw "Short pilot run or estimate is inconsistent: $name"
    }
    $releaseCrc = if ($index -eq 0) { $release.performance_crcfinal } else { $release.validation_crcfinal }
    Assert-ShortEqual $releaseCrc $result.crc.'[0]crcfinal' "pilot final CRC $name"
    $log = [IO.File]::ReadAllText((& $file "$name.uart.txt"))
    if (!$log.Contains('ERROR! Must execute for at least 10 secs for a valid result!') -or
        !$log.Contains('COREMARK_FAIL') -or $log.Contains('COREMARK_PASS') -or
        !$log.Contains("COREMARK_MODE=$mode")) {
        throw "Short pilot UART is not explicitly rejected as an official score: $name"
    }
}
if (!(Get-Command $PythonPath -ErrorAction SilentlyContinue)) { throw "Missing Python for pilot UART recheck: $PythonPath" }
for ($index = 0; $index -lt 2; $index++) {
    $name = $caseNames[$index]; $mode = $modes[$index]
    $recheck = [IO.Path]::GetTempFileName()
    try {
        & $PythonPath (Join-Path $Root 'scripts/check_coremark_production_sim.py') `
            --log (& $file "$name.uart.txt") --mode $mode --kind pilot `
            --rom (& $file 'pilot_bootrom.hex') --binary (& $file 'pilot_bootloader.bin') `
            --build-manifest (& $file 'pilot_bootloader.build.json') `
            --cpu-source (Join-Path $Root 'rtl/cpu/source.json') `
            --cpu-rtl (Join-Path $Root 'rtl/cpu/CoreTop.sv') `
            --cpu-hz $clock.cpu_hz --expected-iterations 10 --output $recheck | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Pilot UART independent recheck failed: $name" }
        Assert-ShortEqual (Get-ShortHash $recheck) $release.files_sha256."$name.json" "pilot UART replay $name"
    } finally {
        Remove-Item -LiteralPath $recheck -Force -ErrorAction SilentlyContinue
    }
}
Write-Output "SOC_SHORT_PILOT_EVIDENCE_PASS cpu_hz=$($clock.cpu_hz) cases=2 formal_score=false"
