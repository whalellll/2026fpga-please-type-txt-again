param(
    [string]$PikafishSource,
    [string]$Pff1Path,
    [string]$PfsbPath,
    [string]$GoldenPath,
    [string]$VerifierPath,
    [string]$Distro = 'pikafish-verify'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$workspace = Split-Path -Parent $root
if (!$PikafishSource) {
    $PikafishSource = Join-Path $workspace 'xiangqi_oss\Pikafish'
}
if (!$Pff1Path) {
    $Pff1Path = Join-Path $root 'linux\boot\pikafish.pff'
}
if (!$PfsbPath) {
    $PfsbPath = Join-Path $root 'artifacts\pikafish-stageb-mac.bin'
}
if (!$GoldenPath) {
    $GoldenPath = Join-Path $root 'artifacts\pikafish-stageb-golden.bin'
}
if (!$VerifierPath) {
    $VerifierPath = Join-Path $root 'artifacts\pikafish-stageb-golden-test-x86_64'
}

$expectedCommit = '56be6f65c21c6a3c7f9b884a976fc85d31d03287'
$expectedModelHash = '3cd15292bf8c979884262f57fc723959fc0dea43b4d8d544f88db5ceb2479e24'
$testSource = Join-Path $root 'linux\pikafish\pikafish_stageb_golden_test.cpp'
$stageBRoot = Join-Path $root 'sw\pikafish_mlp_stage_b'
$referenceSource = Join-Path $stageBRoot 'pf_mlp_stage_b_ref.c'
$buildRoot = Join-Path $root 'build\pikafish-stageb-golden'

foreach ($path in @($testSource, $referenceSource, $Pff1Path, $PfsbPath)) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing Stage B golden acceptance input: $path"
    }
}
$sourceHeader = Join-Path $PikafishSource 'src\nnue\nnue_architecture.h'
$buildFromSource = Test-Path -LiteralPath $sourceHeader -PathType Leaf
if ($buildFromSource) {
    $actualCommit = (& git -C $PikafishSource rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $actualCommit -ne $expectedCommit) {
        throw "Pikafish source commit mismatch: expected $expectedCommit, got $actualCommit"
    }
    $modelPath = Join-Path $PikafishSource 'pikafish.nnue'
    if (!(Test-Path -LiteralPath $modelPath -PathType Leaf)) {
        throw "Missing official Pikafish model: $modelPath"
    }
    $actualModelHash = (Get-FileHash -LiteralPath $modelPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualModelHash -ne $expectedModelHash) {
        throw "Official model SHA-256 mismatch: expected $expectedModelHash, got $actualModelHash"
    }
} elseif (!(Test-Path -LiteralPath $VerifierPath -PathType Leaf)) {
    throw "Missing Pikafish source and delivered Stage B verifier: $VerifierPath"
}

function Convert-ToWslPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot convert path to WSL: $full"
    }
    return '/mnt/' + $Matches[1].ToLowerInvariant() + '/' + $Matches[2].Replace('\', '/')
}

New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
$wslTest = Convert-ToWslPath $testSource
$wslStageB = Convert-ToWslPath $stageBRoot
$wslReference = Convert-ToWslPath $referenceSource
$wslBuild = Convert-ToWslPath $buildRoot
$wslPff1 = Convert-ToWslPath $Pff1Path
$wslPfsb = Convert-ToWslPath $PfsbPath
$wslGolden = Convert-ToWslPath $GoldenPath
$wslVerifier = Convert-ToWslPath $VerifierPath

$compileCommand = "test -f '$wslVerifier'"
if ($buildFromSource) {
    $wslPikafish = Convert-ToWslPath $PikafishSource
    $wslVerifier = "$wslBuild/pikafish-stageb-golden-test"
    $compileCommand = @"
gcc -std=c11 -O2 -Wall -Wextra -Werror \
  -iquote '$wslStageB' -c '$wslReference' -o '$wslBuild/pf_mlp_stage_b_ref.o'
g++ -std=c++17 -O2 -Wall -Wextra -Werror -Wno-unused-but-set-variable \
  -pedantic -DIS_64BIT -DNO_PREFETCH \
  -I'$wslPikafish/src' -iquote '$wslStageB' \
  '$wslTest' '$wslBuild/pf_mlp_stage_b_ref.o' \
  -o '$wslVerifier'
"@.Replace("`r`n", "`n")
}

$command = @"
set -eu
$compileCommand
'$wslVerifier' \
  '$wslPff1' '$wslPfsb' '$expectedModelHash' '$wslGolden'
cp '$wslPfsb' '$wslBuild/pikafish-stageb-corrupt.bin'
printf '\000' | dd of='$wslBuild/pikafish-stageb-corrupt.bin' bs=1 seek=0 conv=notrunc status=none
if '$wslVerifier' \
     '$wslPff1' '$wslBuild/pikafish-stageb-corrupt.bin' '$expectedModelHash' \
     >'$wslBuild/negative.log' 2>&1; then
  echo 'corrupt PFSB unexpectedly passed' >&2
  exit 1
fi
grep -q 'PIKAFISH_STAGEB_GOLDEN_ACCEPT_FAIL reason=pfsb-header-contract' \
  '$wslBuild/negative.log'
echo 'PIKAFISH_STAGEB_GOLDEN_NEGATIVE_PASS reason=pfsb-header-contract'
"@.Replace("`r`n", "`n")

& wsl.exe -d $Distro -- bash -lc $command
if ($LASTEXITCODE -ne 0) {
    throw "Pikafish Stage B golden acceptance failed: $LASTEXITCODE"
}

$goldenBytes = (Get-Item -LiteralPath $GoldenPath).Length
Write-Output "PIKAFISH_STAGEB_GOLDEN_TEST_PASS commit=$expectedCommit model_sha256=$expectedModelHash golden_bytes=$goldenBytes"
