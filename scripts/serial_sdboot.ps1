param(
    [string]$PortName = 'COM5',
    [ValidateRange(1200, 4000000)]
    [int]$BaudRate = 115200,
    [ValidateRange(1, 3600)]
    [int]$PromptTimeoutSeconds = 180,
    [ValidateRange(1, 3600)]
    [int]$BootTimeoutSeconds = 600,
    [string]$LogPath,
    [string]$BootDirectory
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$LogPath) { $LogPath = Join-Path $root 'artifacts\board_sdboot.log' }
if (!$BootDirectory) { $BootDirectory = Join-Path $root 'linux\boot' }
$LogPath = [IO.Path]::GetFullPath($LogPath)
$BootDirectory = [IO.Path]::GetFullPath($BootDirectory)
$utf8 = [Text.UTF8Encoding]::new($false)
$capture = [Text.StringBuilder]::new()

$bootFileNames = @('fw_jump.bin', 'Image', 'rootfs.cpio', 'soc.dtb')
$bootFiles = foreach ($name in $bootFileNames) {
    $path = Join-Path $BootDirectory $name
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing reference Linux boot resource: $path"
    }
    $file = Get-Item -LiteralPath $path
    [pscustomobject]@{ Name = $name; Length = [uint64]$file.Length }
}
$expectedTotalBytes = [uint64](
    ($bootFiles | Measure-Object -Property Length -Sum).Sum
)

function Add-BoardByte([int]$Value, [Text.StringBuilder]$CommandCapture) {
    if ($Value -eq 10 -or $Value -eq 13 -or $Value -eq 9 -or
        ($Value -ge 32 -and $Value -le 126)) {
        $character = [char]$Value
        [void]$script:capture.Append($character)
        if ($null -ne $CommandCapture) {
            [void]$CommandCapture.Append($character)
        }
        Write-Host -NoNewline $character
    }
}

function Write-Paced(
    [IO.Ports.SerialPort]$Port,
    [string]$Text,
    [int]$DelayMilliseconds = 10
) {
    foreach ($character in $Text.ToCharArray()) {
        $Port.Write([string]$character)
        Start-Sleep -Milliseconds $DelayMilliseconds
    }
}

function Read-UntilPrompt([IO.Ports.SerialPort]$Port, [int]$TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $recent = ''
    while ((Get-Date) -lt $deadline) {
        try { $value = $Port.ReadByte() } catch [TimeoutException] { continue }
        Add-BoardByte $value $null
        if ($value -eq 10 -or $value -eq 13 -or $value -eq 9 -or
            ($value -ge 32 -and $value -le 126)) {
            $recent += [char]$value
            if ($recent.Length -gt 512) {
                $recent = $recent.Substring($recent.Length - 512)
            }
            if ($recent.Contains('soc> ')) { return }
        }
    }
    throw "Timed out after $TimeoutSeconds seconds waiting for soc> prompt"
}

function Read-UntilLinuxShell(
    [IO.Ports.SerialPort]$Port,
    [int]$TimeoutSeconds,
    [Text.StringBuilder]$CommandCapture
) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $recent = ''
    while ((Get-Date) -lt $deadline) {
        try { $value = $Port.ReadByte() } catch [TimeoutException] { continue }
        Add-BoardByte $value $CommandCapture
        if ($value -eq 10 -or $value -eq 13 -or $value -eq 9 -or
            ($value -ge 32 -and $value -le 126)) {
            $recent += [char]$value
            if ($recent.Length -gt 4096) {
                $recent = $recent.Substring($recent.Length - 4096)
            }
            if ($recent.Contains('/ # ')) { return }
            if ($recent.Contains('sdboot returned, error') -or
                $recent.Contains('soc> ')) {
                throw 'SDBOOT returned to the bootloader instead of reaching Linux'
            }
        }
    }
    throw "Timed out after $TimeoutSeconds seconds waiting for Linux / # prompt"
}

function Assert-SdBoot(
    [string]$Text,
    [object[]]$ReferenceFiles,
    [uint64]$ReferenceTotalBytes
) {
    $forbidden = @(
        'MicroSD protocol error',
        'MicroSD read failed',
        'MicroSD filesystem error',
        'Missing or invalid SD file',
        'SD file size is unsafe',
        'SD load cancelled by Esc',
        'sdboot returned, error'
    )
    foreach ($marker in $forbidden) {
        if ($Text.Contains($marker)) {
            throw "SDBOOT failed: found '$marker'"
        }
    }

    $requiredPatterns = @(
        'MicroSD Linux boot',
        'Mounted FAT32 volume, cluster bytes=32768',
        ('MicroSD total: bytes={0}, [0-9]+ ms, [1-9][0-9]* KiB/s' -f
            $ReferenceTotalBytes),
        'Starting OpenSBI at 0x18000000',
        'LINUX_BOOT_TO_SHELL_SECONDS=[0-9]+(?:\.[0-9]+)?',
        '/ # '
    )
    foreach ($file in $ReferenceFiles) {
        $requiredPatterns += (
            'Loading {0} to 0x[0-9a-fA-F]+, bytes={1}' -f
            [regex]::Escape($file.Name), $file.Length
        )
    }
    foreach ($pattern in $requiredPatterns) {
        if ($Text -notmatch $pattern) {
            throw "SDBOOT failed: missing pattern '$pattern'"
        }
    }
}

$port = [IO.Ports.SerialPort]::new(
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
    $port.Write([string][char]0x1b)
    Start-Sleep -Milliseconds 50
    Write-Paced $port "`r"
    Read-UntilPrompt $port $PromptTimeoutSeconds

    Write-Host "`nStarting MicroSD Linux boot"
    $commandCapture = [Text.StringBuilder]::new()
    Write-Paced $port "sdboot`r"
    Read-UntilLinuxShell $port $BootTimeoutSeconds $commandCapture
    Assert-SdBoot $commandCapture.ToString() $bootFiles $expectedTotalBytes
    Write-Host (
        "`nSDBOOT_LINUX_SHELL_PASS files=4 bytes={0}" -f $expectedTotalBytes
    )
} finally {
    if ($port.IsOpen) { $port.Close() }
    $port.Dispose()
    $directory = Split-Path -Parent $LogPath
    if (!(Test-Path -LiteralPath $directory)) {
        [void](New-Item -ItemType Directory -Path $directory)
    }
    [IO.File]::WriteAllText($LogPath, $capture.ToString(), $utf8)
    Write-Host "`nSerial log: $LogPath"
}
