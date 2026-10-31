param(
    [string]$PortName = 'COM17',
    [int]$BaudRate = 115200,
    [string]$PatchPath,
    [string]$CopierPath,
    [string]$LoadAddress = '0x14200000',
    [int]$Nodes = 256,
    [int]$BootTimeoutSeconds = 600,
    [int]$ModeTimeoutSeconds = 1200,
    [switch]$WaitForBootloaderStart,
    [switch]$PatchAlreadyLoaded,
    [switch]$RemotePatchReady,
    [switch]$FaultOnly,
    [switch]$SkipFaultInjection,
    [string]$LogPath
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$PatchPath) {
    $PatchPath = Join-Path $root 'artifacts\pikafish-stageb-phase4-search'
}
if (!$CopierPath) {
    $CopierPath = Join-Path $root 'artifacts\pikafish-devmem-copy'
}
if (!$LogPath) {
    $LogPath = Join-Path $root 'artifacts\board_pikafish_stageb_phase4.log'
}
$PatchPath = [IO.Path]::GetFullPath($PatchPath)
$CopierPath = [IO.Path]::GetFullPath($CopierPath)
$LogPath = [IO.Path]::GetFullPath($LogPath)
if (!(Test-Path -LiteralPath $PatchPath -PathType Leaf)) {
    throw "Missing Stage B phase-4 patch: $PatchPath"
}
if (!(Test-Path -LiteralPath $CopierPath -PathType Leaf)) {
    throw "Missing Stage B phase-4 devmem copier: $CopierPath"
}
if ($WaitForBootloaderStart -and $PatchAlreadyLoaded) {
    throw 'WaitForBootloaderStart and PatchAlreadyLoaded are mutually exclusive'
}
if (($RemotePatchReady -or $FaultOnly) -and !$PatchAlreadyLoaded) {
    throw 'RemotePatchReady and FaultOnly require PatchAlreadyLoaded'
}
if ($Nodes -lt 16 -or $Nodes -gt 1000000) {
    throw 'Nodes must be between 16 and 1000000'
}

$load = [Convert]::ToUInt32($LoadAddress.Replace('0x', ''), 16)
[byte[]]$content = [IO.File]::ReadAllBytes($PatchPath)
$blocks = [int][Math]::Ceiling($content.Length / 1024.0)
$paddedLength = $blocks * 1024
if (($load % 1024) -ne 0 -or $load -lt 0x14200000 -or
    ([uint64]$load + [uint64]$paddedLength) -gt 0x15000000) {
    throw 'Patch must stay in the unused, DTS-reserved PFF1 tail 0x14200000..0x14ffffff'
}
[byte[]]$padded = New-Object byte[] $paddedLength
for ($index = 0; $index -lt $padded.Length; ++$index) { $padded[$index] = 0x1a }
[Array]::Copy($content, $padded, $content.Length)
$sha = [Security.Cryptography.SHA256]::Create()
try {
    $expectedHash = ([BitConverter]::ToString($sha.ComputeHash($padded))).Replace('-', '').ToLowerInvariant()
} finally {
    $sha.Dispose()
}
$skipBlocks = [uint32]($load / 1024)
$remotePatch = '/tmp/pikafish-stageb-phase4-search'
$remoteCopier = '/tmp/pikafish-devmem-copy'
$utf8 = [Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText($LogPath, '', $utf8)
$script:commandSequence = 0

function Add-BoardByte([int]$Value) {
    if ($Value -eq 10 -or $Value -eq 13 -or $Value -eq 9 -or
        ($Value -ge 32 -and $Value -le 126)) {
        $text = [string][char]$Value
        [IO.File]::AppendAllText($LogPath, $text, $utf8)
        Write-Host -NoNewline $text
    }
}

function Read-UntilAny(
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
    ++$script:commandSequence
    $id = $script:commandSequence
    $pass = "P4CMD${id}PASS"
    $fail = "P4CMD${id}FAIL"
    # The exact result markers never occur contiguously in the echoed command,
    # so a slow previous command or a stale shell prompt cannot satisfy this
    # wait early.
    $wrapped = "if { $Command; }; then printf 'P4CMD%sPASS\n' '$id'; " +
        "else rc=`$?; printf 'P4CMD%sFAIL%s\n' '$id' `"`$rc`"; fi"
    Write-Paced $Port "$wrapped`r"
    $result = Read-UntilAny $Port @($pass, $fail) $TimeoutSeconds
    if ($result -eq $fail) {
        throw "Board command failed (id=$id): $Command"
    }
    Start-Sleep -Milliseconds 100
}

function Get-XmodemCrc([byte[]]$Data) {
    [int]$crc = 0
    foreach ($value in $Data) {
        $crc = $crc -bxor (([int]$value) -shl 8)
        for ($bit = 0; $bit -lt 8; ++$bit) {
            if (($crc -band 0x8000) -ne 0) {
                $crc = (($crc -shl 1) -bxor 0x1021) -band 0xffff
            } else {
                $crc = ($crc -shl 1) -band 0xffff
            }
        }
    }
    return $crc
}

function Wait-ControlByte(
    [IO.Ports.SerialPort]$Port,
    [int[]]$Allowed,
    [int]$TimeoutSeconds
) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try { $value = $Port.ReadByte() } catch [TimeoutException] { continue }
        if ($Allowed -contains $value) { return $value }
        Add-BoardByte $value
    }
    throw 'Timed out waiting for XMODEM control byte'
}

