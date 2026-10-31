param(
    [string]$BindAddress = '192.168.1.2',
    [int]$Port = 69,
    [string]$Root,
    [int]$InterPacketDelayMs = 2,
    [int]$RecoveryDelayMs = 100,
    [int]$MaxSessionBlocks = 2048,
    [int]$AckTimeoutMs = 750
)

$ErrorActionPreference = 'Stop'
if (!$Root) {
    $Root = Join-Path (Split-Path -Parent $PSScriptRoot) 'linux\boot'
}
$Root = [IO.Path]::GetFullPath($Root)
$required = @('fw_jump.bin', 'Image', 'rootfs.cpio', 'soc.dtb',
              'mac_selftest.bin')
$allowed = $required + @('mac_benchmark.bin')
foreach ($name in $required) {
    if (!(Test-Path -LiteralPath (Join-Path $Root $name) -PathType Leaf)) {
        throw "Missing Linux boot resource: $name"
    }
}

function Send-TftpError([Net.Sockets.UdpClient]$Socket,
                        [Net.IPEndPoint]$Peer,
                        [int]$Code,
                        [string]$Message) {
    $text = [Text.Encoding]::ASCII.GetBytes($Message)
    [byte[]]$packet = New-Object byte[] ($text.Length + 5)
    $packet[1] = 5
    $packet[2] = [byte](($Code -shr 8) -band 255)
    $packet[3] = [byte]($Code -band 255)
    [Array]::Copy($text, 0, $packet, 4, $text.Length)
    [void]$Socket.Send($packet, $packet.Length, $Peer)
}

function New-TftpTransferSocket([int]$LocalPort = 0) {
    $socket = [Net.Sockets.UdpClient]::new($LocalPort)
    $socket.Client.ReceiveTimeout = $AckTimeoutMs
    return $socket
}

