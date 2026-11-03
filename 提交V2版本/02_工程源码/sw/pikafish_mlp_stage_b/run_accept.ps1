param(
    [string]$CC = "clang"
)

$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$outDir = Join-Path $here 'build'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$exe = Join-Path $outDir 'pf_mlp_stage_b_accept.exe'
$sources = @(
    (Join-Path $here 'pf_mlp_stage_b_ref.c'),
    (Join-Path $here 'pf_mlp_stage_b_cases.c'),
    (Join-Path $here 'pf_mlp_stage_b_accept.c')
)

& $CC -std=c99 -Wall -Wextra -Werror -O2 "-I$here" -o $exe @sources
if ($LASTEXITCODE -ne 0) {
    throw "compile failed"
}

& $exe
if ($LASTEXITCODE -ne 0) {
    throw "acceptance failed"
}

Write-Output "PF_MLP_STAGE_B_ACCEPT_BUILT $exe"
