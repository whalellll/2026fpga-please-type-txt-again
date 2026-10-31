param(
    [string]$PortName = 'COM5',
    [int]$BaudRate = 115200,
    [int]$Iterations = 2,
    [int]$PromptTimeoutSeconds = 180,
    [int]$CommandTimeoutSeconds = 30,
    [switch]$WaitForFreshBoot,
    [string]$LogPath
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$socVersion = ([IO.File]::ReadAllText((Join-Path $root 'VERSION'))).Trim()
$cpuSource = Get-Content -LiteralPath (Join-Path $root 'rtl/cpu/source.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$cpuVersion = ([regex]::Match($cpuSource.cpu_version, '^[0-9]+\.[0-9]+')).Value
$bootBanner = "SoC V$socVersion bootloader - CPU V$cpuVersion / RV32IMA"
$rootfsBytes = (Get-Item -LiteralPath (Join-Path $root 'linux/boot/rootfs.cpio')).Length
$dtbBytes = (Get-Item -LiteralPath (Join-Path $root 'linux/boot/soc.dtb')).Length
if (!$LogPath) { $LogPath = Join-Path $root 'artifacts\board_sdinfo_repro.log' }
$LogPath = [IO.Path]::GetFullPath($LogPath)
if ($Iterations -ne 2) { throw 'The board acceptance gate requires exactly two sdinfo iterations' }

$utf8 = New-Object Text.UTF8Encoding($false)
$capture = New-Object Text.StringBuilder

function Add-BoardByte([int]$Value, [Text.StringBuilder]$CommandCapture) {
    if ($Value -eq 10 -or $Value -eq 13 -or $Value -eq 9 -or
        ($Value -ge 32 -and $Value -le 126)) {
        $character = [char]$Value
        [void]$script:capture.Append($character)
        if ($null -ne $CommandCapture) { [void]$CommandCapture.Append($character) }
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

function Read-UntilPrompt(
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
            if ($recent.Length -gt 256) {
                $recent = $recent.Substring($recent.Length - 256)
            }
            if ($recent.Contains('soc> ')) { return }
        }
    }
    throw "Timed out after $TimeoutSeconds seconds waiting for soc> prompt"
}

function Wait-FreshBootConsole(
    [IO.Ports.SerialPort]$Port,
    [int]$TimeoutSeconds
) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $recent = ''
    $freshBootSeen = $false
    while ((Get-Date) -lt $deadline) {
        try { $value = $Port.ReadByte() } catch [TimeoutException] { continue }
        Add-BoardByte $value $null
        if ($value -eq 10 -or $value -eq 13 -or $value -eq 9 -or
            ($value -ge 32 -and $value -le 126)) {
            $recent += [char]$value
            if ($recent.Length -gt 1024) {
                $recent = $recent.Substring($recent.Length - 1024)
            }
            if (!$freshBootSeen -and
                $recent.Contains($bootBanner)) {
                $freshBootSeen = $true
                Write-Host "`nFresh V$socVersion boot observed; waiting for the console"
            }
            if ($freshBootSeen -and $recent.Contains('soc> ')) { return }
        }
    }
    throw "Timed out after $TimeoutSeconds seconds waiting for a fresh V$socVersion boot and soc> prompt"
}

function Assert-SdInfo([string]$Text, [int]$Iteration) {
    $forbidden = @(
        'MicroSD protocol error',
        'MicroSD read failed',
        'MicroSD filesystem error',
        'sector I/O failed',
        'no FAT filesystem',
        'unsupported FAT layout',
        'corrupt FAT metadata',
        'file not found',
        'out of range',
        'invalid FAT cluster chain',
        'unknown FAT error',
        'stable=absent',
        'raw=absent'
    )
    foreach ($marker in $forbidden) {
        if ($Text.Contains($marker)) {
            throw "SDINFO iteration $Iteration failed: found '$marker'"
        }
    }

    $requiredPatterns = @(
        'MicroSD detect: stable=present raw=present',
        'Card: SDHC/SDXC OCR=0x[0-9a-fA-F]{8} RCA=0x(?!00000000)[0-9a-fA-F]{8} sectors=62333952 capacity_MiB=30436 bus_width=4 clock_Hz=24750000',
        'Filesystem: FAT32 partition_lba=32 cluster_bytes=32768',
        'fw_jump\.bin:\s+264680 bytes',
        'Image:\s+7531468 bytes',
        ('rootfs\.cpio:\s+' + $rootfsBytes + ' bytes'),
        ('soc\.dtb:\s+' + $dtbBytes + ' bytes')
    )
    foreach ($pattern in $requiredPatterns) {
        if ($Text -notmatch $pattern) {
            throw "SDINFO iteration $Iteration failed: missing pattern '$pattern'"
        }
    }
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
    if ($WaitForFreshBoot) {
        Wait-FreshBootConsole $port $PromptTimeoutSeconds
    } else {
        $port.Write([string][char]0x1b)
        Start-Sleep -Milliseconds 50
        Write-Paced $port "`r"
        Read-UntilPrompt $port $PromptTimeoutSeconds $null
    }

    for ($iteration = 1; $iteration -le $Iterations; $iteration++) {
        Write-Host "`nSDINFO iteration $iteration/$Iterations"
        $commandCapture = New-Object Text.StringBuilder
        Write-Paced $port "sdinfo`r"
        Read-UntilPrompt $port $CommandTimeoutSeconds $commandCapture
        Assert-SdInfo $commandCapture.ToString() $iteration
    }

    Write-Host "`nSDINFO_2X_PASS"
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
