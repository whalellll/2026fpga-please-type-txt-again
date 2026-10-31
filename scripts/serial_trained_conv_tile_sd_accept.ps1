param(
    [string]$PortName = 'COM17',
    [int]$BaudRate = 115200,
    [int]$BootTimeoutSeconds = 180,
    [int]$TestTimeoutSeconds = 60,
    [string]$LogPath = ''
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$LogPath) {
    $LogPath = Join-Path $root 'build\vision\trained-conv-tile\board_sd_accept.log'
}
$LogPath = [IO.Path]::GetFullPath($LogPath)
$logDir = Split-Path -Parent $LogPath
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$writer = [IO.StreamWriter]::new($LogPath, $false, [Text.UTF8Encoding]::new($false))
$writer.AutoFlush = $true
$port = [IO.Ports.SerialPort]::new(
    $PortName, $BaudRate, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
$port.ReadTimeout = 100
$port.WriteTimeout = 2000
$port.Handshake = [IO.Ports.Handshake]::None
$port.DtrEnable = $false
$port.RtsEnable = $false
function Read-Marker([string[]]$Markers, [int]$Seconds, [bool]$InterruptBoot) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    $nextReturn = Get-Date
    $recent = ''
    while ((Get-Date) -lt $deadline) {
        if ($InterruptBoot -and (Get-Date) -ge $nextReturn) {
            $port.Write([string][char]13)
            $nextReturn = (Get-Date).AddMilliseconds(250)
        }
        try { $value = $port.ReadByte() }
        catch [System.TimeoutException] { continue }
        if ($value -eq 10 -or $value -eq 13 -or $value -eq 9 -or
            ($value -ge 32 -and $value -le 126)) {
            $character = [char]$value
            $writer.Write($character)
            Write-Host -NoNewline $character
            $recent += $character
            if ($recent.Length -gt 1024) {
                $recent = $recent.Substring($recent.Length - 1024)
            }
            foreach ($marker in $Markers) {
                if ($recent.Contains($marker)) { return $marker }
            }
        }
    }
    throw "Timed out waiting for $($Markers -join ', ')"
}
try {
    $port.Open()
    Write-Host "Waiting for soc-v3> bootloader prompt. Reset the board with the prepared SD card in J10."
    [void](Read-Marker @('soc-v3> ') $BootTimeoutSeconds $true)
    $port.Write('xqboot' + [char]13)
    $result = Read-Marker @(
        'MAC_CONV_TRAINED_TILE_BOARD_PASS',
        'MAC_CONV_TRAINED_TILE_FAIL',
        'xqboot returned, error',
        'SD error',
        'Unexpected xqmodel.bin size'
    ) $TestTimeoutSeconds $false
    if ($result -ne 'MAC_CONV_TRAINED_TILE_BOARD_PASS') {
        try { [void](Read-Marker @([string][char]10) 2 $false) } catch { }
        throw "SD board test failed: $result"
    }
    [void](Read-Marker @([string][char]10) 5 $false)
    $writer.Dispose()
    $logText = [IO.File]::ReadAllText($LogPath)
    if ($logText -notmatch
        'MAC_CONV_TRAINED_TILE_BOARD_PASS output_crc32=c49864b6 compute_cycles=([0-9a-f]{8})') {
        throw "Board PASS line lacks the expected CRC/cycle counters: $LogPath"
    }
    Write-Host "SD_CONV_TRAINED_TILE_ACCEPT_PASS log=$LogPath"
}
finally {
    if ($port.IsOpen) { $port.Close() }
    $port.Dispose()
    $writer.Dispose()
}
