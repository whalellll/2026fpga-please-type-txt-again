param(
    [string]$PortName = 'COM17',
    [int]$BaudRate = 115200,
    [int]$ShellTimeoutSeconds = 300,
    [int]$TestTimeoutSeconds = 300,
    [switch]$SkipGuiService,
    [string]$LogPath
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$LogPath) {
    $LogPath = Join-Path $root 'artifacts\board_pikafish_stageb_golden.log'
}
$LogPath = [IO.Path]::GetFullPath($LogPath)
$hostFiles = @(
    (Join-Path $root 'artifacts\pikafish-stageb-board-accept'),
    (Join-Path $root 'artifacts\pikafish-stageb-mac.bin'),
    (Join-Path $root 'artifacts\pikafish-stageb-golden.bin')
)
foreach ($path in $hostFiles) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing Stage B board acceptance payload: $path"
    }
}
$expectedHashes = $hostFiles | ForEach-Object {
    (Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash.ToLowerInvariant()
}

$utf8 = [Text.UTF8Encoding]::new($false)
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
            if ($recent.Length -gt 32768) {
                $recent = $recent.Substring($recent.Length - 32768)
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
    # The prompt preceding an echoed command is not a completion prompt.
    # Split a unique marker across printf's format and argument so the echo
    # cannot itself contain the complete marker.
    $id = [Guid]::NewGuid().ToString('N')
    $marker = "BOARD_CMD_$id"
    Write-Paced $Port ($Command + "; printf 'BOARD_CMD_%s\n' '$id'`r")
    [void](Read-UntilText $Port @($marker) $TimeoutSeconds)
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
    # An earlier board test may leave a foreground command attached to the
    # serial console. Interrupt it before requesting the shell prompt.
    $port.Write([byte[]]@(3), 0, 1)
    $port.Write("`r")
    Write-Host "Waiting for Linux root shell or bootloader on $PortName..."
    $entry = Read-UntilText $port @('/ # ', 'SoC V4.2 bootloader', 'soc-v3> ') `
        $ShellTimeoutSeconds
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
    # Ctrl-C and CR can each produce a prompt. Consume the late prompt before
    # commands so it cannot be mistaken for completion of the first command.
    Start-Sleep -Milliseconds 500
    $port.DiscardInBuffer()

    # Keep exclusive ownership of the shared MAC and DDR window. The init
    # script sends SIGTERM asynchronously, so wait for the original PID to
    # disappear before hashing payloads or starting the acceptance program.
    if (!$SkipGuiService) {
        Write-Command $port ('pid=$(cat /run/xiangqi-pikafish.pid 2>/dev/null); ' +
            '/etc/init.d/S95pikafish stop; n=0; ' +
            'while [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; do ' +
            'sleep 1; n=$((n+1)); [ "$n" -lt 180 ] || exit 1; done') 240
    }
    Write-Command $port ('sha256sum ' +
        '/usr/bin/pikafish-stageb-board-accept ' +
        '/opt/pikafish/stageb-mac.bin ' +
        '/opt/pikafish/stageb-golden.bin') 60
    $installedLog = [IO.File]::ReadAllText($LogPath).ToLowerInvariant()
    foreach ($hash in $expectedHashes) {
        if (!$installedLog.Contains($hash)) {
            throw "Installed Stage B payload hash mismatch: $hash; rewrite the MicroSD rootfs"
        }
    }

    Write-Host "Installed payloads verified; starting Stage B hardware acceptance."
    Write-Paced $port ('/usr/bin/pikafish-stageb-board-accept ' +
        '/opt/pikafish/stageb-mac.bin ' +
        "/opt/pikafish/stageb-golden.bin`r")
    $result = Read-UntilText $port @(
        'PIKAFISH_STAGEB_BOARD_GOLDEN_PASS',
        'PIKAFISH_STAGEB_BOARD_GOLDEN_FAIL',
        'PIKAFISH_STAGEB_BOARD_MISMATCH',
        'PIKAFISH_STAGEB_BOARD_SCORE_MISMATCH',
        'PIKAFISH_STAGEB_BOARD_MAC_FAIL'
    ) $TestTimeoutSeconds
    if ($result -ne 'PIKAFISH_STAGEB_BOARD_GOLDEN_PASS') {
        try { [void](Read-UntilText $port @("`n") 3) } catch { }
        throw "Stage B board acceptance failed: $result"
    }
    [void](Read-UntilText $port @('/ # ') 30)
    if (!$SkipGuiService) {
        Write-Command $port '/etc/init.d/S95pikafish start' 60
    }
    Write-Host "`nPIKAFISH_STAGEB_BOARD_SERIAL_ACCEPT_PASS; log: $LogPath"
} finally {
    if ($port.IsOpen) { $port.Close() }
    $port.Dispose()
}
