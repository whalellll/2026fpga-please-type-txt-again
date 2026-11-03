param(
    [string]$RootfsPath = 'build/vision/mac-conv-compute-clean/rootfs.cpio',
    [string]$DtbPath = 'build/vision/mac-conv-compute-clean/cpu_v2.dtb',
    [string]$Distro = 'pikafish-verify'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (![IO.Path]::IsPathRooted($RootfsPath)) {
    $RootfsPath = Join-Path $root $RootfsPath
}
if (![IO.Path]::IsPathRooted($DtbPath)) {
    $DtbPath = Join-Path $root $DtbPath
}
$rootfsFull = [IO.Path]::GetFullPath($RootfsPath)
$dtbFull = [IO.Path]::GetFullPath($DtbPath)
foreach ($path in @($rootfsFull, $dtbFull)) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing initrd contract input: $path"
    }
}
if ($dtbFull -notmatch '^([A-Za-z]):\\(.*)$') {
    throw "Cannot convert DTB path to WSL: $dtbFull"
}
$wslDtb = '/mnt/' + $Matches[1].ToLowerInvariant() + '/' +
    $Matches[2].Replace('\', '/')
$ErrorActionPreference = 'Continue'
$decoded = (& wsl.exe -d $Distro -u root -- dtc -q -I dtb -O dts $wslDtb 2>$null) -join "`n"
$ErrorActionPreference = 'Stop'
if ($LASTEXITCODE -ne 0) { throw 'DTB decode failed' }
$start = [regex]::Match($decoded, 'linux,initrd-start\s*=\s*<0x([0-9a-fA-F]+)>;')
$end = [regex]::Match($decoded, 'linux,initrd-end\s*=\s*<0x([0-9a-fA-F]+)>;')
if (!$start.Success -or !$end.Success) { throw 'Missing DTB initrd range' }
$startAddress = [Convert]::ToInt64($start.Groups[1].Value, 16)
$endAddress = [Convert]::ToInt64($end.Groups[1].Value, 16)
if ($startAddress -ne 0x03000000) {
    throw ('Unexpected Linux initrd load address: 0x{0:x8}' -f $startAddress)
}
$expectedEnd = $startAddress + (Get-Item -LiteralPath $rootfsFull).Length
if ($endAddress -ne $expectedEnd) {
    throw ('INITRD_RANGE_MISMATCH dtb=0x{0:x8} expected=0x{1:x8} bytes={2}' -f
        $endAddress, $expectedEnd, (Get-Item -LiteralPath $rootfsFull).Length)
}
Write-Output ('MAC_CONV_STAGE2_INITRD_CONTRACT_PASS start=0x{0:x8} end=0x{1:x8} bytes={2}' -f
    $startAddress, $endAddress, (Get-Item -LiteralPath $rootfsFull).Length)
