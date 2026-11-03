param(
    [string]$PortName = 'COM5',
    [int]$BaudRate = 115200,
    [ValidateRange(2, 30)]
    [int]$PlaySeconds = 5,
    [ValidateRange(1, 100)]
    [int]$Volume = 10,
    [ValidateRange(5, 300)]
    [int]$PromptTimeoutSeconds = 180,
    [ValidateRange(5, 180)]
    [int]$LoadTimeoutSeconds = 90,
    [switch]$WaitForFreshBoot,
    [string]$LogPath
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$socVersion = ([IO.File]::ReadAllText((Join-Path $root 'VERSION'))).Trim()
$cpuSource = Get-Content -LiteralPath (Join-Path $root 'rtl/cpu/source.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$cpuVersion = ([regex]::Match($cpuSource.cpu_version, '^[0-9]+\.[0-9]+')).Value
$bootBanner = "SoC V$socVersion bootloader - CPU V$cpuVersion / RV32IMA"
if (!$LogPath) {
    $LogPath = Join-Path $root 'artifacts\board_speaker_test.log'
}
$LogPath = [IO.Path]::GetFullPath($LogPath)
$utf8 = New-Object Text.UTF8Encoding($false)
$capture = New-Object Text.StringBuilder

function Add-BoardByte([int]$Value, [Text.StringBuilder]$LocalCapture) {
    if ($Value -eq 10 -or $Value -eq 13 -or $Value -eq 9 -or
        ($Value -ge 32 -and $Value -le 126)) {
        $character = [char]$Value
        [void]$script:capture.Append($character)
        if ($null -ne $LocalCapture) { [void]$LocalCapture.Append($character) }
        Write-Host -NoNewline $character
    }
}

function Write-Paced([IO.Ports.SerialPort]$Port, [string]$Text) {
    foreach ($character in $Text.ToCharArray()) {
        $Port.Write([string]$character)
        Start-Sleep -Milliseconds 10
    }
}

function Read-Until(
    [IO.Ports.SerialPort]$Port,
    [string]$Marker,
    [int]$TimeoutSeconds,
    [Text.StringBuilder]$LocalCapture,
    [string[]]$FailureMarkers = @()
) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $recent = ''
    while ((Get-Date) -lt $deadline) {
        try { $value = $Port.ReadByte() } catch [TimeoutException] { continue }
        Add-BoardByte $value $LocalCapture
        if ($value -eq 10 -or $value -eq 13 -or $value -eq 9 -or
            ($value -ge 32 -and $value -le 126)) {
            $recent += [char]$value
            if ($recent.Length -gt 4096) {
                $recent = $recent.Substring($recent.Length - 4096)
            }
            foreach ($failure in $FailureMarkers) {
                if ($recent.Contains($failure)) {
                    throw "Speaker test failed: board reported '$failure'"
                }
            }
            if ($recent.Contains($Marker)) { return }
        }
    }
    throw "Timed out after $TimeoutSeconds seconds waiting for '$Marker'"
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
            if ($recent.Length -gt 2048) {
                $recent = $recent.Substring($recent.Length - 2048)
            }
            if (!$freshBootSeen -and
                $recent.Contains($bootBanner)) {
                $freshBootSeen = $true
                Write-Host "`nFresh V$socVersion boot observed; waiting for the console"
            }
            if ($freshBootSeen -and $recent.Contains('soc> ')) { return }
        }
    }
    throw "Timed out waiting for a fresh V$socVersion boot and soc> prompt"
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

$failures = @(
    'Audio hardware ID mismatch',
    'Audio hardware stalled',
    'No MicroSD card',
    'Missing SD file',
    'SD file size is unsafe',
    'MicroSD protocol error',
    'MicroSD filesystem error',
    'SONG.PCM must be',
    'Playback failed',
    'debug speaker returned, error'
)

