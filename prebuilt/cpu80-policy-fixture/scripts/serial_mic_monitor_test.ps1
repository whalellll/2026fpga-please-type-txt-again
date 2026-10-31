param(
    [string]$PortName = 'COM5',
    [int]$BaudRate = 115200,
    [ValidateRange(2, 30)][int]$ListenSeconds = 5,
    [ValidateRange(1, 100)][int]$Volume = 10
)

$ErrorActionPreference = 'Stop'
$port = [IO.Ports.SerialPort]::new($PortName, $BaudRate,
    [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
$port.ReadTimeout = 200
$port.WriteTimeout = 5000
$port.DtrEnable = $false
$port.RtsEnable = $false

function Read-Until([string]$Marker, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    $text = New-Object Text.StringBuilder
    while ((Get-Date) -lt $deadline) {
        try { $c = $port.ReadByte() } catch [TimeoutException] { continue }
        if ($c -eq 10 -or $c -eq 13 -or ($c -ge 32 -and $c -le 126)) {
            [void]$text.Append([char]$c)
            if ($text.ToString().Contains($Marker)) { return $text.ToString() }
        }
    }
    throw "Timed out waiting for '$Marker': $text"
}

function Write-Paced([string]$Command) {
    foreach ($c in $Command.ToCharArray()) {
        $port.Write([string]$c)
        Start-Sleep -Milliseconds 10
    }
}

try {
    $port.Open()
    $port.DiscardInBuffer()
    Write-Paced "`r`r"
    [void](Read-Until 'soc> ' 15)
    Start-Sleep -Milliseconds 200
    $port.DiscardInBuffer()
    Write-Paced "debug speaker volume $Volume`r"
    $setResult = Read-Until 'soc> ' 15
    if (!$setResult.Contains("Audio volume=$Volume%")) {
        throw "Volume command failed: $setResult"
    }
    Write-Paced "debug mic`r"
    $started = Read-Until 'Microphone monitor: live 16 kHz' 15
    if ($started.Contains('returned, error')) { throw $started }
    Start-Sleep -Seconds $ListenSeconds
    $port.Write('q')
    $finished = Read-Until 'soc> ' 15
    if ($finished.Contains('Microphone monitor failed') -or
        $finished.Contains('debug mic returned, error')) {
        throw "Mic monitor failed: $finished"
    }
    if ($finished -notmatch 'samples=([0-9]+), missed=([0-9]+), underflows=([0-9]+), volume=([0-9]+)%') {
        throw "Missing mic monitor statistics: $finished"
    }
    $samples = [uint64]$Matches[1]
    $missed = [uint64]$Matches[2]
    $underflows = [uint64]$Matches[3]
    if ($samples -lt ([uint64]$ListenSeconds * 12000) -or $missed -ne 0) {
        throw "Mic monitor sample rate/drops invalid: samples=$samples missed=$missed"
    }
    Write-Output "MIC_MONITOR_SERIAL_PATH_PASS samples=$samples missed=$missed underflows=$underflows"
    Write-Output 'ACOUSTIC_CONFIRMATION_REQUIRED: confirm that your live voice was audible and recognizable.'
} finally {
    if ($port.IsOpen) { $port.Close() }
    $port.Dispose()
}
