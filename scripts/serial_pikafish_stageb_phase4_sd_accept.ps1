param(
    [string]$PortName = 'COM17',
    [int]$BaudRate = 115200,
    [int]$ShellTimeoutSeconds = 600,
    [int]$EngineTimeoutSeconds = 900,
    [int]$MoveTimeoutSeconds = 600,
    [switch]$WaitForBootloaderStart,
    [string]$LogPath
)

$ErrorActionPreference = 'Stop'
if (!$LogPath) {
    $LogPath = Join-Path (Split-Path -Parent $PSScriptRoot) `
        'artifacts\board_pikafish_stageb_phase4_sd.log'
}

$arguments = @{
    PortName = $PortName
    BaudRate = $BaudRate
    ShellTimeoutSeconds = $ShellTimeoutSeconds
    EngineTimeoutSeconds = $EngineTimeoutSeconds
    MoveTimeoutSeconds = $MoveTimeoutSeconds
    Mode = '1'
    UseInitDefault = $true
    WaitForBootloaderStart = $WaitForBootloaderStart
    LogPath = $LogPath
}

& (Join-Path $PSScriptRoot 'serial_pikafish_stageb_phase3_accept.ps1') @arguments
Write-Output "PIKAFISH_STAGEB_PHASE4_SD_BOARD_PASS mode=1 source=microsd; log=$LogPath"
