$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Out = Join-Path $Root "out"
$Nnue = "g:\fpga\xiangqi_oss\Pikafish\pikafish.nnue"
$Flat = Join-Path $Root "..\..\artifacts\pikafish.nnue.flat"

Write-Host "== decode official nnue =="
python (Join-Path $Root "decode_nnue.py") --nnue $Nnue --outdir $Out --stacks 16 `
  --flat-output $Flat
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "== verify no-decompression PFF1 image =="
python (Join-Path $Root "verify_flat_nnue.py") $Flat `
  --raw (Join-Path $Out "pikafish.nnue.raw") --components $Out
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "== host accept (Stage B bind + PFA1 headers) =="
$Cc = if (Get-Command gcc -ErrorAction SilentlyContinue) { "gcc" }
      elseif (Get-Command clang -ErrorAction SilentlyContinue) { "clang" }
      else { $null }
if (-not $Cc) {
    Write-Host "WARN no gcc/clang; skip C accept (decode already verified hashes)"
    exit 0
}

$StageB = Join-Path $Root "..\pikafish_mlp_stage_b"
$Bin = Join-Path $Root "build\pf_official_accept.exe"
New-Item -ItemType Directory -Force -Path (Join-Path $Root "build") | Out-Null

& $Cc -O2 -std=c11 `
  (Join-Path $Root "pf_official_accept.c") `
  (Join-Path $StageB "pf_mlp_stage_b_ref.c") `
  -I$StageB -I$Root `
  -o $Bin
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Bin $Out
exit $LASTEXITCODE
