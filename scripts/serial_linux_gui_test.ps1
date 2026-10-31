param(
    [string]$PortName = 'COM17',
    [int]$BaudRate = 115200,
    [string]$GuiPath,
    [int]$ShellTimeoutSeconds = 300,
    [int]$EngineTimeoutSeconds = 900,
    [switch]$WaitForBootloader,
    [string]$LogPath
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$GuiPath) { $GuiPath = Join-Path $root 'artifacts\xiangqi-pikafish-gui' }
if (!$LogPath) { $LogPath = Join-Path $root 'artifacts\board_linux_gui_test.log' }
$GuiPath = [IO.Path]::GetFullPath($GuiPath)
$LogPath = [IO.Path]::GetFullPath($LogPath)
if (!(Test-Path -LiteralPath $GuiPath -PathType Leaf)) {
    throw "Missing GUI executable: $GuiPath"
}

$utf8 = [Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText($LogPath, '', $utf8)
$expectedHash = (Get-FileHash -LiteralPath $GuiPath -Algorithm SHA256).Hash.ToLowerInvariant()

function Add-BoardByte([int]$Value) {
    if ($Value -eq 10 -or $Value -eq 13 -or $Value -eq 9 -or
        ($Value -ge 32 -and $Value -le 126)) {
        $valueText = [string][char]$Value
        [IO.File]::AppendAllText($LogPath, $valueText, $utf8)
        Write-Host -NoNewline $valueText
    }
}

function Read-UntilText(
    [IO.Ports.SerialPort]$Port,
    [string[]]$Needles,
    [int]$TimeoutSeconds
) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $recent = ''
    while ((Get-Date) -lt $deadline) {
        try { $value = $Port.ReadByte() } catch [TimeoutException] { continue }
        Add-BoardByte $value
        if ($value -eq 10 -or $value -eq 13 -or $value -eq 9 -or
            ($value -ge 32 -and $value -le 126)) {
            $recent += [char]$value
            if ($recent.Length -gt 16384) {
                $recent = $recent.Substring($recent.Length - 16384)
            }
            foreach ($needle in $Needles) {
                if ($recent.Contains($needle)) { return $needle }
            }
        }
    }
    throw "Timed out waiting for board text: $($Needles -join ', ')"
}

function Write-Paced(
    [IO.Ports.SerialPort]$Port,
    [string]$Text,
    [int]$DelayMilliseconds = 20
) {
    foreach ($char in $Text.ToCharArray()) {
        $Port.Write([string]$char)
        Start-Sleep -Milliseconds $DelayMilliseconds
    }
}

function Write-Command(
    [IO.Ports.SerialPort]$Port,
    [string]$Command,
    [int]$TimeoutSeconds = 30
) {
    Write-Paced $Port "$Command`r"
    [void](Read-UntilText $Port @('/ # ') $TimeoutSeconds)
}

$port = [IO.Ports.SerialPort]::new(
    $PortName, $BaudRate, [IO.Ports.Parity]::None, 8,
    [IO.Ports.StopBits]::One)
$port.Handshake = [IO.Ports.Handshake]::None
$port.ReadTimeout = 200
$port.WriteTimeout = 30000
$port.DtrEnable = $false
$port.RtsEnable = $false
try {
    $port.Open()
    $port.DiscardInBuffer()
    if ($WaitForBootloader) {
        Write-Host "Armed for a newly programmed bootloader on $PortName..."
        $entry = Read-UntilText $port @('SoC V4.2 bootloader') $ShellTimeoutSeconds
    } else {
        $port.Write("`r")
        Write-Host "Waiting for Linux root shell or bootloader on $PortName..."
        $entry = Read-UntilText $port @('/ # ', 'SoC V4.2 bootloader', 'soc-v3> ') `
            $ShellTimeoutSeconds
    }
    if ($entry -eq 'SoC V4.2 bootloader') {
        $port.Write("`r")
        [void](Read-UntilText $port @('soc-v3> ') 30)
        $entry = 'soc-v3> '
    }
    if ($entry -eq 'soc-v3> ') {
        Write-Host "Bootloader detected; starting MicroSD Linux..."
        Write-Paced $port "sdboot`r"
        [void](Read-UntilText $port @('/ # ') $ShellTimeoutSeconds)
    }

    # Test the executable installed in rootfs. Serial upload is deliberately
    # avoided: bootloader-reserved DDR is not readable through Linux /dev/mem,
    # and unacknowledged canonical-TTY transfers can silently lose bytes.
    # On the 27 MHz single-core target, Linux may spend tens of seconds tearing
    # down the engine's large sparse address space before the shell is scheduled.
    Write-Command $port '/etc/init.d/S95pikafish stop' 180
    Write-Command $port 'sleep 1'
    Write-Command $port 'sha256sum /usr/bin/xiangqi-pikafish-gui'
    $log = [IO.File]::ReadAllText($LogPath)
    if (!$log.ToLowerInvariant().Contains($expectedHash)) {
        throw "Installed GUI SHA-256 does not match $expectedHash; rewrite the MicroSD image first"
    }

    Write-Host "Installed GUI verified; starting board test."
    Write-Paced $port "/etc/init.d/S95pikafish start`r"
    $result = Read-UntilText $port @(
        'XQ LINUX PIKAFISH READY',
        'XQ LINUX ENGINE FAILED stage=attacks-map',
        'XQ LINUX ENGINE FAILED stage=attacks-bind',
        'XQ LINUX PIKAFISH PFF1 FAILED',
        'xiangqi-pikafish: engine startup failed'
    ) $EngineTimeoutSeconds
    if ($result -ne 'XQ LINUX PIKAFISH READY') {
        throw "Board GUI test failed: $result"
    }

    $log = [IO.File]::ReadAllText($LogPath)
    foreach ($needle in @(
        'XQ LINUX GUI READY; full Pikafish and official NNUE loading',
        'XQ LINUX ENGINE INIT stage=attacks-ready',
        'XQ LINUX ENGINE DETAIL stage=shared-histories-alloc-ready bytes=41230336',
        'XQ LINUX ENGINE DETAIL stage=shared-correction-clear-ready',
        'XQ LINUX ENGINE DETAIL stage=shared-pawn-clear-ready',
        'XQ LINUX ENGINE DETAIL stage=shared-continuation-clear-ready',
        'XQ LINUX ENGINE DETAIL stage=threadpool-initial-clear-ready',
        'XQ LINUX ENGINE DETAIL stage=tt-fresh-zero-skip',
        'XQ LINUX ENGINE INIT stage=constructor-ready'
    )) {
        if (!$log.Contains($needle)) {
            throw "Board GUI test did not report '$needle'"
        }
    }
    Write-Host "`nLINUX_GUI_BOARD_TEST_PASS; log: $LogPath"
} finally {
    if ($port.IsOpen) { $port.Close() }
    $port.Dispose()
}
