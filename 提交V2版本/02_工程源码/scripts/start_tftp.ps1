param([string]$BindAddress = '192.168.1.2')

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$boot = Join-Path $root 'linux\boot'
foreach ($name in @('fw_jump.bin', 'Image', 'rootfs.cpio', 'soc.dtb',
                    'mac_selftest.bin')) {
    if (!(Test-Path -LiteralPath (Join-Path $boot $name))) {
        throw "Missing Linux boot resource: $name"
    }
}

Write-Output "Board address: 192.168.1.50/24"
Write-Output "TFTP server:  $BindAddress`:69"
Write-Output 'Keep this window open while programming or resetting the FPGA.'
& (Join-Path $PSScriptRoot 'tftp_server.ps1') -BindAddress $BindAddress -Root $boot
exit $LASTEXITCODE
