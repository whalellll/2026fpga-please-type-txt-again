param(
    [string]$Distro = 'Ubuntu-22.04',
    [int]$Jobs = 2,
    [string]$BaseImagePath,
    [string]$OutputPath,
    [string]$LinuxArchivePath,
    [switch]$IncludeAudio
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$buildRoot = Join-Path $root ('build\linux-mac-scheduler\' + [guid]::NewGuid().ToString('N'))
if (!$OutputPath) {
    $OutputPath = Join-Path $buildRoot 'out'
}
if (!$BaseImagePath) {
    $BaseImagePath = Join-Path $root 'linux\boot\Image'
}

function Convert-ToWslPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot convert path to WSL: $full"
    }
    return '/mnt/' + $Matches[1].ToLowerInvariant() + '/' +
        $Matches[2].Replace('\', '/')
}

$buildFull = [IO.Path]::GetFullPath($buildRoot)
$allowedBase = [IO.Path]::GetFullPath((Join-Path $root 'build'))
if (!$buildFull.StartsWith($allowedBase, [StringComparison]::OrdinalIgnoreCase) -or
    [IO.Path]::GetFileName((Split-Path -Parent $buildFull)) -ne 'linux-mac-scheduler') {
    throw "Unsafe kernel build path: $buildFull"
}
if (!$LinuxArchivePath) {
    $LinuxArchivePath = Join-Path $root 'linux\sources\linux-5.14.tar.xz'
}
$archive = [IO.Path]::GetFullPath($LinuxArchivePath)
$driver = Join-Path $root 'linux\mac_accel\kernel\pango_mac.c'
$uapi = Join-Path $root 'linux\mac_accel\pango_mac_uapi.h'
$copyChunks = Join-Path $root 'linux\mac_accel\kernel\pango_mac_copy_chunks.h'
$integration = Join-Path $root 'linux\mac_accel\linux-5.14-integration.patch'
$dts = Join-Path $root 'linux\soc.dts'
foreach ($path in @($archive, $driver, $copyChunks, $uapi, $integration, $dts,
                     $BaseImagePath)) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing Linux MAC scheduler input: $path"
    }
}
if ($IncludeAudio) {
    foreach ($path in @('linux\audio\kernel\pango_audio.c','linux\audio\pango_audio_uapi.h')) {
        if (!(Test-Path -LiteralPath (Join-Path $root $path) -PathType Leaf)) {
            throw "Missing Linux audio source: $path"
        }
    }
}
if ((Test-Path -LiteralPath $OutputPath) -and
    @(Get-ChildItem -LiteralPath $OutputPath -Force).Count) {
    throw 'Choose an empty candidate OutputPath; existing outputs are preserved'
}
New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
New-Item -ItemType Directory -Path $OutputPath -Force | Out-Null

$wslArchive = Convert-ToWslPath $archive
$wslDriver = Convert-ToWslPath $driver
$wslCopyChunks = Convert-ToWslPath $copyChunks
$wslUapi = Convert-ToWslPath $uapi
$wslIntegration = Convert-ToWslPath $integration
$wslDts = Convert-ToWslPath $dts
$wslBaseImage = Convert-ToWslPath $BaseImagePath
$wslOutput = Convert-ToWslPath $OutputPath
$audioCopy = ''
$audioConfig = ''
$audioVerify = ''
if ($IncludeAudio) {
    $wslAudioDriver = Convert-ToWslPath (Join-Path $root 'linux\audio\kernel\pango_audio.c')
    $wslAudioUapi = Convert-ToWslPath (Join-Path $root 'linux\audio\pango_audio_uapi.h')
    $audioCopy = @"
cp '$wslAudioDriver' "`$tree/drivers/misc/pango_audio.c"
cp '$wslAudioUapi' "`$tree/include/uapi/linux/pango_audio.h"
"@
    $audioConfig = '"$tree/scripts/config" --file "$tree/.config" --enable PANGO_AUDIO_CAPTURE'
    $audioVerify = "grep -q '^CONFIG_PANGO_AUDIO_CAPTURE=y$' '$wslOutput/kernel.config'"
}

$command = @"
set -eu
command -v riscv64-linux-gnu-gcc >/dev/null
command -v flex >/dev/null
command -v bison >/dev/null
command -v bc >/dev/null
tmp=`$(mktemp -d)
trap 'rm -rf -- "`$tmp"' EXIT
tar -xJf '$wslArchive' -C "`$tmp"
tree="`$tmp/linux-5.14"
cp '$wslDriver' "`$tree/drivers/misc/pango_mac.c"
cp '$wslCopyChunks' "`$tree/drivers/misc/pango_mac_copy_chunks.h"
cp '$wslUapi' "`$tree/include/uapi/linux/pango_mac.h"
$audioCopy
patch -d "`$tree" -p1 < '$wslIntegration'
"`$tree/scripts/extract-ikconfig" '$wslBaseImage' > "`$tmp/production.config"
test -s "`$tmp/production.config"
cp "`$tmp/production.config" "`$tree/.config"
"`$tree/scripts/config" --file "`$tree/.config" --enable MISC_DEVICES
"`$tree/scripts/config" --file "`$tree/.config" --enable PANGO_MAC_ACCEL
$audioConfig
make -C "`$tree" ARCH=riscv CROSS_COMPILE=riscv64-linux-gnu- olddefconfig
make -C "`$tree" -j'$Jobs' ARCH=riscv CROSS_COMPILE=riscv64-linux-gnu- Image
"`$tree/scripts/dtc/dtc" -I dts -O dtb -o '$wslOutput/soc.dtb' '$wslDts'
cp "`$tree/arch/riscv/boot/Image" '$wslOutput/Image'
cp "`$tree/.config" '$wslOutput/kernel.config'
grep -q '^CONFIG_PANGO_MAC_ACCEL=y$' '$wslOutput/kernel.config'
$audioVerify
grep -q '^CONFIG_32BIT=y$' '$wslOutput/kernel.config'
grep -q '^# CONFIG_RISCV_ISA_C is not set$' '$wslOutput/kernel.config'
grep -q '^# CONFIG_FPU is not set$' '$wslOutput/kernel.config'
base_size=`$(wc -c < '$wslBaseImage')
candidate_size=`$(wc -c < '$wslOutput/Image')
test "`$candidate_size" -le "`$((base_size + 1048576))"
printf '%s\n' LINUX_MAC_SCHEDULER_KERNEL_BUILD_PASS
"@.Replace("`r`n", "`n")

$command | wsl.exe -d $Distro -- bash -s
if ($LASTEXITCODE -ne 0) {
    throw 'Linux MAC scheduler kernel build failed'
}

Write-Output "Candidate kernel: $(Join-Path $OutputPath 'Image')"
Write-Output "Candidate DTB: $(Join-Path $OutputPath 'soc.dtb')"
Write-Output 'The candidate was not promoted to linux/boot and was not programmed to the board.'
