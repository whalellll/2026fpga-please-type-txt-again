param(
    [Parameter(Mandatory=$true)][string]$PilotDirectory,
    [string]$Destination,
    [string]$PythonPath = 'D:\LJL\WORK\msys64\mingw64\bin\python3.exe'
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd('\')
$scratch = [IO.Path]::GetFullPath((Join-Path $root 'artifacts/selftest')).TrimEnd('\')
$pilot = [IO.Path]::GetFullPath($PilotDirectory).TrimEnd('\')
if (!$pilot.StartsWith($scratch + '\', [StringComparison]::OrdinalIgnoreCase) -or
    !(Test-Path -LiteralPath $pilot -PathType Container)) {
    throw 'Short pilot source must be an existing artifacts/selftest directory in this checkout'
}
. (Join-Path $PSScriptRoot 'coremark_release_checks.ps1')
if (!$Destination) {
    $version = [IO.File]::ReadAllText((Join-Path $root 'VERSION')).Trim()
    $Destination = 'docs/validation/v' + $version.Replace('.', '_') + '-short-pilot'
}
$dest = Resolve-CoremarkReleaseEvidencePath -Root $root -Requested $Destination
$summary = [IO.File]::ReadAllText((Join-Path $pilot 'summary.json')) | ConvertFrom-Json
$clock = [IO.File]::ReadAllText((Join-Path $root 'config/clocks.json')) | ConvertFrom-Json
if ($summary.status -cne 'PILOT_ONLY_NOT_A_SCORE' -or $summary.kind -cne 'Pilot' -or
    $summary.cpu_hz -ne $clock.cpu_hz -or $summary.sys_hz -ne $clock.sys_hz -or
    $summary.timebase_hz -ne $clock.timebase_hz -or @($summary.cases).Count -ne 2 -or
    (@($summary.run_plan) -join ',') -cne 'performance,validation') {
    throw 'Source is not the completed current-clock two-mode short pilot'
}
$stage = Join-Path $scratch ('short-pilot-release-stage-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stage | Out-Null
$files = [ordered]@{
    'summary.json' = Join-Path $pilot 'summary.json'
    'run01-performance.json' = Join-Path $pilot 'run01-performance.json'
    'run01-performance.uart.txt' = Join-Path $pilot 'run01-performance.log'
    'run01-performance.stderr.txt' = Join-Path $pilot 'run01-performance.log.stderr.log'
    'run02-validation.json' = Join-Path $pilot 'run02-validation.json'
    'run02-validation.uart.txt' = Join-Path $pilot 'run02-validation.log'
    'run02-validation.stderr.txt' = Join-Path $pilot 'run02-validation.log.stderr.log'
    'verilator_model.json' = Join-Path $pilot 'verilator_model/model.json'
    'verilator_model.exe' = Join-Path $pilot 'verilator_model/Vtb_cpu_integration.exe'
    'verilator_build.txt' = Join-Path $pilot 'verilator_model/build.log'
    'verilator_build_script.txt' = Join-Path $pilot 'verilator_model/build.sh'
    'verilator_generated_makefile.txt' = Join-Path $pilot 'verilator_model/Vtb_cpu_integration.mk'
    'pilot_firmware_build.json' = Join-Path $pilot 'pilot_firmware/fixed-build.json'
    'pilot_bootloader.build.json' = Join-Path $pilot 'pilot_firmware/fixed_bootloader.build.json'
    'pilot_bootloader.bin' = Join-Path $pilot 'pilot_firmware/fixed_bootloader.bin'
    'pilot_bootrom.hex' = Join-Path $pilot 'pilot_firmware/fixed_bootrom.hex'
    'production_bootloader.build.json' = Join-Path $root 'artifacts/bootloader.build.json'
    'cpu_source.json' = Join-Path $root 'rtl/cpu/source.json'
    'fpga_input_snapshot.json' = Join-Path $root 'artifacts/build_snapshot.json'
    'fpga_build_evidence.json' = Join-Path $root 'artifacts/build_evidence.json'
    'timing_summary.txt' = Join-Path $root 'artifacts/timing_summary.txt'
}
$hashes = [ordered]@{}
foreach ($name in $files.Keys) {
    $source = $files[$name]
    if (!(Test-Path -LiteralPath $source -PathType Leaf) -or
        ((Get-Item -LiteralPath $source -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Missing or linked short pilot source: $source"
    }
    $target = Join-Path $stage $name
    Copy-Item -LiteralPath $source -Destination $target
    $hashes[$name] = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
}
$snapshot = [IO.File]::ReadAllText((Join-Path $stage 'fpga_input_snapshot.json')) | ConvertFrom-Json
$fpga = [IO.File]::ReadAllText((Join-Path $stage 'fpga_build_evidence.json')) | ConvertFrom-Json
$record = [ordered]@{
    schema_version = 1
    evidence_kind = 'short_pilot'
    status = 'RTL_SHORT_PILOT_ESTIMATE_NOT_A_SCORE_NOT_BOARD'
    created_utc = [datetime]::UtcNow.ToString('o')
    formal_coremark_score_valid = $false
    board_acceptance = $false
    firmware_matches_released_bitstream = $false
    cpu_hz = $summary.cpu_hz
    sys_hz = $summary.sys_hz
    timebase_hz = $summary.timebase_hz
    iterations_per_mode = 10
    target_minimum_seconds = 10
    run_plan = @('performance','validation')
    performance_target_seconds = $summary.cases[0].result.timer_seconds
    validation_target_seconds = $summary.cases[1].result.timer_seconds
    performance_estimate_coremark_per_mhz = $summary.cases[0].result.coremark_per_mhz
    validation_estimate_coremark_per_mhz = $summary.cases[1].result.coremark_per_mhz
    performance_crcfinal = $summary.cases[0].result.crc.'[0]crcfinal'
    validation_crcfinal = $summary.cases[1].result.crc.'[0]crcfinal'
    pds_snapshot_run_id = $snapshot.run_id
    pds_snapshot_sha256 = $hashes['fpga_input_snapshot.json']
    pds_build_evidence_sha256 = $hashes['fpga_build_evidence.json']
    released_bitstream_sha256 = $fpga.outputs.'artifacts/soc_top.sbit'
    release_firmware_binary_sha256 = $snapshot.inputs.'artifacts/bootloader.bin'
    release_bootrom_sha256 = $snapshot.inputs.'artifacts/bootrom.hex'
    pilot_firmware_binary_sha256 = $hashes['pilot_bootloader.bin']
    pilot_bootrom_sha256 = $hashes['pilot_bootrom.hex']
    cpu_rtl_sha256 = $summary.cpu_rtl_sha256
    verilator_model_sha256 = $hashes['verilator_model.exe']
    verilator_model_manifest_sha256 = $hashes['verilator_model.json']
    files_sha256 = $hashes
    limitations = @(
        'Each fixed-ten run is below the CoreMark ten-second minimum; the UART explicitly reports COREMARK_FAIL. Exact ticks and durations are recorded per mode.',
        'The pilot used a distinct fixed-ten firmware and ROM; the released FPGA bitstream contains the separately hashed production bootloader and ROM.',
        'The model and FPGA inputs share the recorded CPU, CDC and clock source hashes. This does not prove a timed run of the released firmware or board operation.',
        'The displayed CoreMark/MHz values are short-run estimates only, not official or production 3+1 scores.'
    )
}
[IO.File]::WriteAllText((Join-Path $stage 'release_evidence.json'),
    ($record | ConvertTo-Json -Depth 12) + "`n", [Text.UTF8Encoding]::new($false))
& (Join-Path $PSScriptRoot 'verify_coremark_short_pilot_evidence.ps1') `
    -Root $root -EvidenceDirectory $stage -PythonPath $PythonPath
if ($LASTEXITCODE -ne 0) { throw 'Short pilot staging verification failed' }
if (Test-Path -LiteralPath $dest) { throw 'Short pilot destination was created during staging' }
[IO.Directory]::Move($stage, $dest)
Write-Output "SOC_SHORT_PILOT_PROMOTION_PASS path=$dest"
