param(
    [string]$PortName = 'COM5',
    [int]$BaudRate = 115200,
    [string]$BoardAddress = '192.168.1.50',
    [string]$ServerAddress = '192.168.1.2',
    [int]$CaptureSeconds = 600,
    [string]$StopText = '/ # ',
    [string]$LogPath
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$LogPath) { $LogPath = Join-Path $root 'artifacts\board_linux_tftp_boot.log' }
$LogPath = [IO.Path]::GetFullPath($LogPath)
$utf8 = [Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText($LogPath, '', $utf8)

function Read-Board([IO.Ports.SerialPort]$Port, [datetime]$Deadline,
                    [string]$Needle = '') {
    $recent = ''
    while ((Get-Date) -lt $Deadline) {
        try { $value = $Port.ReadByte() } catch [TimeoutException] { continue }
        if ($value -eq 10 -or $value -eq 13 -or $value -eq 9 -or
            ($value -ge 32 -and $value -le 126)) {
            $char = [char]$value
            [IO.File]::AppendAllText($LogPath, [string]$char, $utf8)
            Write-Host -NoNewline $char
            if ($Needle) {
                $recent += $char
                if ($recent.Length -gt 4096) {
                    $recent = $recent.Substring($recent.Length - 4096)
                }
                if ($recent.Contains($Needle)) { return $true }
            }
        }
    }
    return !$Needle
}

function Read-BootState([IO.Ports.SerialPort]$Port, [datetime]$Deadline) {
    $recent = ''
    while ((Get-Date) -lt $Deadline) {
        try { $value = $Port.ReadByte() } catch [TimeoutException] { continue }
        if ($value -eq 10 -or $value -eq 13 -or $value -eq 9 -or
            ($value -ge 32 -and $value -le 126)) {
            $char = [char]$value
            [IO.File]::AppendAllText($LogPath, [string]$char, $utf8)
            Write-Host -NoNewline $char
            $recent += $char
            if ($recent.Length -gt 4096) {
                $recent = $recent.Substring($recent.Length - 4096)
            }
            if ($recent.Contains('soc> ')) { return 'prompt' }
            if ($recent.Contains('Linux netboot server') -or
                $recent.Contains('TFTP RRQ')) { return 'autoboot' }
        }
    }
    return ''
}

$port = [IO.Ports.SerialPort]::new(
    $PortName, $BaudRate, [IO.Ports.Parity]::None, 8,
    [IO.Ports.StopBits]::One)
$port.Handshake = [IO.Ports.Handshake]::None
$port.ReadTimeout = 200
$port.WriteTimeout = 10000
$port.DtrEnable = $true
$port.RtsEnable = $true
try {
    $port.Open()
    $port.DiscardInBuffer()
    $port.Write("`r")
    $bootState = Read-BootState $port (Get-Date).AddSeconds(180)
    if (!$bootState) {
        throw 'Timed out waiting for the SoC prompt or automatic netboot'
    }

    if ($bootState -eq 'prompt') {
        $port.Write("netcfg $BoardAddress`r")
        if (!(Read-Board $port (Get-Date).AddSeconds(10) 'soc> ')) {
            throw 'Board did not accept netcfg'
        }
        $port.Write("netboot $ServerAddress`r")
    } else {
        Write-Host "`nDetected automatic netboot; keeping the active transfer."
    }
    if (!(Read-Board $port (Get-Date).AddSeconds($CaptureSeconds) $StopText)) {
        throw "Timed out waiting for Linux root prompt: $StopText"
    }
} finally {
    if ($port.IsOpen) { $port.Close() }
    $port.Dispose()
}

Write-Host "`nTFTP boot log saved: $LogPath"
