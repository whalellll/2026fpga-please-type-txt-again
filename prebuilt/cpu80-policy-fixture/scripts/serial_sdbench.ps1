param(
    [string]$PortName = 'COM5',
    [ValidateRange(1200, 4000000)]
    [int]$BaudRate = 115200,
    [ValidateRange(1, 3600)]
    [int]$PromptTimeoutSeconds = 180,
    [ValidateRange(1, 3600)]
    [int]$BenchmarkTimeoutSeconds = 180,
    [ValidateRange(0, 2147483647)]
    [int]$MinimumKiBPerSecond = 0,
    [string]$LogPath
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$LogPath) { $LogPath = Join-Path $root 'artifacts\board_sdbench.log' }
$LogPath = [IO.Path]::GetFullPath($LogPath)
$utf8 = [Text.UTF8Encoding]::new($false)
$capture = [Text.StringBuilder]::new()

function Add-BoardByte([int]$Value, [Text.StringBuilder]$CommandCapture) {
    if ($Value -eq 10 -or $Value -eq 13 -or $Value -eq 9 -or
        ($Value -ge 32 -and $Value -le 126)) {
        $character = [char]$Value
        [void]$script:capture.Append($character)
        if ($null -ne $CommandCapture) {
            [void]$CommandCapture.Append($character)
        }
        Write-Host -NoNewline $character
    }
}

function Write-Paced(
    [IO.Ports.SerialPort]$Port,
    [string]$Text,
    [int]$DelayMilliseconds = 10
) {
    foreach ($character in $Text.ToCharArray()) {
        $Port.Write([string]$character)
        Start-Sleep -Milliseconds $DelayMilliseconds
    }
}

function Read-UntilPrompt(
    [IO.Ports.SerialPort]$Port,
    [int]$TimeoutSeconds,
    [Text.StringBuilder]$CommandCapture
) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $recent = ''
    while ((Get-Date) -lt $deadline) {
        try { $value = $Port.ReadByte() } catch [TimeoutException] { continue }
        Add-BoardByte $value $CommandCapture
        if ($value -eq 10 -or $value -eq 13 -or $value -eq 9 -or
            ($value -ge 32 -and $value -le 126)) {
            $recent += [char]$value
            if ($recent.Length -gt 512) {
                $recent = $recent.Substring($recent.Length - 512)
            }
            if ($recent.Contains('soc> ')) { return }
        }
    }
    throw "Timed out after $TimeoutSeconds seconds waiting for soc> prompt"
}

function Assert-SdBench([string]$Text, [uint64]$MinimumThroughput) {
    $forbidden = @(
        'sdbench initialization failed',
        'sdbench scratch DDR range is unsafe',
        'sdbench cancelled by Esc',
        'sdbench failed at LBA',
        'sdbench returned, error',
        'MicroSD protocol error',
        'MicroSD read failed'
    )
    foreach ($marker in $forbidden) {
        if ($Text.Contains($marker)) {
            throw "SDBENCH failed: found '$marker'"
        }
    }

    if ($Text -notmatch 'sdbench read-only bytes=8388608 batch_sectors=32') {
        throw 'SDBENCH failed: the full 8 MiB read-only benchmark did not start'
    }
    $match = [regex]::Match(
        $Text,
        'sdbench complete: bytes=8388608, ([0-9]+) ms, ([0-9]+) KiB/s'
    )
    if (!$match.Success) {
        throw 'SDBENCH failed: completion and throughput report is missing'
    }
    $milliseconds = [uint64]$match.Groups[1].Value
    $kibPerSecond = [uint64]$match.Groups[2].Value
    if ($milliseconds -eq 0 -or $kibPerSecond -eq 0) {
        throw 'SDBENCH failed: elapsed time and throughput must both be nonzero'
    }
    if ($MinimumThroughput -gt 0 -and $kibPerSecond -lt $MinimumThroughput) {
        throw "SDBENCH failed: $kibPerSecond KiB/s is below the required $MinimumThroughput KiB/s"
    }
    return [pscustomobject]@{
        Bytes = [uint64]8388608
        Milliseconds = $milliseconds
        KiBPerSecond = $kibPerSecond
    }
}

$port = [IO.Ports.SerialPort]::new(
    $PortName,
    $BaudRate,
    [IO.Ports.Parity]::None,
    8,
    [IO.Ports.StopBits]::One
)
$port.Handshake = [IO.Ports.Handshake]::None
$port.ReadTimeout = 200
$port.WriteTimeout = 10000
$port.DtrEnable = $false
$port.RtsEnable = $false

try {
    $port.Open()
    $port.DiscardInBuffer()
    $port.Write([string][char]0x1b)
    Start-Sleep -Milliseconds 50
    Write-Paced $port "`r"
    Read-UntilPrompt $port $PromptTimeoutSeconds $null

    Write-Host "`nStarting the read-only 8 MiB MicroSD benchmark"
    $commandCapture = [Text.StringBuilder]::new()
    Write-Paced $port "sdbench`r"
    Read-UntilPrompt $port $BenchmarkTimeoutSeconds $commandCapture
    $result = Assert-SdBench $commandCapture.ToString() $MinimumKiBPerSecond
    Write-Host (
        "`nSDBENCH_READ_PASS bytes={0} ms={1} KiB/s={2}" -f
        $result.Bytes, $result.Milliseconds, $result.KiBPerSecond
    )
    if ($MinimumKiBPerSecond -gt 0) {
        Write-Host (
            "SDBENCH_THRESHOLD_PASS minimum_KiB/s={0}" -f
            $MinimumKiBPerSecond
        )
    }
} finally {
    if ($port.IsOpen) { $port.Close() }
    $port.Dispose()
    $directory = Split-Path -Parent $LogPath
    if (!(Test-Path -LiteralPath $directory)) {
        [void](New-Item -ItemType Directory -Path $directory)
    }
    [IO.File]::WriteAllText($LogPath, $capture.ToString(), $utf8)
    Write-Host "`nSerial log: $LogPath"
}
