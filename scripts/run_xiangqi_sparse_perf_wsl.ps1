param(
    [string]$Distro = 'chiplab_sim',
    [string]$IcarusBin = 'D:\LJL\WORK\iverilog\bin'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$logPath = Join-Path $root 'artifacts\xiangqi_sparse_perf_sim.log'
$iverilog = Join-Path $IcarusBin 'iverilog.exe'
$vvp = Join-Path $IcarusBin 'vvp.exe'

if ((Test-Path -LiteralPath $iverilog -PathType Leaf) -and
    (Test-Path -LiteralPath $vvp -PathType Leaf)) {
    $simulation = Join-Path $env:TEMP 'soc_xiangqi_sparse_perf.vvp'
    Push-Location $root
    try {
        & $iverilog -g2012 -s tb_xiangqi_sparse_eval_perf `
            -o $simulation `
            'rtl/mac_accel/xiangqi_sparse_eval.v' `
            'sim/tb_xiangqi_sparse_eval_perf.sv'
        if ($LASTEXITCODE -ne 0) {
            throw "Native Xiangqi sparse performance compile failed: $LASTEXITCODE"
        }
        & $vvp $simulation | Tee-Object -FilePath $logPath
        $exitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
} else {
    $drive = $root.Substring(0, 1).ToLowerInvariant()
    $tail = $root.Substring(2).Replace('\', '/')
    $wslRoot = "/mnt/$drive$tail"
    $command = @"
set -e
cd '$wslRoot'
iverilog -g2012 -s tb_xiangqi_sparse_eval_perf \
  -o /tmp/tb_xiangqi_sparse_eval_perf.vvp \
  rtl/mac_accel/xiangqi_sparse_eval.v \
  sim/tb_xiangqi_sparse_eval_perf.sv
vvp /tmp/tb_xiangqi_sparse_eval_perf.vvp
"@

    $command = $command.Replace("`r`n", "`n")
    & wsl.exe -d $Distro -- bash -lc $command |
        Tee-Object -FilePath $logPath
    $exitCode = $LASTEXITCODE
}
if ($exitCode -ne 0) {
    throw "Xiangqi sparse performance simulation failed: $exitCode"
}
if (-not ([IO.File]::ReadAllText($logPath).Contains(
        'XIANGQI_SPARSE_PERF_PASS'))) {
    throw "Performance simulation did not report PASS: $logPath"
}
Write-Output "Performance log: $logPath"
