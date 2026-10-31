param(
    [string]$PortName = 'COM17',
    [int]$BaudRate = 115200,
    [int]$ShellTimeoutSeconds = 300,
    [int]$EngineTimeoutSeconds = 900,
    [int]$MoveTimeoutSeconds = 600,
    [ValidateSet('verify', '1')]
    [string]$Mode = 'verify',
    [switch]$UseInitDefault,
    [switch]$RequireHealthyCheckpoint,
    [switch]$WaitForBootloaderStart,
    [string]$LogPath
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$LogPath) {
    $LogPath = Join-Path $root 'artifacts\board_pikafish_stageb_phase3.log'
}
$LogPath = [IO.Path]::GetFullPath($LogPath)
$hostFiles = @(
    (Join-Path $root 'artifacts\xiangqi-pikafish-gui'),
    (Join-Path $root 'artifacts\pikafish-stageb-mac.bin')
)
foreach ($path in $hostFiles) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing Stage B phase-3 board payload: $path"
    }
}
$expectedHashes = $hostFiles | ForEach-Object {
    (Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash.ToLowerInvariant()
}
$expectedMode = if ($UseInitDefault) { '1' } else { $Mode }

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
$guiStarted = $false
try {
    $port.Open()
    $port.DiscardInBuffer()
    if ($WaitForBootloaderStart) {
        Write-Host "Waiting for a fresh CRAM boot or an in-progress Linux boot on $PortName..."
        $entry = Read-UntilText $port @(
            'SoC V4.2 bootloader',
            'Starting OpenSBI',
            'Linux version',
            '/ # '
        ) $ShellTimeoutSeconds
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
        Write-Host 'Bootloader detected; starting MicroSD Linux...'
        Write-Paced $port "sdboot`r"
        [void](Read-UntilText $port @('/ # ') $ShellTimeoutSeconds)
    } elseif ($entry -eq 'Starting OpenSBI' -or $entry -eq 'Linux version') {
        Write-Host 'Linux boot already in progress; waiting for the root shell...'
        [void](Read-UntilText $port @('/ # ') $ShellTimeoutSeconds)
    }

    Write-Command $port ('pid=$(cat /run/xiangqi-pikafish.pid 2>/dev/null); ' +
        '/etc/init.d/S95pikafish stop; n=0; ' +
        'while [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; do ' +
        'sleep 1; n=$((n+1)); [ "$n" -lt 180 ] || exit 1; done') 240
    Write-Command $port ('sha256sum /usr/bin/xiangqi-pikafish-gui ' +
        '/opt/pikafish/stageb-mac.bin') 60
    $installedLog = [IO.File]::ReadAllText($LogPath).ToLowerInvariant()
    foreach ($hash in $expectedHashes) {
        if (!$installedLog.Contains($hash)) {
            throw "Installed Stage B phase-3 payload hash mismatch: $hash; rewrite MicroSD"
        }
    }
    if ($UseInitDefault) {
        Write-Command $port ('grep -F ''PIKAFISH_STAGEB_ACCEL="${PIKAFISH_STAGEB_ACCEL:-1}"'' ' +
            '/etc/init.d/S95pikafish >/dev/null') 30
    }

    Write-Host "Installed payloads verified; starting GUI in Stage B mode $expectedMode."
    if ($UseInitDefault) {
        Write-Paced $port "/etc/init.d/S95pikafish start`r"
    } else {
        Write-Paced $port "PIKAFISH_STAGEB_ACCEL=$Mode /etc/init.d/S95pikafish start`r"
    }
    $startup = Read-UntilText $port @(
        'XQ LINUX PIKAFISH READY',
        'PIKAFISH_STAGEB_CPU_FALLBACK',
        'PIKAFISH_MAC_RUNTIME_FUSED',
        'XQ LINUX PIKAFISH PFF1 FAILED',
        'XQ LINUX ENGINE FAILED',
        'xiangqi-pikafish: engine startup failed'
    ) $EngineTimeoutSeconds
    if ($startup -ne 'XQ LINUX PIKAFISH READY') {
        throw "Stage B phase-3 startup failed: $startup"
    }
    $startupLog = [IO.File]::ReadAllText($LogPath)
    $ready = 'PIKAFISH_STAGEB_ACCEL_READY version=00020000 stacks=16 ' +
        'mlps_crc32=8c4b6711 pfsb_crc32=7261d3e8 model=2f6c8ed9 mode=' + $expectedMode
    if (!$startupLog.Contains($ready)) {
        throw "Stage B phase-3 READY contract missing: $ready"
    }
    $guiStarted = $true

    Write-Host "`nGUI is ready. Make one legal red move on HDMI now; waiting for hardware verify and black reply..."
    $move = Read-UntilText $port @(
        ' ELAPSED_MS=',
        'PIKAFISH_STAGEB_ACCEL_MISMATCH',
        'PIKAFISH_STAGEB_CPU_FALLBACK',
        'PIKAFISH_MAC_RUNTIME_FUSED',
        'XQ LINUX SEARCH FAILED'
    ) $MoveTimeoutSeconds
    if ($move -ne ' ELAPSED_MS=') {
        throw "Stage B phase-3 search failed: $move"
    }
    # Preserve the numeric elapsed value in the evidence log before closing the
    # serial port. Read-UntilText returns as soon as it sees the field name.
    [void](Read-UntilText $port @("`n") 10)

    $finalLog = [IO.File]::ReadAllText($LogPath)
    foreach ($needle in @(
        'PIKAFISH_STAGEB_ACCEL_ACTIVE bucket=',
        " jobs=4 mode=$expectedMode ",
        'XQ LINUX SEARCH START movetime_ms=',
        'XQ LINUX PIKAFISH DIRECT BESTMOVE=',
        ' ELAPSED_MS=')) {
        if (!$finalLog.Contains($needle)) {
            throw "Stage B phase-3 search evidence missing: $needle"
        }
    }
    if ($finalLog -notmatch
        'XQ LINUX PIKAFISH DIRECT BESTMOVE=[a-i][0-9][a-i][0-9] NODES=[1-9][0-9]* ') {
        throw 'Stage B phase-3 did not capture a legal non-empty black bestmove'
    }
    foreach ($forbidden in @(
        'PIKAFISH_STAGEB_ACCEL_MISMATCH',
        'PIKAFISH_STAGEB_CPU_FALLBACK',
        'PIKAFISH_MAC_RUNTIME_FUSED',
        'XQ LINUX SEARCH FAILED')) {
        if ($finalLog.Contains($forbidden)) {
            throw "Stage B phase-3 forbidden marker observed: $forbidden"
        }
    }

    if ($RequireHealthyCheckpoint) {
        Write-Host "`nFirst hardware search passed. Click the GUI restart button now; waiting for the phase-5 checkpoint..."
        $checkpoint = Read-UntilText $port @(
            'PIKAFISH_STAGEB_CHECKPOINT_PASS checks=',
            'PIKAFISH_STAGEB_CPU_FALLBACK',
            'PIKAFISH_MAC_RUNTIME_FUSED',
            'PIKAFISH_STAGEB_ACCEL_MISMATCH'
        ) $MoveTimeoutSeconds
        if ($checkpoint -ne 'PIKAFISH_STAGEB_CHECKPOINT_PASS checks=') {
            throw "Stage B phase-5 checkpoint failed: $checkpoint"
        }
        [void](Read-UntilText $port @('XQ LINUX ENGINE NEW GAME READY reset=position-snapshot') 30)
        [void](Read-UntilText $port @("`n") 10)
        $resetLog = [IO.File]::ReadAllText($LogPath)
        if ($resetLog -notmatch
            'XQ LINUX ENGINE NEW GAME READY reset=position-snapshot tt=retained histories=retained checkpoint=pass elapsed_us=[0-9]+') {
            throw 'Stage B phase-5 bounded new-game marker missing'
        }
        if ($resetLog.Contains('ENGINE DETAIL stage=worker-clear-start thread=0')) {
            $lastCheckpoint = $resetLog.LastIndexOf('PIKAFISH_STAGEB_CHECKPOINT_PASS checks=')
            $lastClear = $resetLog.LastIndexOf('ENGINE DETAIL stage=worker-clear-start thread=0')
            if ($lastClear -gt $lastCheckpoint) {
                throw 'Stage B phase-5 restart performed a blocking history clear'
            }
        }

        Write-Host "`nCheckpoint passed. Make one legal red move after restart; waiting for the black reply..."
        $postCheckpointMove = Read-UntilText $port @(
            ' ELAPSED_MS=',
            'PIKAFISH_STAGEB_ACCEL_MISMATCH',
            'PIKAFISH_STAGEB_CPU_FALLBACK',
            'PIKAFISH_MAC_RUNTIME_FUSED',
            'XQ LINUX SEARCH FAILED'
        ) $MoveTimeoutSeconds
        if ($postCheckpointMove -ne ' ELAPSED_MS=') {
            throw "Stage B phase-5 post-checkpoint search failed: $postCheckpointMove"
        }
        [void](Read-UntilText $port @("`n") 10)

        $pidWait = 'pid=$(cat /run/xiangqi-pikafish.pid 2>/dev/null); ' +
            '/etc/init.d/S95pikafish stop; n=0; ' +
            'while [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; do ' +
            'sleep 1; n=$((n+1)); [ "$n" -lt 180 ] || exit 1; done'
        Write-Command $port $pidWait 240
        $guiStarted = $false
        $healthLog = [IO.File]::ReadAllText($LogPath)
        if ($healthLog -notmatch
            'PIKAFISH_STAGEB_HEALTH checkpoints=[1-9][0-9]* checkpoint_failures=0') {
            throw 'Stage B phase-5 healthy checkpoint summary missing'
        }
        $bestMoves = [regex]::Matches(
            $healthLog,
            'XQ LINUX PIKAFISH DIRECT BESTMOVE=[a-i][0-9][a-i][0-9] NODES=[1-9][0-9]* ')
        if ($bestMoves.Count -lt 2) {
            throw "Stage B phase-5 expected two legal black replies, got $($bestMoves.Count)"
        }
        foreach ($forbidden in @(
            'PIKAFISH_STAGEB_ACCEL_MISMATCH',
            'PIKAFISH_STAGEB_CPU_FALLBACK',
            'PIKAFISH_MAC_RUNTIME_FUSED',
            'XQ LINUX SEARCH FAILED')) {
            if ($healthLog.Contains($forbidden)) {
                throw "Stage B phase-5 forbidden marker observed: $forbidden"
            }
        }
        Write-Command $port '/etc/init.d/S95pikafish start' 60
        $guiStarted = $true
        Write-Host "`nPIKAFISH_STAGEB_PHASE5_GUI_PASS mode=$expectedMode checkpoint=healthy post-checkpoint-search=pass; log: $LogPath"
    }
    Write-Host "`nPIKAFISH_STAGEB_PHASE3_BOARD_PASS mode=$expectedMode search=official-network; log: $LogPath"
} finally {
    if (!$guiStarted -and $port.IsOpen) {
        try { Write-Command $port '/etc/init.d/S95pikafish start' 60 } catch {
            Write-Warning "Failed to restore GUI after acceptance failure: $_"
        }
    }
    if ($port.IsOpen) { $port.Close() }
    $port.Dispose()
}
