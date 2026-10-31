param(
    [string]$PortName = 'COM17',
    [int]$BaudRate = 115200,
    [int]$StartupTimeoutSeconds = 120,
    [int]$BootTimeoutSeconds = 900,
    [string]$LogPath
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$LogPath) { $LogPath = Join-Path $root 'artifacts\board_sd_native_test.log' }
$LogPath = [IO.Path]::GetFullPath($LogPath)
$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText($LogPath, '', $utf8)

function Add-BoardByte([int]$Value) {
    if ($Value -eq 10 -or $Value -eq 13 -or $Value -eq 9 -or
        ($Value -ge 32 -and $Value -le 126)) {
        $text = [string][char]$Value
        [IO.File]::AppendAllText($LogPath, $text, $utf8)
        Write-Host -NoNewline $text
    }
}

function Read-UntilText(
    [IO.Ports.SerialPort]$Port,
    [string]$Needle,
    [int]$TimeoutSeconds
) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $text = ''
    while ((Get-Date) -lt $deadline) {
        try { $value = $Port.ReadByte() } catch [TimeoutException] { continue }
        Add-BoardByte $value
        if ($value -eq 10 -or $value -eq 13 -or $value -eq 9 -or
            ($value -ge 32 -and $value -le 126)) {
            $text += [char]$value
            if ($text.Contains($Needle)) { return $text }
        }
    }
    throw "Timed out waiting for board text: $Needle"
}

function Invoke-BoardCommand(
    [IO.Ports.SerialPort]$Port,
    [string]$Command,
    [int]$TimeoutSeconds
) {
    $Port.Write("$Command`r")
    return Read-UntilText $Port 'soc-v3> ' $TimeoutSeconds
}

function Assert-Contains([string]$Text, [string]$Needle, [string]$Stage) {
    if (!$Text.Contains($Needle)) {
        throw "$Stage did not report '$Needle'"
    }
}

$port = New-Object IO.Ports.SerialPort(
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
    Write-Host "Waiting for a newly programmed SoC V4.2 bootloader on $PortName..."
    [void](Read-UntilText $port 'SoC V4.2 bootloader' $StartupTimeoutSeconds)

    # Queue a harmless CR before either Flash or MicroSD autoboot starts.
    $port.Write("`r")
    [void](Read-UntilText $port 'soc-v3> ' 30)

    $info = Invoke-BoardCommand $port 'info' 15
    Assert-Contains $info 'DDR=ready' 'info'
    Assert-Contains $info 'SD_ID=0x53444e32' 'info'
    Assert-Contains $info 'SD=present' 'info'

    $sdinfo = Invoke-BoardCommand $port 'sdinfo' 60
    Assert-Contains $sdinfo 'MicroSD detect: stable=present raw=present' 'sdinfo'
    Assert-Contains $sdinfo 'bus_width=4' 'sdinfo'
    Assert-Contains $sdinfo 'rootfs.cpio:' 'sdinfo'
    Assert-Contains $sdinfo 'pikafish.pff:' 'sdinfo'
    Assert-Contains $sdinfo 'pikafish.atk:' 'sdinfo'
    Assert-Contains $sdinfo 'xqmodel.bin:' 'sdinfo'

    $sdbench = Invoke-BoardCommand $port 'sdbench' 180
    Assert-Contains $sdbench 'sdbench complete:' 'sdbench'

    $port.Write("sdboot`r")
    $linux = Read-UntilText $port 'XQ LINUX PIKAFISH READY' $BootTimeoutSeconds
    Assert-Contains $linux 'MicroSD total:' 'sdboot'
    Assert-Contains $linux 'PFF1 DMA preload ready:' 'sdboot'
    Assert-Contains $linux 'PFA1 DMA preload ready:' 'sdboot'
    Assert-Contains $linux 'LINUX_BOOT_TO_SHELL_SECONDS=' 'Linux startup'
    Assert-Contains $linux 'XQ LINUX GUI READY; full Pikafish and official NNUE loading' 'GUI startup'
    Assert-Contains $linux 'XQ LINUX ENGINE INIT stage=attacks-ready' 'attack-table startup'
    Assert-Contains $linux 'XQ LINUX ENGINE DETAIL stage=shared-histories-alloc-ready bytes=41230336' 'shared-history allocation'
    Assert-Contains $linux 'XQ LINUX ENGINE DETAIL stage=shared-correction-clear-ready' 'fresh correction-history bypass'
    Assert-Contains $linux 'XQ LINUX ENGINE DETAIL stage=shared-pawn-clear-ready' 'fresh pawn-history bypass'
    Assert-Contains $linux 'XQ LINUX ENGINE DETAIL stage=shared-continuation-clear-ready' 'fresh continuation-history bypass'
    Assert-Contains $linux 'XQ LINUX ENGINE DETAIL stage=threadpool-initial-clear-ready' 'thread-pool initialization'
    Assert-Contains $linux 'XQ LINUX ENGINE DETAIL stage=tt-fresh-zero-skip' 'fresh transposition-table bypass'
    Assert-Contains $linux 'XQ LINUX PIKAFISH READY' 'Pikafish startup'
    Write-Host "`nSD_NATIVE_BOARD_TEST_PASS; log: $LogPath"
} finally {
    if ($port.IsOpen) { $port.Close() }
    $port.Dispose()
}
