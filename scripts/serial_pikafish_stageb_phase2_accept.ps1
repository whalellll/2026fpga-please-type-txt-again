param(
    [string]$PortName = 'COM17',
    [int]$BaudRate = 115200,
    [int]$ShellTimeoutSeconds = 300,
    [int]$TestTimeoutSeconds = 900,
    [string]$LogPath
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$LogPath) {
    $LogPath = Join-Path $root 'artifacts\board_pikafish_stageb_phase2.log'
}
$LogPath = [IO.Path]::GetFullPath($LogPath)
$hostFiles = @(
    (Join-Path $root 'artifacts\pikafish-stageb-position-accept'),
    (Join-Path $root 'artifacts\pikafish-stageb-mac.bin'),
    (Join-Path $root 'artifacts\pikafish-stageb-position-golden.bin')
)
foreach ($path in $hostFiles) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing Stage B phase-2 board payload: $path"
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
            if ($recent.Length -gt 65536) {
                $recent = $recent.Substring($recent.Length - 65536)
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
$guiStopped = $false
try {
    $port.Open()
    $port.DiscardInBuffer()
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
        Write-Host 'Bootloader detected; starting MicroSD Linux...'
        Write-Paced $port "sdboot`r"
        [void](Read-UntilText $port @('/ # ') $ShellTimeoutSeconds)
    }

    Write-Command $port ('pid=$(cat /run/xiangqi-pikafish.pid 2>/dev/null); ' +
        '/etc/init.d/S95pikafish stop; n=0; ' +
        'while [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; do ' +
        'sleep 1; n=$((n+1)); [ "$n" -lt 180 ] || exit 1; done') 240
    $guiStopped = $true
    Write-Command $port ('sha256sum ' +
        '/usr/bin/pikafish-stageb-position-accept ' +
        '/opt/pikafish/stageb-mac.bin ' +
        '/opt/pikafish/stageb-position-golden.bin') 60
    $installedLog = [IO.File]::ReadAllText($LogPath).ToLowerInvariant()
    foreach ($hash in $expectedHashes) {
        if (!$installedLog.Contains($hash)) {
            throw "Installed Stage B phase-2 payload hash mismatch: $hash; rewrite the MicroSD rootfs"
        }
    }

    Write-Host 'Installed payloads verified; starting legal-position hardware acceptance.'
    Write-Paced $port ('/usr/bin/pikafish-stageb-position-accept --board ' +
        'pff1-view:0x10000000:68122688 - ' +
        '/opt/pikafish/stageb-mac.bin ' +
        "/opt/pikafish/stageb-position-golden.bin`r")
    $result = Read-UntilText $port @(
        'PIKAFISH_STAGEB_PHASE2_BOARD_PASS',
        'PIKAFISH_STAGEB_PHASE2_FAIL'
    ) $TestTimeoutSeconds
    if ($result -ne 'PIKAFISH_STAGEB_PHASE2_BOARD_PASS') {
        try { [void](Read-UntilText $port @("`n") 3) } catch { }
        throw "Stage B phase-2 board acceptance failed: $result"
    }
    [void](Read-UntilText $port @('/ # ') 30)
    Write-Host "`nPIKAFISH_STAGEB_PHASE2_SERIAL_ACCEPT_PASS; log: $LogPath"
} finally {
    if ($guiStopped -and $port.IsOpen) {
        try { Write-Command $port '/etc/init.d/S95pikafish start' 60 } catch {
            Write-Warning "Failed to restart GUI after acceptance: $_"
        }
    }
    if ($port.IsOpen) { $port.Close() }
    $port.Dispose()
}
