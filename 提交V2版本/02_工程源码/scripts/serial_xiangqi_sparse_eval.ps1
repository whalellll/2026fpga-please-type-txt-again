param(
    [string]$PortName = 'COM17',
    [int]$BaudRate = 115200,
    [int]$TimeoutSeconds = 60
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $PSScriptRoot 'serial_mac_selftest.ps1'
$image = Join-Path $root 'artifacts\xiangqi_sparse_eval_selftest.bin'
$log = Join-Path $root 'artifacts\board_xiangqi_sparse_eval.log'
$failures = @(
    'XQ_SPARSE_MMIO_FAIL',
    'XQ_SPARSE_CONFIG_CHECK_FAIL',
    'XQ_SPARSE_EXEC_FAIL',
    'XQ_SPARSE_RESULT_FAIL',
    'XQ_SPARSE_RUN_COUNT_FAIL'
)

& $runner -PortName $PortName -BaudRate $BaudRate -ImagePath $image `
    -LoadAddress '0x01000000' -TimeoutSeconds $TimeoutSeconds `
    -LogPath $log -SuccessMarker 'XIANGQI_SPARSE_BOARD_PASS' `
    -FailureMarkers $failures