function Send-XmodemPatch([IO.Ports.SerialPort]$Port) {
    Write-Host "`nXMODEM phase-4 patch -> $LoadAddress"
    Write-Paced $Port "loadx $LoadAddress`r"
    [void](Read-UntilAny $Port @('Start XMODEM-CRC transfer now...') 15)
    [void](Wait-ControlByte $Port @(10) 5)
    [void](Wait-ControlByte $Port @(0x43) 5)

    for ($index = 0; $index -lt $blocks; ++$index) {
        [byte[]]$payload = New-Object byte[] 1024
        [Array]::Copy($padded, $index * 1024, $payload, 0, 1024)
        $number = ($index + 1) -band 0xff
        $crc = Get-XmodemCrc $payload
        [byte[]]$packet = New-Object byte[] 1029
        $packet[0] = 0x02
        $packet[1] = [byte]$number
        $packet[2] = [byte](0xff - $number)
        [Array]::Copy($payload, 0, $packet, 3, 1024)
        $packet[1027] = [byte](($crc -shr 8) -band 0xff)
        $packet[1028] = [byte]($crc -band 0xff)

        $acked = $false
        for ($attempt = 0; $attempt -lt 10 -and !$acked; ++$attempt) {
            $Port.Write($packet, 0, $packet.Length)
            $response = Wait-ControlByte $Port @(0x06, 0x15, 0x18) 8
            if ($response -eq 0x06) { $acked = $true }
            elseif ($response -eq 0x18) {
                throw "Board cancelled patch at block $($index + 1)"
            }
        }
        if (!$acked) { throw "XMODEM retries exhausted at block $($index + 1)" }
        if ((($index + 1) % 256) -eq 0 -or ($index + 1) -eq $blocks) {
            $percent = [Math]::Floor((($index + 1) * 100.0) / $blocks)
            Write-Host "  $percent% ($($index + 1)/$blocks blocks)"
        }
    }
    $Port.Write([byte[]]@(0x04), 0, 1)
    [void](Wait-ControlByte $Port @(0x06) 8)
    [void](Read-UntilAny $Port @('soc-v3> ') 15)
    Write-Host "XMODEM patch loaded ($paddedLength padded bytes)"
}

