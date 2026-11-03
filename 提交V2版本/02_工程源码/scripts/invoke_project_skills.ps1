param([Parameter(Mandatory=$true)][string[]]$Arguments)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$manager = Join-Path $root 'skills/manage.py'
if (!(Test-Path -LiteralPath $manager -PathType Leaf)) { throw 'Missing portable skills/manage.py' }
if ($env:FPGA_SKILLS_PYTHON) {
    & $env:FPGA_SKILLS_PYTHON $manager @Arguments
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python $manager @Arguments
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $manager @Arguments
} else {
    throw 'Python 3 is required for skills validation; set FPGA_SKILLS_PYTHON to its executable'
}
if ($LASTEXITCODE -ne 0) { throw "Skills command failed: $($Arguments[0])" }
