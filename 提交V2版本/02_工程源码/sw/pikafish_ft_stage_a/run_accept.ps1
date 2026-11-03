param(
    [string]$CC = "clang"
)

$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$outDir = Join-Path $here 'build'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$exe = Join-Path $outDir 'pf_ft_stage_a_accept.exe'
$sources = @(
    (Join-Path $here 'pf_ft_stage_a_ref.c'),
    (Join-Path $here 'pf_ft_stage_a_cases.c'),
    (Join-Path $here 'pf_ft_stage_a_accept.c')
)

& $CC -std=c99 -Wall -Wextra -Werror -O2 "-I$here" -o $exe @sources
if ($LASTEXITCODE -ne 0) {
    throw "compile failed"
}

& $exe
if ($LASTEXITCODE -ne 0) {
    throw "acceptance failed"
}

Write-Output "PF_FT_STAGE_A_ACCEPT_BUILT $exe"
