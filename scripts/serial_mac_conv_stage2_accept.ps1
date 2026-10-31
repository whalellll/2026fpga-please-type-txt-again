param(
    [string]$PortName = 'COM17',
    [int]$BaudRate = 115200,
    [string]$LogPath = '',
    [int]$TimeoutSeconds = 180,
    [switch]$SchedulerOnly,
    [int]$IdleProbeSeconds = 0,
    [string]$SchedulerLoopList = '64',
    [int]$PostTestSettleSeconds = 0,
    [switch]$StartHeartbeat,
    [switch]$SkipGuiService,
    [switch]$MemoryProbe,
    [switch]$OpenHoldProbe
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$LogPath) {
    $LogPath = Join-Path $root 'build\vision\mac-conv-board\board_accept.log'
}
$LogPath = [IO.Path]::GetFullPath($LogPath)
New-Item -ItemType Directory -Path (Split-Path -Parent $LogPath) -Force | Out-Null
$utf8 = [Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText($LogPath, '', $utf8)
$port = [IO.Ports.SerialPort]::new($PortName, $BaudRate,
    [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
$port.ReadTimeout = 200
$port.WriteTimeout = 10000
$port.DtrEnable = $false
$port.RtsEnable = $false

function Write-Paced([string]$Command) {
    foreach ($char in $Command.ToCharArray()) {
        $port.Write([string]$char)
        Start-Sleep -Milliseconds 20
    }
}

function Wait-ForText([string]$Needle, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    $recent = ''
    while ((Get-Date) -lt $deadline) {
        try { $value = $port.ReadByte() } catch [TimeoutException] { continue }
        if ($value -eq 10 -or $value -eq 13 -or $value -eq 9 -or
            ($value -ge 32 -and $value -le 126)) {
            $char = [char]$value
            [IO.File]::AppendAllText($LogPath, [string]$char, $utf8)
            Write-Host -NoNewline $char
            $recent += $char
            if ($recent.Length -gt 2048) {
                $recent = $recent.Substring($recent.Length - 2048)
            }
            if ($recent.Contains($Needle)) { return }
        }
    }
    throw "Board did not print '$Needle' within $Seconds seconds; see $LogPath"
}

function Invoke-ShellCommand([string]$Command, [int]$Seconds) {
    $id = [Guid]::NewGuid().ToString('N')
    $marker = "MAC_CONV_CMD_$id"
    Write-Paced ($Command + "; printf 'MAC_CONV_CMD_%s\n' '$id'`r")
    Wait-ForText $marker $Seconds
    Wait-ForText '/ # ' 30
}

function Assert-SerialAlive([string]$Stage) {
    Invoke-ShellCommand "echo MAC_CONV_SHELL_ALIVE_$Stage" 30
    $port.Close()
    Start-Sleep -Seconds 2
    $port.Open()
    $port.DiscardInBuffer()
    $port.Write([byte[]]@(3), 0, 1)
    Write-Paced "`r"
    Wait-ForText '/ # ' 15
    Start-Sleep -Milliseconds 500
    $port.DiscardInBuffer()
    Write-Output "MAC_CONV_SHELL_RECONNECT_PASS stage=$Stage"
}

try {
    $port.Open()
    $port.DiscardInBuffer()
    $port.Write([byte[]]@(3), 0, 1)
    Write-Paced "`r"
    Wait-ForText '/ # ' 30
    Start-Sleep -Milliseconds 500
    $port.DiscardInBuffer()
    if (!$SkipGuiService) {
        Invoke-ShellCommand ('pid=$(cat /run/xiangqi-pikafish.pid 2>/dev/null); ' +
            '/etc/init.d/S95pikafish stop; n=0; ' +
            'while [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; do ' +
            'sleep 1; n=$((n+1)); [ "$n" -lt 180 ] || exit 1; done') 240
    }
    Assert-SerialAlive 'preflight'
    if ($StartHeartbeat) {
        Invoke-ShellCommand 'while :; do echo MAC_CONV_HEARTBEAT; sleep 5; done >/dev/console 2>&1 & echo $! > /run/mac_conv_heartbeat.pid' 30
    }
    if ($MemoryProbe) {
        Write-Paced "dd if=/dev/zero of=/tmp/mac-shadow-probe bs=1048576 count=1 2>/dev/null && echo MAC_CONV_MEM_''WRITE_OK`r"
        Wait-ForText 'MAC_CONV_MEM_WRITE_OK' 60
        Wait-ForText '/ # ' 30
        Assert-SerialAlive 'mem_write'
        Write-Paced "rm -f /tmp/mac-shadow-probe; echo MAC_CONV_MEM_''FREE_OK`r"
        Wait-ForText 'MAC_CONV_MEM_FREE_OK' 30
        Wait-ForText '/ # ' 30
        Assert-SerialAlive 'mem_free'
        Write-Paced "sh -c 'exec 3<>/dev/pango-mac0; exec 3>&-' && echo MAC_CONV_SHELL_''OPEN_OK`r"
        Wait-ForText 'MAC_CONV_SHELL_OPEN_OK' 60
        Wait-ForText '/ # ' 30
        Assert-SerialAlive 'shell_open'
    }
    if ($OpenHoldProbe) {
        Write-Paced "exec 3<>/dev/pango-mac0; echo MAC_CONV_OPEN_''HELD_OK`r"
        Wait-ForText 'MAC_CONV_OPEN_HELD_OK' 60
        Wait-ForText '/ # ' 30
        Assert-SerialAlive 'open_held'
        Write-Paced "exec 3>&-; echo MAC_CONV_OPEN_''CLOSED_OK`r"
        Wait-ForText 'MAC_CONV_OPEN_CLOSED_OK' 60
        Wait-ForText '/ # ' 30
        Assert-SerialAlive 'open_closed'
    }
    if ($IdleProbeSeconds -gt 0) {
        $elapsed = 0
        while ($elapsed -lt $IdleProbeSeconds) {
            Start-Sleep -Seconds 20
            $elapsed += 20
            Invoke-ShellCommand "echo MAC_CONV_IDLE_ALIVE_$elapsed" 30
            Write-Output "MAC_CONV_IDLE_PROBE_PASS elapsed=$elapsed"
        }
    }
    if (!$SchedulerOnly) {
        Write-Paced "pango-mac-conv-window-test`r"
        Wait-ForText 'PANGO_MAC_CONV_WINDOW_BOARD_PASS' $TimeoutSeconds
        Wait-ForText '/ # ' 30
        Assert-SerialAlive 'window'
        Write-Paced "pango-mac-conv-compute-test`r"
        Wait-ForText 'PANGO_MAC_CONV_COMPUTE_BOARD_PASS' $TimeoutSeconds
        Wait-ForText 'PANGO_MAC_CONV_SHAPE_BOARD_PASS case=pointwise bytes=320 crc32=344efaaf input=80 weight=128 windows=20' $TimeoutSeconds
        Wait-ForText 'PANGO_MAC_CONV_SHAPE_BOARD_PASS case=three_by_three bytes=144 crc32=c674620c input=100 weight=896 windows=81' $TimeoutSeconds
        Wait-ForText '/ # ' 30
        Assert-SerialAlive 'compute'
        Write-Paced "pango-mac-pool-test`r"
        Wait-ForText 'PANGO_MAC_POOL_TEST_PASS contexts=8 bytes=1048576 opens=9' $TimeoutSeconds
        Wait-ForText '/ # ' 30
        Assert-SerialAlive 'pool'
    }
    foreach ($loopText in $SchedulerLoopList.Split(',')) {
        $loops = 0
        if (![int]::TryParse($loopText, [ref]$loops)) {
            throw "Invalid scheduler loop count: $loopText"
        }
        $parallelMode = $loops -le -11 -and $loops -ge -32 -and
            [Math]::Truncate(-$loops / 10) -ge 1 -and
            [Math]::Truncate(-$loops / 10) -le 3 -and
            (-$loops % 10) -ge 1 -and (-$loops % 10) -le 2
        if (!(($loops -ge -7 -and $loops -le 64) -or $parallelMode)) {
            throw "Invalid scheduler loop count: $loopText"
        }
        $processes = if ($parallelMode) { [int][Math]::Truncate(-$loops / 10) } elseif ($loops -in @(-5, -6, -7)) { 1 } else { 3 }
        $threads = if ($parallelMode) { -$loops % 10 } elseif ($loops -in @(-5, -6, -7)) { 0 } else { 2 }
        $jobs = if ($parallelMode) { 0 } else { [Math]::Max(0, $loops * 6) }
        Write-Paced "pango-mac-scheduler-test $loops`r"
        Wait-ForText "PANGO_MAC_SCHEDULER_TEST_PASS processes=$processes threads_per_process=$threads jobs=$jobs" $TimeoutSeconds
        Wait-ForText '/ # ' 30
        if ($PostTestSettleSeconds -gt 0) {
            Start-Sleep -Seconds $PostTestSettleSeconds
        }
        Assert-SerialAlive "scheduler_$loops"
    }
    if ($StartHeartbeat) {
        Invoke-ShellCommand 'kill $(cat /run/mac_conv_heartbeat.pid)' 30
    }
    if (!$SkipGuiService) {
        Invoke-ShellCommand '/etc/init.d/S95pikafish start' 60
    }
    if ($SchedulerOnly) {
        Write-Output "MAC_SCHEDULER_BOARD_ACCEPT_PASS log=$LogPath"
    } else {
        Write-Output "MAC_CONV_STAGE2_BOARD_ACCEPT_PASS log=$LogPath"
    }
} finally {
    if ($port.IsOpen) { $port.Close() }
    $port.Dispose()
}
