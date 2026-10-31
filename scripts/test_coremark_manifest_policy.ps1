param([string]$PythonPath = 'D:\LJL\WORK\msys64\mingw64\bin\python3.exe')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'coremark_release_checks.ps1')

$manifestPath = Join-Path $root 'artifacts/bootloader.build.json'
$binaryPath = Join-Path $root 'artifacts/bootloader.bin'
$romPath = Join-Path $root 'artifacts/bootrom.hex'
foreach ($path in @($PythonPath, $manifestPath, $binaryPath, $romPath)) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing fixture input: $path" }
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
Assert-CoremarkIterationPolicy -BuildManifest $manifest -ExpectedIterations 0 -Production
Assert-CoremarkIterationPolicy -BuildManifest ([pscustomobject]@{ coremark_iterations = 10 }) -ExpectedIterations 10

$scratchRoot = [IO.Path]::GetFullPath((Join-Path $root 'artifacts/selftest')).TrimEnd('\')
$temporary = Join-Path $scratchRoot ('coremark_manifest_policy_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary -Force | Out-Null
$utf8 = [Text.UTF8Encoding]::new($false)
try {
    $clock = Get-Content -LiteralPath (Join-Path $root 'config/clocks.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $cpuHalf = [long][decimal]::Truncate(([decimal]500000000000000 +
        [decimal][math]::Floor($clock.cpu_hz / 2)) / [decimal]$clock.cpu_hz)
    $sysHalf = [long][decimal]::Truncate(([decimal]500000000000000 +
        [decimal][math]::Floor($clock.sys_hz / 2)) / [decimal]$clock.sys_hz)
    $logPath = Join-Path $temporary 'synthetic.log'
    [IO.File]::WriteAllText($logPath,
        "SIM_CLOCK_QUANTIZATION cpu_half_fs=$cpuHalf sys_half_fs=$sysHalf`n", $utf8)

    function Check-Case([string]$Name, $Record, [string]$ExpectedError) {
        $path = Join-Path $temporary ($Name + '.json')
        [IO.File]::WriteAllText($path, ($Record | ConvertTo-Json -Depth 20) + "`n", $utf8)
        $arguments = @((Join-Path $PSScriptRoot 'check_coremark_production_sim.py'),
            '--log', $logPath, '--mode', 'performance', '--kind', 'long',
            '--rom', $romPath, '--binary', $binaryPath,
            '--build-manifest', $path, '--cpu-source', (Join-Path $root 'rtl/cpu/source.json'),
            '--cpu-rtl', (Join-Path $root 'rtl/cpu/CoreTop.sv'),
            '--cpu-hz', [string]$clock.cpu_hz, '--expected-iterations', '0',
            '--output', (Join-Path $temporary ($Name + '.result.json')))
        $oldPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $output = (@(& $PythonPath @arguments 2>&1 | ForEach-Object {
                if ($_ -is [Management.Automation.ErrorRecord]) {
                    $_.Exception.Message
                } else { [string]$_ }
            }) -join "`n")
            $exitCode = $LASTEXITCODE
        } finally { $ErrorActionPreference = $oldPreference }
        if ($exitCode -eq 0 -or !$output.Contains($ExpectedError)) {
            throw "CoreMark manifest fixture $Name produced wrong result: exit=$exitCode output=$output"
        }
    }

    # A valid manifest must pass the iteration gate and reach the intentionally
    # incomplete synthetic UART log. All malformed manifests must stop earlier.
    Check-Case 'valid_policy' $manifest 'Production console banner or CoreMark command missing'
    $missing = $manifest | ConvertTo-Json -Depth 20 | ConvertFrom-Json
    $missing.PSObject.Properties.Remove('coremark_iterations')
    Check-Case 'missing_policy' $missing 'does not explicitly bind the selected CoreMark iteration policy'
    $wrong = $manifest | ConvertTo-Json -Depth 20 | ConvertFrom-Json
    $wrong.coremark_iterations = 10
    Check-Case 'wrong_policy' $wrong 'does not explicitly bind the selected CoreMark iteration policy'
    $wrongMacro = $manifest | ConvertTo-Json -Depth 20 | ConvertFrom-Json
    $wrongMacro.coremark_contract.preprocessed_macros.ITERATIONS = '10'
    Check-Case 'wrong_preprocessed_macro' $wrongMacro 'differs from preprocessed GCC macros'

    foreach ($case in @(
        [pscustomobject]@{ name='missing'; record=$missing },
        [pscustomobject]@{ name='wrong'; record=$wrong },
        [pscustomobject]@{ name='wrong_macro'; record=$wrongMacro }
    )) {
        $errorText = ''
        try {
            Assert-CoremarkIterationPolicy -BuildManifest $case.record -ExpectedIterations 0 -Production
        } catch { $errorText = $_.Exception.Message }
        if (!$errorText) { throw "PowerShell preflight accepted invalid $($case.name) iteration policy" }
    }
    Write-Output 'COREMARK_MANIFEST_POLICY_PASS production=0 pilot=10 rejected=3 checker_rejected=3'
} finally {
    $safePrefix = $scratchRoot + '\coremark_manifest_policy_'
    if (!$temporary.StartsWith($safePrefix, [StringComparison]::OrdinalIgnoreCase) -or
        @(Get-ChildItem -LiteralPath $temporary -Recurse -Force |
            Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
        throw 'Refusing unsafe CoreMark fixture cleanup'
    }
    Remove-Item -LiteralPath $temporary -Recurse -Force
}