function Send-TftpFile([string]$Name, [Net.IPEndPoint]$Peer,
                       [int]$BlockSize = 512, [bool]$UseOack = $false,
                       [int]$StartOffset = 0, [bool]$HexEncode = $false) {
    if ($allowed -notcontains $Name) {
        $denied = [Net.Sockets.UdpClient]::new(0)
        try { Send-TftpError $denied $Peer 1 'File not found' } finally { $denied.Dispose() }
        Write-Host "DENY $($Peer.Address):$($Peer.Port) '$Name'"
        return
    }

    $path = Join-Path $Root $Name
    [byte[]]$content = [IO.File]::ReadAllBytes($path)
    if ($StartOffset -lt 0 -or $StartOffset -gt $content.Length) {
        $denied = [Net.Sockets.UdpClient]::new(0)
        try { Send-TftpError $denied $Peer 0 'Invalid offset' } finally { $denied.Dispose() }
        Write-Host "DENY $Name invalid offset=$StartOffset"
        return
    }
    $transfer = New-TftpTransferSocket
    try {
        $wireMode = if ($HexEncode) { 'hexcrc' } else { 'raw' }
        Write-Host "SEND $Name ($($content.Length) bytes, offset=$StartOffset, blksize=$BlockSize, encoding=$wireMode) -> $($Peer.Address):$($Peer.Port)"
        if ($UseOack) {
            $optionText = "blksize`0$BlockSize`0"
            if ($HexEncode) { $optionText += "encoding`0hexcrc`0" }
            [byte[]]$option = [Text.Encoding]::ASCII.GetBytes($optionText)
            [byte[]]$oack = New-Object byte[] ($option.Length + 2)
            $oack[1] = 6
            [Array]::Copy($option, 0, $oack, 2, $option.Length)
            $oackAcked = $false
            for ($retry = 0; $retry -lt 4 -and !$oackAcked; $retry++) {
                [void]$transfer.Send($oack, $oack.Length, $Peer)
                try {
                    $ackPeer = [Net.IPEndPoint]::new([Net.IPAddress]::Any, 0)
                    [byte[]]$ack = $transfer.Receive([ref]$ackPeer)
                    $oackAcked = $ackPeer.Address.Equals($Peer.Address) -and
                        $ackPeer.Port -eq $Peer.Port -and $ack.Length -eq 4 -and
                        $ack[0] -eq 0 -and $ack[1] -eq 4 -and
                        $ack[2] -eq 0 -and $ack[3] -eq 0
                } catch [Net.Sockets.SocketException] {
                    # Retry OACK until ACK block zero arrives.
                }
            }
            if (!$oackAcked) {
                Write-Host "TIMEOUT $Name OACK"
                return
            }
        }
        $offset = $StartOffset
        $block = 1
        $sessionBlocks = 0
        $rawPerBlock = if ($HexEncode) { [int](($BlockSize - 8) / 2) } else { $BlockSize }
        [byte[]]$hexDigits = [Text.Encoding]::ASCII.GetBytes('0123456789ABCDEF')
        do {
            $rawCount = [Math]::Min($rawPerBlock, $content.Length - $offset)
            $wireCount = if ($HexEncode) { 8 + 2 * $rawCount } else { $rawCount }
            [byte[]]$packet = New-Object byte[] ($wireCount + 4)
            $packet[1] = 3
            $packet[2] = [byte](($block -shr 8) -band 255)
            $packet[3] = [byte]($block -band 255)
            if ($rawCount -gt 0 -and $HexEncode) {
                $adlerA = 1
                $adlerB = 0
                for ($i = 0; $i -lt $rawCount; $i++) {
                    $value = [int]$content[$offset + $i]
                    $adlerA += $value
                    if ($adlerA -ge 65521) { $adlerA -= 65521 }
                    $adlerB += $adlerA
                    if ($adlerB -ge 65521) { $adlerB -= 65521 }
                    $packet[12 + 2 * $i] = $hexDigits[($value -shr 4) -band 15]
                    $packet[13 + 2 * $i] = $hexDigits[$value -band 15]
                }
                [uint64]$adler = ([uint64]$adlerB * 65536) + [uint64]$adlerA
                for ($i = 0; $i -lt 8; $i++) {
                    $packet[4 + $i] = $hexDigits[($adler -shr (28 - 4 * $i)) -band 15]
                }
            } elseif ($HexEncode) {
                # Adler-32 of an empty payload is 00000001.
                [Array]::Copy([Text.Encoding]::ASCII.GetBytes('00000001'), 0, $packet, 4, 8)
            } elseif ($rawCount -gt 0) {
                [Array]::Copy($content, $offset, $packet, 4, $rawCount)
            }

            $acked = $false
            # Return to the UDP/69 listener promptly when the client abandons
            # this transfer ID and issues a resume RRQ.  A 64 x 2 s loop made
            # an otherwise recoverable single lost ACK look like a dead link.
            for ($retry = 0; $retry -lt 16 -and !$acked; $retry++) {
                [void]$transfer.Send($packet, $packet.Length, $Peer)
                try {
                    $ackPeer = [Net.IPEndPoint]::new([Net.IPAddress]::Any, 0)
                    [byte[]]$ack = $transfer.Receive([ref]$ackPeer)
                    # Cast before shifting. PowerShell otherwise preserves the
                    # byte type and truncates every ACK block >= 256 to 8 bits.
                    $ackBlock = if ($ack.Length -ge 4) {
                        (([int]$ack[2]) -shl 8) -bor ([int]$ack[3])
                    } else { -1 }
                    $ackOp = if ($ack.Length -ge 2) {
                        (([int]$ack[0]) -shl 8) -bor ([int]$ack[1])
                    } else { -1 }
                    if ($ackPeer.Address.Equals($Peer.Address) -and
                        $ackPeer.Port -eq $Peer.Port -and $ackOp -eq 5) {
                        Write-Host "ABORT $Name offset=$offset by client resume"
                        return
                    }
                    if ($ackPeer.Address.Equals($Peer.Address) -and
                        $ackPeer.Port -eq $Peer.Port -and
                        $ack.Length -eq 4 -and $ack[0] -eq 0 -and $ack[1] -eq 4 -and
                        $ackBlock -eq $block) {
                        $acked = $true
                    } else {
                        Write-Host "STALE $Name expected=$block op=$ackOp block=$ackBlock from=$($ackPeer.Address):$($ackPeer.Port)"
                        if ($RecoveryDelayMs -gt 0) {
                            # A small polled FPGA MAC may restart its RX path
                            # before repeating the previous ACK.  Do not send
                            # the replacement DATA into that recovery window.
                            Start-Sleep -Milliseconds $RecoveryDelayMs
                        }
                    }
                } catch [Net.Sockets.SocketException] {
                    # Retry the same DATA block after an ACK timeout.
                    Write-Host "NOACK $Name block=$block retry=$($retry + 1)"
                }
            }
            if (!$acked) {
                Write-Host "TIMEOUT $Name block=$block"
                return
            }
            if ($InterPacketDelayMs -gt 0) {
                # Allow a small polled MAC's RX ownership acknowledgement to
                # cross back into the RGMII clock domain before the next DATA.
                Start-Sleep -Milliseconds $InterPacketDelayMs
            }
            $offset += $rawCount
            $sessionBlocks++
            if (($block -band 1023) -eq 0) {
                Write-Host "PROGRESS $Name block=$block bytes=$offset"
                # Some Windows USB-Ethernet drivers eventually stop advancing
                # a very long stop-and-wait UDP flow on one socket.  Reopen the
                # socket proactively while preserving its TFTP transfer ID
                # (UDP source port), so the client sees one continuous session.
                $localPort = ([Net.IPEndPoint]$transfer.Client.LocalEndPoint).Port
                $transfer.Dispose()
                $transfer = New-TftpTransferSocket $localPort
                Write-Host "ROTATE $Name transfer-port=$localPort"
            }
            if ($sessionBlocks -ge $MaxSessionBlocks -and $offset -lt $content.Length) {
                Write-Host "CHUNK $Name next-offset=$offset"
                return
            }
            $block = ($block + 1) -band 0xffff
        } while ($wireCount -eq $BlockSize)
        Write-Host "DONE $Name ($offset bytes)"
    } finally {
        $transfer.Dispose()
    }
}

