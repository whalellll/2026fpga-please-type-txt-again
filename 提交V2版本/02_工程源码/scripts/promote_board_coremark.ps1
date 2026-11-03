param(
    [Parameter(Mandatory=$true)][string]$MeasurementDirectory,
    [Parameter(Mandatory=$true)][string]$ProgramEvidence,
    [Parameter(Mandatory=$true)][string]$ProgramLog,
    [Parameter(Mandatory=$true)][string]$PreflightLog,
    [Parameter(Mandatory=$true)][string]$Destination,
    [string]$PythonPath = 'D:\LJL\WORK\Anaconda3\python.exe',
    [string]$HostGccPath = 'D:\LJL\WORK\msys64\mingw64\bin\gcc.exe'
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
. (Join-Path $PSScriptRoot 'coremark_release_checks.ps1')
$dest = Resolve-CoremarkReleaseEvidencePath -Root $root -Requested $Destination
$stage = Join-Path $root ('artifacts/selftest/board-release-stage-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stage -Force | Out-Null
$files = [ordered]@{
    'uart.txt' = Join-Path $MeasurementDirectory 'uart.log'
    'result.json' = Join-Path $MeasurementDirectory 'result.json'
    'program.json' = $ProgramEvidence
    'program.txt' = $ProgramLog
    'preflight.txt' = $PreflightLog
    'clock.json' = Join-Path $root 'config/clocks.json'
    'cpu_source.json' = Join-Path $root 'rtl/cpu/source.json'
    'fpga_input_snapshot.json' = Join-Path $root 'artifacts/build_snapshot.json'
    'fpga_build_evidence.json' = Join-Path $root 'artifacts/build_evidence.json'
    'firmware.build.json' = Join-Path $root 'artifacts/bootloader.build.json'
    'firmware.bin' = Join-Path $root 'artifacts/bootloader.bin'
    'bootrom.hex' = Join-Path $root 'artifacts/bootrom.hex'
    'soc_top.sbit' = Join-Path $root 'artifacts/soc_top.sbit'
    'pll_video.v' = Join-Path $root 'rtl/video/pll_video.v'
    'soc.fdc' = Join-Path $root 'pds/soc.fdc'
}
foreach ($name in @('timing_summary.txt','preflight_gate.json','cpu_ads_controls.json',
    'cpu_sys_cdc_ads.json','icache_pad_ads.json','final_timing_report.txt','final_timing_xml.xml')) {
    $files[$name] = Join-Path $root ('artifacts/' + $name)
}
$hashes = [ordered]@{}
foreach ($name in $files.Keys) {
    $source = Get-Item -LiteralPath $files[$name] -Force
    if ($source.PSIsContainer -or ($source.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Board evidence source is not a regular file: $($files[$name])"
    }
    Copy-Item -LiteralPath $source.FullName -Destination (Join-Path $stage $name)
    $hashes[$name] = (Get-FileHash -LiteralPath (Join-Path $stage $name) -Algorithm SHA256).Hash.ToLowerInvariant()
}
$session = [ordered]@{
    schema_version = 1
    evidence_kind = 'board_coremark_session'
    status = 'BOARD_COREMARK_3_PLUS_1_PASS'
    created_utc = [DateTime]::UtcNow.ToString('o')
    files_sha256 = $hashes
    scope = 'One fresh volatile CRAM load, sequential live performance 3+1 and same-run FPGA evidence; no Flash or SD writes.'
}
$sessionPath = Join-Path $stage 'session.json'
[IO.File]::WriteAllText($sessionPath, ($session | ConvertTo-Json -Depth 12) + "`n", [Text.UTF8Encoding]::new($false))
Write-Output 'Board evidence validation: normally under 15 seconds; each host compile/reference process has a 60-second bound. Ctrl+C stops verification; unpromoted staging evidence is retained.'
& $PythonPath -B (Join-Path $root 'scripts/verify_board_release.py') --root $root --session $sessionPath --host-gcc $HostGccPath
if ($LASTEXITCODE -ne 0) { throw "Board evidence staging validation failed; retained at $stage" }
if (Test-Path -LiteralPath $dest) { throw 'Board evidence destination was created during validation' }
[IO.Directory]::Move($stage, $dest)
Write-Output "SOC_BOARD_COREMARK_PROMOTION_PASS path=$dest"
