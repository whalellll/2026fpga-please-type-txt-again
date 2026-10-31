param(
    [string]$PortName = 'COM17',
    [int]$BaudRate = 115200
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
& (Join-Path $PSScriptRoot 'serial_mac_selftest.ps1') `
    -PortName $PortName -BaudRate $BaudRate `
    -ImagePath (Join-Path $root 'artifacts\xiangqi_fb_demo.bin') `
    -LoadAddress '0x01000000' -TimeoutSeconds 180 `
    -LogPath (Join-Path $root 'artifacts\board_xiangqi_fb_demo.log') `
    -SuccessMarker 'XIANGQI_FB_GUI_READY' `
    -FailureMarkers @('XIANGQI_FB_ID_FAIL', 'XIANGQI_FB_DMA_FAIL')
