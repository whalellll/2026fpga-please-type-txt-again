param(
    [string]$PortName = 'COM17',
    [int]$BaudRate = 115200,
    [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$serial = Join-Path $PSScriptRoot 'serial_mac_selftest.ps1'
$image = Join-Path $root 'artifacts\pf_mlp_stage_b_board.bin'
$log = Join-Path $root 'artifacts\board_pf_mlp_stage_b.log'

& $serial `
    -PortName $PortName `
    -BaudRate $BaudRate `
    -ImagePath $image `
    -LoadAddress '0x01000000' `
    -TimeoutSeconds $TimeoutSeconds `
    -LogPath $log `
    -SuccessMarker 'PF_MLP_STAGE_B_BOARD_PASS' `
    -FailureMarkers @(
        'PF_MLP_STAGE_B_BOARD_FAIL',
        'MAC_MMIO_FAIL',
        'MAC_EXEC_FAIL',
        'MAC_RESULT_FAIL'
    )
