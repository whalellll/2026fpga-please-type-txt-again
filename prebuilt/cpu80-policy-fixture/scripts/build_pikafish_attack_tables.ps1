param(
    [string]$PikafishSource,
    [string]$OutputPath,
    [string]$Distro = 'chiplab_sim'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$workspace = Split-Path -Parent $root
$expectedCommit = '56be6f65c21c6a3c7f9b884a976fc85d31d03287'

if (!$PikafishSource) {
    $PikafishSource = Join-Path $workspace 'xiangqi_oss\Pikafish'
}
if (!$OutputPath) {
    $OutputPath = Join-Path $root 'linux\boot\pikafish.atk'
}

function Convert-ToWslPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot convert path to WSL: $full"
    }
    return '/mnt/' + $Matches[1].ToLowerInvariant() + '/' +
        $Matches[2].Replace('\', '/')
}

$actualCommit = (& git -C $PikafishSource rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $actualCommit -ne $expectedCommit) {
    throw "Pikafish source commit mismatch: expected $expectedCommit, got $actualCommit"
}
& git -C $PikafishSource diff --quiet $expectedCommit -- src
if ($LASTEXITCODE -ne 0) {
    throw 'Pikafish src has tracked changes; refusing a non-reproducible attack-table build'
}

$generator = Join-Path $root 'linux\pikafish\generate_attack_tables.cpp'
$verifier = Join-Path $root 'linux\pikafish\verify_attack_tables.py'
$buildRoot = Join-Path $root 'build\pikafish-attack-tables'
$generatorExe = Join-Path $buildRoot 'generate-attack-tables'
$temporaryOutput = Join-Path $buildRoot 'pikafish.atk.tmp'
$outputFull = [IO.Path]::GetFullPath($OutputPath)

New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
New-Item -ItemType Directory -Path (Split-Path -Parent $outputFull) -Force | Out-Null
if (Test-Path -LiteralPath $temporaryOutput) {
    Remove-Item -LiteralPath $temporaryOutput -Force
}

$wslSource = Convert-ToWslPath (Join-Path $PikafishSource 'src')
$wslGenerator = Convert-ToWslPath $generator
$wslGeneratorExe = Convert-ToWslPath $generatorExe
$wslTemporaryOutput = Convert-ToWslPath $temporaryOutput
$wslVerifier = Convert-ToWslPath $verifier
$command = @"
set -e
g++ -std=c++17 -O3 -DNDEBUG -DIS_64BIT -DNO_PREFETCH \
    -Wall -Wextra -Werror \
    -I '$wslSource' '$wslGenerator' -o '$wslGeneratorExe'
'$wslGeneratorExe' '$wslTemporaryOutput'
python3 '$wslVerifier' '$wslTemporaryOutput'
"@.Replace("`r`n", "`n")

& wsl.exe -d $Distro -- bash -lc $command
if ($LASTEXITCODE -ne 0) {
    throw 'Pikafish attack-table generation failed'
}

$expectedBytes = 0x2100040L
$actualBytes = (Get-Item -LiteralPath $temporaryOutput).Length
if ($actualBytes -ne $expectedBytes) {
    throw "Unexpected attack-table size: expected $expectedBytes, got $actualBytes"
}
Move-Item -LiteralPath $temporaryOutput -Destination $outputFull -Force

$hash = (Get-FileHash -LiteralPath $outputFull -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Output "PIKAFISH_ATTACK_TABLE_BUILD_PASS commit=$expectedCommit"
Write-Output "PIKAFISH_ATTACK_TABLE_SHA256=$hash"
Get-Item -LiteralPath $outputFull | Select-Object FullName, Length, LastWriteTime
