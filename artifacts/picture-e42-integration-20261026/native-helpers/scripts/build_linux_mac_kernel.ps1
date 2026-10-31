param(
    [string]$Distro = 'Ubuntu-22.04',
    [int]$Jobs = 2,
    [string]$BaseImagePath,
    [string]$OutputPath,
    [string]$LinuxArchivePath,
    [string]$LinuxArchiveWslPath,
    [switch]$IncludeAudio,
    [switch]$IncludeVoice,
    [switch]$DirectWorkspaceTree
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
foreach ($target in @($buildFull, [IO.Path]::GetFullPath($OutputPath))) {
    if (!$target.StartsWith('G:\fpga\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Kernel outputs must remain inside the workspace' }
    $cursor = $target
    while ($cursor -and $cursor -ne 'G:\fpga') {
        if ((Test-Path -LiteralPath $cursor) -and ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Kernel output traverses a filesystem link: $cursor" }
        $cursor = Split-Path -Parent $cursor
    }
}
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
if($LinuxArchiveWslPath){
    if($LinuxArchiveWslPath -cnotmatch '^/mnt/g/fpga/[a-zA-Z0-9_./-]+\.tar\.xz$' -or $LinuxArchiveWslPath -match '(^|/)\.\.(/|$)'){throw 'Linux archive must be inside the workspace'}
    $localHash=(& wsl.exe -d $Distro -- sha256sum $LinuxArchiveWslPath | Select-Object -Last 1).Split(' ')[0]
    if($localHash -cne (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()){throw 'WSL-local Linux archive differs from frozen archive'}
    $wslArchive=$LinuxArchiveWslPath
}
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
$voiceCopy = ''
$voiceConfig = ''
$voiceVerify = ''
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
if ($IncludeVoice) {
    if (!$IncludeAudio) { throw 'Voice build also requires the existing audio driver' }
    $voiceDriver = Convert-ToWslPath (Join-Path $root 'linux/audio/kernel/pango_voice.c')
    $voiceUapi = Convert-ToWslPath (Join-Path $root 'linux/audio/pango_voice_uapi.h')
    $voiceCopy = @"
cp '$voiceDriver' "`$tree/drivers/misc/pango_voice.c"
cp '$voiceUapi' "`$tree/include/uapi/linux/pango_voice.h"
printf '\nobj-`$(CONFIG_PANGO_VOICE_ACCEL) += pango_voice.o\n' >> "`$tree/drivers/misc/Makefile"
printf '\nconfig PANGO_VOICE_ACCEL\n\tbool "Pango XQT1 voice accelerator"\n\tdepends on OF\n' >> "`$tree/drivers/misc/Kconfig"
"@
    $voiceConfig = '"$tree/scripts/config" --file "$tree/.config" --enable PANGO_VOICE_ACCEL'
    $voiceVerify = "grep -q '^CONFIG_PANGO_VOICE_ACCEL=y$' '$wslOutput/kernel.config'"
}

$wslBuildProfile = Convert-ToWslPath (Join-Path $root 'scripts/wsl_build_profile.sh')
$wslBuildRoot = Convert-ToWslPath $buildRoot
$wslFilesystemHelper = Convert-ToWslPath (Join-Path $root 'scripts/linux/workspace_kernel_fs.py')
$workspaceMounted = $false
$kernelDirectorySetup = "mkdir '$wslBuildRoot/kernel'"
if (!$DirectWorkspaceTree) {
    $savedPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $buildUid = (& wsl.exe -d $Distro -- id -u 2>$null | Select-Object -Last 1)
        if ($LASTEXITCODE -ne 0 -or $buildUid -notmatch '^\d+$') { throw 'Cannot determine WSL build uid' }
        $buildGid = (& wsl.exe -d $Distro -- id -g 2>$null | Select-Object -Last 1)
        if ($LASTEXITCODE -ne 0 -or $buildGid -notmatch '^\d+$') { throw 'Cannot determine WSL build gid' }
        $fsResult = @(& wsl.exe -d $Distro --user root -- python3 $wslFilesystemHelper prepare --image "$wslBuildRoot/kernel.ext4" --mount "$wslBuildRoot/kernel" --uid $buildUid --gid $buildGid 2>&1)
        $fsExit = $LASTEXITCODE
        $fsResult | Out-File -LiteralPath (Join-Path $OutputPath 'filesystem-prepare.log') -Encoding utf8
        if ($fsExit -ne 0 -or !($fsResult -match 'WORKSPACE_EXT4_MOUNTED')) { throw 'Workspace filesystem preparation failed; preserve the image and logs' }
        $workspaceMounted = $true
        $kernelDirectorySetup = "test -d '$wslBuildRoot/kernel/lost+found'"
    } finally { $ErrorActionPreference = $savedPreference }
}
$command = @"
set -eu
export PATH=/opt/toolchain/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export FPGA_BUILD_REQUESTED_JOBS=$Jobs
export FPGA_BUILD_NO_CACHE=1
. '$wslBuildProfile'
command -v riscv64-linux-gnu-gcc >/dev/null
command -v flex >/dev/null
command -v bison >/dev/null
command -v bc >/dev/null
tmp='$wslBuildRoot/kernel'
$kernelDirectorySetup
mkdir "`$tmp/tmp"
export TMPDIR="`$tmp/tmp" TMP="`$tmp/tmp" TEMP="`$tmp/tmp"
trap 'rc=`$?; printf "PRESERVED_KERNEL_TREE=%s EXIT=%s\n" "`$tmp" "`$rc"' EXIT
tar -xJf '$wslArchive' -C "`$tmp"
tree="`$tmp/linux-5.14"
cp '$wslDriver' "`$tree/drivers/misc/pango_mac.c"
cp '$wslCopyChunks' "`$tree/drivers/misc/pango_mac_copy_chunks.h"
cp '$wslUapi' "`$tree/include/uapi/linux/pango_mac.h"
$audioCopy
patch -d "`$tree" -p1 < '$wslIntegration'
$voiceCopy
"`$tree/scripts/extract-ikconfig" '$wslBaseImage' > "`$tmp/production.config"
test -s "`$tmp/production.config"
cp "`$tmp/production.config" "`$tree/.config"
"`$tree/scripts/config" --file "`$tree/.config" --enable MISC_DEVICES
"`$tree/scripts/config" --file "`$tree/.config" --enable PANGO_MAC_ACCEL
$audioConfig
$voiceConfig
make -C "`$tree" ARCH=riscv CROSS_COMPILE=riscv64-linux-gnu- olddefconfig
make -C "`$tree" -j"`$FPGA_BUILD_JOBS" ARCH=riscv CROSS_COMPILE=riscv64-linux-gnu- Image
"`$tree/scripts/dtc/dtc" -I dts -O dtb -o '$wslOutput/soc.dtb' '$wslDts'
cp "`$tree/arch/riscv/boot/Image" '$wslOutput/Image'
cp "`$tree/.config" '$wslOutput/kernel.config'
grep -q '^CONFIG_PANGO_MAC_ACCEL=y$' '$wslOutput/kernel.config'
$audioVerify
$voiceVerify
grep -q '^CONFIG_32BIT=y$' '$wslOutput/kernel.config'
grep -q '^# CONFIG_RISCV_ISA_C is not set$' '$wslOutput/kernel.config'
grep -q '^# CONFIG_FPU is not set$' '$wslOutput/kernel.config'
base_size=`$(wc -c < '$wslBaseImage')
candidate_size=`$(wc -c < '$wslOutput/Image')
test "`$candidate_size" -le "`$((base_size + 1048576))"
printf '%s\n' LINUX_MAC_SCHEDULER_KERNEL_BUILD_PASS
"@.Replace("`r`n", "`n")

$savedPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
$command | wsl.exe -d $Distro -- bash -s 2>&1 | Tee-Object -FilePath (Join-Path $OutputPath 'build.log')
$kernelExitCode = $LASTEXITCODE
} finally {
    if ($workspaceMounted) {
        $fsResult = @(& wsl.exe -d $Distro --user root -- python3 $wslFilesystemHelper unmount --image "$wslBuildRoot/kernel.ext4" --mount "$wslBuildRoot/kernel" 2>&1)
        $fsExit = $LASTEXITCODE
        $fsResult | Out-File -LiteralPath (Join-Path $OutputPath 'filesystem-unmount.log') -Encoding utf8
        if ($fsExit -ne 0 -or !($fsResult -match 'WORKSPACE_EXT4_UNMOUNTED_PRESERVED')) { throw 'Workspace kernel filesystem unmount failed; inspect its recorded owner before recovery' }
    }
    $ErrorActionPreference = $savedPreference
}
if ($kernelExitCode -ne 0) {
    throw 'Linux MAC scheduler kernel build failed'
}

Write-Output "Candidate kernel: $(Join-Path $OutputPath 'Image')"
Write-Output "Candidate DTB: $(Join-Path $OutputPath 'soc.dtb')"
Write-Output 'The candidate was not promoted to linux/boot and was not programmed to the board.'
