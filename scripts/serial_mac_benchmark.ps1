param(
    [string]$PortName = 'COM17',
    [int]$BaudRate = 115200,
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $PSScriptRoot 'serial_mac_selftest.ps1'
$image = Join-Path $root 'artifacts\mac_benchmark.bin'
$log = Join-Path $root 'artifacts\board_mac_benchmark.log'
$failures = @(
    'SOC_ID_FAIL',
    'DDR_NOT_READY',
    'MAC_ABI_FAIL',
    'SYS_CLOCK_FAIL',
    'MEM_VERIFY_FAIL',
    'MEM_CHECKSUM_FAIL',
    'MAC_EXEC_FAIL',
    'MAC_RESULT_FAIL',
    'MAC_COMPLETED_COUNT_FAIL',
    'MAC_CONTENTION_EXEC_FAIL',
    'MAC_CONTENTION_TIMEOUT'
)

& $runner -PortName $PortName -BaudRate $BaudRate -ImagePath $image `
    -LoadAddress '0x01000000' -TimeoutSeconds $TimeoutSeconds `
    -LogPath $log -SuccessMarker 'MAC_STRESS_PASS' `
    -FailureMarkers $failures