$endpoint = [Net.IPEndPoint]::new([Net.IPAddress]::Parse($BindAddress), $Port)
$listener = [Net.Sockets.UdpClient]::new($endpoint)
try {
    Write-Host "SoC TFTP root: $Root"
    Write-Host "Listening on ${BindAddress}:$Port; board is 192.168.1.50"
    while ($true) {
        $peer = [Net.IPEndPoint]::new([Net.IPAddress]::Any, 0)
        [byte[]]$request = $listener.Receive([ref]$peer)
        $drained = 0
        while ($listener.Available -gt 0) {
            $newPeer = [Net.IPEndPoint]::new([Net.IPAddress]::Any, 0)
            [byte[]]$newRequest = $listener.Receive([ref]$newPeer)
            if ($newPeer.Address.Equals($peer.Address) -and
                $newPeer.Port -eq $peer.Port) {
                $request = $newRequest
                $peer = $newPeer
                $drained++
            }
        }
        if ($drained) { Write-Host "DRAIN duplicate RRQ count=$drained" }
        if ($request.Length -lt 4 -or $request[0] -ne 0 -or $request[1] -ne 1) {
            Write-Host "IGNORE malformed request from $($peer.Address):$($peer.Port)"
            continue
        }
        $nul = [Array]::IndexOf($request, [byte]0, 2)
        if ($nul -le 2) {
            Write-Host "IGNORE malformed RRQ from $($peer.Address):$($peer.Port)"
            continue
        }
        $name = [Text.Encoding]::ASCII.GetString($request, 2, $nul - 2)
        $blockSize = 512
        $useOack = $false
        $startOffset = 0
        $hexEncode = $false
        $modeStart = $nul + 1
        $modeEnd = [Array]::IndexOf($request, [byte]0, $modeStart)
        $position = if ($modeEnd -ge $modeStart) { $modeEnd + 1 } else { $request.Length }
        while ($position -lt $request.Length) {
            $optionEnd = [Array]::IndexOf($request, [byte]0, $position)
            if ($optionEnd -le $position) { break }
            $optionName = [Text.Encoding]::ASCII.GetString(
                $request, $position, $optionEnd - $position)
            $valueStart = $optionEnd + 1
            $valueEnd = [Array]::IndexOf($request, [byte]0, $valueStart)
            if ($valueEnd -lt $valueStart) { break }
            $optionValue = [Text.Encoding]::ASCII.GetString(
                $request, $valueStart, $valueEnd - $valueStart)
            if ($optionName -ieq 'blksize') {
                $requested = 0
                if ([int]::TryParse($optionValue, [ref]$requested) -and
                    $requested -ge 8 -and $requested -le 512) {
                    $blockSize = $requested
                    $useOack = $true
                }
            } elseif ($optionName -ieq 'offset') {
                $requestedOffset = 0
                if ([int]::TryParse($optionValue, [ref]$requestedOffset) -and
                    $requestedOffset -ge 0) {
                    $startOffset = $requestedOffset
                    $useOack = $true
                }
            } elseif ($optionName -ieq 'encoding' -and $optionValue -ieq 'hexcrc') {
                $hexEncode = $true
                $useOack = $true
            }
            $position = $valueEnd + 1
        }
        if ($startOffset -gt 0) {
            # The bootloader already knows the block size it placed in this
            # resume RRQ.  Sending DATA block 1 directly avoids an extra OACK
            # round trip while the link is recovering.
            $useOack = $false
        }
        Send-TftpFile $name $peer $blockSize $useOack $startOffset $hexEncode
    }
} finally {
    $listener.Dispose()
}