function Send-Base64File(
    [IO.Ports.SerialPort]$Port,
    [string]$LocalPath,
    [string]$RemotePath
) {
    [byte[]]$bytes = [IO.File]::ReadAllBytes($LocalPath)
    $encoded = [Convert]::ToBase64String($bytes)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        $hash = ([BitConverter]::ToString($hasher.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    } finally {
        $hasher.Dispose()
    }
    Write-Host "`nSerial Base64 helper -> $RemotePath ($($bytes.Length) bytes)"
    Write-Command $Port "stty -echo; : > $RemotePath" 30
    # Linux LiteUART has no hardware flow control. Decode independently valid
    # Base64 chunks and wait for an acknowledgement after every chunk, so an
    # overrun cannot silently corrupt the helper.
    $chunkChars = 768  # multiple of four; decodes to at most 576 bytes
    $chunkCount = [int][Math]::Ceiling($encoded.Length / [double]$chunkChars)
    $delayTicks = [int64]([Diagnostics.Stopwatch]::Frequency * 2 / 1000)
    for ($chunk = 0; $chunk -lt $chunkCount; ++$chunk) {
        $offset = $chunk * $chunkChars
        $count = [Math]::Min($chunkChars, $encoded.Length - $offset)
        $part = $encoded.Substring($offset, $count)
        $pass = "P4CHUNK${chunk}PASS"
        $fail = "P4CHUNK${chunk}FAIL"
        $command = "if printf '%s' '$part' | base64 -d >> $RemotePath; " +
            "then printf 'P4CHUNK%sPASS\n' '$chunk'; " +
            "else printf 'P4CHUNK%sFAIL\n' '$chunk'; fi`r"
        for ($burst = 0; $burst -lt $command.Length; $burst += 2) {
            $burstLength = [Math]::Min(2, $command.Length - $burst)
            $Port.Write($command.Substring($burst, $burstLength))
            $deadlineTicks = [Diagnostics.Stopwatch]::GetTimestamp() + $delayTicks
            while ([Diagnostics.Stopwatch]::GetTimestamp() -lt $deadlineTicks) { }
        }
        $result = Read-UntilAny $Port @($pass, $fail) 30
        if ($result -eq $fail) {
            throw "Serial Base64 decode failed at chunk $chunk"
        }
        Start-Sleep -Milliseconds 100
        if ((($chunk + 1) % 16) -eq 0 -or ($chunk + 1) -eq $chunkCount) {
            $percent = [Math]::Floor((($chunk + 1) * 100.0) / $chunkCount)
            Write-Host "  $percent% ($($chunk + 1)/$chunkCount acknowledged chunks)"
        }
    }
    $logOffset = (Get-Item -LiteralPath $LogPath).Length
    Write-Command $Port "stty echo; chmod 700 $RemotePath; sha256sum $RemotePath" 60
    $stream = [IO.File]::Open($LogPath, [IO.FileMode]::Open, [IO.FileAccess]::Read,
                             [IO.FileShare]::ReadWrite)
    try {
        $stream.Position = $logOffset
        $reader = [IO.StreamReader]::new($stream, $utf8, $true, 4096, $true)
        try { $segment = $reader.ReadToEnd() } finally { $reader.Dispose() }
    } finally {
        $stream.Dispose()
    }
    if (!$segment.ToLowerInvariant().Contains($hash)) {
        throw "Serial helper SHA-256 mismatch; expected $hash"
    }
    Write-Host "Serial helper verified: $hash"
}

function Run-Mode(
    [IO.Ports.SerialPort]$Port,
    [string]$Mode,
    [string]$Fault = ''
) {
    $startOffset = (Get-Item -LiteralPath $LogPath).Length
    $faultPrefix = if ($Fault) { "PIKAFISH_MAC_FAULT=$Fault " } else { '' }
    $command = $faultPrefix + "PIKAFISH_STAGEB_ACCEL=$Mode " +
        'PIKAFISH_STAGEB_PACK=/opt/pikafish/stageb-mac.bin ' +
        'PIKAFISH_PHASE4_MODEL=pff1-view:0x10000000:68122688 ' +
        "PIKAFISH_PHASE4_NODES=$Nodes $remotePatch"
    Write-Host "`nRunning phase-4 fixed-node acceptance: mode=$Mode fault=$Fault"
    Write-Paced $Port "$command`r"
    $needles = @(
        "PIKAFISH_STAGEB_PHASE4_SEARCH_PASS mode=$Mode cases=3 nodes=$Nodes",
        'PIKAFISH_STAGEB_PHASE4_SEARCH_FAIL reason=',
        'Segmentation fault',
        'Killed'
    )
    $result = Read-UntilAny $Port $needles $ModeTimeoutSeconds
    if (!$result.StartsWith('PIKAFISH_STAGEB_PHASE4_SEARCH_PASS')) {
        throw "Stage B phase-4 board search failed: $result"
    }
    [void](Read-UntilAny $Port @('/ # ') 60)
    $stream = [IO.File]::Open($LogPath, [IO.FileMode]::Open, [IO.FileAccess]::Read,
                             [IO.FileShare]::ReadWrite)
    try {
        $stream.Position = $startOffset
        $reader = [IO.StreamReader]::new($stream, $utf8, $true, 4096, $true)
        try { $segment = $reader.ReadToEnd() } finally { $reader.Dispose() }
    } finally {
        $stream.Dispose()
    }
    return $segment
}

function Get-SearchRecords([string]$Text, [string]$Mode) {
    $records = @()
    foreach ($line in ($Text -split "`r?`n")) {
        if ($line -match ('^PIKAFISH_STAGEB_PHASE4_SEARCH mode=' +
            [regex]::Escape($Mode) + ' case=(?<case>[0-2]) ' +
            'bestmove=(?<bestmove>\S+) ponder=(?<ponder>\S*) ' +
            'score=(?<score>-?[0-9]+) wdl=(?<wdl>[0-9]+,[0-9]+,[0-9]+) ' +
            'nodes=(?<nodes>[1-9][0-9]*) elapsed_ms=(?<elapsed>[0-9]+) ' +
            'nps=(?<nps>[0-9]+)$')) {
            $records += [pscustomobject]@{
                Case = [int]$Matches.case
                Signature = "$($Matches.case)|$($Matches.bestmove)|$($Matches.ponder)|" +
                    "$($Matches.score)|$($Matches.wdl)|$($Matches.nodes)"
                Elapsed = [uint64]$Matches.elapsed
            }
        }
    }
    if ($records.Count -ne 3) {
        throw "Expected three phase-4 records for mode $Mode, got $($records.Count)"
    }
    return @($records | Sort-Object Case)
}

$port = [IO.Ports.SerialPort]::new(
    $PortName, $BaudRate, [IO.Ports.Parity]::None, 8,
    [IO.Ports.StopBits]::One)
$port.Handshake = [IO.Ports.Handshake]::None
$port.ReadTimeout = 200
$port.WriteTimeout = 30000
$port.DtrEnable = $false
$port.RtsEnable = $false
$linuxReady = $false
$guiStopped = $false
try {
    $port.Open()
    $port.DiscardInBuffer()
    if ($PatchAlreadyLoaded) {
        $port.Write([string][char]3)
        $port.Write("`r")
        Write-Host "Resuming the DDR patch at $LoadAddress from Linux on $PortName..."
        [void](Read-UntilAny $port @('/ # ') 120)
        $linuxReady = $true
    } elseif ($WaitForBootloaderStart) {
        Write-Host "Waiting for a fresh CRAM bootloader on $PortName..."
        [void](Read-UntilAny $port @('SoC V4.2 bootloader') 600)
        $port.Write("`r")
        [void](Read-UntilAny $port @('soc-v3> ') 30)
    } else {
        $port.Write([string][char]3)
        $port.Write("`r")
        Write-Host "Waiting for Linux shell or bootloader on $PortName..."
        $entry = Read-UntilAny $port @('/ # ', 'soc-v3> ', 'SoC V4.2 bootloader') 120
        if ($entry -eq '/ # ') {
            throw ('Linux software reset cannot restart this board. Start this script with ' +
                   '-WaitForBootloaderStart, then download the production sbit to CRAM.')
        } elseif ($entry -eq 'SoC V4.2 bootloader') {
            $port.Write("`r")
            [void](Read-UntilAny $port @('soc-v3> ') 30)
        }
    }

    if (!$PatchAlreadyLoaded) {
        Send-XmodemPatch $port
        Write-Paced $port "sdboot`r"
        [void](Read-UntilAny $port @('/ # ') $BootTimeoutSeconds)
        $linuxReady = $true
    }
    Write-Command $port ('pid=$(cat /run/xiangqi-pikafish.pid 2>/dev/null); ' +
        '/etc/init.d/S95pikafish stop; n=0; ' +
        'while [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; do ' +
        'sleep 1; n=$((n+1)); [ "$n" -lt 180 ] || exit 1; done') 240
    $guiStopped = $true

    if (!$RemotePatchReady) {
        Send-Base64File $port $CopierPath $remoteCopier
        Write-Command $port ("$remoteCopier $LoadAddress $paddedLength $remotePatch; " +
            "chmod 700 $remotePatch; " +
            "sha256sum $remotePatch") 120
    } else {
        Write-Command $port "sha256sum $remotePatch" 60
    }
    $copyLog = [IO.File]::ReadAllText($LogPath).ToLowerInvariant()
    if (!$copyLog.Contains($expectedHash)) {
        throw "Board patch SHA-256 mismatch; expected padded hash $expectedHash"
    }
    Write-Host "`nVolatile patch verified: $expectedHash"

    $recommendation = '1'
    if (!$FaultOnly) {
        $segments = @{}
        foreach ($mode in @('0', 'verify', '1')) {
            $segment = Run-Mode $port $mode
            if ($mode -ne '0') {
                foreach ($forbidden in @('PIKAFISH_STAGEB_ACCEL_MISMATCH',
                                         'PIKAFISH_STAGEB_CPU_FALLBACK',
                                         'PIKAFISH_MAC_RUNTIME_FUSED')) {
                    if ($segment.Contains($forbidden)) {
                        throw "Forbidden marker in board mode ${mode}: $forbidden"
                    }
                }
                foreach ($required in @('PIKAFISH_STAGEB_ACCEL_ACTIVE bucket=',
                                        'mismatches=0')) {
                    if (!$segment.Contains($required)) {
                        throw "Missing board mode ${mode} marker: $required"
                    }
                }
            }
            if ($mode -eq '1' -and
                !$segment.Contains('resident=reused copied_bytes=0')) {
                throw 'Enabled mode did not reuse the resident Stage B model'
            }
            $segments[$mode] = Get-SearchRecords $segment $mode
        }

        foreach ($case in 0..2) {
            $expected = $segments['0'][$case].Signature
            if ($segments['verify'][$case].Signature -ne $expected -or
                $segments['1'][$case].Signature -ne $expected) {
                throw "Board fixed-node result mismatch in case $case"
            }
        }
        $cpuMs = ($segments['0'] | Measure-Object Elapsed -Sum).Sum
        $verifyMs = ($segments['verify'] | Measure-Object Elapsed -Sum).Sum
        $enabledMs = ($segments['1'] | Measure-Object Elapsed -Sum).Sum
        $recommendation = if (($enabledMs * 10) -le ($cpuMs * 9)) { '1' } else { 'verify' }
        Write-Host ("`nPIKAFISH_STAGEB_PHASE4_BOARD_COMPARE_PASS cases=3 nodes=$Nodes " +
            "cpu_ms=$cpuMs verify_ms=$verifyMs enabled_ms=$enabledMs " +
            "default=$recommendation")
    }

    if (!$SkipFaultInjection) {
        foreach ($fault in @('busy', 'error', 'timeout')) {
            $segment = Run-Mode $port '1' $fault
            foreach ($required in @(
                "reason=injected-$fault",
                'PIKAFISH_STAGEB_CPU_FALLBACK reason=')) {
                if (!$segment.Contains($required)) {
                    throw "Fault injection $fault marker missing: $required"
                }
            }
            if ($segment.Contains('PIKAFISH_STAGEB_ACCEL_MISMATCH')) {
                throw "Fault injection $fault caused a Stage B mismatch"
            }
            Write-Host "PIKAFISH_STAGEB_PHASE4_BOARD_FAULT_PASS fault=$fault"
        }
    }
    if ($FaultOnly) {
        Write-Host "PIKAFISH_STAGEB_PHASE4_BOARD_FAULT_SUITE_PASS; log: $LogPath"
    } else {
        Write-Host "PIKAFISH_STAGEB_PHASE4_BOARD_PASS default=$recommendation; log: $LogPath"
    }
} finally {
    if ($linuxReady -and $port.IsOpen) {
        try {
            $port.Write([string][char]3)
            $port.Write("`r")
            [void](Read-UntilAny $port @('/ # ') 30)
            Write-Command $port "rm -f $remotePatch $remoteCopier" 30
            if ($guiStopped) { Write-Command $port '/etc/init.d/S95pikafish start' 90 }
        } catch {
            Write-Warning "Failed to remove volatile patch or restore GUI: $_"
        }
    }
    if ($port.IsOpen) { $port.Close() }
    $port.Dispose()
}
