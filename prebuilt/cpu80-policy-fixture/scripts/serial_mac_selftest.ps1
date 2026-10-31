param(
    [string]$PortName = 'COM17',
    [int]$BaudRate = 115200,
    [string]$ImagePath,
    [string]$LoadAddress = '0x01000000',
    [int]$TimeoutSeconds = 30,
    [switch]$WaitForBootloaderStart,
    [string]$LogPath,
    [string]$SuccessMarker = 'MAC_DDR_SOC_TEST_PASS',
    [string[]]$FailureMarkers = @(
        'MAC_MMIO_FAIL', 'MAC_EXEC_FAIL', 'MAC_RESULT_FAIL'
    )
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$ImagePath) { $ImagePath = Join-Path $root 'artifacts\mac_selftest.bin' }
if (!$LogPath) { $LogPath = Join-Path $root 'artifacts\board_mac_selftest.log' }
$ImagePath = [IO.Path]::GetFullPath($ImagePath)
$LogPath = [IO.Path]::GetFullPath($LogPath)
if (!(Test-Path -LiteralPath $ImagePath -PathType Leaf)) {
    throw "Missing MAC self-test image: $ImagePath"
}

$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText($LogPath, '', $utf8)

function Add-BoardByte([int]$Value) {
    if ($Value -eq 10 -or $Value -eq 13 -or $Value -eq 9 -or
        ($Value -ge 32 -and $Value -le 126)) {
        $s = [string][char]$Value
        [IO.File]::AppendAllText($LogPath, $s, $utf8)
        Write-Host -NoNewline $s
    }
}

function Read-UntilAny(
    [IO.Ports.SerialPort]$Port,
    [string[]]$Needles,
    [int]$Seconds
) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    $recent = ''
    while ((Get-Date) -lt $deadline) {
        try { $value = $Port.ReadByte() } catch [TimeoutException] { continue }
        Add-BoardByte $value
        if ($value -ge 9 -and $value -le 126) {
            $recent += [char]$value
            if ($recent.Length -gt 1024) {
                $recent = $recent.Substring($recent.Length - 1024)
            }
            foreach ($needle in $Needles) {
                if ($recent.Contains($needle)) { return $needle }
            }
        }
    }
    throw "Timed out waiting for board text: $($Needles -join ', ')"
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

function Wait-ControlByte(
    [IO.Ports.SerialPort]$Port,
    [int[]]$Allowed,
    [int]$Seconds
) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try { $value = $Port.ReadByte() } catch [TimeoutException] { continue }
        if ($Allowed -contains $value) { return $value }
        Add-BoardByte $value
    }
    throw 'Timed out waiting for XMODEM control byte'
}

function Send-XmodemFile(
    [IO.Ports.SerialPort]$Port,
    [string]$Path,
    [string]$Address
) {
    $Port.Write("loadx $Address`r")
    [void](Read-UntilAny $Port @('Start XMODEM-CRC transfer now...') 10)
    [void](Wait-ControlByte $Port @(10) 5)
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
            elseif ($response -eq 0x18) {
                throw "Board cancelled XMODEM at block $($index + 1)"
            }
        }
        if (!$acked) { throw "XMODEM retries exhausted at block $($index + 1)" }
    }

    $Port.Write([byte[]]@(0x04), 0, 1)
    [void](Wait-ControlByte $Port @(0x06) 8)
    [void](Read-UntilAny $Port @('soc> ') 10)
    Write-Host "`nXMODEM loaded $($content.Length) bytes in $blocks blocks"
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
    $port.Write("`r")
    [void](Read-UntilAny $port @('soc> ') 10)
    $port.Write("info`r")
    [void](Read-UntilAny $port @('soc> ') 10)
    Send-XmodemFile $port $ImagePath $LoadAddress
    $port.Write("boot $LoadAddress`r")
    $markers = @($SuccessMarker) + @($FailureMarkers)
    $result = Read-UntilAny $port $markers $TimeoutSeconds
    if ($result -ne $SuccessMarker) {
        # Failure markers are prefixes of diagnostic lines. Drain the rest of
        # that line so run/error/index details are preserved in the log.
        try { [void](Read-UntilAny $port @("`n") 2) } catch { }
        throw "Board program failed: $result"
    }
    Write-Host "`nBoard program passed ($SuccessMarker); log: $LogPath"
} finally {
    if ($port.IsOpen) { $port.Close() }
    $port.Dispose()
}
