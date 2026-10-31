param(
    [string]$Config = (Join-Path $PSScriptRoot '../toolchain.local.json'),
    [ValidateRange(1,86400)][int]$TimeoutSeconds = 18000
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$cfg = Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json
if (!$cfg.NativeBash -or !$cfg.NativePath) { throw 'A native Bash and PATH are required for bounded CoreMark.' }
if (!('CpuSimulation.BoundedProcess' -as [type])) {
    Add-Type -Path (Join-Path $PSScriptRoot 'bounded_process.cs')
}
$savedPath = $env:PATH
$savedVerilator = $env:VERILATOR
$logRoot = Join-Path $root 'work/logs/coremark-release'
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$runName = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,6)
$stdout = Join-Path $logRoot ($runName + '.stdout.log')
$stderr = Join-Path $logRoot ($runName + '.stderr.log')
Write-Output "COREMARK_RELEASE_START timeout=${TimeoutSeconds}s owner_powershell_pid=$PID stdout=$stdout stderr=$stderr"
Write-Output 'Ending this PowerShell process closes its Windows job and stops all four simulations. Ctrl+C may wait while the native call blocks.'
try {
    $env:PATH = $cfg.NativePath + ';' + $savedPath
    if ($cfg.Verilator) { $env:VERILATOR = $cfg.Verilator }
    $script = Join-Path $PSScriptRoot 'run_coremark_release.sh'
    $arguments = '--noprofile --norc "' + $script.Replace('"', '\"') + '"'
    $exitCode = [CpuSimulation.BoundedProcess]::Run($cfg.NativeBash, $arguments, $root,
        $stdout, $stderr, $TimeoutSeconds)
    if ($exitCode -ne 0) { throw "CoreMark release group failed ($exitCode): $stdout ; $stderr" }
    Get-Content -LiteralPath $stdout | Select-Object -Last 12
    Write-Output "COREMARK_RELEASE_PASS stdout=$stdout stderr=$stderr"
} finally {
    $env:PATH = $savedPath
    $env:VERILATOR = $savedVerilator
}
