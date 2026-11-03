param(
    [string]$RepoRoot,
    [string]$Distro = 'pikafish-verify',
    [int]$TimeoutSeconds = 300
)

$ErrorActionPreference = 'Stop'
if (!$RepoRoot) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}
$RepoRoot = [IO.Path]::GetFullPath($RepoRoot)
$enginePath = Join-Path $RepoRoot 'artifacts\pikafish-rv32'
$viewEnginePath = Join-Path $RepoRoot 'artifacts\pikafish-view-reference-x86_64'
$sourceModelPath = Join-Path $RepoRoot 'artifacts\pikafish.nnue.flat'
$externalModelPath = Join-Path $RepoRoot 'linux\boot\pikafish.pff'
$testRoot = Join-Path $RepoRoot 'build\pikafish-pff1-load-test'
$corruptModelPath = Join-Path $testRoot 'pikafish-corrupt.pff'
$positiveLogPath = Join-Path $testRoot 'positive.log'
$negativeLogPath = Join-Path $testRoot 'negative.log'
$viewPositiveLogPath = Join-Path $testRoot 'view-positive.log'
$viewNegativeLogPath = Join-Path $testRoot 'view-negative.log'
$expectedHash = 'de0906fa1bea82248523eb39fc6b2956613b02ae675ccf67eef3f392de939260'
$expectedBytes = 68122688

foreach ($path in @($externalModelPath, $enginePath, $viewEnginePath, $sourceModelPath)) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing PFF1 load regression input: $path"
    }
}

function Convert-ToWslPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot convert path to WSL: $full"
    }
    return '/mnt/' + $Matches[1].ToLowerInvariant() + '/' +
        $Matches[2].Replace('\', '/')
}

New-Item -ItemType Directory -Force -Path $testRoot | Out-Null
$externalModel = Get-Item -LiteralPath $externalModelPath
$entrySize = $externalModel.Length
$actualHash = (Get-FileHash -LiteralPath $externalModelPath -Algorithm SHA256).Hash.ToLowerInvariant()
$sourceHash = (Get-FileHash -LiteralPath $sourceModelPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($entrySize -ne $expectedBytes -or $actualHash -ne $expectedHash -or
    $sourceHash -ne $expectedHash) {
    throw "External/source PFF1 mismatch: bytes=$entrySize external=$actualHash source=$sourceHash"
}
$header = [IO.File]::ReadAllBytes($externalModelPath)[0..3]
if ([Text.Encoding]::ASCII.GetString($header) -ne 'PFF1') {
    throw 'External PFF1 model has an invalid header'
}

Copy-Item -LiteralPath $externalModelPath -Destination $corruptModelPath -Force
$corrupt = [IO.File]::Open($corruptModelPath, [IO.FileMode]::Open,
    [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
try {
    $null = $corrupt.Seek(-1, [IO.SeekOrigin]::End)
    $value = $corrupt.ReadByte()
    $null = $corrupt.Seek(-1, [IO.SeekOrigin]::End)
    $corrupt.WriteByte($value -bxor 0xff)
} finally {
    $corrupt.Dispose()
}

$wslEngine = Convert-ToWslPath $enginePath
$wslViewEngine = Convert-ToWslPath $viewEnginePath
$wslModel = Convert-ToWslPath $externalModelPath
$wslCorruptModel = Convert-ToWslPath $corruptModelPath
$wslPositiveLog = Convert-ToWslPath $positiveLogPath
$wslNegativeLog = Convert-ToWslPath $negativeLogPath
$wslViewPositiveLog = Convert-ToWslPath $viewPositiveLogPath
$wslViewNegativeLog = Convert-ToWslPath $viewNegativeLogPath
$positiveCommand = @"
set -eu
printf 'uci\nsetoption name EvalFile value $wslModel\nisready\nquit\n' |
  timeout ${TimeoutSeconds}s qemu-riscv32 '$wslEngine' >'$wslPositiveLog' 2>&1
grep -q 'PIKAFISH_PFF1_READY bytes=68122688' '$wslPositiveLog'
grep -q '^readyok$' '$wslPositiveLog'
grep -q 'PIKAFISH_PFF1_SECTION_READY name=FTBI' '$wslPositiveLog'
grep -q 'PIKAFISH_PFF1_SECTION_READY name=FTTW' '$wslPositiveLog'
grep -q 'PIKAFISH_PFF1_SECTION_READY name=FTTP' '$wslPositiveLog'
grep -q 'PIKAFISH_PFF1_SECTION_READY name=FTPW' '$wslPositiveLog'
grep -q 'PIKAFISH_PFF1_SECTION_READY name=FTPP' '$wslPositiveLog'
grep -q 'PIKAFISH_PFF1_SECTION_READY name=MLPS' '$wslPositiveLog'
"@.Replace("`r`n", "`n")
& wsl.exe -d $Distro -- bash -lc $positiveCommand
if ($LASTEXITCODE -ne 0) {
    throw "Positive PFF1 load regression failed; see $positiveLogPath"
}

$negativeCommand = @"
set +e
printf 'uci\nsetoption name EvalFile value $wslCorruptModel\nisready\nquit\n' |
  timeout ${TimeoutSeconds}s qemu-riscv32 '$wslEngine' >'$wslNegativeLog' 2>&1
grep -q 'PIKAFISH_PFF1_LOAD_FAILED stage=MLPS reason=crc' '$wslNegativeLog'
grep -q 'PIKAFISH_PFF1_FAILED path=' '$wslNegativeLog'
"@.Replace("`r`n", "`n")
& wsl.exe -d $Distro -- bash -lc $negativeCommand
if ($LASTEXITCODE -ne 0) {
    throw "Negative PFF1 load regression failed; see $negativeLogPath"
}

$viewCommand = @"
set -eu
printf 'uci\nsetoption name EvalFile value $wslModel\nisready\nquit\n' |
  timeout ${TimeoutSeconds}s '$wslViewEngine' >'$wslViewPositiveLog' 2>&1
grep -q 'PIKAFISH_PFF1_VIEW_READY direct_bytes=67548352 mlp_direct_bytes=563264' '$wslViewPositiveLog'
grep -q 'PIKAFISH_PFF1_MLPS_STACK_READY stack=15 bytes=563264' '$wslViewPositiveLog'
grep -q 'PIKAFISH_PFF1_STAGE stage=view-bind-ready' '$wslViewPositiveLog'
grep -q 'PIKAFISH_PFF1_READY bytes=68122688' '$wslViewPositiveLog'
grep -q '^readyok$' '$wslViewPositiveLog'
set +e
printf 'uci\nsetoption name EvalFile value $wslCorruptModel\nisready\nquit\n' |
  timeout ${TimeoutSeconds}s '$wslViewEngine' >'$wslViewNegativeLog' 2>&1
grep -q 'PIKAFISH_PFF1_LOAD_FAILED stage=MLPS reason=crc' '$wslViewNegativeLog'
"@.Replace("`r`n", "`n")
& wsl.exe -d $Distro -- bash -lc $viewCommand
if ($LASTEXITCODE -ne 0) {
    throw "Direct-view PFF1 regression failed; see $viewPositiveLogPath and $viewNegativeLogPath"
}

Write-Output ("PIKAFISH_PFF1_LOAD_REGRESSION_PASS bytes={0} sha256={1}" -f `
    $entrySize, $actualHash)
Write-Output "PIKAFISH_PFF1_LOAD_NEGATIVE_PASS stage=MLPS reason=crc"
Write-Output "PIKAFISH_PFF1_DIRECT_VIEW_PASS direct_bytes=67548352 mlp_direct_bytes=563264"
