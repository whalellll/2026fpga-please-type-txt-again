param(
    [Parameter(Mandatory=$true)][string]$ToolchainBin,
    [Parameter(Mandatory=$true)][string]$EvidenceDirectory,
    [string]$IcarusBin = 'D:\LJL\WORK\iverilog\bin',
    [string]$MsysRoot = 'D:\LJL\WORK\msys64',
    [string]$PythonPath = 'D:\LJL\WORK\Anaconda3\python.exe',
    [string]$HostGccPath = 'D:\LJL\WORK\msys64\mingw64\bin\gcc.exe',
    [string]$PdsRoot = '',
    [string]$VendorModels = '',
    [ValidateRange(60,14400)][int]$TimeoutSeconds = 7200
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent)).TrimEnd('\')
. (Join-Path $PSScriptRoot 'build_snapshot.ps1')
$out = [IO.Path]::GetFullPath($EvidenceDirectory).TrimEnd('\')
$allowed = Join-Path $root 'docs\validation'
if (!$out.StartsWith($allowed + '\', [StringComparison]::OrdinalIgnoreCase) -or
    (Test-Path -LiteralPath $out)) {
    throw 'Choose a new evidence directory below this repository docs/validation'
}
$cursor = Split-Path $out -Parent
while ($cursor -and $cursor.Length -ge $root.Length) {
    if ((Test-Path -LiteralPath $cursor) -and
        ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Regression evidence may not traverse a filesystem link'
    }
    $cursor = Split-Path $cursor -Parent
}
# Complete the version/header generation before freezing this identity.
. (Join-Path $PSScriptRoot 'release_version.ps1')
Assert-SocReleaseHeader $root
& (Join-Path $PSScriptRoot 'sync_cpu.ps1') -Check
function Get-ReleaseRegressionTestPaths([string]$Root) {
    # Keep in sync with regression_test_paths in verify_board_release.py.
    $extensions = @('.ps1','.py','.cs','.c','.h','.tcl','.sh','.ld','.s','.sv','.v','.vh','.hex','.json')
    foreach ($directory in @('scripts','sim')) {
        Get-ChildItem -LiteralPath (Join-Path $Root $directory) -Recurse -File -Force | Where-Object {
            $_.Extension.ToLowerInvariant() -in $extensions -and $_.FullName -notmatch '[\\/]__pycache__[\\/]' -and
            !($directory -eq 'scripts' -and $_.DirectoryName -eq (Join-Path $Root 'scripts') -and $_.Name -match '^pds_.*_run\.tcl$') -and
            $_.FullName -ine (Join-Path $Root 'sim/linux_capability.hex')
        } | ForEach-Object { $_.FullName.Substring($Root.Length + 1).Replace('\','/') }
    }
}
# Source/configuration/recipe inputs must match the eventual FPGA snapshot;
# rebuildable binary outputs are produced by the regression itself.
$sourcePaths = @(Get-FpgaInputPaths $root | Where-Object { $_ -notlike 'artifacts/*' })
$sourceHashes = Get-FpgaHashMap $root $sourcePaths
$testPaths = @(Get-ReleaseRegressionTestPaths $root)
$testHashes = Get-FpgaHashMap $root @($testPaths | Sort-Object -Unique)
New-Item -ItemType Directory -Path $out | Out-Null
$stdout = Join-Path $out 'regression.stdout.txt'
$stderr = Join-Path $out 'regression.stderr.txt'
$relativeOut = $out.Substring($root.Length + 1).Replace('\','/')
$record = [ordered]@{
    schema_version=1; status='INCOMPLETE'; exit_code=$null; marker=$null
    started_utc=[DateTime]::UtcNow.ToString('o'); completed_utc=$null
    owner_pid=$PID; timeout_seconds=$TimeoutSeconds
    cpu_rtl_sha256=$sourceHashes['rtl/cpu/CoreTop.sv']
    source_files_sha256=$sourceHashes; test_files_sha256=$testHashes
    transcript=$null; stderr=$null
}
Write-Output "FULL_RTL_REGRESSION owner_pid=$PID timeout_seconds=$TimeoutSeconds; stop: Stop-Process -Id $PID"
if (-not ('CpuSimulation.BoundedProcess' -as [type])) {
    Add-Type -Path (Join-Path $PSScriptRoot 'bounded_process.cs')
}
foreach ($value in @($ToolchainBin,$IcarusBin,$MsysRoot,$PythonPath,$HostGccPath,$PSScriptRoot,$PdsRoot,$VendorModels)) {
    if ($value.Contains('"')) { throw 'Tool paths cannot contain quotes' }
}
$arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $PSScriptRoot 'run_all_tests.ps1') +
    '" -ToolchainBin "' + $ToolchainBin + '" -IcarusBin "' + $IcarusBin +
    '" -MsysRoot "' + $MsysRoot + '" -PythonPath "' + $PythonPath + '" -HostGccPath "' + $HostGccPath + '"'
if ($PdsRoot) { $arguments += ' -PdsRoot "' + $PdsRoot + '"' }
if ($VendorModels) { $arguments += ' -VendorModels "' + $VendorModels + '"' }
$record.command = $arguments
[IO.File]::WriteAllText((Join-Path $out 'regression.json'),($record | ConvertTo-Json -Depth 8) + "`n",[Text.UTF8Encoding]::new($false))
try {
    $code = [CpuSimulation.BoundedProcess]::Run(
        (Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'),
        $arguments,$root,$stdout,$stderr,$TimeoutSeconds)
    $record.exit_code = $code
    $afterPaths = @(Get-FpgaInputPaths $root | Where-Object { $_ -notlike 'artifacts/*' })
    Assert-FpgaMap $sourceHashes (Get-FpgaHashMap $root $afterPaths) 'Regression source/configuration changed during execution'
    $afterTestPaths = @(Get-ReleaseRegressionTestPaths $root | Sort-Object -Unique)
    Assert-FpgaMap $testHashes (Get-FpgaHashMap $root $afterTestPaths) 'Regression implementation changed during execution'
    $successLines = [regex]::Matches([IO.File]::ReadAllText($stdout), '(?m)^SOC_ALL_TESTS_PASS[ \t]*\r?$')
    if ($code -ne 0 -or $successLines.Count -ne 1) {
        throw "Complete RTL regression failed exit=$code; see $out"
    }
    $record.status='PASS'; $record.marker='SOC_ALL_TESTS_PASS'
} catch {
    $record.status='FAIL'; $record.error=$_.Exception.Message
    throw
} finally {
    $record.completed_utc=[DateTime]::UtcNow.ToString('o')
    if (Test-Path -LiteralPath $stdout) {
        $record.transcript=[ordered]@{path="$relativeOut/regression.stdout.txt";sha256=(Get-FileHash -LiteralPath $stdout -Algorithm SHA256).Hash.ToLowerInvariant()}
    }
    if (Test-Path -LiteralPath $stderr) {
        $record.stderr=[ordered]@{path="$relativeOut/regression.stderr.txt";sha256=(Get-FileHash -LiteralPath $stderr -Algorithm SHA256).Hash.ToLowerInvariant()}
    }
    [IO.File]::WriteAllText((Join-Path $out 'regression.json'),($record | ConvertTo-Json -Depth 8) + "`n",[Text.UTF8Encoding]::new($false))
}
Write-Output "RELEASE_RTL_REGRESSION_PASS evidence=$out"
