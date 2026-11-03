param(
    [string]$Pff1Path,
    [string]$PfsbPath,
    [string]$GoldenPath,
    [string]$VerifierPath,
    [string]$Distro = 'pikafish-verify'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$Pff1Path) {
    $Pff1Path = Join-Path $root 'linux\boot\pikafish.pff'
}
if (!$PfsbPath) {
    $PfsbPath = Join-Path $root 'artifacts\pikafish-stageb-mac.bin'
}
if (!$GoldenPath) {
    $GoldenPath = Join-Path $root 'artifacts\pikafish-stageb-position-golden.bin'
}
if (!$VerifierPath) {
    $VerifierPath = Join-Path $root 'artifacts\pikafish-stageb-position-view-x86_64'
}

foreach ($path in @($Pff1Path, $PfsbPath, $GoldenPath, $VerifierPath)) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing Stage B phase-2 acceptance input: $path"
    }
}
if ((Get-Item -LiteralPath $GoldenPath).Length -ne 38176) {
    throw 'Stage B phase-2 golden vector has the wrong size'
}

function Convert-ToWslPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot convert path to WSL: $full"
    }
    return '/mnt/' + $Matches[1].ToLowerInvariant() + '/' +
        $Matches[2].Replace('\', '/')
}

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) `
    ('pikafish-stageb-phase2-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
try {
    $corruptGolden = Join-Path $tempRoot 'corrupt.bin'
    $positiveLog = Join-Path $tempRoot 'positive.log'
    $negativeLog = Join-Path $tempRoot 'negative.log'
    Copy-Item -LiteralPath $GoldenPath -Destination $corruptGolden -Force
    $stream = [IO.File]::Open($corruptGolden, [IO.FileMode]::Open,
        [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    try {
        $stream.Position = 40
        $value = $stream.ReadByte()
        $stream.Position = 40
        $stream.WriteByte($value -bxor 1)
    } finally {
        $stream.Dispose()
    }

    $verifier = Convert-ToWslPath $VerifierPath
    $pff1 = Convert-ToWslPath $Pff1Path
    $pfsb = Convert-ToWslPath $PfsbPath
    $golden = Convert-ToWslPath $GoldenPath
    $corrupt = Convert-ToWslPath $corruptGolden
    $positive = Convert-ToWslPath $positiveLog
    $negative = Convert-ToWslPath $negativeLog
    $command = @"
set -eu
'$verifier' --verify '$pff1' '$pff1' '$pfsb' '$golden' | tee '$positive'
grep -q '^PIKAFISH_STAGEB_PHASE2_HOST_PASS buckets=16 cases=32 features=32768 fc0_lanes=1024 ' '$positive'
if '$verifier' --verify '$pff1' '$pff1' '$pfsb' '$corrupt' >'$negative' 2>&1; then
  echo 'corrupt phase-2 golden unexpectedly passed' >&2
  exit 1
fi
grep -q '^PIKAFISH_STAGEB_PHASE2_FAIL reason=golden-contract' '$negative'
echo 'PIKAFISH_STAGEB_PHASE2_NEGATIVE_PASS reason=golden-contract'
"@.Replace("`r`n", "`n")
    & wsl.exe -d $Distro -- bash -lc $command
    if ($LASTEXITCODE -ne 0) {
        throw "Pikafish Stage B phase-2 acceptance failed: $LASTEXITCODE"
    }
} finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}

$goldenHash = (Get-FileHash -LiteralPath $GoldenPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Output "PIKAFISH_STAGEB_PHASE2_TEST_PASS golden_sha256=$goldenHash"
