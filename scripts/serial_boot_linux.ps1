param(
    [string]$PortName = 'COM5',
    [int]$BaudRate = 115200,
    [int]$CaptureSeconds = 600,
    [string]$LogPath,
    [string]$OpenSbiPath,
    [string]$OpenSbiAddress = '0x18000000',
    [string]$KernelPath,
    [string]$RootfsPath,
    [string]$DtbPath,
    [switch]$LoadPikafishAssets,
    [string]$PikafishModelPath,
    [string]$PikafishAttackPath,
    [switch]$PreflightOnly,
    [switch]$OpenSbiSmokeTest,
    [switch]$KernelSmokeTest,
    [switch]$ResumeRootfs,
    [switch]$SkipLoad
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$LogPath) { $LogPath = Join-Path $root 'artifacts\board_linux_boot.log' }
$LogPath = [IO.Path]::GetFullPath($LogPath)
$utf8 = New-Object Text.UTF8Encoding($false)

$defaultOpenSbi = Join-Path $root 'linux\boot\fw_jump.bin'
if (!$OpenSbiPath) { $OpenSbiPath = $defaultOpenSbi }
$OpenSbiPath = [IO.Path]::GetFullPath($OpenSbiPath)
$images = @(
    @{ Name = 'fw_jump.bin'; Address = $OpenSbiAddress; Path = $OpenSbiPath },
    @{ Name = 'Image';       Address = '0x00400000'; Path = $KernelPath },
    @{ Name = 'rootfs.cpio'; Address = '0x03000000'; Path = $RootfsPath },
    @{ Name = 'soc.dtb';  Address = '0x1a000000'; Path = $DtbPath }
)
foreach ($image in $images) {
    if (!$image.Path) { $image.Path = Join-Path $root ('linux\boot\' + $image.Name) }
    if (!(Test-Path -LiteralPath $image.Path -PathType Leaf)) {
        throw "Missing Linux boot resource: $($image.Path)"
    }
}
if ($OpenSbiSmokeTest) {
    $images = @($images | Where-Object { $_.Name -in @('fw_jump.bin', 'soc.dtb') })
}
if ($KernelSmokeTest) {
    $images = @($images | Where-Object { $_.Name -in @('fw_jump.bin', 'Image', 'soc.dtb') })
}
if ($ResumeRootfs) {
    if ($OpenSbiSmokeTest -or $KernelSmokeTest -or $SkipLoad) {
        throw 'ResumeRootfs cannot be combined with smoke tests or SkipLoad'
    }
    # XMODEM already confirmed OpenSBI and Image before a rootfs transfer
    # interruption; retry the unfinished archive and DTB in their own DDR
    # ranges without restarting those completed transfers.
    $images = @($images | Where-Object { $_.Name -in @('rootfs.cpio', 'soc.dtb') })
}
if ($SkipLoad) { $images = @() }
if ($LoadPikafishAssets) {
    if ($OpenSbiSmokeTest -or $KernelSmokeTest -or $ResumeRootfs -or $SkipLoad) {
        throw 'Pikafish asset preload requires a complete four-file Linux boot'
    }
    if (!$PikafishModelPath) { $PikafishModelPath = Join-Path $root 'linux\boot\pikafish.pff' }
    if (!$PikafishAttackPath) { $PikafishAttackPath = Join-Path $root 'linux\boot\pikafish.atk' }
    $assets = @(
        @{ Name='pikafish.pff'; Address='0x10000000'; Path=$PikafishModelPath;
           Size=68122688; Limit=0x05000000;
           Hash='de0906fa1bea82248523eb39fc6b2956613b02ae675ccf67eef3f392de939260' },
        @{ Name='pikafish.atk'; Address='0x15000000'; Path=$PikafishAttackPath;
           Size=34603072; Limit=0x02200000;
           Hash='2235f0b1cca2e447a828bf1c7c7247237580603026d6152954da07efca2d474c' }
    )
    foreach ($asset in $assets) {
        $asset.Path = [IO.Path]::GetFullPath($asset.Path)
        if (!(Test-Path -LiteralPath $asset.Path -PathType Leaf)) {
            throw "Missing Pikafish asset: $($asset.Path)"
        }
        $size = (Get-Item -LiteralPath $asset.Path).Length
        $padded = [int64][Math]::Ceiling($size / 1024.0) * 1024
        $hash = (Get-FileHash -LiteralPath $asset.Path -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($size -ne $asset.Size -or $padded -gt $asset.Limit -or $hash -cne $asset.Hash) {
            throw "Pikafish asset identity/range mismatch: $($asset.Name)"
        }
        Write-Host "PIKAFISH_ASSET_PREFLIGHT_PASS name=$($asset.Name) bytes=$size sha256=$hash"
        $images += @{ Name=$asset.Name; Address=$asset.Address; Path=$asset.Path }
    }
}
if ($PreflightOnly) {
    foreach ($image in $images) {
        $size = (Get-Item -LiteralPath $image.Path).Length
        $hash = (Get-FileHash -LiteralPath $image.Path -Algorithm SHA256).Hash.ToLowerInvariant()
        Write-Host "BOOT_FILE_PREFLIGHT_PASS name=$($image.Name) bytes=$size sha256=$hash"
    }
    return
}
[IO.File]::WriteAllText($LogPath, '', $utf8)

function Add-BoardByte([int]$Value) {
    if ($Value -eq 10 -or $Value -eq 13 -or $Value -eq 9 -or
        ($Value -ge 32 -and $Value -le 126)) {
        $s = [char]$Value
        [IO.File]::AppendAllText($LogPath, $s, $utf8)
        Write-Host -NoNewline $s
    }
}

function Write-Paced([IO.Ports.SerialPort]$Port, [string]$Text, [int]$DelayMilliseconds = 20) {
    foreach ($char in $Text.ToCharArray()) {
        $Port.Write([string]$char)
        Start-Sleep -Milliseconds $DelayMilliseconds
    }
}

function Read-UntilText([IO.Ports.SerialPort]$Port, [string]$Needle, [int]$TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $text = ''
    while ((Get-Date) -lt $deadline) {
        try { $value = $Port.ReadByte() } catch [TimeoutException] { continue }
        Add-BoardByte $value
        if ($value -ge 9 -and $value -le 126) {
            $text += [char]$value
            if ($text.Length -gt 512) { $text = $text.Substring($text.Length - 512) }
            if ($text.Contains($Needle)) {
                $script:LastReadText = $text
                return
            }
        }
    }
    throw "Timed out waiting for board text: $Needle"
}

function Get-XmodemCrc([byte[]]$Data) {
    [int]$crc = 0
    foreach ($value in $Data) {
        $crc = $crc -bxor (([int]$value) -shl 8)
        for ($bit = 0; $bit -lt 8; $bit++) {
            if (($crc -band 0x8000) -ne 0) {
                $crc = (($crc -shl 1) -bxor 0x1021) -band 0xffff
            } else {
                $crc = ($crc -shl 1) -band 0xffff
            }
        }
    }
    return $crc
}

function Wait-ControlByte([IO.Ports.SerialPort]$Port, [int[]]$Allowed, [int]$TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try { $value = $Port.ReadByte() } catch [TimeoutException] { continue }
        if ($Allowed -contains $value) { return $value }
        Add-BoardByte $value
    }
    throw 'Timed out waiting for XMODEM control byte'
}

function Send-XmodemFile([IO.Ports.SerialPort]$Port, [string]$Path, [string]$Address) {
    $name = Split-Path -Leaf $Path
    Write-Host "`nXMODEM $name -> $Address"
    $Port.Write("loadx $Address`r")
    Read-UntilText $Port 'Start XMODEM-CRC transfer now...' 10
    # Consume the rest of that line, then wait for the receiver's standalone C.
    do { $value = Wait-ControlByte $Port @(10) 5 } while ($value -ne 10)
    [void](Wait-ControlByte $Port @(0x43) 5)

    [byte[]]$content = [IO.File]::ReadAllBytes($Path)
    $blocks = [int][Math]::Ceiling($content.Length / 1024.0)
    for ($index = 0; $index -lt $blocks; $index++) {
        [byte[]]$payload = New-Object byte[] 1024
        for ($p = 0; $p -lt $payload.Length; $p++) { $payload[$p] = 0x1a }
        $offset = $index * 1024
        $count = [Math]::Min(1024, $content.Length - $offset)
        [Array]::Copy($content, $offset, $payload, 0, $count)
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
        for ($attempt = 0; $attempt -lt 10 -and !$acked; $attempt++) {
            $Port.Write($packet, 0, $packet.Length)
            $response = Wait-ControlByte $Port @(0x06, 0x15, 0x18) 8
            if ($response -eq 0x06) { $acked = $true }
            elseif ($response -eq 0x18) { throw "Board cancelled $name at block $($index + 1)" }
        }
        if (!$acked) { throw "XMODEM retries exhausted for $name block $($index + 1)" }
        if ((($index + 1) % 256) -eq 0 -or ($index + 1) -eq $blocks) {
            $percent = [Math]::Floor((($index + 1) * 100.0) / $blocks)
            Write-Host "  $percent% ($($index + 1)/$blocks blocks)"
        }
    }

    $Port.Write([byte[]]@(0x04), 0, 1)
    $response = Wait-ControlByte $Port @(0x06) 8
    if ($response -ne 0x06) { throw "No final XMODEM ACK for $name" }
    Read-UntilText $Port 'soc> ' 10
    $expectedBytes = [int64]$blocks * 1024
    $receipt = [regex]::Match($script:LastReadText, 'received\s+(\d+)\s+bytes')
    if (!$receipt.Success -or [int64]$receipt.Groups[1].Value -ne $expectedBytes) {
        throw "Board XMODEM byte count mismatch for $name; expected $expectedBytes padded bytes, receipt: $($script:LastReadText)"
    }
    Write-Host "XMODEM DONE $name ($($content.Length) bytes)"
}

$port = New-Object IO.Ports.SerialPort($PortName, $BaudRate, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
$port.Handshake = [IO.Ports.Handshake]::None
$port.ReadTimeout = 200
$port.WriteTimeout = 10000
$port.DtrEnable = $false
$port.RtsEnable = $false
try {
    $port.Open()
    $port.DiscardInBuffer()
    # A single CR is safe even while automatic netboot is running.  It remains
    # in the RX FIFO and produces a fresh prompt when the bootloader returns.
    $port.Write("`r")
    Read-UntilText $port 'soc> ' 180
    foreach ($image in $images) { Send-XmodemFile $port $image.Path $image.Address }
    Write-Host "`nAll images loaded; starting OpenSBI/Linux"
    $port.Write("linux $OpenSbiAddress 0x1a000000`r")
    $deadline = (Get-Date).AddSeconds($CaptureSeconds)
    $recent = ''
    while ((Get-Date) -lt $deadline) {
        try { $value = $port.ReadByte() } catch [TimeoutException] { continue }
        Add-BoardByte $value
        if ($value -eq 10 -or $value -eq 13 -or $value -eq 9 -or
            ($value -ge 32 -and $value -le 126)) {
            $recent += [char]$value
            if ($recent.Length -gt 1024) { $recent = $recent.Substring($recent.Length - 1024) }
        }
        if (!$OpenSbiSmokeTest -and !$KernelSmokeTest -and
            $recent.Contains('LINUX_BOOT_TO_SHELL_SECONDS=') -and
            $recent.Contains('/ # ')) {
            Write-Host "`nLinux root shell ready; COM port released."
            break
        }
    }
} finally {
    if ($port.IsOpen) { $port.Close() }
    $port.Dispose()
}
