# Shared post-synthesis gate. Dot-source this file; it does not launch PDS.
function Initialize-PdsAuditProcess {
    if (-not ('CpuSimulation.BoundedProcess' -as [type])) {
        Add-Type -Path (Join-Path $PSScriptRoot 'bounded_process.cs')
    }
}

function Resolve-PdsAuditPython {
    param([string]$PythonPath, [Parameter(Mandatory=$true)][string]$LogDirectory)
    if (!$PythonPath) {
        $command = Get-Command python.exe,python3.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command) { $PythonPath = $command.Source }
    }
    if (!$PythonPath -or !(Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
        throw 'PdsSynthesis needs Python >= 3.8; set config.PythonPath, pass -PythonPath, or put Python on PATH.'
    }
    $PythonPath = [IO.Path]::GetFullPath($PythonPath)
    New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
    Initialize-PdsAuditProcess
    $exitCode = [CpuSimulation.BoundedProcess]::Run($PythonPath,
        '-c "import sys; print(sys.version); assert sys.version_info >= (3, 8)"',
        $LogDirectory, (Join-Path $LogDirectory 'python.stdout.log'),
        (Join-Path $LogDirectory 'python.stderr.log'), 10)
    if ($exitCode -ne 0) { throw "PDS audit Python prerequisite failed, exit $exitCode; inspect $LogDirectory" }
    return $PythonPath
}

function Invoke-PdsControlAudit {
    param(
        [Parameter(Mandatory=$true)][string]$PythonPath,
        [Parameter(Mandatory=$true)][string]$AuditScript,
        [Parameter(Mandatory=$true)][string]$Netlist,
        [Parameter(Mandatory=$true)][string]$OutputPath,
        [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$ExpectedAuditSha256,
        [ValidateRange(1,600)][int]$TimeoutSeconds = 300
    )
    foreach ($path in @($PythonPath, $AuditScript, $Netlist)) {
        if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing ADS audit input: $path" }
    }
    $AuditScript = [IO.Path]::GetFullPath($AuditScript)
    $Netlist = [IO.Path]::GetFullPath($Netlist)
    $OutputPath = [IO.Path]::GetFullPath($OutputPath)
    if (Test-Path -LiteralPath $OutputPath) { throw "Refusing to reuse an existing ADS audit result: $OutputPath" }
    $actualAuditHash = (Get-FileHash -LiteralPath $AuditScript -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualAuditHash -ne $ExpectedAuditSha256.ToLowerInvariant()) { throw 'ADS audit script changed after its input was frozen' }
    $netlistHash = (Get-FileHash -LiteralPath $Netlist -Algorithm SHA256).Hash.ToLowerInvariant()
    $directory = Split-Path $OutputPath -Parent
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    Initialize-PdsAuditProcess
    $arguments = '"' + $AuditScript + '" "' + $Netlist + '" --output "' + $OutputPath + '"'
    $exitCode = [CpuSimulation.BoundedProcess]::Run($PythonPath, $arguments, $directory,
        ($OutputPath + '.stdout.log'), ($OutputPath + '.stderr.log'), $TimeoutSeconds)
    if ($exitCode -ne 0) { throw "ADS control audit failed, exit $exitCode; inspect $OutputPath and its .stderr.log" }
    if (!(Test-Path -LiteralPath $OutputPath -PathType Leaf)) { throw 'ADS control audit did not create a result' }
    $result = Get-Content -LiteralPath $OutputPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($result.schema_version -ne 1 -or $result.status -ne 'PASS' -or
        $result.frontend_cases -ne 42880 -or $result.pma_address_cases -ne 2144 -or
        $result.rsmem_hint_cases -ne 17152) { throw 'ADS control audit result does not satisfy the current bare-CPU gate' }
    if ($result.netlist_sha256 -ne $netlistHash -or $result.audit_script_sha256 -ne $actualAuditHash -or
        (Get-FileHash -LiteralPath $Netlist -Algorithm SHA256).Hash.ToLowerInvariant() -ne $netlistHash -or
        (Get-FileHash -LiteralPath $AuditScript -Algorithm SHA256).Hash.ToLowerInvariant() -ne $actualAuditHash) {
        throw 'ADS control audit input/result hashes disagree'
    }
    return [pscustomobject][ordered]@{
        status = 'PASS'; resultPath = $OutputPath
        resultSha256 = (Get-FileHash -LiteralPath $OutputPath -Algorithm SHA256).Hash.ToLowerInvariant()
        netlistSha256 = $netlistHash; auditScriptSha256 = $actualAuditHash
        frontendCases = $result.frontend_cases; pmaAddressCases = $result.pma_address_cases
        rsmemHintCases = $result.rsmem_hint_cases; timeoutSeconds = $TimeoutSeconds
    }
}
