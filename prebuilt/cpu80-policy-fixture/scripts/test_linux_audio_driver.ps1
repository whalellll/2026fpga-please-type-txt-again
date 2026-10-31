param([string]$Distro = 'chiplab_sim')

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$driverPath = Join-Path $root 'linux\audio\kernel\pango_audio.c'
$uapiPath = Join-Path $root 'linux\audio\pango_audio_uapi.h'
$dtsPath = Join-Path $root 'linux\soc.dts'
$configPath = Join-Path $root 'linux\soc_defconfig.fragment'
$integrationPath = Join-Path $root 'linux\mac_accel\linux-5.14-integration.patch'
foreach ($path in @($driverPath, $uapiPath, $dtsPath, $configPath,
                     $integrationPath)) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing Linux audio input: $path"
    }
}

$driver = [IO.File]::ReadAllText($driverPath)
$dts = [IO.File]::ReadAllText($dtsPath)
$config = [IO.File]::ReadAllText($configPath)
$integration = [IO.File]::ReadAllText($integrationPath)
foreach ($needle in @('atomic_cmpxchg(&audio->reader_open, 0, 1)',
        'PANGO_AUDIO_IOC_GET_INFO', 'PANGO_AUDIO_IOC_GET_STATS',
        'PANGO_AUDIO_CONTROL_POP', 'usleep_range(250, 500)',
        'miscdev.name = "pango-audio0"')) {
    if (!$driver.Contains($needle)) {
        throw "Linux audio ownership contract missing: $needle"
    }
}
if (!$dts.Contains('compatible = "pango,audio-capture-v2";') -or
    !$dts.Contains('reg = <0x1fe00600 0x00000100>;')) {
    throw 'Linux audio device-tree node is missing'
}
if (!$config.Contains('CONFIG_PANGO_AUDIO_CAPTURE=y') -or
    !$config.Contains('CONFIG_UNIX=y') -or
    !$integration.Contains('config PANGO_AUDIO_CAPTURE') -or
    !$integration.Contains('obj-$(CONFIG_PANGO_AUDIO_CAPTURE) += pango_audio.o')) {
    throw 'Linux audio kernel integration is incomplete'
}

function Convert-ToWslPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot convert repository path to WSL: $full"
    }
    return '/mnt/' + $Matches[1].ToLowerInvariant() + '/' +
        $Matches[2].Replace('\', '/')
}
$wslRoot = Convert-ToWslPath $root
$command = @"
set -eu
cc -std=c11 -Wall -Wextra -Werror -I'$wslRoot/linux/audio' \
  '$wslRoot/sim/test_pango_audio_uapi.c' -o /tmp/pango-audio-uapi
/tmp/pango-audio-uapi
cc -std=gnu11 -O2 -Wall -Wextra -Werror -I'$wslRoot/linux/audio' \
  '$wslRoot/sim/test_audio_capture.c' -o /tmp/pango-audio-capture-test
/tmp/pango-audio-capture-test
printf '%s\n' LINUX_AUDIO_DRIVER_TEST_PASS
"@.Replace("`r`n", "`n")
& wsl.exe -d $Distro -- bash -lc $command
if ($LASTEXITCODE -ne 0) {
    throw 'Linux audio host validation failed'
}