try {
    $port.Open()
    $port.DiscardInBuffer()
    if ($WaitForFreshBoot) {
        Wait-FreshBootConsole $port $PromptTimeoutSeconds
    } else {
        $port.Write([string][char]0x1b)
        Start-Sleep -Milliseconds 50
        # The currently programmed image can consume CR while leaving a lone
        # ESC state, so send a second CR to resynchronize its prompt.
        Write-Paced $port "`r`r"
        Read-Until $port 'soc> ' $PromptTimeoutSeconds $null
        Start-Sleep -Milliseconds 200
        $port.DiscardInBuffer()
    }

    $info = New-Object Text.StringBuilder
    Write-Paced $port "info`r"
    Read-Until $port 'soc> ' 15 $info
    if (!$info.ToString().Contains('AUDIO_ID=0x41554431')) {
        throw 'Speaker test failed: info did not report AUDIO_ID=0x41554431'
    }

    $debugHelp = New-Object Text.StringBuilder
    Write-Paced $port "debug help`r"
    Read-Until $port 'soc> ' 15 $debugHelp
    foreach ($command in @('debug mic', 'debug speaker',
            'debug speaker volume', 'debug camera')) {
        if (!$debugHelp.ToString().Contains($command)) {
            throw "V$socVersion debug help is missing '$command'"
        }
    }

    $migration = New-Object Text.StringBuilder
    Write-Paced $port "maikefen`r"
    Read-Until $port 'soc> ' 15 $migration
    if (!$migration.ToString().Contains('Use debug mic')) {
        throw 'Legacy microphone command did not print a migration hint'
    }

    $speaker = New-Object Text.StringBuilder
    Write-Paced $port "debug speaker volume $Volume`r"
    Read-Until $port 'soc> ' 15 $null $failures
    Write-Paced $port "debug speaker`r"
    Read-Until $port 'Playing raw s16le: 16 kHz mono' `
        $LoadTimeoutSeconds $speaker $failures

    # At the usual 10%, exercise live volume by stepping safely down to 5%.
    if ($Volume -ge 6) {
        $port.Write('-')
        $expectedFinalVolume = [Math]::Max(1, $Volume - 5)
    } else {
        $port.Write('+')
        $expectedFinalVolume = [Math]::Min(100, $Volume + 5)
    }

    $playDeadline = (Get-Date).AddSeconds($PlaySeconds)
    while ((Get-Date) -lt $playDeadline) {
        try { $value = $port.ReadByte() } catch [TimeoutException] { continue }
        Add-BoardByte $value $speaker
    }
    $port.Write('q')
    Read-Until $port 'soc> ' 15 $speaker $failures

    $text = $speaker.ToString()
    if ($text -notmatch 'Found SONG\.PCM, bytes=6162968') {
        throw 'Speaker test failed: unexpected SONG.PCM size'
    }
    if (!$text.Contains("volume=$Volume%")) {
        throw "Speaker test failed: bootloader did not apply $Volume% volume"
    }
    if ($text -notmatch 'Playback stopped after ([0-9]+) samples \(([0-9]+) s\), underflows=([0-9]+), volume=([0-9]+)%\.') {
        throw 'Speaker test failed: missing playback completion counters'
    }
    $samples = [uint64]$Matches[1]
    $seconds = [uint64]$Matches[2]
    $underflows = [uint64]$Matches[3]
    $finalVolume = [uint64]$Matches[4]
    if ($finalVolume -ne [uint64]$expectedFinalVolume) {
        throw "Speaker live volume test failed: final=$finalVolume expected=$expectedFinalVolume"
    }
    $minimumSamples = [uint64]$PlaySeconds * 12000
    $maximumSamples = [uint64]($PlaySeconds + 2) * 16000
    if ($samples -lt $minimumSamples -or $samples -gt $maximumSamples -or
        $seconds -lt [uint64]([Math]::Max(1, $PlaySeconds - 1)) -or
        $seconds -gt [uint64]($PlaySeconds + 1)) {
        throw "Speaker test failed: implausible playback rate ($samples samples / $seconds seconds over a $PlaySeconds-second observation)"
    }
    # The command clears the counter before printing its startup line, so a
    # small UART-induced startup count is expected.  A large value means the
    # CPU did not keep the I2S FIFO supplied during playback.
    if ($underflows -gt 1024) {
        throw "Speaker test failed: excessive FIFO underflows ($underflows)"
    }

    $history = New-Object Text.StringBuilder
    Write-Paced $port "info`r"
    Read-Until $port 'soc> ' 15 $history
    Write-Paced $port ([string][char]0x1b + "[A`r")
    Read-Until $port 'SYS_ID=0x53563300' 15 $history
    Read-Until $port 'soc> ' 15 $history
    $historyReplies = [regex]::Matches(
        $history.ToString(), 'SYS_ID=0x53563300').Count
    if ($historyReplies -ne 2 -or
        $history.ToString().Contains('unknown command')) {
        throw "Bootloader history test failed: Up did not recall info ($historyReplies replies)"
    }
    Write-Host "`nSPEAKER_SERIAL_PATH_PASS samples=$samples seconds=$seconds underflows=$underflows"
    Write-Host 'BOOTLOADER_HISTORY_SERIAL_PASS'
    Write-Host 'ACOUSTIC_CONFIRMATION_REQUIRED: confirm that music was audible from the speaker.'
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
