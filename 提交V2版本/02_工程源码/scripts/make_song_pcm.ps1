param(
    [string]$InputMp3 = (Join-Path ([Environment]::GetFolderPath('Desktop')) 'M500002qRExR0tiDCz.mp3'),
    [string]$OutputPcm = '',
    [string]$FfmpegPath = 'D:\LJL\WORK\FormatFactory\ffmpeg.exe',
    [double]$ExpectedSeconds = 192.63,
    [double]$DurationToleranceSeconds = 0.25,
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($OutputPcm)) {
    $OutputPcm = Join-Path $root 'artifacts\SONG.PCM'
}
$outputFull = [IO.Path]::GetFullPath($OutputPcm)
$outputDirectory = Split-Path -Parent $outputFull
$temporary = "$outputFull.tmp"

if ($ValidateOnly) {
    if (!(Test-Path -LiteralPath $outputFull -PathType Leaf) -or
        (Get-Item -LiteralPath $outputFull).Length -ne 6162968 -or
        (Get-FileHash -LiteralPath $outputFull -Algorithm SHA256).Hash.ToLowerInvariant() -ne
        '863f5f298c2dde0cfda90fff23f6af748e780cc8967c310727591f648bed88dd') {
        throw 'Bundled SONG.PCM validation failed'
    }
    Write-Output "SONG_PCM_FIXED_INPUT_PASS $outputFull"
    return
}

if (!(Test-Path -LiteralPath $FfmpegPath -PathType Leaf)) {
    throw "Missing ffmpeg: $FfmpegPath"
}
if (!(Test-Path -LiteralPath $InputMp3 -PathType Leaf)) {
    throw "Missing source MP3: $InputMp3"
}
if ($ExpectedSeconds -le 0.0 -or $DurationToleranceSeconds -lt 0.0) {
    throw 'Invalid duration expectation'
}

New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
if (Test-Path -LiteralPath $temporary) {
    Remove-Item -LiteralPath $temporary -Force
}
try {
    & $FfmpegPath -hide_banner -loglevel error -y -i $InputMp3 `
        -vn -sn -dn -map_metadata -1 -f s16le -acodec pcm_s16le `
        -ar 16000 -ac 1 $temporary
    if ($LASTEXITCODE -ne 0) { throw "ffmpeg failed: $LASTEXITCODE" }
    $bytes = (Get-Item -LiteralPath $temporary).Length
    if ($bytes -le 0 -or ($bytes % 2) -ne 0 -or $bytes -gt 8MB) {
        throw "Invalid SONG.PCM byte length: $bytes"
    }
    $frames = [long]($bytes / 2)
    $seconds = [double]$frames / 16000.0
    if ([Math]::Abs($seconds - $ExpectedSeconds) -gt $DurationToleranceSeconds) {
        throw ('Unexpected duration: {0:F6} s' -f $seconds)
    }
    Move-Item -LiteralPath $temporary -Destination $outputFull -Force
    $hash = (Get-FileHash -LiteralPath $outputFull -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Output "SONG_PCM_READY path=$outputFull bytes=$bytes frames=$frames seconds=$($seconds.ToString('F6')) sha256=$hash"
} finally {
    if (Test-Path -LiteralPath $temporary) {
        Remove-Item -LiteralPath $temporary -Force
    }
}
