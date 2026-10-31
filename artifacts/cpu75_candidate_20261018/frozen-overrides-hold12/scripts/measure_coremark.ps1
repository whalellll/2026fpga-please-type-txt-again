[CmdletBinding(DefaultParameterSetName = 'Board')]
param(
    [Parameter(Mandatory = $true, ParameterSetName = 'Board')][string]$Port,
    [Parameter(Mandatory = $true, ParameterSetName = 'Offline')][string[]]$InputLog,
    [ValidateSet(115200)][int]$BaudRate = 115200,
    [ValidateRange(10, 600)][int]$TimeoutSeconds = 180,
    [ValidateRange(1, 1000000000)][long]$CpuHz = 75000000,
    [ValidateSet('O2', 'O3')][string]$Optimization = 'O2',
    [string]$CompilerVersion = '',
    [string]$BitstreamPath = (Join-Path $PSScriptRoot '../artifacts/soc_top.sbit'),
    [string]$FirmwarePath = (Join-Path $PSScriptRoot '../artifacts/bootloader.bin'),
    [string]$OutputDirectory = (Join-Path ([IO.Path]::GetTempPath()) ('cpu-coremark-' + [guid]::NewGuid().ToString('N')))
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'riscv_toolchain.ps1')
$clock = Get-Content -LiteralPath (Join-Path (Split-Path -Parent $PSScriptRoot) 'config/clocks.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if (!$CompilerVersion) { $CompilerVersion = $CpuGccVersion }
$offline = $PSCmdlet.ParameterSetName -eq 'Offline'
$utf8 = New-Object Text.UTF8Encoding($false)
$capture = New-Object Text.StringBuilder
$serial = $null
$failure = $null
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$resultPath = Join-Path $OutputDirectory 'result.json'
$logPath = Join-Path $OutputDirectory 'uart.log'
if ((Test-Path -LiteralPath $resultPath) -or (Test-Path -LiteralPath $logPath)) {
    throw 'Use a new output directory; existing evidence will not be overwritten.'
}
$report = [ordered]@{
    schema_version = 2
    status = 'INCOMPLETE'
    evidence_kind = $(if ($offline) { 'offline_log_validation' } else { 'board_uart_capture' })
    board_acceptance = $false
    acceptance_scope = 'CoreMark UART only; routed STA and peripheral acceptance are separate'
    transport = $(if ($offline) { 'offline files' } else { "$Port / $BaudRate baud / $TimeoutSeconds seconds per command" })
    captured_utc = [DateTime]::UtcNow.ToString('o')
    frequency = [ordered]@{ candidate_hz = $CpuHz; maximum_verified = $false; source = 'operator-supplied candidate; UART CPU_HZ must match' }
    provenance = 'File hashes identify supplied build outputs; this tool does not program or read back the FPGA.'
    required_flags = "-$Optimization -march=rv32ima_zicsr_zifencei -mabi=ilp32"
    required_compiler = "riscv32-unknown-elf-gcc $CompilerVersion"
    required_runs = 'three performance runs and one validation-seed run, each >=10 seconds'
    bitstream = $null
    firmware = $null
    runs = @()
}
function Get-Artifact([string]$Path) {
    $item = Get-Item -LiteralPath $Path
    if ($item.PSIsContainer -or $item.Length -eq 0 -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Expected nonempty regular artifact: $Path"
    }
    return [ordered]@{ name = $item.Name; bytes = $item.Length; sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
}
function Get-One([string]$Text, [string]$Pattern, [string]$Name) {
    $found = [regex]::Matches($Text, $Pattern)
    if ($found.Count -ne 1) { throw "Expected exactly one $Name; found $($found.Count)." }
    return $found[0].Groups[1].Value
}
function Parse-Runs([string]$Text) {
    # Every run is bounded by its production command's frequency and DONE line.
    $normalized = $Text.Replace("`r", '')
    if ($normalized -match '(?im)COREMARK_FAIL|ERROR!|Errors detected|Cannot validate operation|command failed validation') {
        throw 'The log contains a CoreMark failure marker.'
    }
    $runs = [regex]::Matches($normalized, '(?ms)^CPU_HZ=([0-9]+)[ \t]*\n(.*?)^COREMARK_DONE[ \t]*(?:\n|$)')
    if ($runs.Count -ne 4 -or [regex]::Matches($normalized, '(?m)^CPU_HZ=').Count -ne 4 -or
        [regex]::Matches($normalized, '(?m)^COREMARK_DONE[ \t]*$').Count -ne 4) {
        throw 'Exactly three performance runs followed by one validation run are required.'
    }
    $parsed = @()
    $finalCrcByIterations = @{}
    foreach ($run in $runs) {
        $hz = [long]::Parse($run.Groups[1].Value, [Globalization.CultureInfo]::InvariantCulture)
        $body = $run.Groups[2].Value
        if ($hz -ne $CpuHz) { throw "CPU_HZ $hz differs from candidate $CpuHz." }
        $sysHz = [long]::Parse((Get-One $body '(?m)^SYS_HZ=([0-9]+)[ \t]*$' 'SYS frequency'), [Globalization.CultureInfo]::InvariantCulture)
        $timebaseHz = [long]::Parse((Get-One $body '(?m)^TIMEBASE_HZ=([0-9]+)[ \t]*$' 'timer frequency'), [Globalization.CultureInfo]::InvariantCulture)
        if ($sysHz -ne $clock.sys_hz -or $timebaseHz -ne $clock.timebase_hz) { throw 'SYS/TIMEBASE frequency does not match config/clocks.json.' }
        $mode = Get-One $body '(?m)^COREMARK_MODE=(performance|validation)[ \t]*$' 'seed mode'
        $expectedMode = if ($parsed.Count -lt 3) { 'performance' } else { 'validation' }
        if ($mode -ne $expectedMode) { throw "Expected seed mode $expectedMode, got $mode." }
        $ticks = [decimal]::Parse((Get-One $body '(?m)^PORT_TICKS64[ \t]*:[ \t]*([0-9]+)[ \t]*$' '64-bit CLINT ticks'), [Globalization.CultureInfo]::InvariantCulture)
        $officialTicks = [decimal]::Parse((Get-One $body '(?m)^Total ticks[ \t]*:[ \t]*([0-9]+)[ \t]*$' 'official low-32 ticks'), [Globalization.CultureInfo]::InvariantCulture)
        if ($ticks % 4294967296 -ne $officialTicks) { throw 'Official ticks disagree with the full 64-bit timer.' }
        $iterations = [decimal]::Parse((Get-One $body '(?m)^Iterations[ \t]*:[ \t]*([0-9]+)[ \t]*$' 'Iterations'), [Globalization.CultureInfo]::InvariantCulture)
        if ($ticks -lt ([decimal]$timebaseHz * 10) -or $iterations -lt 1) { throw 'Timed run is shorter than 10 seconds or has no iterations.' }
        foreach ($marker in @('Correct operation validated\. See readme\.txt for run and reporting rules\.', 'COREMARK_PASS')) {
            if ([regex]::Matches($body, "(?m)^$marker[ \t]*$").Count -ne 1) { throw "Missing/duplicate success marker: $marker" }
        }
        $compilerReport = Get-One $body '(?m)^Compiler flags[ \t]*:[ \t]*(.+)$' 'compiler flags'
        foreach ($required in @("-$Optimization", '-march=rv32ima_zicsr_zifencei', '-mabi=ilp32')) {
            if ($required -notin ($compilerReport -split '\s+')) { throw "Missing compiler flag: $required" }
        }
        $compiler = Get-One $body '(?m)^Compiler version[ \t]*:[ \t]*(.+)$' 'compiler version'
        if ($compiler.Trim() -ne "riscv32-unknown-elf-gcc $CompilerVersion") { throw "Unexpected compiler: $compiler" }
        foreach ($flag in [regex]::Matches($body, '(?<!\S)(-march=\S+|-mabi=\S+|-O\S+)')) {
            if ($flag.Value -notin @("-$Optimization", '-march=rv32ima_zicsr_zifencei', '-mabi=ilp32')) { throw "Unexpected compiler flag: $($flag.Value)" }
        }
        # 2000-byte static workspace: official known_id 3 (perf) or 4 (validation).
        $crc = [ordered]@{}
        $expectedCrc = if ($mode -eq 'performance') {
            @(@('seedcrc','e9f5'), @('[0]crclist','e714'), @('[0]crcmatrix','1fd7'), @('[0]crcstate','8e3a'), @('[0]crcfinal',''))
        } else {
            @(@('seedcrc','18f2'), @('[0]crclist','e3c1'), @('[0]crcmatrix','0747'), @('[0]crcstate','8d84'), @('[0]crcfinal',''))
        }
        foreach ($entry in $expectedCrc) {
            $value = (Get-One $body ('(?m)^' + [regex]::Escape($entry[0]) + '[ \t]*:[ \t]*0x([0-9a-fA-F]{4})[ \t]*$') $entry[0]).ToLowerInvariant()
            if ($entry[1] -and $value -ne $entry[1]) { throw "CRC mismatch for $($entry[0]): $value, expected $($entry[1])." }
            $crc[$entry[0]] = $value
        }
        # crcfinal depends on iteration count, unlike the known first-iteration CRCs.
        $iterationKey = $mode + ':' + $iterations.ToString([Globalization.CultureInfo]::InvariantCulture)
        if ($finalCrcByIterations.ContainsKey($iterationKey) -and $finalCrcByIterations[$iterationKey] -ne $crc['[0]crcfinal']) {
            throw 'Equal iteration counts produced different final CRCs.'
        }
        $finalCrcByIterations[$iterationKey] = $crc['[0]crcfinal']
        $parsed += [ordered]@{
            run = $parsed.Count + 1; mode = $mode; cpu_hz = $hz; sys_hz = $sysHz; timebase_hz = $timebaseHz; ticks = $ticks; iterations = $iterations
            duration_seconds = [double]($ticks / $timebaseHz)
            iterations_per_second = [double]($iterations * $timebaseHz / $ticks)
            coremark_per_mhz = [double]($iterations * $timebaseHz * 1000000 / ($ticks * $hz))
            compiler = $compiler.Trim(); compiler_report = $compilerReport.Trim(); crc = $crc; validated = $true
        }
    }
    return $parsed
}
function Read-Until([string]$Pattern, [int]$LimitSeconds, [Text.StringBuilder]$Current) {
    $timer = [Diagnostics.Stopwatch]::StartNew()
    while ($timer.Elapsed.TotalSeconds -lt $LimitSeconds) {
        $chunk = $script:serial.ReadExisting()
        if ($chunk) {
            [void]$script:capture.Append($chunk)
            [void]$Current.Append($chunk)
            if ($script:capture.Length -gt 2MB) { throw 'UART capture exceeded the 2 MiB bound.' }
            if ($Current.ToString().Replace("`r", '') -match $Pattern) { return }
        }
        Start-Sleep -Milliseconds 100
    }
    throw "UART timed out after $LimitSeconds seconds."
}
try {
    $report.bitstream = Get-Artifact $BitstreamPath
    $report.firmware = Get-Artifact $FirmwarePath
    if ($offline) {
        foreach ($path in $InputLog) {
            $file = Get-Item -LiteralPath $path
            if ($file.PSIsContainer -or $file.Length -gt 2MB) { throw 'Each input must be a log file no larger than 2 MiB.' }
            [void]$capture.AppendLine([IO.File]::ReadAllText($file.FullName))
            if ($capture.Length -gt 2MB) { throw 'Combined input logs exceed the 2 MiB bound.' }
        }
    } else {
        Write-Output "Three performance commands and one validation command, at most $TimeoutSeconds seconds each plus 10 seconds for the prompt. Ctrl+C stops capture and closes the port."
        $discoveredPorts = @([IO.Ports.SerialPort]::GetPortNames())
        if ($Port -notin $discoveredPorts) { throw "Serial port no longer present: $Port" }
        $report.serial_discovery = [ordered]@{
            captured_utc = [DateTime]::UtcNow.ToString('o')
            available_ports = $discoveredPorts
            selected_port = $Port; baud = $BaudRate; data_bits = 8
            parity = 'None'; stop_bits = 'One'; dtr = $false; rts = $false
        }
        $serial = New-Object IO.Ports.SerialPort($Port, $BaudRate, 'None', 8, 'One')
        $serial.DtrEnable = $false; $serial.RtsEnable = $false
        $serial.ReadTimeout = 250; $serial.WriteTimeout = 1000
        $serial.Open()
        $serial.DiscardInBuffer()
        $serial.Write("`r")
        $prompt = New-Object Text.StringBuilder
        Read-Until '(?m)^soc> ?$' 10 $prompt
        for ($index = 1; $index -le 4; $index++) {
            $current = New-Object Text.StringBuilder
            $command = if ($index -le 3) { "coremark`r" } else { "coremark validate`r" }
            $serial.Write($command)
            Read-Until '(?ms)^COREMARK_DONE\s*\n.*^soc> ?$' $TimeoutSeconds $current
            Write-Output "Captured run $index/4."
        }
    }
    $report.runs = @(Parse-Runs $capture.ToString())
    $scores = @($report.runs | Where-Object { $_.mode -eq 'performance' } | ForEach-Object { $_.coremark_per_mhz } | Sort-Object)
    $throughput = @($report.runs | Where-Object { $_.mode -eq 'performance' } | ForEach-Object { $_.iterations_per_second } | Sort-Object)
    $report.summary = [ordered]@{
        performance_runs = 3; validation_runs = 1
        mean_coremark_per_mhz = ($scores | Measure-Object -Average).Average
        minimum_coremark_per_mhz = $scores[0]; median_coremark_per_mhz = $scores[1]; maximum_coremark_per_mhz = $scores[2]
        mean_coremark = ($throughput | Measure-Object -Average).Average
        minimum_coremark = $throughput[0]; median_coremark = $throughput[1]; maximum_coremark = $throughput[2]
    }
    $report.status = $(if ($offline) { 'OFFLINE_VALID' } else { 'PASS' })
    $report.board_acceptance = !$offline
} catch {
    $failure = $_.Exception.Message
    $report.status = 'FAIL'
    $report.error = $failure
} finally {
    if ($null -ne $serial) { if ($serial.IsOpen) { $serial.Close() }; $serial.Dispose() }
    [IO.File]::WriteAllText($logPath, $capture.ToString(), $utf8)
    $report.log_sha256 = (Get-FileHash -LiteralPath $logPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $report.completed_utc = [DateTime]::UtcNow.ToString('o')
    [IO.File]::WriteAllText($resultPath, ($report | ConvertTo-Json -Depth 8), $utf8)
}
if ($failure) { throw "CoreMark measurement failed: $failure Evidence: $resultPath" }
Write-Output "COREMARK_MEASURE_$($report.status): $resultPath"
