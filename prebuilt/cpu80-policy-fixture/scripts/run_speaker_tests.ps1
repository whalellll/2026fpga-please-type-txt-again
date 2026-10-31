param(
    [string]$IcarusBin = 'D:\LJL\WORK\iverilog\bin',
    [string]$ToolchainRoot = '',
    [switch]$SkipBootloaderBuild,
    [string]$HostGccPath = 'D:\LJL\WORK\msys64\mingw64\bin\gcc.exe'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$iverilog = Join-Path $IcarusBin 'iverilog.exe'
$vvp = Join-Path $IcarusBin 'vvp.exe'
if (!(Test-Path -LiteralPath $iverilog)) {
    throw "Icarus not found: $iverilog"
}

Push-Location $root
try {
    if (!$SkipBootloaderBuild) {
        & (Join-Path $PSScriptRoot 'build_bootloader.ps1') `
            -ToolchainRoot $ToolchainRoot
        if ($LASTEXITCODE -ne 0) {
            throw 'Speaker bootloader build failed'
        }
    }

    $speakerVvp = Join-Path $env:TEMP 'performance_soc_speaker.vvp'
    & $iverilog -g2012 -Wall -s tb_i2s_audio -o $speakerVvp `
        'rtl\audio\i2s_audio_duplex.v' 'sim\tb_i2s_audio.v'
    if ($LASTEXITCODE -ne 0) { throw 'Speaker I2S compile failed' }
    & $vvp $speakerVvp
    if ($LASTEXITCODE -ne 0) { throw 'Speaker I2S serialization failed' }

    $audioHeader = [IO.File]::ReadAllText(
        (Join-Path $root 'sw\bootloader\audio.h'))
    $audioSource = [IO.File]::ReadAllText(
        (Join-Path $root 'sw\bootloader\audio.c'))
    $mainSource = [IO.File]::ReadAllText(
        (Join-Path $root 'sw\bootloader\main.c'))
    foreach ($required in @(
        @($audioHeader, 'int cmd_debug_speaker(void)', 'speaker command declaration'),
        @($audioHeader, 'int cmd_debug_mic(void)', 'microphone command declaration'),
        @($audioSource, 'SONG.PCM', 'MicroSD song filename'),
        @($audioSource, 'AUDIO_PLAYBACK', 'audio FIFO writes'),
        @($mainSource, 'streq(av[0],"debug")', 'bootloader dispatch'),
        @($mainSource, 'streq(av[1],"speaker")', 'speaker dispatch'),
        @($mainSource, 'streq(av[1],"mic")', 'microphone dispatch'))) {
        if (!$required[0].Contains($required[1])) {
            throw "SPEAKER_PLAYBACK_PATH_MISSING: $($required[2])"
        }
    }

    $bootloaderMap = Join-Path $root 'artifacts\bootloader.map'
    $bootloaderBin = Join-Path $root 'artifacts\bootloader.bin'
    if (!(Test-Path -LiteralPath $bootloaderMap -PathType Leaf)) {
        throw "Missing bootloader map: $bootloaderMap"
    }
    if (!(Select-String -LiteralPath $bootloaderMap `
            -SimpleMatch 'cmd_debug_speaker' -Quiet)) {
        throw 'SPEAKER_BOOTLOADER_PATH_MISSING: cmd_debug_speaker is absent from bootloader.map'
    }
    if (!(Test-Path -LiteralPath $bootloaderBin -PathType Leaf)) {
        throw "Missing bootloader binary: $bootloaderBin"
    }
    $bootloaderText = [Text.Encoding]::ASCII.GetString(
        [IO.File]::ReadAllBytes($bootloaderBin))
    $release = ([IO.File]::ReadAllText((Join-Path $root 'VERSION'))).Trim()
    foreach ($marker in @("SoC V$release bootloader", 'debug speaker', 'debug mic', 'SONG.PCM')) {
        if (!$bootloaderText.Contains($marker)) {
            throw "SPEAKER_BOOTLOADER_PATH_MISSING: '$marker' is absent from bootloader.bin"
        }
    }

    $songPath = Join-Path $root 'artifacts\SONG.PCM'
    $expectedSongBytes = 6162968L
    $expectedSongHash = `
        '863f5f298c2dde0cfda90fff23f6af748e780cc8967c310727591f648bed88dd'
    if (!(Test-Path -LiteralPath $songPath -PathType Leaf)) {
        throw "Missing speaker media: $songPath; run scripts\make_song_pcm.ps1 first"
    }
    $actualSongBytes = (Get-Item -LiteralPath $songPath).Length
    if ($actualSongBytes -ne $expectedSongBytes) {
        throw "SONG.PCM length mismatch: expected $expectedSongBytes, got $actualSongBytes"
    }
    $actualSongHash = (Get-FileHash -LiteralPath $songPath `
        -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualSongHash -ne $expectedSongHash) {
        throw "SONG.PCM SHA256 mismatch: expected $expectedSongHash, got $actualSongHash"
    }
    & (Join-Path $PSScriptRoot 'run_bootloader_io_tests.ps1') -HostGccPath $HostGccPath
    if ($LASTEXITCODE -ne 0) { throw 'Bootloader console/audio host regression failed' }
    Write-Output 'SOC_SPEAKER_COMMAND_PATH_PASS'
} finally {
    Pop-Location
}
